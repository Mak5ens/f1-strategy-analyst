"""How far the strategy simulation can be trusted (LAB-213): its lines, extended past the laps they were fitted on.

Moving a stop runs a stint longer, or shorter, than it was raced: the simulation then extends the stint's line to
tyre ages it never saw. This measures that error on real stints. For each race stint of a season with at least 15
clean laps, the line is fitted on its first clean laps only, then extended to the following clean laps of the same
stint, and the time it projects for them is compared with the time they took:

    error of k laps = projected time of the k laps that follow - their real time

`just simulation-validate 2025` writes `evals/reports/simulation-<season>.json`: the median and 90th percentile of the
absolute error by number of laps extended (1 to 5, 6 to 10, 11 to 20), and its median signed error (bias). The
simulation shows the one of its longest extension next to each projection (`expected_error`).
"""

import argparse
import json
import statistics
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from f1.tools.data import RaceData, SessionRef, is_clean, number
from f1.tools.degradation import DEFAULT_FUEL_EFFECT_S_PER_LAP, by_stint, fit

REPORTS = Path("evals/reports")
MIN_CLEAN = 15
FITTED_SHARE = 0.6
BUCKETS = [(1, 5), (6, 10), (11, 20)]


def extension_errors(laps: Sequence[dict[str, Any]], stint: int) -> list[tuple[int, float]]:
    """(laps extended, error in seconds) for each length the stint's held-out clean laps allow."""
    clean = [lap for lap in laps if is_clean(lap)]
    if len(clean) < MIN_CLEAN:
        return []
    cut = int(len(clean) * FITTED_SHARE)
    fitted = fit(stint, [lap for lap in laps if int(lap["lap_number"]) <= int(clean[cut - 1]["lap_number"])])
    slope, intercept = fitted.summary.degradation_s_per_lap, fitted.intercept_s
    if slope is None or intercept is None:
        return []
    errors, total = [], 0.0
    for k, lap in enumerate(clean[cut:], start=1):
        age = number(lap["tyre_life"]) or float(lap["lap_number"])
        projected = intercept + slope * age - DEFAULT_FUEL_EFFECT_S_PER_LAP * (int(lap["lap_number"]) - 1)
        total += projected - float(lap["lap_time_s"])
        errors.append((k, round(total, 3)))
    return errors


def validate(data: RaceData, season: int) -> dict[str, Any]:
    samples: list[tuple[int, float]] = []
    stints = 0
    for event in data.events(season):
        ref = SessionRef(season=season, round=int(event["round"]))
        try:
            laps = data.laps(ref)
        except Exception:  # a round without a race yet
            continue
        for code in sorted({str(lap["driver"]) for lap in laps}):
            mine = {int(lap["lap_number"]): lap for lap in laps if lap["driver"] == code}
            for number_, stint_laps in by_stint(mine).items():
                found = extension_errors(stint_laps, number_)
                stints += bool(found)
                samples += found
    buckets = []
    for low, high in BUCKETS:
        signed = [error for k, error in samples if low <= k <= high]
        errors = sorted(abs(error) for error in signed)
        if errors:
            buckets.append(
                {
                    "laps": [low, high],
                    "samples": len(errors),
                    "median_s": round(statistics.median(errors), 3),
                    "p90_s": round(errors[int(0.9 * (len(errors) - 1))], 3),
                    # Negative: the line projects the laps faster than they were (the tyres wear faster late on).
                    "bias_s": round(statistics.median(signed), 3),
                }
            )
    return {
        "season": season,
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "stints": stints,
        "fitted_share": FITTED_SHARE,
        "min_clean_laps": MIN_CLEAN,
        "buckets": buckets,
    }


def expected_error(laps: int, season: int, reports: Path = REPORTS) -> dict[str, Any] | None:
    """The measured error of a line extended by `laps` laps, from the latest validation report; None without one."""
    found = sorted(reports.glob("simulation-*.json"), key=lambda path: (path.stem != f"simulation-{season}", path.stem))
    if laps <= 0 or not found:
        return None
    report = json.loads(found[0].read_text())
    for bucket in report["buckets"]:
        low, high = bucket["laps"]
        if low <= laps <= high or (laps > high and bucket is report["buckets"][-1]):
            return {**bucket, "season": report["season"]}
    return None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("season", type=int)
    args = parser.parse_args(argv)
    from f1.data import connect

    report = validate(RaceData(connect()), args.season)
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / f"simulation-{args.season}.json"
    path.write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(report["buckets"], indent=1))
    print(f"{report['stints']} stints. Report: {path}")
    return 0
