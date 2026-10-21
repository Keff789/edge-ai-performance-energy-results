"""Render supplementary studies through their existing offline renderers.

The caller owns the language context. All plotting happens in this process so
that labels are translated before Matplotlib computes layout. Numerical source
exports stay in their original language and retain their existing identities.
No compiler, accelerator, network service, or hardware acquisition is invoked.
"""
from __future__ import annotations

from contextlib import contextmanager, redirect_stdout
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys


STUDIES = (
    "stage-cost-composition",
    "mlsys-selection-20261007",
    "rq2-all-cuts-20261020",
    "dissertation-development-2026",
    "thesis20-ranking-20261005",
    "native-endpoint-reconstruction",
    "thesis-v49-confirmation-20261019",
    "yolov7-completion-20261007",
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path):
    name = "_dissertation_" + hashlib.sha256(str(path).encode()).hexdigest()[:16]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@contextmanager
def _imports(directory: Path):
    """Isolate sibling imports made by the standalone historical renderers."""
    names = {path.stem for path in directory.glob("*.py")}
    previous = {name: sys.modules.pop(name) for name in names if name in sys.modules}
    old_path = sys.path[:]
    before = set(sys.modules)
    sys.path.insert(0, str(directory))
    try:
        yield
    finally:
        sys.path[:] = old_path
        for name in names:
            sys.modules.pop(name, None)
        sys.modules.update(previous)
        for name in set(sys.modules) - before:
            if name.startswith("_dissertation_"):
                sys.modules.pop(name, None)


def _copy_tables(source: Path, output: Path, *, include=None) -> list[Path]:
    """Copy reader-facing tables, never raw archives or full model inputs.

    Existing TeX wrappers may refer to neighbouring tables. Their relative paths
    are retained. Minimal table_preview.tex wrappers are passed to the table
    translator, which checks that all referenced tables are exported. Other
    standalone documents and general README files are not table assets.
    Adjacent CSV/JSON exports remain exact source bytes. An explicit include
    list can select a published table without importing diagnostic reports.
    """
    copied = []
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        if include is not None and relative.as_posix() not in include:
            continue
        if any(part in {"inputs", "source", "scripts"} for part in relative.parts):
            continue
        if path.suffix not in {".tex", ".md", ".csv", ".json"}:
            continue
        if (path.suffix == ".tex" and "\\documentclass" in path.read_text()
                and path.name != "table_preview.tex"):
            continue
        if path.suffix == ".md":
            if path.name == "README.md":
                continue
            if not any(line.lstrip().startswith("|") for line in path.read_text().splitlines()):
                continue
        if include is None and path.suffix in {".csv", ".json"} and not any(
            part in {"tables", "analysis", "current", "historical", "success"}
            for part in relative.parts
        ):
            continue
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
        copied.append(path)
    return copied


def _stage(repo, source, output, numeric_only):
    directory = repo / "scripts/supplementary-studies/stage-cost-composition"
    with _imports(directory):
        renderer = _load(directory / "render_stage_costs.py")
        analysis = json.loads((source / "results/ANALYSIS.json").read_text())
        plan = json.loads((source / "inputs/PLAN.json").read_text())
        with (source / "tables/COMPOSITION_COMPARISON.csv").open(newline="") as stream:
            comparisons = list(csv.DictReader(stream))
        renderer.render_tables(analysis, plan, output / "tables")
        if not numeric_only:
            renderer.plots(analysis, plan, comparisons, output / "figures")
    return directory / "render_stage_costs.py"


def _selection(repo, source, output, numeric_only):
    directory = repo / "scripts/supplementary-studies/mlsys-selection-20261007"
    if not numeric_only:
        with _imports(directory):
            renderer = _load(directory / "render_paper_figures.py")
            renderer.render(source / "inputs/analysis", source / "analysis", output / "figures")
    return directory / "render_paper_figures.py"


def _all_cuts(repo, source, output, numeric_only):
    directory = repo / "scripts/supplementary-studies/rq2-all-cuts-20261020"
    with _imports(directory):
        _load(directory / "paper_assets.py").run(source, output, numeric_only)
    return directory / "paper_assets.py"


