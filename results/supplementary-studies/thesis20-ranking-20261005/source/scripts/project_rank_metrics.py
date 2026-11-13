"""Verbatim pure existing project rank functions; see rank_function_provenance.json."""
from __future__ import annotations
import math,copy
from collections import defaultdict
from collections.abc import Mapping,Sequence
from typing import Any
STRATUM=("model_id","setup_id","direction","precision","comparison_backend","output_endpoint_id","boundary_class")

def _rank(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda idx: values[idx])
    ranks = [0.0] * len(values)
    pos = 0
    while pos < len(order):
        end = pos + 1
        while end < len(order) and values[order[end]] == values[order[pos]]:
            end += 1
        avg = (pos + 1 + end) / 2.0
        for offset in range(pos, end):
            ranks[order[offset]] = avg
        pos = end
    return ranks

def _pearson(x: Sequence[float], y: Sequence[float]) -> float | None:
    if len(x) != len(y) or len(x) < 2:
        return None
    mx = sum(x) / len(x)
    my = sum(y) / len(y)
    sx = sum((v - mx) ** 2 for v in x)
    sy = sum((v - my) ** 2 for v in y)
    if sx <= 0 or sy <= 0:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / math.sqrt(sx * sy)

def _spearman(x: Sequence[float], y: Sequence[float]) -> float | None:
    return _pearson(_rank(x), _rank(y))

def _kendall_tau_b(x: Sequence[float], y: Sequence[float]) -> float | None:
    if len(x) != len(y) or len(x) < 2:
        return None
    concordant = discordant = tie_x = tie_y = 0
    for i in range(len(x)):
        for j in range(i + 1, len(x)):
            dx = (x[i] > x[j]) - (x[i] < x[j])
            dy = (y[i] > y[j]) - (y[i] < y[j])
            if dx == 0 and dy == 0:
                continue
            if dx == 0:
                tie_x += 1
            elif dy == 0:
                tie_y += 1
            elif dx == dy:
                concordant += 1
            else:
                discordant += 1
    denom = math.sqrt((concordant + discordant + tie_x) * (concordant + discordant + tie_y))
    return (concordant - discordant) / denom if denom > 0 else None

def _pairwise_counts(x: Sequence[float], y: Sequence[float]) -> tuple[int, int]:
    comparable = correct = 0
    for i in range(len(x)):
        for j in range(i + 1, len(x)):
            dx = (x[i] > x[j]) - (x[i] < x[j])
            dy = (y[i] > y[j]) - (y[i] < y[j])
            if dx == 0 or dy == 0:
                continue
            comparable += 1
            correct += int(dx == dy)
    return correct, comparable

def completion_groups(pairs: list[dict[str, Any]], *, minimum_candidates: int = 3) -> list[dict[str, Any]]:
    """Use the existing Cross-Runner rank/tie rules within each exact stratum."""
    grouped = defaultdict(list)
    fields = ("model_id", "setup_id", "direction", "precision", "comparison_backend", "output_endpoint_id", "boundary_class")
    for pair in pairs:
        grouped[tuple(str(pair.get(key) or "") for key in fields)].append(pair)
    groups = []
    for key, rows in sorted(grouped.items()):
        group = dict(zip(fields, key))
        group.update(planned_candidate_count=len(rows), minimum_candidates=minimum_candidates)
        for tier in ("technical", "quality", "claim"):
            eligible = [r for r in rows if r.get(f"eligible_for_{tier}_transfer")]
            # Same lower-is-better cycle ranking as the original reporter;
            # inverse here is only a rank coordinate of already measured FPS.
            generic = [1000.0 / r["generic_completed_task_fps"] for r in eligible]
            native = [1000.0 / r["native_completed_task_fps"] for r in eligible]
            count = len(eligible)
            enough = count >= minimum_candidates
            rho = _spearman(generic, native) if enough else None
            tau = _kendall_tau_b(generic, native) if enough else None
            concordant, comparable = _pairwise_counts(generic, native)
            group.update({
                f"{tier}_candidate_count": count,
                f"{tier}_spearman_rho": rho,
                f"{tier}_kendall_tau_b": tau,
                f"{tier}_pairwise_concordance": concordant / comparable if enough and comparable else None,
                f"{tier}_pairwise_comparable_count": comparable,
                f"{tier}_status": "insufficient_candidates" if not enough else "constant_ranks" if rho is None else "ok",
            })
            for row, grank, nrank in zip(eligible, _rank(generic), _rank(native)):
                row[f"{tier}_generic_rank"] = grank
                row[f"{tier}_native_rank"] = nrank
        groups.append(group)
    return groups

def _stratum(row: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(str(row.get(key) or "") for key in STRATUM)

def _groups(pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reuse the ranker; add the existing Cross-Runner Top-1 cycle regret."""
    groups = completion_groups(copy.deepcopy(pairs), minimum_candidates=3)
    by_stratum: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in pairs:
        by_stratum[_stratum(row)].append(row)
    for group in groups:
        rows = by_stratum[_stratum(group)]
        close = [row for row in rows if row.get("eligible_for_quality_transfer") is True
                 and row.get("generic_task_quality_status") == "reference_close"
                 and row.get("native_task_quality_status") == "reference_close"]
        filtered = completion_groups(copy.deepcopy(close), minimum_candidates=3)
        for key in ("candidate_count", "spearman_rho", "kendall_tau_b", "pairwise_concordance", "status"):
            group[f"reference_close_{key}"] = (filtered[0].get(f"quality_{key}") if filtered else
                0 if key == "candidate_count" else "insufficient_candidates" if key == "status" else None)
        for tier in ("technical", "quality", "claim", "reference_close"):
            eligible = close if tier == "reference_close" else [
                row for row in rows if row.get(f"eligible_for_{tier}_transfer") is True]
            group[f"{tier}_native_best_hit_at_1"] = None
            group[f"{tier}_native_regret_at_1"] = None
            if len(eligible) >= 3:
                # Identical ordering, cycle coordinate and stable tie handling
                # to cross_runner_reporting.add_shortlist_metrics(k=1).
                native_best = min(eligible, key=lambda row: 1000.0 / row["native_completed_task_fps"])
                selected = min(eligible, key=lambda row: 1000.0 / row["generic_completed_task_fps"])
                best_cycle = 1000.0 / native_best["native_completed_task_fps"]
                selected_cycle = 1000.0 / selected["native_completed_task_fps"]
                group[f"{tier}_native_best_hit_at_1"] = selected is native_best
                group[f"{tier}_native_regret_at_1"] = (selected_cycle - best_cycle) / best_cycle
        group["top3_at_n3_is_trivial"] = group["technical_candidate_count"] == 3
        group["top3_is_performance_claim"] = False
        group["quality_cohort_meaning"] = "valid_accuracy_observation_including_accuracy_loss"
        group["reference_close_cohort_meaning"] = "both_runners_reference_close_with_existing_quality_checks"
        group["observation_origins"] = sorted({row["observation_origin"] for row in rows})
        group["runtime_conditions_comparable"] = all(row.get("runtime_conditions_comparable") is True for row in rows)
    return groups

