from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .auto_pipeline import load_auto_pipeline_config, run_auto_pipeline
from .analysis import (
    analyse_real_measurements,
    common_trace_for_run,
    determine_fmin,
    phase_only_source_sensitivity_for_run,
    summarise_phase_only_source_sensitivity,
    load_reference_measurements,
    prepare_caches,
    summarise_common_trace,
    validate_dataset,
    validate_real_measurement_selection,
)
from .config import load_config
from .duration_sensitivity import (
    duration_sensitivity_for_run,
    summarise_duration_sensitivity,
)
from .legacy_duration import (
    analyse_legacy_duration_campaign,
    write_duration_summary,
)
from .plotting import plot_energy_error, plot_psd, plot_same_trace
from .paper_artifacts import generate_paper_artifacts
from .psd import psd_for_run, summarise_psd
from .report import write_manifest, write_summary
from .selftest import run_selftest
from .scope_config import load_scope_config
from .scope_compare import run_scope_comparison
from .workload_config import load_multi_workload_config
from .workload_compare import run_multi_workload_analysis, run_multi_workload_inventory
from .utils import LOGGER, parse_run_spec, setup_logging


def _log_runtime_identity(config_path: Path | None = None) -> None:
    """Record the exact package and interpreter used for this command."""
    LOGGER.info("Tool version: %s", __version__)
    LOGGER.info("Tool source: %s", Path(__file__).resolve().parents[1])
    LOGGER.info("Python executable: %s", sys.executable)
    if config_path is not None:
        LOGGER.info("Config: %s", config_path.resolve())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="common-reference-psd",
        description="Generate common-reference-trace and PSD results from calibrated power traces.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("selftest", help="Run internal numerical sanity checks.")

    auto = subparsers.add_parser(
        "auto-pipeline",
        help=(
            "Discover every paired-scope workload directory, generate effective "
            "scope and multi-workload configs, reuse fresh analyses, process only "
            "new or stale campaigns, and regenerate all cross-workload paper artifacts."
        ),
    )
    auto.add_argument("--config", type=Path, required=True)
    auto.add_argument(
        "--workloads",
        type=str,
        default=None,
        help="Optional comma-separated discovered workload IDs.",
    )
    auto.add_argument("--force-scope", action="store_true")
    auto.add_argument("--force-multi", action="store_true")
    auto.add_argument(
        "--discover-only",
        action="store_true",
        help="Only discover datasets and generate effective configs/status reports.",
    )
    auto.add_argument(
        "--artifacts-only",
        action="store_true",
        help="Regenerate multi-workload paper artifacts from completed scope outputs.",
    )
    auto.add_argument("--verbose", action="store_true")

    journal = subparsers.add_parser("journal-artifacts", aliases=["journal-psd"],
        help="Generate isolated Pico/Tek and cross-platform native-PSD journal artifacts.")
    journal.add_argument("--config", type=Path, default=Path(__file__).resolve().parents[1] / "config_journal.yaml")
    journal.add_argument("--output-root", type=Path, default=None)
    journal.add_argument("--force", action="store_true")
    journal.add_argument("--artifacts-only", action="store_true")
    journal.add_argument("--verbose", action="store_true")

    scope = subparsers.add_parser(
        "scope-compare",
        help=(
            "Validate paired Tektronix/PicoScope Parquet segments, reconstruct "
            "energy with the configured current-dependent voltage model, and "
            "compare PSD/coherence across all discovered sampling rates."
        ),
    )
    scope.add_argument("--config", type=Path, required=True)
    scope.add_argument(
        "--runs",
        type=str,
        default=None,
        help="Optional paired segment IDs, e.g. 0 or 0-9 or 0,2,5.",
    )
    scope.add_argument("--output-root", type=Path, default=None)
    scope.add_argument("--force", action="store_true")
    scope.add_argument("--verbose", action="store_true")

    workload_inventory = subparsers.add_parser(
        "workload-inventory",
        help=(
            "Inventory all configured Edge-AI workload campaigns at the common "
            "5-MS/s rate while skipping missing or incomplete campaigns read-only."
        ),
    )
    workload_inventory.add_argument("--config", type=Path, required=True)
    workload_inventory.add_argument("--output-root", type=Path, default=None)
    workload_inventory.add_argument("--verbose", action="store_true")

    workload = subparsers.add_parser(
        "workload-compare",
        help=(
            "Generate common-rate cross-workload Tektronix current/power PSDs, "
            "same-trace multi-duration energy bounds, direct-rate validation, "
            "worst-case envelopes, and paper-ready artifacts."
        ),
    )
    workload.add_argument("--config", type=Path, required=True)
    workload.add_argument(
        "--workloads",
        type=str,
        default=None,
        help="Optional comma-separated workload IDs; missing workloads remain skipped.",
    )
    workload.add_argument("--output-root", type=Path, default=None)
    workload.add_argument("--force", action="store_true")
    workload.add_argument(
        "--artifacts-only",
        action="store_true",
        help="Regenerate tables/figures/bundles from completed multi-workload results.",
    )
    workload.add_argument("--verbose", action="store_true")

    paper = subparsers.add_parser(
        "paper-artifacts",
        help=(
            "Generate the exact paper-ready figures currently used by the manuscript, "
            "LaTeX/CSV/Markdown tables, numeric LaTeX macros, compact provenance data, "
            "and complete plus compact-review documentation bundles from an existing completed analysis."
        ),
    )
    paper.add_argument("--config", type=Path, required=True)
    paper.add_argument(
        "--metadata",
        type=Path,
        default=None,
        help="Paper-artifact metadata YAML; defaults to paper_artifacts_metadata.yaml next to the analysis config.",
    )
    paper.add_argument(
        "--scope-output-root",
        type=Path,
        default=None,
        help="Optional completed paired-scope output root to include scope-validation documentation artifacts.",
    )
    paper.add_argument("--runs", type=str, default=None)
    paper.add_argument("--output-root", type=Path, default=None)
    paper.add_argument("--force", action="store_true")
    paper.add_argument("--verbose", action="store_true")

    for name, help_text in (
        ("validate", "Validate the reference runs and metadata."),
        ("prepare", "Build resumable downsampled cache traces."),
        ("common", "Run anti-aliased and phase-only common-reference-trace analyses."),
        ("psd", "Run primary/sensitivity PSD, variance-capture, and cumulative-spectrum analyses."),
        ("duration", "Determine duration-dependent energy error, minimum sampling-rate bounds, and legacy 5--600-s protocol convergence."),
        ("rate-duration", "Alias for the duration-dependent sampling and protocol-convergence analysis."),
        ("figures", "Regenerate diagnostic figures plus paper-ready figures, tables, macros, and provenance artifacts from existing result files."),
        ("all", "Run validation, caches, analyses, diagnostic/paper artifacts, and report."),
    ):
        sub = subparsers.add_parser(name, help=help_text)
        sub.add_argument("--config", type=Path, required=True)
        sub.add_argument(
            "--runs",
            type=str,
            default=None,
            help="Override runs, e.g. 2 or 2-14 or 2,4,8",
        )
        sub.add_argument("--output-root", type=Path, default=None)
        sub.add_argument("--force", action="store_true", help="Rebuild existing stage outputs.")
        sub.add_argument("--verbose", action="store_true")
        sub.add_argument(
            "--paper-metadata",
            type=Path,
            default=None,
            help="Optional paper-artifact metadata YAML. For figures/all, defaults to paper_artifacts_metadata.yaml next to the analysis config when present.",
        )
        sub.add_argument(
            "--scope-output-root",
            type=Path,
            default=None,
            help="Optional paired-scope output root to include in documentation artifacts.",
        )

    return parser


