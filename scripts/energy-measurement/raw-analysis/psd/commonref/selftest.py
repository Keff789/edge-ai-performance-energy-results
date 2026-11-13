from __future__ import annotations

import json
import os
import zipfile
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import numpy as np

from . import __version__
from scipy.integrate import trapezoid
from scipy.signal import welch

from .auto_pipeline import (
    discover_workloads as _auto_discover_workloads,
    generate_multi_workload_config as _auto_generate_multi_workload_config,
    generate_scope_config as _auto_generate_scope_config,
    load_auto_pipeline_config as _auto_load_pipeline_config,
)
from .config import load_config
from .duration_sensitivity import _window_starts
from .io import MeasurementMetadata
from .legacy_duration import _method_summaries
from .scope_config import load_scope_config
from .scope_compare import (
    _SCOPE_ANALYSIS_SCHEMA_VERSION,
    _aggregate_psd,
    _aligned_overlap,
    _cache_reuse_status,
    _configured_shared_trigger_time,
    _estimate_lag_samples,
    _pair_source_identity,
    _pair_metrics,
    _spectral_bundle,
    _source_rates_for_directory,
    _duration_match_tolerance_s,
    _derive_zero_offset_decision,
    _build_zero_offset_model,
    _resample_signal,
    _select_representative_run,
    _zero_offset_for_rate,
    _windows_from_shared_trigger,
    _native_spectral_bundle,
    discover_pairs,
    discover_rate_directories,
)
from .paper_artifacts import (
    PAPER_ARTIFACT_SCHEMA_VERSION,
    _latex_command_name,
    _optional_float,
    _table_tex,
    _write_macros,
    _write_review_bundle,
    _write_table_include,
)
from .utils import load_yaml, write_json
from .workload_config import load_multi_workload_config
from .workload_compare import (
    _classify_idle_load_peak as _multi_classify_idle_load_peak,
    _density_cumulative as _multi_density_cumulative,
    _density_integral_band as _multi_density_integral_band,
    _frequency_at_fraction as _multi_frequency_at_fraction,
    _human_duration_tick as _multi_human_duration_tick,
    _human_frequency_tick as _multi_human_frequency_tick,
    _human_percent_tick as _multi_human_percent_tick,
    _human_rate_tick as _multi_human_rate_tick,
    _log_frequency_variance_density as _multi_log_frequency_variance_density,
    _log_binned_active_idle_ratio_rows as _multi_log_binned_active_idle_ratio_rows,
    _welch_parameters as _multi_welch_parameters,
    _summarise_common_reference as _multi_summarise_common_reference,
    _window_starts as _multi_window_starts,
    _build_bundles as _multi_build_bundles,
    _write_multi_workload_artifact_summary as _multi_write_artifact_summary,
)
from .resampling import (
    integrate_uniform_fixed_window,
    phase_only_grid,
    resample_phase_grid,
)


