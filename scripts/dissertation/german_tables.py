"""German presentation copies of existing scientific tables.

Translations are explicit, reviewed strings. Source identities, data files,
formulas, row order and numeric tokens remain unchanged. The catalog is shared
by the TeX and Markdown exporters; there is no translation service dependency.
"""
from __future__ import annotations

from collections import Counter
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re

CATALOG = Path(__file__).parent / 'locales' / 'tables_de.json'


@lru_cache(maxsize=1)
def catalog():
    return json.loads(CATALOG.read_text(encoding='utf-8'))


@lru_cache(maxsize=1)
def matcher():
    return re.compile(r'(?<![A-Za-z0-9_])(?:' + '|'.join(
        re.escape(s) for s in sorted(catalog(), key=len, reverse=True)) + r')(?![A-Za-z0-9_])')


@lru_cache(maxsize=1)
def long_matcher():
    return re.compile('|'.join(re.escape(s) for s in sorted(catalog(),key=len,reverse=True) if len(s)>=40))


def _protected(text):
    """Keep references, paths and LaTeX structural arguments verbatim."""
    kept = []
    pattern = re.compile(r'\\(?:label|ref|eqref|autoref|cite\w*|url|path|input|include|begin|end)\*?(?:\[[^\]]*\])?\{[^{}]*\}|`[^`]*`|https?://[^\s<>]+')
    def save(match):
        kept.append(match.group())
        return f'@@KEEP{len(kept)-1}@@'
    return pattern.sub(save, text), kept


def _replace(text):
    # Long reviewed phrases can include code spans. Their catalog entries
    # preserve those spans verbatim; remaining individual spans are protected.
    text = long_matcher().sub(lambda m: catalog()[m.group()], text)
    source, kept = _protected(text)
    translated = matcher().sub(lambda match: catalog()[match.group()], source)
    for index, value in enumerate(kept):
        translated = translated.replace(f'@@KEEP{index}@@', value)
    return translated


def _command_arguments(text, name):
    for match in re.finditer(r'\\' + name + r'\*?(?:\[[^\]]*\])?\{', text):
        start = match.end(); depth = 1; end = start
        while end < len(text) and depth:
            if text[end] == '{' and (end == 0 or text[end-1] != '\\'):
                depth += 1
            elif text[end] == '}' and (end == 0 or text[end-1] != '\\'):
                depth -= 1
            end += 1
        if depth == 0:
            yield text[start:end-1]


def text_fragments(text, markdown=False):
    """Visible text units used to audit new, untranslated table wording."""
    if markdown:
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith('|'):
                yield from (cell.strip() for cell in re.split(r'(?<!\\)\|', line.strip('|')) if cell.strip())
            else:
                yield re.sub(r'^#+\s*', '', line)
        return
    yield from _command_arguments(text, 'caption')
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('%'):
            yield line[1:].strip()
        elif re.search(r'(?<!\\)&', line):
            for cell in re.split(r'(?<!\\)&', line):
                yield re.sub(r'\\\\\s*$', '', cell).strip()
        elif line.startswith(r'\multicolumn'):
            yield line


_NEUTRAL = set('''
Generic Native Full Split GF Bytes Weighted Cycle Stream Fit Hailo HailoRT TensorRT TRT
DeepX DX H8 H10 H10H Hailo8 Hailo10H Orin NX MobileNet MobileNetV3 MobileNetV3Large
MobileNetV3L MobileNetV3Large RegNet RegNetX ResNet YOLO YOLO11l YOLO26m YOLO26s YOLOv7
FPS TOP Top1 Top5 COCO AP mAP AP50 ImageNet RGB UINT8 uint8 float32 float16 int8
FP16 FP32 INT8 FLOAT CPU GPU NPU ONNX L4T MAXN SUPER A4 API PCIe EMC OC CUDA CUDART
NMS HEF JSON CSV UID UIDs NA N A true false nn
ModelNet mm ms s J mJ W Hz MHz GHz kHz kS GT GB MB MiB GiB percent
R F P C PC G N S I GP NP GS NS SD Q q n k b x y L K T i j comm imb ten global host
min max log abs sum exp rel atol rtol nan inf float bool int double
TopK ReduceMax Softmax Mod Batch FIFO H2D D2H PID FPS Median Maximum localhost
booktabs longtable siunitx tabular table tabularx tabularstar p r l c S
small footnotesize scriptsize centering textwidth columnwidth linewidth tabcolsep pt cm
textbf textit textrm textsc texttt textstyle rm mathrm multicolumn shortstack
leq geq times pm Delta alpha beta mu sigma infty textquotesingle title
stable native_full_tensorrt native_full_deepx native_full_hailo8 native_full_hailo10h
ARCS R22 R30 R31 Refresh16 THESIS20 Oracle Sparse Backend Decoder Status Runner ResNet50
'''.split())