def _development(repo, source, output, numeric_only):
    directory = repo / "scripts/supplementary-studies/dissertation-development-2026"
    tables = output / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    with _imports(directory):
        renderer = _load(directory / "render_tables.py")
        renderer.render(tables, directory / "templates", tables)
        renderer.render_rankings(tables, tables)
        if not numeric_only:
            _load(directory / "plot_rankings.py").render(tables, output)
    return directory / "plot_rankings.py"


def _thesis20(repo, source, output, numeric_only):
    directory = source / "scripts"
    if not numeric_only:
        with _imports(directory):
            _load(directory / "render_methods.py").render(source / "source", source, output)
    return directory / "render_methods.py"


def _endpoint(repo, source, output, numeric_only):
    # This study has no figures. Its validated tables are copied byte-for-byte
    # before the caller translates only the presentation layer.
    return repo / "scripts/supplementary-studies/native-endpoint-reconstruction/reproduce.py"


def _confirmation(repo, source, output, numeric_only):
    # This confirmation bundle currently publishes CSV/JSON, not a typeset table
    # or chart. Keep this fact explicit in the returned inventory.
    return repo / "scripts/supplementary-studies/thesis-v49-confirmation-20261019/reproduce.py"


def _yolov7_completion(repo, source, output, numeric_only):
    # The historical task-completion cohort publishes one Markdown table.
    # Its reported repeats are separate from the instrumented stage diagnosis.
    return source / "extract_reported_results.py"


RUNNERS = dict(zip(STUDIES, (
    _stage, _selection, _all_cuts, _development, _thesis20,
    _endpoint, _confirmation, _yolov7_completion,
)))
EXPECTED_FIGURES = dict(zip(STUDIES, (2, 4, 4, 2, 2, 0, 0, 0)))


def render_supplementary(repo: Path, work: Path, *, numeric_only=False) -> dict:
    """Create a separate study directory and source report for every study.

    ``work`` must be empty or absent and outside the repository. A caller may
    activate its locale hook around this function. The output still contains
    English TeX/Markdown and language-neutral machine data, which the caller's
    table localizer handles separately. The returned paths are absolute.
    """
    repo, work = Path(repo).resolve(), Path(work).resolve()
    if work == repo or repo in work.parents:
        raise ValueError("Supplement rendering requires a work directory outside the repository")
    if work.exists() and (not work.is_dir() or any(work.iterdir())):
        raise ValueError("Supplement rendering requires a fresh or empty work directory")
    work.mkdir(parents=True, exist_ok=True)
    results = {}
    for study in STUDIES:
        source = repo / "results/supplementary-studies" / study
        output = work / study
        output.mkdir()
        include = ({"reported_results.md", "reported_results.csv",
                    "reported_results.provenance.json"}
                   if study == "yolov7-completion-20261007" else None)
        copied = _copy_tables(source, output, include=include)
        if numeric_only:
            with redirect_stdout(io.StringIO()):
                generator = RUNNERS[study](repo, source, output, True)
        else:
            import matplotlib.pyplot as plt
            # Each legacy renderer chooses its established layout/style. Those
            # choices must not leak to the next study or to the main exporter.
            with plt.rc_context(), redirect_stdout(io.StringIO()):
                generator = RUNNERS[study](repo, source, output, False)
        figures = sorted(output.rglob("*.pdf"))
        expected = 0 if numeric_only else EXPECTED_FIGURES[study]
        if len(figures) != expected:
            raise ValueError(f"{study}: expected {expected} figures, produced {len(figures)}")
        source_files = sorted({*copied, generator})
        # Source fingerprints cover the compact numerical inputs used by each
        # renderer, not only the small selection copied to the display bundle.
        for path in sorted(source.rglob("*")):
            if path.is_file() and path.suffix in {".csv", ".json"}:
                source_files.append(path)
        provenance = {str(path.relative_to(repo)): _sha(path) for path in sorted(set(source_files))}
        results[study] = {
            "output": str(output),
            "source": str(source.relative_to(repo)),
            "generator": str(generator.relative_to(repo)),
            "figure_count": len(figures),
            "table_count": len(list(output.rglob("*.tex"))),
            "source_sha256": provenance,
            "numerical_data_policy": "Original CSV/JSON identities and values are not translated.",
            "presentation_status": (
                "machine_tables_only" if study == "thesis-v49-confirmation-20261019"
                else "table_translation_pending"
            ),
        }
    return results