def _load(args: argparse.Namespace):
    cfg = load_config(args.config, output_override=args.output_root)
    runs = parse_run_spec(args.runs, cfg.primary_runs)
    setup_logging(cfg.output_root, verbose=args.verbose)
    _log_runtime_identity(args.config)
    write_manifest(cfg, runs, args.config)
    return cfg, runs


def run_command(args: argparse.Namespace) -> int:
    if args.command == "selftest":
        print(f"Tool version: {__version__}")
        print(f"Tool source: {Path(__file__).resolve().parents[1]}")
        run_selftest()
        return 0


    if args.command == "auto-pipeline":
        cfg = load_auto_pipeline_config(args.config)
        setup_logging(cfg.state_root, verbose=args.verbose)
        _log_runtime_identity(args.config)
        selected = (
            [item.strip() for item in args.workloads.split(",") if item.strip()]
            if args.workloads
            else None
        )
        LOGGER.info("Command: auto-pipeline")
        LOGGER.info("Dataset root: %s", cfg.dataset_root)
        LOGGER.info("State root: %s", cfg.state_root)
        LOGGER.info("Selected workloads: %s", selected or "all discovered")
        summary = run_auto_pipeline(
            cfg,
            selected_workloads=selected,
            force_scope=args.force_scope,
            force_multi=args.force_multi,
            discover_only=args.discover_only,
            artifacts_only=args.artifacts_only,
            verbose=args.verbose,
        )
        LOGGER.info("Complete. Automatic-pipeline summary: %s", summary)
        return 0

    if args.command in {"journal-artifacts", "journal-psd"}:
        from .journal_data import load_journal_config
        from .journal import run_journal
        cfg = load_journal_config(args.config, args.output_root)
        run_journal(cfg, force=args.force, artifacts_only=args.artifacts_only, verbose=args.verbose)
        return 0

    if args.command == "scope-compare":
        cfg = load_scope_config(args.config, output_override=args.output_root)
        default_runs: tuple[int, ...] = ()
        selected_runs = None if args.runs is None else parse_run_spec(args.runs, default_runs)
        setup_logging(cfg.output_root, verbose=args.verbose)
        _log_runtime_identity(args.config)
        LOGGER.info("Command: scope-compare")
        LOGGER.info("Output root: %s", cfg.output_root)
        LOGGER.info("Selected paired segment IDs: %s", selected_runs or "all discovered")
        summary = run_scope_comparison(
            cfg,
            config_path=args.config,
            selected_runs=selected_runs,
            force=args.force,
        )
        LOGGER.info("Complete. Summary: %s", summary)
        return 0

    if args.command == "workload-inventory":
        cfg = load_multi_workload_config(
            args.config, output_override=args.output_root
        )
        setup_logging(cfg.output_root, verbose=args.verbose)
        _log_runtime_identity(args.config)
        LOGGER.info("Command: workload-inventory")
        LOGGER.info("Output root: %s", cfg.output_root)
        summary = run_multi_workload_inventory(cfg)
        LOGGER.info("Complete. Inventory: %s", summary)
        return 0

    if args.command == "workload-compare":
        cfg = load_multi_workload_config(
            args.config, output_override=args.output_root
        )
        setup_logging(cfg.output_root, verbose=args.verbose)
        _log_runtime_identity(args.config)
        selected = (
            [item.strip() for item in args.workloads.split(",") if item.strip()]
            if args.workloads
            else None
        )
        LOGGER.info("Command: workload-compare")
        LOGGER.info("Output root: %s", cfg.output_root)
        LOGGER.info("Selected workloads: %s", selected or "all available")
        summary = run_multi_workload_analysis(
            cfg,
            config_path=args.config,
            selected_workloads=selected,
            force=args.force,
            artifacts_only=args.artifacts_only,
        )
        LOGGER.info("Complete. Summary: %s", summary)
        return 0

    if args.command == "paper-artifacts":
        cfg = load_config(args.config, output_override=args.output_root)
        runs = parse_run_spec(args.runs, cfg.primary_runs)
        setup_logging(cfg.output_root, verbose=args.verbose)
        _log_runtime_identity(args.config)
        metadata = args.metadata or (args.config.parent / "paper_artifacts_metadata.yaml")
        LOGGER.info("Command: paper-artifacts")
        LOGGER.info("Analysis output root: %s", cfg.output_root)
        LOGGER.info("Paper metadata: %s", metadata)
        summary = generate_paper_artifacts(
            cfg,
            runs,
            metadata,
            scope_output_root=args.scope_output_root,
            force=args.force,
        )
        LOGGER.info("Complete. Paper-artifact summary: %s", summary)
        return 0

    cfg, runs = _load(args)
    LOGGER.info("Command: %s", args.command)
    LOGGER.info("Output root: %s", cfg.output_root)
    LOGGER.info("Runs: %s", runs)

    if args.command in ("validate", "all"):
        validate_dataset(cfg, runs)
        validate_real_measurement_selection(cfg, runs)

    if args.command in ("prepare", "all"):
        prepare_caches(cfg, runs, force=args.force)

    if args.command in ("common", "all"):
        for meta in load_reference_measurements(cfg, runs):
            common_trace_for_run(cfg, meta, force=args.force)
            phase_only_source_sensitivity_for_run(
                cfg, meta, force=args.force
            )
        _, common_summary = summarise_common_trace(cfg, runs)
        determine_fmin(cfg, common_summary)
        summarise_phase_only_source_sensitivity(cfg, runs)
        analyse_real_measurements(cfg, runs)

    if args.command in ("psd", "all"):
        for run in runs:
            psd_for_run(cfg, run, force=args.force)
        summarise_psd(cfg, runs)

    if args.command in ("duration", "rate-duration", "all"):
        if cfg.duration_sensitivity.enabled:
            if args.command in ("duration", "rate-duration"):
                # This stage consumes the configured source-rate cache. Build
                # only missing caches; --force applies to the duration outputs
                # and must not unexpectedly rebuild multi-gigabyte traces.
                prepare_caches(cfg, runs, force=False)
            for meta in load_reference_measurements(cfg, runs):
                duration_sensitivity_for_run(cfg, meta, force=args.force)
            summarise_duration_sensitivity(cfg, runs)
            analyse_legacy_duration_campaign(cfg, force=args.force)
            duration_summary = write_duration_summary(cfg)
            LOGGER.info("Duration decision summary: %s", duration_summary)
        else:
            LOGGER.info("Duration-sensitivity analysis is disabled in the config")

    if args.command in ("figures", "all"):
        plot_energy_error(cfg)
        plot_psd(cfg)
        plot_same_trace(cfg, runs)
        metadata = args.paper_metadata or (args.config.parent / "paper_artifacts_metadata.yaml")
        if metadata.is_file():
            generate_paper_artifacts(
                cfg,
                runs,
                metadata,
                scope_output_root=args.scope_output_root,
                force=args.force,
            )
        else:
            LOGGER.warning(
                "Paper-artifact metadata not found at %s; paper-ready figures/tables were not generated.",
                metadata,
            )

    if args.command == "all":
        summary = write_summary(cfg, runs)
        LOGGER.info("Complete. Summary: %s", summary)
    return 0


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        raise SystemExit(run_command(args))
    except KeyboardInterrupt:
        print("Interrupted by user.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as error:
        LOGGER.exception("Analysis failed: %s", error)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