def unknown_fragments(text, markdown=False):
    unknown = []
    for fragment in text_fragments(text, markdown):
        fragment_remaining = long_matcher().sub('', fragment)
        residual, kept = _protected(fragment_remaining)
        residual = matcher().sub('', residual)
        # Formula contents and stable machine identifiers are language neutral.
        residual = re.sub(r'\$[^$]*\$', ' ', residual)
        residual = re.sub(r'<[^>]+>', '', residual)
        residual = re.sub(r'@@KEEP\d+@@', '', residual)
        residual = re.sub(r'\\[A-Za-z]+\*?', '', residual)
        residual = re.sub(r'\b[A-Za-z][A-Za-z0-9]*(?:[_/.-][A-Za-z0-9]+)+\b', '', residual)
        residual = re.sub(r'\b(?:b\d+|[A-Z][A-Z0-9]+|\d+(?:\.\d+)?)\b', '', residual)
        words = re.findall(r'[A-Za-z][A-Za-z0-9]*', residual)
        words = [w for w in words if w not in _NEUTRAL and len(w)>1]
        if words:
            unknown.append({'text':fragment,'words': sorted(set(words))})
    return unknown


def _numeric_cells(text, markdown=False):
    """Number tokens in table rows, excluding descriptive captions/comments."""
    result=[]
    for line in text.splitlines():
        if (markdown and line.strip().startswith('|')) or (not markdown and re.search(r'(?<!\\)&',line)):
            # Counts in macro arguments are formatting, not observations.
            clean=re.sub(r'\\(?:multicolumn|multirow)\{\d+\}\{[^{}]+\}', '', line)
            result.extend(re.findall(r'(?<![A-Za-z])[-+]?\d+(?:[.,]\d+)*(?:[eE][-+]?\d+)?', clean))
    return result


def _translate(text, markdown=False, strict=True):
    missing=unknown_fragments(text,markdown)
    if strict and missing:
        raise ValueError('Missing German table translations: '+json.dumps(missing[:15],ensure_ascii=False))
    result=_replace(text)
    if _numeric_cells(result,markdown) != _numeric_cells(text,markdown):
        raise ValueError('German table translation changed numeric row tokens')
    # Captions may reorder phrases but must retain all numeric values as well.
    numbers = lambda s: Counter(re.findall(r'\d+(?:[.,]\d+)*(?:[eE][-+]?\d+)?', s))
    if numbers(result) != numbers(text):
        raise ValueError('German table translation changed numeric content')
    return result


def translate_tex(text, *, strict=True):
    result = _translate(text,strict=strict)
    # German headings are longer. These line breaks use only core LaTeX and
    # leave numeric cells, formulas and the original table structure intact.
    result = result.replace(r'\shortstack{Global schnellstes\\Full}',
                            r'\shortstack{Global\\schnellstes\\Full}')
    result = result.replace(r'\shortstack{Schnellstes Full\\gleicher Host}',
                            r'\shortstack{Schnellstes\\Full\\gleicher Host}')
    result = result.replace(r'\shortstack{Lokales Full\\FPS}',
                            r'\shortstack{Lokales\\Full-FPS}')
    result = result.replace(r'(Runner, System/Cut)', r'(Runner,\\System/Cut)')
    breaks = {
        'Gewählter Split': r'Gewählter\\Split',
        r'Medianer Verlust (\%)': r'Medianer\\Verlust (\%)',
        r'Mittlerer Verlust (\%)': r'Mittlerer\\Verlust (\%)',
        'Medianes FPS-Verhältnis': r'Medianes\\FPS-Verhältnis',
        'Medianes Energieverhältnis': r'Medianes\\Energieverhältnis',
    }
    lines = []
    for line in result.splitlines(keepends=True):
        if re.search(r'(?<!\\)&', line):
            for old, new in breaks.items():
                line = re.sub(r'(?<![A-Za-z])' + re.escape(old) + r'(?![A-Za-z])',
                              lambda _: r'\shortstack{' + new + '}', line)
        lines.append(line)
    result = ''.join(lines).replace('Ausführungskonfigurationen', r'Ausführungs\-konfigurationen')
    if r'\cutbytes' in result:
        historical_labels = {
            r'Kleinste Grenzdatenmenge (\cutbytes)': r'Kleinste Grenzdatenmenge\\(\cutbytes)',
            r'Historischer gewichteter Score (\weighted)': r'Historischer gewichteter\\Score (\weighted)',
            r'Gespeicherte H10-Anpassung (\hardware)': r'Gespeicherte\\H10-Anpassung (\hardware)',
            r'Heuristischer Zyklus ohne Übergabe (\cycle)': r'Heuristischer Zyklus\\ohne Übergabe (\cycle)',
            r'Gespeicherte Streaming-Rate (\stream)': r'Gespeicherte Streaming-Rate\\(\stream)',
            r'Gemessener \generic{}-Aufgabenabschluss': r'Gemessener \generic{}-\\Aufgabenabschluss',
            r'mehrbedarf /18 (\%)': r'mehrbedarf\\/18 (\%)',
        }
        for old, new in historical_labels.items():
            result = result.replace(old, r'\shortstack[l]{' + new + '}')
    definitions = _compatibility_definitions(result)
    if definitions:
        result = ('% Kompatibilitätsdefinitionen historischer Methodennamen.\n'
                  + '\n'.join('\\providecommand{\\' + name + '}{' + value + '}'
                              for name, value in definitions.items()) + '\n' + result)
    return result


