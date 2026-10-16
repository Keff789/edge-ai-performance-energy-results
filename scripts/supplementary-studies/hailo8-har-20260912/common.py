"""Local, bounded diagnostics. No product configuration or cache writes."""
from __future__ import annotations
import contextlib, hashlib, json, os, signal, stat, subprocess, time
from pathlib import Path, PurePosixPath

TEXT_SUFFIXES = {'.json', '.jsonl', '.csv', '.tsv', '.md', '.txt', '.log', '.py', '.sh', '.yaml', '.yml', '.xml'}
MAX_TEXT = 64 * 1024 * 1024

def plain(path: Path) -> Path:
    path = Path(path).expanduser().absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Symlink nicht zulaessig: ' + str(path))
    return path

def safe_rel(value: str) -> Path:
    p = PurePosixPath(value)
    if (not p.parts or p.is_absolute() or '..' in p.parts or
            any(c in value for c in '\\\x00\n\r\t')):
        raise ValueError('Unsicherer relativer Pfad: ' + repr(value))
    return Path(*p.parts)

def signature(p):
    s = Path(p).stat()
    if not stat.S_ISREG(s.st_mode): raise ValueError('Keine regulaere Datei: ' + str(p))
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)

def identity(p):
    p = plain(Path(p)); before = signature(p)
    h = hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''): h.update(block)
    if signature(p) != before: raise ValueError('Datei waehrend Lesen veraendert: ' + str(p))
    return {'path': str(p), 'size_bytes': before[2], 'sha256': h.hexdigest()}

def bound(record):
    actual = identity(record['path'])
    if (actual['sha256'] != str(record['sha256']).removeprefix('sha256:') or
            actual['size_bytes'] != record['size_bytes']):
        raise ValueError('Dateibindung abweichend: ' + str(record['path']))
    return Path(actual['path'])

def text_bytes(p):
    p = plain(Path(p)); before = signature(p)
    if before[2] > MAX_TEXT: raise ValueError('Textdatei groesser als 64 MiB: ' + str(p))
    data = p.read_bytes()
    if signature(p) != before: raise ValueError('Quelldatei aendert sich: ' + str(p))
    if b'\x00' in data: raise ValueError('Binaerinhalt: ' + str(p))
    data.decode('utf-8')
    return data

def read_json(p): return json.loads(text_bytes(p))

def write_json(p, value):
    p = plain(Path(p)); p.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode()
    temp = p.with_name('.' + p.name + '.tmp-' + str(os.getpid()))
    with temp.open('xb') as f:
        f.write(raw); f.flush(); os.fsync(f.fileno())
    os.replace(temp, p)

def immutable_copy(data: bytes, destination: Path):
    destination = plain(destination)
    if destination.exists():
        if text_bytes(destination) != data: raise ValueError('Vorhandenes Ergebnis abweichend; nicht ersetzt: ' + str(destination))
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('xb') as f: f.write(data)
    return True

@contextlib.contextmanager
def interlock(home):
    import fcntl
    p = plain(Path(home) / '.onnx_splitpoint_tool/locks/workflow_platform_interlock.lock')
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(p, os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise RuntimeError('workflow_or_platform_operation_active; GUI/Workflow geordnet beenden')
        yield
    finally: os.close(fd)

def child_env(out):
    env = os.environ.copy()
    for key in ('PYTHONPATH', 'PYTHONHOME', 'CUDA_HOME', 'CUDA_PATH', 'XLA_FLAGS',
                'TF_XLA_FLAGS', 'LD_LIBRARY_PATH', 'LD_PRELOAD'):
        env.pop(key, None)
    # CPU emulator, not a GPU build test. All settings are child-local.
    env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', CUDA_VISIBLE_DEVICES='-1',
        TF_NUM_INTEROP_THREADS='2', TF_NUM_INTRAOP_THREADS='2', OMP_NUM_THREADS='2',
        OPENBLAS_NUM_THREADS='2', MKL_NUM_THREADS='2', ORT_DISABLE_TELEMETRY='1',
        TF_CPP_MIN_LOG_LEVEL='1', MPLBACKEND='Agg')
    for key, name in [('TMPDIR', 'tmp'), ('XDG_CACHE_HOME', 'cache'), ('MPLCONFIGDIR', 'mpl'), ('KERAS_HOME', 'keras')]:
        p = Path(out) / name; p.mkdir(parents=True, exist_ok=True); env[key] = str(p)
    return env

def group_members(pgid):
    rows = []
    for p in Path('/proc').glob('[0-9]*/stat'):
        try:
            s = p.read_text(); rest = s[s.rfind(')') + 2:].split()
            if int(rest[2]) == pgid and rest[0] != 'Z': rows.append(int(p.parent.name))
        except (OSError, ValueError, IndexError): pass
    return rows

def supervised(command, cwd, env, timeout, log, heartbeat=15):
    start = time.monotonic(); interrupted = False; timed_out = False
    p = None; next_tick = start + heartbeat
    Path(log).parent.mkdir(parents=True, exist_ok=True)
    with Path(log).open('wb') as f:
        try:
            p = subprocess.Popen(command, cwd=cwd, env=env, stdout=f, stderr=subprocess.STDOUT,
                                 start_new_session=True)
            while p.poll() is None:
                now = time.monotonic()
                if now - start > timeout: timed_out = True; break
                if now >= next_tick:
                    print(f'HEARTBEAT={Path(log).stem} elapsed_s={now-start:.0f} limit_s={timeout}', flush=True)
                    next_tick = now + heartbeat
                time.sleep(0.15)
        except KeyboardInterrupt: interrupted = True
        finally:
            if p is not None and (p.poll() is None or group_members(p.pid)):
                try: os.killpg(p.pid, signal.SIGTERM)
                except ProcessLookupError: pass
                until = time.monotonic() + 5
                while group_members(p.pid) and time.monotonic() < until: time.sleep(0.1)
                if group_members(p.pid):
                    try: os.killpg(p.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
            if p is not None:
                try: p.wait(timeout=5)
                except subprocess.TimeoutExpired: pass
    survivors = group_members(p.pid) if p else []
    return {'argv': list(map(str, command)), 'returncode': p.returncode if p else None,
        'timed_out': timed_out, 'cancelled': interrupted, 'elapsed_s': time.monotonic()-start,
        'owned_survivors': survivors, 'process_cleanup_complete': p is not None and p.poll() is not None and not survivors}