def run_selftest() -> None:
    # No passing predefined instrument-agreement band is a valid result.
    # Artifact generation must render it as n/a rather than calling float(None).
    if not np.isnan(_optional_float(None)):
        raise AssertionError("Optional validated-band edge self-test failed")

    # Fixed-window integration on a constant signal must be exact.
    fs = 1000.0
    values = np.full(10_001, 12.5, dtype=np.float64)
    energy = integrate_uniform_fixed_window(
        values,
        sample_rate=fs,
        first_sample_time_s=0.0,
        start_time_s=0.1234,
        stop_time_s=9.8765,
    )
    expected = 12.5 * (9.8765 - 0.1234)
    if abs(energy - expected) > 1e-9:
        raise AssertionError(f"Integration self-test failed: {energy} != {expected}")

    duration_meta = MeasurementMetadata(
        run=0,
        sample_rate_sps=fs,
        energy_j=1.0,
        duration_s=10.0,
        start_idx=1000,
        stop_idx=10_999,
        npy_path=Path("unused.npy"),
        yaml_path=Path("unused.yaml"),
        use_voltage=True,
        measurement_type="synthetic",
    )
    starts = _window_starts(
        duration_meta,
        2.0,
        count=4,
        edge_margin_s=0.5,
    )
    if starts.size != 4 or np.any(starts < 1.5) or np.any(starts + 2.0 > 10.5):
        raise AssertionError("Duration-window placement self-test failed")

    # Phase-only grid generation must preserve a constant signal for all phases.
    source = np.full(20_001, 7.25, dtype=np.float64)
    grid, grid_rate, _ = phase_only_grid(
        source,
        source_rate=2000,
        target_rate=125,
        phase_count=8,
    )
    if grid_rate != 1000 or not np.allclose(grid, 7.25, atol=1e-12):
        raise AssertionError("Phase-only grid self-test failed")

    for phase in range(8):
        phase_values = grid[phase::8]
        first_time = phase / grid_rate
        phase_energy = integrate_uniform_fixed_window(
            phase_values,
            sample_rate=125,
            first_sample_time_s=first_time,
            start_time_s=0.1,
            stop_time_s=9.0,
        )
        if abs(phase_energy - 7.25 * 8.9) > 1e-9:
            raise AssertionError("Phase-only fixed-window integration self-test failed")

    # The anti-aliased phase-grid branch must also preserve DC gain.
    minimal_cfg = SimpleNamespace(
        resampling_quality="VHQ",
        anti_alias=SimpleNamespace(
            attenuation_db=60.0,
            passband_fraction_of_nyquist=0.90,
            stopband_fraction_of_nyquist=1.00,
        ),
    )
    aa_grid, aa_rate, _ = resample_phase_grid(
        source,
        source_rate=2000,
        target_rate=125,
        phase_count=8,
        cfg=minimal_cfg,
    )
    if aa_rate != 1000 or not np.allclose(aa_grid[1000:-1000], 7.25, atol=1e-8):
        raise AssertionError("Anti-aliased phase-grid DC-gain self-test failed")

    # PSD sanity check: a 50-Hz tone should dominate.
    duration = 4.0
    t = np.arange(int(fs * duration)) / fs
    signal = 10.0 + 2.0 * np.sin(2 * np.pi * 50.0 * t)
    frequencies, density = welch(signal, fs=fs, nperseg=1000, detrend="constant")
    peak_frequency = frequencies[np.argmax(density[1:]) + 1]
    if abs(peak_frequency - 50.0) > 1.0:
        raise AssertionError(f"PSD self-test failed: peak={peak_frequency}")

    # Scope-comparison sanity checks. A known two-sample Pico delay must be
    # detected with the documented positive-lag convention and alignment must
    # recover identical overlapping signals.
    scope_config_path = Path(__file__).resolve().parent.parent / "config_scope_comparison.yaml"
    if scope_config_path.is_file():
        scope_cfg = load_scope_config(scope_config_path)

        # A disabled or unavailable adaptive zero model is a valid state.  The
        # evidence CSVs must still be emitted as header-only files instead of
        # failing because there are no rows from which to infer the schema.
        with TemporaryDirectory() as temp_directory:
            zero_cfg = replace(
                scope_cfg,
                output_root=Path(temp_directory) / "scope_zero_disabled",
            )
            zero_model = _build_zero_offset_model(zero_cfg, {})
            if zero_model.get("status") != "disabled":
                raise AssertionError("Disabled zero-model status self-test failed")
            zero_root = zero_cfg.output_root / "zero_correction"
            for filename in (
                "zero_offset_pair_evidence.csv",
                "zero_offset_rate_evidence.csv",
            ):
                target = zero_root / filename
                if not target.is_file() or not target.read_text(encoding="utf-8").strip():
                    raise AssertionError(
                        f"Header-only zero-evidence CSV self-test failed: {target}"
                    )

        if not scope_cfg.input_policy.ignore_empty_rate_directories:
            raise AssertionError("Scope empty-directory input policy self-test failed")
        if not scope_cfg.input_policy.ignore_invalid_pairs:
            raise AssertionError("Scope invalid-pair input policy self-test failed")
        if scope_cfg.input_policy.expected_duration_s is not None:
            raise AssertionError("Scope auto-duration input policy self-test failed")
        if scope_cfg.spectral.max_analysis_rate_sps < 250_000_000:
            raise AssertionError("Scope high-rate PSD ceiling self-test failed")
        tek_rate, pico_rate = _source_rates_for_directory(scope_cfg, 12_500_000)
        if tek_rate != 12_500_000 or pico_rate != 5_000_000:
            raise AssertionError(
                f"Scope dual-rate policy self-test failed: {tek_rate}, {pico_rate}"
            )
        tek_rows = 62_500_000
        pico_rows = 25_000_000
        tek_duration = tek_rows / tek_rate
        pico_duration = pico_rows / pico_rate
        tolerance = _duration_match_tolerance_s(
            scope_cfg, tek_rate, pico_rate, tek_duration
        )
        if abs(tek_duration - pico_duration) > tolerance:
            raise AssertionError("Scope equal-duration dual-rate self-test failed")
        configured_trigger, configured_source = _configured_shared_trigger_time(
            scope_cfg, 12_500_000, 5.0
        )
        if configured_trigger is not None or configured_source != "first_valid_detection":
            raise AssertionError("Scope default shared-trigger policy self-test failed")

        # Adaptive zero-offset detection must apply only when several exact-rate
        # idle campaigns show a material, bounded, same-sign and rate-stable
        # Pico-minus-Tek baseline difference.  This pure decision test does not
        # require the optional PyArrow runtime.
        zero_cfg = SimpleNamespace(
            minimum_reference_rates=2,
            minimum_reference_pairs_total=10,
            minimum_abs_offset_ma=50.0,
            maximum_abs_correction_ma=500.0,
            maximum_rate_median_deviation_ma=10.0,
            minimum_sign_consistency_fraction=1.0,
            apply_when_detected=True,
        )
        stable_evidence = [
            {
                "rate_sps": 2500,
                "valid_offset_pairs": 11,
                "offset_median_ma": 129.6,
                "offset_mad_ma": 0.4,
                "eligible_for_session_model": True,
            },
            {
                "rate_sps": 1_000_000,
                "valid_offset_pairs": 11,
                "offset_median_ma": 129.9,
                "offset_mad_ma": 0.5,
                "eligible_for_session_model": True,
            },
        ]
        zero_decision = _derive_zero_offset_decision(
            zero_cfg, stable_evidence
        )
        if (
            zero_decision["status"]
            != "stable_offset_detected_and_corrected"
            or not zero_decision["correction_applied"]
            or abs(float(zero_decision["offset_applied_ma"]) - 129.75)
            > 1e-9
        ):
            raise AssertionError("Adaptive zero-offset decision self-test failed")

        unstable_evidence = [
            stable_evidence[0],
            {
                **stable_evidence[1],
                "offset_median_ma": 95.0,
            },
        ]
        unstable_decision = _derive_zero_offset_decision(
            zero_cfg, unstable_evidence
        )
        if (
            unstable_decision["correction_applied"]
            or unstable_decision["status"]
            != "offset_detected_but_rate_unstable"
        ):
            raise AssertionError("Adaptive zero-offset safety-gate self-test failed")

        excluded_rate_evidence = [
            stable_evidence[0],
            {
                **stable_evidence[1],
                "candidate_for_session_model": True,
                "eligible_for_session_model": False,
            },
        ]
        excluded_rate_decision = _derive_zero_offset_decision(
            zero_cfg, excluded_rate_evidence
        )
        if (
            excluded_rate_decision["correction_applied"]
            or excluded_rate_decision["status"]
            != "offset_evidence_contains_unstable_rates"
        ):
            raise AssertionError(
                "Adaptive zero-offset no-cherry-picking self-test failed"
            )

        # The actual trace correction is additive, is applied before the
        # current-dependent voltage model, and must leave the raw metrics intact.
        identity_scope_cfg = replace(
            scope_cfg,
            tek=replace(
                scope_cfg.tek,
                raw_unit="A",
                offset_raw=0.0,
                gain_a_per_raw=1.0,
            ),
            pico=replace(
                scope_cfg.pico,
                raw_unit="A",
                offset_raw=0.0,
                gain_a_per_raw=1.0,
            ),
            windows=replace(
                scope_cfg.windows,
                mode="full",
                minimum_active_duration_s=0.1,
            ),
            spectral=replace(scope_cfg.spectral, enabled=False),
        )
        correction_rate = 2500
        correction_time = np.arange(5000, dtype=np.float64) / correction_rate
        true_current = 1.2 + 0.15 * np.sin(
            2.0 * np.pi * 17.0 * correction_time
        )
        tek_wrong_zero = true_current - 0.13
        pico_reference = true_current.copy()
        correction_model = {
            "status": "stable_offset_detected_and_corrected",
            "offset_detected": True,
            "correction_applied": True,
            "target_source": "tek",
            "reference_source": "external_idle_rate_medians",
            "offset_estimate_a": 0.13,
            "offset_estimate_ma": 130.0,
            "offset_applied_a": 0.13,
            "offset_applied_ma": 130.0,
            "model_hash": "zero-offset-selftest",
            "independent_reference": False,
        }
        if abs(_zero_offset_for_rate(correction_model, correction_rate) - 0.13) > 1e-12:
            raise AssertionError("Adaptive zero-offset lookup self-test failed")
        pair_result = _pair_metrics(
            identity_scope_cfg,
            correction_rate,
            0,
            tek_wrong_zero,
            pico_reference,
            Path("tek-selftest.parquet"),
            Path("pico-selftest.parquet"),
            {},
            {},
            zero_correction_model=correction_model,
        )
        corrected_metrics = pair_result[0]
        if abs(float(corrected_metrics["pico_vs_tek_energy_error_pct"])) > 1e-8:
            raise AssertionError("Adaptive zero-offset trace correction self-test failed")
        if abs(float(corrected_metrics["raw_pico_vs_tek_energy_error_pct"])) < 5.0:
            raise AssertionError("Adaptive zero-offset raw-metric preservation failed")
        if not corrected_metrics["zero_offset_correction_applied"]:
            raise AssertionError("Adaptive zero-offset audit flag self-test failed")

        test_resample = _resample_signal(
            np.ones(12_500, dtype=np.float64), 12_500.0, 5_000.0
        )
        if test_resample.size != 5_000 or not np.allclose(
            test_resample[100:-100], 1.0, atol=1e-8
        ):
            raise AssertionError("Scope common-grid resampling self-test failed")
        t_scope = np.arange(5000, dtype=np.float64) / 2500.0
        tek_scope = 1.0 + 0.3 * np.sin(2 * np.pi * 37.0 * t_scope)
        pico_scope = np.concatenate([np.full(2, tek_scope[0]), tek_scope[:-2]])
        lag, lag_meta = _estimate_lag_samples(
            tek_scope, pico_scope, 2500.0, scope_cfg
        )
        if lag != 2 or abs(float(lag_meta["lag_ms"]) - 0.8) > 1e-9:
            raise AssertionError(
                f"Scope-alignment self-test failed: lag={lag}, meta={lag_meta}"
            )
        tek_aligned, pico_aligned, _, _ = _aligned_overlap(
            tek_scope, pico_scope, lag
        )
        if not np.allclose(tek_aligned, pico_aligned, atol=1e-12):
            raise AssertionError("Scope aligned-overlap self-test failed")
        test_current = np.asarray([0.0, 1.0, 3.5])
        test_voltage = scope_cfg.voltage_model.voltage(test_current)
        expected_voltage = (
            scope_cfg.voltage_model.intercept_v
            + scope_cfg.voltage_model.slope_v_per_a * test_current
        )
        if not np.allclose(test_voltage, expected_voltage):
            raise AssertionError("Scope voltage-model self-test failed")

        # A short idle window must no longer reduce the active Welch grid.  At
        # 2.5 kS/s and a 0.5-s segment, the active PSD has 1250-point segments
        # (626 one-sided bins), while a 0.1-s idle window has only 250 samples.
        duration_scope = 10.0
        t_spectral = np.arange(int(2500 * duration_scope), dtype=np.float64) / 2500.0
        tek_power = 30.0 + 2.0 * np.sin(2 * np.pi * 73.0 * t_spectral)
        pico_power = 30.0 + 1.98 * np.sin(2 * np.pi * 73.0 * t_spectral + 0.01)
        short_idle_windows = {
            "active_start_s": 0.7,
            "active_stop_s": 9.8,
            "idle_start_s": 0.0,
            "idle_stop_s": 0.1,
        }
        arrays_short_idle, metrics_short_idle, _ = _spectral_bundle(
            tek_power,
            pico_power,
            2500.0,
            short_idle_windows,
            scope_cfg,
        )
        if arrays_short_idle["frequencies_hz"].size != 626:
            raise AssertionError("Scope active-grid PSD self-test failed")
        if int(metrics_short_idle["active_nperseg"]) != 1250:
            raise AssertionError("Scope active nperseg self-test failed")
        idle_nperseg = int(metrics_short_idle["idle_nperseg"])
        idle_segments = int(metrics_short_idle["idle_welch_segments"])
        if idle_nperseg >= 250 or idle_segments < scope_cfg.spectral.minimum_idle_welch_segments:
            raise AssertionError(
                "Scope adaptive idle-Welch self-test failed: "
                f"nperseg={idle_nperseg}, segments={idle_segments}"
            )
        if metrics_short_idle["spectral_basis"] != "active_minus_prebenchmark_idle":
            raise AssertionError("Scope idle-subtracted spectral-basis self-test failed")

        # Short records must either retain at least the configured number of
        # Welch averages or suppress coherence.  A one-segment coherence of
        # exactly one must never be reported as a physical result.
        short_duration = 0.08
        t_short = np.arange(int(2500 * short_duration), dtype=np.float64) / 2500.0
        short_signal = 1.0 + 0.2 * np.sin(2 * np.pi * 120.0 * t_short)
        short_windows = {
            "active_start_s": 0.0,
            "active_stop_s": short_duration,
            "idle_start_s": 0.0,
            "idle_stop_s": 0.0,
        }
        short_arrays, short_metrics, _ = _spectral_bundle(
            short_signal, short_signal * 0.99, 2500.0, short_windows, scope_cfg
        )
        if (
            int(short_metrics["active_welch_segments"])
            < scope_cfg.spectral.minimum_welch_segments
            and np.any(np.isfinite(short_arrays["coherence"]))
        ):
            raise AssertionError("Insufficient-segment coherence was not suppressed")
        if bool(short_metrics["workload_related_psd_available"]):
            raise AssertionError("Active-only PSD was mislabelled as workload-related")

        # An independent exact-rate idle data set may be used only when the
        # same-run pre-benchmark idle is unavailable.  The resulting PSD basis
        # must remain explicitly labelled and the external source must never be
        # confused with a trigger-matched same-run interval.
        yolo_config_path = (
            Path(__file__).resolve().parent.parent / "config_scope_yolofp32.yaml"
        )
        if yolo_config_path.is_file():
            yolo_cfg = load_scope_config(yolo_config_path)
            if not yolo_cfg.external_idle.enabled:
                raise AssertionError("External-idle configuration self-test failed")
            if not yolo_cfg.zero_offset_correction.enabled:
                raise AssertionError("Adaptive zero-offset configuration self-test failed")
            if (
                yolo_cfg.windows.mode != "full"
                or yolo_cfg.windows.shared_anchor_mode != "fixed_time"
                or yolo_cfg.windows.trigger_time_s != 0.0
            ):
                raise AssertionError("Record-start GPIO window configuration self-test failed")
            if (
                yolo_cfg.zero_offset_correction.detection_source
                != "workload_minus_external_idle_rate_medians"
                or yolo_cfg.zero_offset_correction.application_scope
                != "workload_only"
            ):
                raise AssertionError("Session-shift zero-model configuration self-test failed")
            full_windows = _windows_from_shared_trigger(
                duration_s=2.5,
                trigger_s=0.0,
                cfg=yolo_cfg,
                source_run=-1,
                detected_trigger_s=1.3,
            )
            if (
                full_windows["active_start_s"] != 0.0
                or full_windows["active_stop_s"] != 2.5
                or full_windows["idle_duration_s"] != 0.0
            ):
                raise AssertionError("Record-start full-window construction self-test failed")

            stable_offset_rows = [
                {
                    "rate_sps": 2_500,
                    "valid_offset_pairs": 11,
                    "offset_median_ma": 129.4,
                    "offset_mad_ma": 0.6,
                    "eligible_for_session_model": True,
                },
                {
                    "rate_sps": 25_000,
                    "valid_offset_pairs": 11,
                    "offset_median_ma": 130.1,
                    "offset_mad_ma": 0.7,
                    "eligible_for_session_model": True,
                },
                {
                    "rate_sps": 100_000,
                    "valid_offset_pairs": 11,
                    "offset_median_ma": 129.8,
                    "offset_mad_ma": 0.5,
                    "eligible_for_session_model": True,
                },
            ]
            stable_decision = _derive_zero_offset_decision(
                yolo_cfg.zero_offset_correction, stable_offset_rows
            )
            if (
                stable_decision["status"]
                != "stable_offset_detected_and_corrected"
                or not stable_decision["correction_applied"]
                or abs(float(stable_decision["offset_applied_ma"]) - 129.8)
                > 1e-9
            ):
                raise AssertionError(
                    f"Adaptive stable-offset decision self-test failed: {stable_decision}"
                )
            stable_model = {
                **stable_decision,
                "target_source": "tek",
            }
            if abs(_zero_offset_for_rate(stable_model, 250_000_000) - 0.1298) > 1e-12:
                raise AssertionError("Adaptive all-rate offset propagation self-test failed")

            unstable_rows = [
                {
                    "rate_sps": 2_500,
                    "valid_offset_pairs": 11,
                    "offset_median_ma": 100.0,
                    "offset_mad_ma": 0.5,
                    "eligible_for_session_model": True,
                },
                {
                    "rate_sps": 25_000,
                    "valid_offset_pairs": 11,
                    "offset_median_ma": 140.0,
                    "offset_mad_ma": 0.5,
                    "eligible_for_session_model": True,
                },
            ]
            unstable_decision = _derive_zero_offset_decision(
                yolo_cfg.zero_offset_correction, unstable_rows
            )
            if unstable_decision["correction_applied"] or (
                unstable_decision["status"]
                != "offset_detected_but_rate_unstable"
            ):
                raise AssertionError(
                    f"Adaptive unstable-offset rejection self-test failed: {unstable_decision}"
                )

            small_offset_rows = [
                {
                    "rate_sps": 2_500,
                    "valid_offset_pairs": 11,
                    "offset_median_ma": 3.0,
                    "offset_mad_ma": 0.2,
                    "eligible_for_session_model": True,
                },
                {
                    "rate_sps": 25_000,
                    "valid_offset_pairs": 11,
                    "offset_median_ma": 3.5,
                    "offset_mad_ma": 0.2,
                    "eligible_for_session_model": True,
                },
            ]
            small_decision = _derive_zero_offset_decision(
                yolo_cfg.zero_offset_correction, small_offset_rows
            )
            if small_decision["correction_applied"] or (
                small_decision["status"] != "no_material_offset_detected"
            ):
                raise AssertionError(
                    f"Adaptive immaterial-offset rejection self-test failed: {small_decision}"
                )

            if yolo_cfg.windows.step_detector_diagnostics:
                raise AssertionError("YOLO step-detector diagnostic policy self-test failed")
            external_frequencies = np.linspace(0.0, 1250.0, 626)
            external_reference = {
                "status": "available",
                "valid_pairs": 11,
                "source_fingerprint_sha256": "external-idle-selftest",
                "summary": {
                    "common_nperseg": 1250,
                    "common_welch_segments_minimum": 15,
                    "native_nperseg": 1250,
                    "native_welch_segments_minimum": 15,
                    "duration_s_median": 10.0,
                },
                "common": {
                    "frequencies_hz": external_frequencies,
                    "tek_idle_psd_w2_per_hz_median": np.full(626, 1e-4),
                    "pico_idle_psd_w2_per_hz_median": np.full(626, 1.1e-4),
                },
                "native": {
                    "tek_native_frequencies_hz": external_frequencies,
                    "tek_native_idle_psd_w2_per_hz_median": np.full(626, 1e-4),
                },
            }
            no_idle_windows = {
                "active_start_s": 0.0,
                "active_stop_s": 4.0,
                "idle_start_s": 0.0,
                "idle_stop_s": 0.0,
            }
            external_arrays, external_metrics, _ = _spectral_bundle(
                tek_power[:10_000],
                pico_power[:10_000],
                2500.0,
                no_idle_windows,
                yolo_cfg,
                external_idle_reference=external_reference,
            )
            if (
                external_metrics["spectral_basis"]
                != "active_minus_external_rate_matched_idle"
                or external_metrics["idle_reference_source"]
                != "external_rate_matched_median"
                or not bool(external_metrics["workload_related_psd_available"])
                or int(external_metrics["external_idle_pair_count"]) != 11
            ):
                raise AssertionError("External-idle paired-PSD fallback self-test failed")
            if not np.any(np.isfinite(external_arrays["tek_analysis_psd_w2_per_hz"])):
                raise AssertionError("External-idle paired PSD contains no finite data")

            native_external_metrics, native_external_arrays = _native_spectral_bundle(
                tek_power[:10_000],
                2500.0,
                no_idle_windows,
                2500.0,
                yolo_cfg,
                external_idle_reference=external_reference,
            )
            if (
                native_external_arrays is None
                or native_external_metrics["tek_native_psd_basis"]
                != "active_minus_external_rate_matched_idle"
                or native_external_metrics["tek_native_idle_reference_source"]
                != "external_rate_matched_median"
                or not bool(
                    native_external_metrics[
                        "tek_native_workload_related_psd_available"
                    ]
                )
            ):
                raise AssertionError("External-idle native-PSD fallback self-test failed")

        representative_rows = [
            {
                "run": 0, "tek_mean_current_a": 0.30,
                "tek_estimated_energy_j": 1.0, "operating_region": "low_current",
            },
            {
                "run": 1, "tek_mean_current_a": 1.90,
                "tek_estimated_energy_j": 5.0, "operating_region": "nominal_current",
            },
            {
                "run": 2, "tek_mean_current_a": 2.00,
                "tek_estimated_energy_j": 5.1, "operating_region": "nominal_current",
            },
            {
                "run": 3, "tek_mean_current_a": 2.10,
                "tek_estimated_energy_j": 5.2, "operating_region": "nominal_current",
            },
        ]
        representative_run, _ = _select_representative_run(representative_rows)
        if representative_run not in {1, 2, 3}:
            raise AssertionError("Low-current run selected as visual representative")

        native_metrics, native_arrays = _native_spectral_bundle(
            short_signal, 2500.0, short_windows, 2500.0, scope_cfg
        )
        if native_arrays is None or bool(
            native_metrics["tek_native_workload_related_psd_available"]
        ):
            raise AssertionError("Tek active-only native PSD labelling failed")

        # Legacy caches can still contain unequal Welch grids.  Aggregation must
        # conservatively harmonise them rather than failing at np.vstack().
        with TemporaryDirectory() as temporary:
            output = Path(temporary)
            (output / "psd").mkdir(parents=True)
            f_fine = np.linspace(0.0, 1250.0, 626)
            f_coarse = np.linspace(0.0, 1250.0, 126)
            fine = 1.0 / (1.0 + f_fine)
            coarse = 1.0 / (1.0 + f_coarse)
            spectral_entries = [
                (
                    0,
                    {
                        "frequencies_hz": f_fine,
                        "tek_active_psd_w2_per_hz": fine,
                    },
                    {"nyquist_hz": 1250.0, "nperseg": 1250},
                ),
                (
                    1,
                    {
                        "frequencies_hz": f_coarse,
                        "tek_active_psd_w2_per_hz": coarse,
                    },
                    {"nyquist_hz": 1250.0, "nperseg": 250},
                ),
            ]
            aggregate_summary, _ = _aggregate_psd(
                output,
                2500,
                spectral_entries,
                [],
                scope_cfg,
            )
            aggregate = np.load(output / "psd" / "psd_summary.npz")
            if aggregate["frequencies_hz"].size != 126:
                raise AssertionError("Scope PSD-grid harmonisation self-test failed")
            if not bool(aggregate_summary["psd_grid_harmonized"]):
                raise AssertionError("Scope PSD-grid status self-test failed")
            if not (output / "psd" / "psd_grid_harmonization.csv").is_file():
                raise AssertionError("Scope PSD-grid audit self-test failed")

        # Per-pair caches must be invalidated when source Parquet files are
        # overwritten under the same names.  The sampled content fingerprint
        # supplements file size and nanosecond timestamps.
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            tek_source = root / "tek.parquet"
            pico_source = root / "pico.parquet"
            tek_source.write_bytes(b"A" * 4096)
            pico_source.write_bytes(b"P" * 4096)
            metrics_cache = root / "run_0.json"
            psd_cache = root / "run_0.npz"
            bands_cache = root / "run_0_bands.csv"
            for cache_path in (metrics_cache, psd_cache, bands_cache):
                cache_path.write_bytes(b"cache")
            identity_before = _pair_source_identity(tek_source, pico_source)
            config_hash = "config-selftest"
            payload = {
                "scope_analysis_schema_version": _SCOPE_ANALYSIS_SCHEMA_VERSION,
                "source_fingerprint_sha256": identity_before["fingerprint_sha256"],
                "analysis_config_hash": config_hash,
                "metrics": {
                    "scope_analysis_schema_version": _SCOPE_ANALYSIS_SCHEMA_VERSION,
                    "shared_trigger_time_s": 1.25,
                },
            }
            reuse, reason, upgrade = _cache_reuse_status(
                payload=payload,
                source_identity=identity_before,
                analysis_config_hash=config_hash,
                required_outputs=[metrics_cache, psd_cache, bands_cache],
                shared_trigger_time_s=None,
            )
            if not reuse or reason != "fingerprint_match" or upgrade:
                raise AssertionError("Scope source-fingerprint cache-hit self-test failed")
            reuse, reason, _ = _cache_reuse_status(
                payload=payload,
                source_identity=identity_before,
                analysis_config_hash=config_hash,
                required_outputs=[metrics_cache, psd_cache, bands_cache],
                shared_trigger_time_s=1.5,
            )
            if reuse or reason != "shared_trigger_anchor_changed":
                raise AssertionError("Scope shared-trigger cache invalidation self-test failed")

            # Legacy payloads from the previous paired-scope schema are
            # intentionally invalidated because rate-name and duration semantics
            # changed in v0.5.4 and again for dual-rate pairs in v0.5.5.
            source_time_ns = 1_000_000_000
            cache_time_ns = 2_000_000_000
            for source_path in (tek_source, pico_source):
                os.utime(source_path, ns=(source_time_ns, source_time_ns))
            for cache_path in (metrics_cache, psd_cache, bands_cache):
                os.utime(cache_path, ns=(cache_time_ns, cache_time_ns))
            identity_before = _pair_source_identity(tek_source, pico_source)
            legacy_payload = {
                "scope_analysis_schema_version": 2,
                "metrics": {"scope_analysis_schema_version": 2},
            }
            reuse, reason, upgrade = _cache_reuse_status(
                payload=legacy_payload,
                source_identity=identity_before,
                analysis_config_hash=config_hash,
                required_outputs=[metrics_cache, psd_cache, bands_cache],
                shared_trigger_time_s=None,
            )
            if reuse or reason != f"analysis_schema_changed:2<{_SCOPE_ANALYSIS_SCHEMA_VERSION}" or upgrade:
                raise AssertionError("Scope legacy-schema invalidation self-test failed")

            tek_source.write_bytes(b"B" * 4096)
            identity_after = _pair_source_identity(tek_source, pico_source)
            if identity_after["fingerprint_sha256"] == identity_before["fingerprint_sha256"]:
                raise AssertionError("Scope source fingerprint did not change")
            reuse, reason, _ = _cache_reuse_status(
                payload=legacy_payload,
                source_identity=identity_after,
                analysis_config_hash=config_hash,
                required_outputs=[metrics_cache, psd_cache, bands_cache],
                shared_trigger_time_s=None,
            )
            if reuse or reason != f"analysis_schema_changed:2<{_SCOPE_ANALYSIS_SCHEMA_VERSION}":
                raise AssertionError("Scope stale legacy-schema self-test failed")
            reuse, reason, _ = _cache_reuse_status(
                payload=payload,
                source_identity=identity_after,
                analysis_config_hash=config_hash,
                required_outputs=[metrics_cache, psd_cache, bands_cache],
                shared_trigger_time_s=None,
            )
            if reuse or reason != "source_fingerprint_changed":
                raise AssertionError("Scope stale-cache invalidation self-test failed")

        # A read-only measurement tree may already contain an empty next-rate
        # directory or a one-sided pair while acquisition is still in progress.
        # Discovery must document and skip these inputs rather than failing.
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            empty_rate = root / "1000000Sps"
            partial_rate = root / "2500Sps"
            bare_high_rate = root / "125000000"
            empty_rate.mkdir()
            partial_rate.mkdir()
            bare_high_rate.mkdir()
            (partial_rate / "tek_hsi_0.parquet").touch()
            tolerant_cfg = SimpleNamespace(
                dataset_root=root,
                rate_directories="auto",
                tek=scope_cfg.tek,
                pico=scope_cfg.pico,
                input_policy=scope_cfg.input_policy,
            )
            rates = discover_rate_directories(tolerant_cfg)
            if [rate for rate, _ in rates] != [2500, 1_000_000, 125_000_000]:
                raise AssertionError("Scope mixed rate-directory discovery self-test failed")
            pairs, inventory = discover_pairs(tolerant_cfg, empty_rate, None)
            if pairs or inventory["paired_run_ids"]:
                raise AssertionError("Empty rate-directory tolerance self-test failed")
            pairs, inventory = discover_pairs(tolerant_cfg, partial_rate, None)
            if pairs or inventory["missing_pico_run_ids"] != [0]:
                raise AssertionError("Unpaired-run tolerance self-test failed")
            pairs, inventory = discover_pairs(tolerant_cfg, partial_rate, [1])
            if pairs or inventory["missing_pico_run_ids"]:
                raise AssertionError("Selected-run discovery filtering self-test failed")

            # Variable-duration high-rate records use a per-rate modal row-count
            # contract instead of the old fixed 10-s assumption.
            from .scope_compare import _apply_auto_duration_inference
            probe_rows = [
                {
                    "run": 0, "status": "valid",
                    "tek_rows": 1000, "pico_rows": 40,
                    "tek_duration_s": 1000 / 125_000_000,
                    "pico_duration_s": 40 / 5_000_000,
                    "common_nominal_duration_s": 1000 / 125_000_000,
                },
                {
                    "run": 1, "status": "valid",
                    "tek_rows": 1000, "pico_rows": 40,
                    "tek_duration_s": 1000 / 125_000_000,
                    "pico_duration_s": 40 / 5_000_000,
                    "common_nominal_duration_s": 1000 / 125_000_000,
                },
                {
                    "run": 2, "status": "valid",
                    "tek_rows": 500, "pico_rows": 20,
                    "tek_duration_s": 500 / 125_000_000,
                    "pico_duration_s": 20 / 5_000_000,
                    "common_nominal_duration_s": 500 / 125_000_000,
                },
            ]
            contract = _apply_auto_duration_inference(
                scope_cfg, 125_000_000, None, probe_rows
            )
            if (
                contract["tek_expected_rows"] != 1000
                or contract["pico_expected_rows"] != 40
                or probe_rows[2]["status"] != "skipped"
            ):
                raise AssertionError("Scope auto-duration inference self-test failed")

    # Validate the documentation-artifact metadata and LaTeX table renderer.
    paper_metadata_path = Path(__file__).resolve().parent.parent / "paper_artifacts_metadata.yaml"
    if paper_metadata_path.is_file():
        paper_metadata = load_yaml(paper_metadata_path)
        if int(paper_metadata.get("schema_version", 0)) != PAPER_ARTIFACT_SCHEMA_VERSION:
            raise AssertionError("Paper-artifact metadata schema self-test failed")
        required_figures = {
            "sampling_rate_method",
            "measurement_setup_heterogeneous",
            "common_trace_results_paper",
            "psd_variance_results_paper",
        }
        if not required_figures.issubset(set(paper_metadata.get("figure_captions", {}))):
            raise AssertionError("Paper-artifact figure metadata self-test failed")
        required_tables = {"measurement_paths", "jetson_rate_sweep", "duration_campaign"}
        if not required_tables.issubset(set(paper_metadata.get("static_tables", {}))):
            raise AssertionError("Paper-artifact static-table metadata self-test failed")
        latex_probe = _table_tex(
            caption="Self-test",
            label="tab:selftest",
            environment="tabular",
            column_spec="@{}lr@{}",
            headers=["A", "B"],
            rows=[["x", "1"]],
        )
        if "\\begin{table}" not in latex_probe or "\\end{table}" not in latex_probe:
            raise AssertionError("Paper-artifact LaTeX renderer self-test failed")

        # TeX control-sequence names must contain letters only.  Previous
        # artifact releases emitted digits in macro names, causing collisions
        # such as \ScopeTekReferenceF95Hz -> \ScopeTekReferenceF.
        macro_probe_names = {
            "AntiAliasFiftyQ95Pct": 0.1,
            "ScopeTekReferenceF99Q05Hz": 123.0,
            "DurationTwoKMinWindowFor0Point5PctSeconds": 5.0,
        }
        with TemporaryDirectory() as temporary:
            macro_path = Path(temporary) / "macros.tex"
            _write_macros(macro_path, macro_probe_names)
            macro_text = macro_path.read_text(encoding="utf-8")
            for original in macro_probe_names:
                command = _latex_command_name(original)
                if not command.isalpha() or f"\\{command}" not in macro_text:
                    raise AssertionError(
                        f"Paper-artifact TeX macro sanitisation failed: {original} -> {command}"
                    )

        # JSON artifacts must be strict RFC-compatible JSON.  Non-finite
        # numerical results are represented as null rather than NaN/Infinity.
        with TemporaryDirectory() as temporary:
            json_path = Path(temporary) / "strict.json"
            write_json(
                json_path,
                {
                    "nan": float("nan"),
                    "positive_infinity": float("inf"),
                    "negative_infinity": float("-inf"),
                    "numpy_nan": np.float64(float("nan")),
                    "finite": 1.25,
                },
            )
            json_text = json_path.read_text(encoding="utf-8")
            if any(token in json_text for token in ("NaN", "Infinity")):
                raise AssertionError("Strict JSON non-finite conversion self-test failed")
            json_payload = json.loads(json_text)
            if any(
                json_payload[key] is not None
                for key in (
                    "nan", "positive_infinity", "negative_infinity", "numpy_nan"
                )
            ):
                raise AssertionError("Strict JSON null representation self-test failed")

        # Scope table snippets must be valid from the manuscript root, and wide
        # interval tables must support a width-safe resize wrapper.
        with TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            table_path = temporary_root / "table_scope_probe.tex"
            table_path.write_text("% probe\n", encoding="utf-8")
            snippet_path = temporary_root / "scope_table_snippets.tex"
            _write_table_include(
                snippet_path,
                [table_path],
                include_prefix="scope_validation/tables",
            )
            snippet_text = snippet_path.read_text(encoding="utf-8")
            if (
                "\\input{scope_validation/tables/table_scope_probe.tex}"
                not in snippet_text
            ):
                raise AssertionError("Scope table include-prefix self-test failed")
            resize_probe = _table_tex(
                caption="Wide self-test",
                label="tab:wide-selftest",
                environment="tabular_resize",
                column_spec="@{}rrrrrrr@{}",
                headers=["A", "B", "C", "D", "E", "F", "G"],
                rows=[["1", "2", "3", "4", "5", "6", "7"]],
            )
            if "\\resizebox{\\textwidth}{!}{%" not in resize_probe:
                raise AssertionError("Width-safe table-rendering self-test failed")

        # The compact review bundle intentionally omits NPZ arrays but must
        # regenerate inventories after omission, so it never lists absent files.
        with TemporaryDirectory() as temporary:
            artifact_root = Path(temporary) / "paper_artifacts"
            (artifact_root / "data").mkdir(parents=True)
            (artifact_root / "data" / "result.csv").write_text(
                "x\n1\n", encoding="utf-8"
            )
            (artifact_root / "data" / "large.npz").write_bytes(b"npz-probe")
            (artifact_root / "manifest").mkdir(parents=True)
            (artifact_root / "manifest" / "paper_artifacts_inventory.csv").write_text(
                "relative_path,bytes,sha256,suffix\ndata/large.npz,9,stale,.npz\n",
                encoding="utf-8",
            )
            (artifact_root / "scope_validation" / "manifest").mkdir(
                parents=True
            )
            (artifact_root / "scope_validation" / "data").mkdir(
                parents=True
            )
            (artifact_root / "scope_validation" / "data" / "probe.csv").write_text(
                "x\n1\n", encoding="utf-8"
            )
            (
                artifact_root
                / "scope_validation"
                / "manifest"
                / "scope_paper_artifacts_inventory.csv"
            ).write_text(
                "relative_path,bytes,sha256,suffix\nmissing.npz,1,stale,.npz\n",
                encoding="utf-8",
            )
            review_zip, review_hash = _write_review_bundle(artifact_root)
            if not review_zip.is_file() or not review_hash.is_file():
                raise AssertionError("Review-bundle creation self-test failed")
            with zipfile.ZipFile(review_zip) as archive:
                names = set(archive.namelist())
                if "data/large.npz" in names:
                    raise AssertionError("Review bundle retained an NPZ array")
                required_names = {
                    "REVIEW_BUNDLE_NOTICE.md",
                    "manifest/review_bundle_manifest.json",
                    "manifest/paper_artifacts_inventory.csv",
                    "scope_validation/manifest/scope_paper_artifacts_inventory.csv",
                }
                if not required_names.issubset(names):
                    raise AssertionError("Review-bundle contract files are missing")
                root_inventory_text = archive.read(
                    "manifest/paper_artifacts_inventory.csv"
                ).decode("utf-8")
                if "large.npz" in root_inventory_text or "missing.npz" in root_inventory_text:
                    raise AssertionError("Review-bundle inventory lists omitted files")
                review_manifest = json.loads(
                    archive.read("manifest/review_bundle_manifest.json")
                )
                omitted_paths = {
                    row["relative_path"]
                    for row in review_manifest.get("omitted_files", [])
                }
                if "data/large.npz" not in omitted_paths:
                    raise AssertionError("Review-bundle omission manifest self-test failed")

        # Archived duration-campaign u.RECS values already contain the 0.97
        # setup correction.  The artifact pipeline must not generate a second
        # factor-corrected variant from those stored values.
        legacy_probe = [
            {
                "workload": "probe",
                "requested_duration_s": 5.0,
                "method": "u.RECS",
                "variant": "raw",
                "mean_power_w": 10.0,
            }
        ]
        legacy_summary = _method_summaries(
            legacy_probe,
            correction_factor=0.97,
            values_already_include_correction_factor=True,
        )
        if any(row.get("variant") == "factor_corrected" for row in legacy_summary):
            raise AssertionError("u.RECS correction-factor double-application self-test failed")

    # Load the shipped configuration when running from the source package. This
    # catches schema drift between configuration, analysis, plotting and report code.
    packaged_config = Path(__file__).resolve().parent.parent / "config_gemm_fp16.yaml"
    if packaged_config.is_file():
        cfg = load_config(packaged_config)
        required = (
            cfg.common_trace.reconstruction_modes,
            cfg.common_trace.fmin_thresholds_pct,
            cfg.common_trace.phase_only_sensitivity_source_rates_sps,
            cfg.common_trace.phase_only_sensitivity_target_rates_sps,
            cfg.psd.sensitivity_rates_sps,
            cfg.psd.sensitivity_check_rates_sps,
            cfg.psd.variance_capture_rates_sps,
            cfg.psd.variance_capture_thresholds,
            cfg.psd.variance_bands,
            cfg.psd.low_frequency_nyquist_rates_sps,
            cfg.psd.full_frequency_nyquist_rates_sps,
            cfg.duration_sensitivity.target_rates_sps,
            cfg.duration_sensitivity.window_durations_s,
            cfg.duration_sensitivity.thresholds_pct,
        )
        if any(not value for value in required):
            raise AssertionError("Packaged configuration self-test failed")
        if not cfg.duration_sensitivity.campaign.urecs_values_already_include_correction_factor:
            raise AssertionError("Packaged u.RECS correction semantics self-test failed")

    # Automatic workload discovery/orchestration contract. New directories must
    # be included without hand-written start scripts, while the reserved idle
    # tree is excluded and generated configs remain deterministic.
    packaged_auto = Path(__file__).resolve().parent.parent / "config_auto_pipeline.yaml"
    if packaged_auto.is_file():
        auto_cfg = _auto_load_pipeline_config(packaged_auto)
        if auto_cfg.common_rate_sps != 5_000_000:
            raise AssertionError("Automatic-pipeline common-rate config self-test failed")
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_root = root / "measurements"
            idle_root = data_root / "idle" / "5000000"
            int8_root = data_root / "gemmint8" / "5000000"
            unknown_root = data_root / "customnetbf16" / "2500Sps"
            for directory in (idle_root, int8_root, unknown_root):
                directory.mkdir(parents=True, exist_ok=True)
            for directory in (idle_root, int8_root, unknown_root):
                (directory / "tek_hsi_0.parquet").write_bytes(b"synthetic")
                (directory / "usb_osc_data_0.parquet").write_bytes(b"synthetic")
            auto_payload = load_yaml(packaged_auto)
            auto_payload["dataset_root"] = str(data_root)
            auto_payload["analysis_root"] = str(root / "analysis")
            auto_payload["state_root"] = str(root / "state")
            auto_payload["base_multi_workload_config"] = str(
                Path(__file__).resolve().parent.parent / "config_multi_workload.yaml"
            )
            auto_payload["generic_scope_template"] = str(
                Path(__file__).resolve().parent.parent / "config_scope_resnet50.yaml"
            )
            auto_payload["known_scope_configs"] = {}
            auto_path = root / "config_auto.yaml"
            with auto_path.open("w", encoding="utf-8") as handle:
                import yaml as _yaml
                _yaml.safe_dump(auto_payload, handle, sort_keys=False)
            synthetic_auto = _auto_load_pipeline_config(auto_path)
            discovered = _auto_discover_workloads(synthetic_auto)
            ids = [row.workload_id for row in discovered]
            if ids != ["gemmint8", "customnetbf16"]:
                raise AssertionError(f"Automatic workload discovery self-test failed: {ids}")
            int8 = discovered[0]
            if int8.label != "GEMM-INT8" or int8.common_rate_paired_runs != 1:
                raise AssertionError("Automatic workload metadata self-test failed")
            for workload in discovered:
                generated = _auto_generate_scope_config(synthetic_auto, workload)
                generated_data = load_yaml(generated)
                if generated_data["dataset_root"] != str(workload.dataset_root):
                    raise AssertionError("Generated scope dataset binding self-test failed")
                windows = generated_data.get("analysis_windows", {})
                if windows.get("shared_anchor_mode") != "fixed_time" or float(windows.get("trigger_time_s")) != 0.0:
                    raise AssertionError("Generated record-start trigger self-test failed")
            generated_multi = _auto_generate_multi_workload_config(
                synthetic_auto, discovered
            )
            multi_data = load_yaml(generated_multi)
            generated_ids = [row["id"] for row in multi_data["workloads"]]
            if generated_ids != ids:
                raise AssertionError("Generated multi-workload registry self-test failed")

    # Multi-workload analysis contract: identical-rate PSDs, hierarchical
    # same-trace summaries, suffix-monotonic f_min selection, and optional
    # missing workload campaigns must remain schema-valid without PyArrow I/O.
    packaged_multi = Path(__file__).resolve().parent.parent / "config_multi_workload.yaml"
    if packaged_multi.is_file():
        multi_cfg = load_multi_workload_config(packaged_multi)
        if multi_cfg.psd.comparison_rate_sps != 5_000_000:
            raise AssertionError("Multi-workload common PSD-rate self-test failed")
        if set(multi_cfg.common_reference.sources) != {"tek", "pico"}:
            raise AssertionError("Multi-workload source-contract self-test failed")
        if not multi_cfg.psd.log_frequency_derivative_enabled:
            raise AssertionError("Multi-workload log-frequency derivative config self-test failed")
        if len(multi_cfg.psd.fine_structure_windows) < 5:
            raise AssertionError("Multi-workload fine-structure config self-test failed")
        if not any(
            abs(low_hz - 25_000.0) < 1e-9 and abs(high_hz - 35_000.0) < 1e-9
            for _, low_hz, high_hz in multi_cfg.psd.fine_structure_windows
        ):
            raise AssertionError("INT8 25–35-kHz fine-structure window self-test failed")
        with TemporaryDirectory() as provenance_tmp:
            provenance_root = Path(provenance_tmp)
            provenance_cfg = replace(multi_cfg, output_root=provenance_root)
            effective_config = (
                provenance_root
                / "generated_configs"
                / "config_multi_workload_auto.yaml"
            )
            effective_config.parent.mkdir(parents=True, exist_ok=True)
            effective_config.write_text("synthetic: true\n", encoding="utf-8")
            stale_summary = (
                provenance_root
                / "paper_artifacts"
                / "MULTI_WORKLOAD_PAPER_ARTIFACTS_SUMMARY.md"
            )
            stale_summary.parent.mkdir(parents=True, exist_ok=True)
            stale_summary.write_text(
                "# Multi-workload paper artifacts\n\n"
                "Generated with tool `0.7.3` from `/stale/config.yaml`.\n",
                encoding="utf-8",
            )
            current_summary = _multi_write_artifact_summary(
                provenance_cfg, effective_config, []
            )
            if current_summary != stale_summary:
                raise AssertionError("Artifact-summary target self-test failed")
            bundle_paths = _multi_build_bundles(provenance_cfg)
            review_zip = next(
                path
                for path in bundle_paths
                if path.name == "multi_workload_documentation_artifacts_review.zip"
            )
            with zipfile.ZipFile(review_zip) as archive:
                bundled_summary = archive.read(
                    "paper_artifacts/MULTI_WORKLOAD_PAPER_ARTIFACTS_SUMMARY.md"
                ).decode("utf-8")
            if f"Generated with tool `{__version__}`" not in bundled_summary:
                raise AssertionError("Current bundle-version provenance self-test failed")
            if str(effective_config.resolve()) not in bundled_summary:
                raise AssertionError("Current bundle-config provenance self-test failed")
            if "0.7.3" in bundled_summary or "/stale/config.yaml" in bundled_summary:
                raise AssertionError("Stale bundle provenance self-test failed")
        if not multi_cfg.psd.idle_load_comparison_enabled:
            raise AssertionError("Multi-workload idle/load comparison config self-test failed")
        if multi_cfg.psd.idle_record_policy != "full_record_per_run_equal_weight":
            raise AssertionError("Full-record idle aggregation policy self-test failed")
        active_welch = _multi_welch_parameters(5_000_000, 5_000_000.0)
        longer_idle_welch = _multi_welch_parameters(50_000_000, 5_000_000.0)
        if active_welch[0] != longer_idle_welch[0] or longer_idle_welch[2] <= active_welch[2]:
            raise AssertionError("Long-idle Welch averaging self-test failed")
        if multi_cfg.psd.idle_load_ratio_bins_per_decade != 24:
            raise AssertionError("Idle/load log-ratio binning config self-test failed")
        ratio_f = np.geomspace(1.0, 100_000.0, 5000)
        ratio_idle = 1.0 / ratio_f
        ratio_active = 2.0 * ratio_idle
        ratio_rows = _multi_log_binned_active_idle_ratio_rows(
            ratio_f, ratio_active, ratio_idle, bins_per_decade=24
        )
        ratio_values = np.asarray(
            [row["active_to_idle_ratio_db"] for row in ratio_rows],
            dtype=np.float64,
        )
        ratio_values = ratio_values[np.isfinite(ratio_values)]
        if ratio_values.size < 8 or np.max(np.abs(ratio_values - 10.0 * np.log10(2.0))) > 0.02:
            raise AssertionError("Idle/load log-frequency ratio self-test failed")
        if _multi_classify_idle_load_peak(
            active_to_idle_db=12.0,
            idle_peak_matched=False,
            amplification_threshold_db=3.0,
            load_only_threshold_db=6.0,
        ) != "no_dominant_idle_match_load_only_candidate":
            raise AssertionError("Idle/load peak classification self-test failed")
        active_probe = np.asarray([4.0, 1.0, 3.0])
        idle_probe = np.asarray([1.5, 2.0, 3.0])
        overlap_probe = np.minimum(active_probe, idle_probe)
        additional_probe = np.maximum(active_probe - idle_probe, 0.0)
        if not np.allclose(active_probe, overlap_probe + additional_probe):
            raise AssertionError("Idle/load PSD decomposition self-test failed")
        starts = _multi_window_starts(0.5, 2.0, 4, 0.0, 1000.0)
        if starts.size != 4 or starts[0] < 0 or starts[-1] + 0.5 > 2.0:
            raise AssertionError("Multi-workload window placement self-test failed")
        f_probe = np.linspace(0.0, 500.0, 501)
        d_probe = np.exp(-f_probe / 50.0)
        c_probe = _multi_density_cumulative(f_probe, d_probe)
        f95_probe = _multi_frequency_at_fraction(f_probe, c_probe, 0.95)
        if not 100.0 < f95_probe < 200.0:
            raise AssertionError("Multi-workload cumulative PSD self-test failed")
        idle_probe = np.full_like(f_probe, 1.0)
        load_probe = np.full_like(f_probe, 0.5)
        active_probe = idle_probe + load_probe
        overlap_probe = np.minimum(active_probe, idle_probe)
        excess_probe = np.maximum(active_probe - idle_probe, 0.0)
        active_area = _multi_density_integral_band(
            f_probe, active_probe, 0.0, 500.0
        )
        overlap_area = _multi_density_integral_band(
            f_probe, overlap_probe, 0.0, 500.0
        )
        excess_area = _multi_density_integral_band(
            f_probe, excess_probe, 0.0, 500.0
        )
        if abs(active_area - overlap_area - excess_area) > 1e-9:
            raise AssertionError("Active/idle spectral decomposition self-test failed")
        if (
            _multi_classify_idle_load_peak(
                active_to_idle_db=7.0,
                idle_peak_matched=False,
                amplification_threshold_db=3.0,
                load_only_threshold_db=6.0,
            )
            != "no_dominant_idle_match_load_only_candidate"
        ):
            raise AssertionError("Idle/load peak-classification self-test failed")

        f_log = np.geomspace(1.0, 100_000.0, 5000)
        d_log = 1.0 / f_log
        per_decade = _multi_log_frequency_variance_density(f_log, d_log)
        derivative_area = float(trapezoid(per_decade, np.log10(f_log)))
        if abs(derivative_area - 100.0) > 0.05:
            raise AssertionError(
                f"Log-frequency cumulative-derivative self-test failed: {derivative_area}"
            )
        synthetic_rows = []
        for workload_id, multiplier in (("a", 1.0), ("b", 1.2)):
            for run in (0, 1, 2):
                for rate in (1000, 2000, 4000):
                    for duration in (1.0, 2.0):
                        synthetic_rows.append(
                            {
                                "workload_id": workload_id,
                                "workload_label": workload_id.upper(),
                                "source": "tek",
                                "run": run,
                                "mode": "phase_only",
                                "target_rate_sps": rate,
                                "duration_s": duration,
                                "abs_error_pct_q95": multiplier * 1000.0 / rate / duration,
                                "abs_error_pct_median": 0.5 * multiplier * 1000.0 / rate / duration,
                            }
                        )
        summary_rows, fmin_rows, threshold_rows, worst_rows = (
            _multi_summarise_common_reference(multi_cfg, synthetic_rows)
        )
        if not summary_rows or not fmin_rows or not threshold_rows or not worst_rows:
            raise AssertionError("Multi-workload summary self-test failed")
        one_pct = [
            row for row in worst_rows
            if row["source"] == "tek"
            and row["mode"] == "phase_only"
            and abs(float(row["threshold_pct"]) - 1.0) < 1e-12
            and abs(float(row["duration_s"]) - 1.0) < 1e-12
        ]
        if not one_pct or one_pct[0]["worst_case_f_min_sps"] != 2000:
            raise AssertionError("Multi-workload worst-case envelope self-test failed")
        formatting_probes = {
            _multi_human_frequency_tick(10.0): "10 Hz",
            _multi_human_frequency_tick(1_000.0): "1 kHz",
            _multi_human_frequency_tick(1_000_000.0): "1 MHz",
            _multi_human_rate_tick(2_000.0): "2 kS/s",
            _multi_human_rate_tick(5_000_000.0): "5 MS/s",
            _multi_human_duration_tick(0.1): "100 ms",
            _multi_human_duration_tick(5.0): "5 s",
            _multi_human_percent_tick(0.1): "0.1%",
            _multi_human_percent_tick(1.0): "1%",
            _multi_human_percent_tick(10.0): "10%",
        }
        if any(actual != expected for actual, expected in formatting_probes.items()):
            raise AssertionError("Multi-workload human-readable axis formatter self-test failed")

    from .journal_selftest import run_journal_selftest
    run_journal_selftest()

    print(
        "Self-test passed: configuration schema, fixed-window integration, "
        "anti-aliased and phase-only sampling, 1-MS/s PSD configuration, "
        "bandwidth-sensitivity checks, paired-scope alignment, the "
        "current-dependent voltage model, mixed rate-directory discovery, "
        "dual-rate equal-duration comparison, variable-duration read-only "
        "input validation, source-fingerprint "
        "cache invalidation, adaptive Welch safeguards, Tek-primary PSD "
        "selection, operating-point diagnostics, duration-dependent energy-rate "
        "bounds, external exact-rate idle fallback, record-start GPIO windows, workload-minus-idle session-shift detection and salvage correction, paired-scope PSD-grid "
        "harmonisation, strict JSON, manuscript-relative scope snippets, "
        "compact-review inventories, optional-band n/a handling, current-run "
        "log provenance, cross-workload PSD/common-reference analysis, full-record external-idle comparison with equal physical-run weighting, active/idle/excess spectral decomposition, direct-Hz PSD axes without angular-frequency conversion, cumulative-spectrum derivatives, linear fine-structure plots, full-record external-idle versus load diagnostics, setup terminology, human-readable plot units, and "
        "automatic workload discovery and incremental orchestration, header-only zero-offset evidence artifacts, current bundle provenance, the INT8 25–35-kHz fine-structure zoom, and paper-artifact metadata are valid."
    )