def _compatibility_definitions(text):
    labels = {'cutbytes':r'\texttt{cut\_bytes}', 'weighted':r'\texttt{weighted}',
              'hardware':r'\texttt{hardware}', 'cycle':r'\texttt{cycle}',
              'stream':r'\texttt{stream}', 'generic':'Generic'}
    return {name:value for name,value in labels.items()
            if re.search(r'\\'+name+r'\b',text)
            and not re.search(r'\\(?:newcommand|providecommand)\{\\'+name+r'\}',text)}


def translate_markdown(text, *, strict=True):
    return _translate(text,markdown=True,strict=strict)


def translate_tables(source_root: Path, dest_root: Path, *, strict=True):
    source_root,dest_root=Path(source_root),Path(dest_root)
    files=[];missing=[]
    paths=[]
    for path in sorted(source_root.rglob('*.tex')):
        text=path.read_text(encoding='utf-8')
        if not re.search(r'\\begin\{(?:tabular\*?|longtable|tabularx)\}',text):
            continue
        paths.append(path)
        if path.with_suffix('.md').is_file(): paths.append(path.with_suffix('.md'))
        if path.name=='stage_cost_table.tex' and (path.parent/'STAGE_COST_SUMMARY.md').is_file():
            paths.append(path.parent/'STAGE_COST_SUMMARY.md')
    # Some study generators emit Markdown tables without a TeX counterpart.
    # A header separator distinguishes real tables from ordinary prose files.
    for path in sorted(source_root.rglob('*.md')):
        if path.name.lower() in {'readme.md', 'methods.md'} or path.name in {
            'H8_B044_REGRESSION_ANALYSIS.md', 'SPLIT_STAGE_PROFILE.md'
        }:
            continue
        text = path.read_text(encoding='utf-8')
        if re.search(r'^\s*\|?\s*:?-{3,}:?\s*\|(?:\s*:?-{3,}:?\s*\|?)+\s*$', text, re.M):
            paths.append(path)
    for path in dict.fromkeys(paths):
        relative=path.relative_to(source_root);source=path.read_text(encoding='utf-8')
        unresolved=unknown_fragments(source,path.suffix=='.md')
        missing.extend({'file':str(relative),**m} for m in unresolved)
        translated = (translate_markdown(source,strict=strict) if path.suffix=='.md'
                      else translate_tex(source,strict=strict))
        target=dest_root/relative;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(translated,encoding='utf-8')
        files.append({'source':str(relative),'target':str(relative),
                      'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                      'target_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
                      'numeric_row_tokens_unchanged':True,
                      'numeric_content_unchanged':True,
                      'compatibility_definitions':(_compatibility_definitions(source)
                                                   if path.suffix=='.tex' else {})})
    # Retain a supplied minimal compilation wrapper only when all its inputs
    # are part of this export. Do not copy unrelated document prose or macros.
    exported = {path.resolve() for path in paths}
    for path in sorted(source_root.rglob('table_preview.tex')):
        source = path.read_text(encoding='utf-8')
        body = re.search(r'\\begin\{document\}(.*?)\\end\{document\}', source, re.S)
        if not body:
            continue
        inputs = list(_command_arguments(body.group(1), 'input'))
        dependencies = [(path.parent / name).with_suffix('.tex').resolve() for name in inputs]
        residual = re.sub(r'%[^\n]*|\\input\{[^{}]*\}|\\(?:clearpage|newpage)\b', '', body.group(1)).strip()
        if not inputs or residual or not all(dep in exported for dep in dependencies):
            continue
        relative = path.relative_to(source_root)
        target = dest_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding='utf-8')
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        files.append({'source':str(relative), 'target':str(relative),
                      'source_sha256':digest, 'target_sha256':digest,
                      'kind':'compilation_wrapper',
                      'numeric_row_tokens_unchanged':True,
                      'numeric_content_unchanged':True})
    return {'files':files,'file_count':len(files),'untranslated':missing,
            'catalog_sha256':hashlib.sha256(CATALOG.read_bytes()).hexdigest()}
