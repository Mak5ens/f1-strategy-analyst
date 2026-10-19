"""How far the strategy simulation can be trusted (LAB-213): its lines, extended past the laps they were fitted on.

Moving a stop runs a stint longer, or shorter, than it was raced: the simulation then extends the stint's line to
tyre ages it never saw. This measures that error on real stints. For each race stint of a season with at least 15
clean laps, the line is fitted on its first clean laps only, then extended to the following clean laps of the same
stint, and the time it projects for them is compared with the time they took:

    error of k laps = projected time of the k laps that follow - their real time

A stint run on another compound takes the driver's line on the compound raced, shifted by what the other drivers of
the race lose or gain between the two (`degradation.compound_shift`). That is measured the same way: for each driver
who ran two compounds in a race, the line of one, shifted by the others' difference, projects the clean laps of the
stint on the other, whose times are known:

    error of k laps = projected time of the stint's first k clean laps - their real time

`just simulation-validate 2025` writes `evals/reports/simulation-<season>.json`: the median and 90th percentile of the
absolute error by number of laps extended (1 to 5, 6 to 10, 11 to 20), and its median signed error (bias), then the
same by number of laps run on another compound (1 to 10, 11 to 20, 21 to 40). The simulation shows the one of its
longest extension next to each projection (`expected_error`), and the one of its longest stint on another compound
(`compound_error`).
"""

import argparse
import json
import statistics
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from f1.tools.data import RaceData, SessionRef, is_clean, number
from f1.tools.degradation import DEFAULT_FUEL_EFFECT_S_PER_LAP, StintFit, by_stint, compound_shift, fit, race_fits

REPORTS = Path("evals/reports")
MIN_CLEAN = 15
FITTED_SHARE = 0.6
BUCKETS = [(1, 5), (6, 10), (11, 20)]
COMPOUND_BUCKETS = [(1, 10), (11, 20), (21, 40)]
MIN_COMPOUND_CLEAN = 8


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


def compound_errors(
    laps: Sequence[dict[str, Any]], driver: str, fits: Mapping[str, Sequence[StintFit]] | None = None
) -> list[tuple[int, float]]:
    """(laps projected, error in seconds) for each stint of the driver projected from their line on another compound,
    shifted by the other drivers' difference between the two."""
    fits = race_fits(laps) if fits is None else fits
    mine = {int(lap["lap_number"]): lap for lap in laps if lap["driver"] == driver}
    stints = by_stint(mine)
    errors: list[tuple[int, float]] = []
    for target in fits.get(driver, []):
        compound = target.summary.compound
        clean = [lap for lap in stints[target.summary.stint] if is_clean(lap)]
        if compound is None or len(clean) < MIN_COMPOUND_CLEAN:
            continue
        for source in _sources(fits[driver], compound):
            shift = compound_shift(fits, str(source.summary.compound), compound, exclude=driver)
            if shift is None or source.intercept_s is None or source.summary.degradation_s_per_lap is None:
                continue
            intercept = source.intercept_s + shift.intercept_s
            slope = source.summary.degradation_s_per_lap + shift.degradation_s_per_lap
            total = 0.0
            for k, lap in enumerate(clean, start=1):
                age = number(lap["tyre_life"]) or float(lap["lap_number"])
                projected = intercept + slope * age - DEFAULT_FUEL_EFFECT_S_PER_LAP * (int(lap["lap_number"]) - 1)
                total += projected - float(lap["lap_time_s"])
                errors.append((k, round(total, 3)))
    return errors


def _sources(lines: Sequence[StintFit], compound: str) -> list[StintFit]:
    """The driver's line on each other compound they ran: their first stint on it."""
    found: dict[str, StintFit] = {}
    for line in lines:
        if line.summary.compound and line.summary.compound != compound:
            found.setdefault(line.summary.compound, line)
    return list(found.values())


def _buckets(samples: Sequence[tuple[int, float]], ranges: Sequence[tuple[int, int]]) -> list[dict[str, Any]]:
    buckets = []
    for low, high in ranges:
        signed = [error for k, error in samples if low <= k <= high]
        errors = sorted(abs(error) for error in signed)
        if errors:
            buckets.append(
                {
                    "laps": [low, high],
                    "samples": len(errors),
                    "median_s": round(statistics.median(errors), 3),
                    "p90_s": round(errors[int(0.9 * (len(errors) - 1))], 3),
                    # Negative: the line projects the laps faster than they were.
                    "bias_s": round(statistics.median(signed), 3),
                }
            )
    return buckets


def validate(data: RaceData, season: int) -> dict[str, Any]:
    samples: list[tuple[int, float]] = []
    compound_samples: list[tuple[int, float]] = []
    stints = 0
    for event in data.events(season):
        ref = SessionRef(season=season, round=int(event["round"]))
        try:
            laps = data.laps(ref)
        except Exception:  # a round without a race yet
            continue
        fits = race_fits(laps)
        for code in sorted({str(lap["driver"]) for lap in laps}):
            compound_samples += compound_errors(laps, code, fits)
            mine = {int(lap["lap_number"]): lap for lap in laps if lap["driver"] == code}
            for number_, stint_laps in by_stint(mine).items():
                found = extension_errors(stint_laps, number_)
                stints += bool(found)
                samples += found
    return {
        "season": season,
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "stints": stints,
        "fitted_share": FITTED_SHARE,
        "min_clean_laps": MIN_CLEAN,
        "buckets": _buckets(samples, BUCKETS),
        "min_compound_clean_laps": MIN_COMPOUND_CLEAN,
        "compound_buckets": _buckets(compound_samples, COMPOUND_BUCKETS),
    }


def expected_error(laps: int, season: int, reports: Path = REPORTS) -> dict[str, Any] | None:
    """The measured error of a line extended by `laps` laps, from the latest validation report; None without one."""
    return _error(laps, season, reports, "buckets")


def compound_error(laps: int, season: int, reports: Path = REPORTS) -> dict[str, Any] | None:
    """The measured error of `laps` laps projected from another compound's line; None without a report."""
    return _error(laps, season, reports, "compound_buckets")


def _error(laps: int, season: int, reports: Path, key: str) -> dict[str, Any] | None:
    found = sorted(reports.glob("simulation-*.json"), key=lambda path: (path.stem != f"simulation-{season}", path.stem))
    if laps <= 0 or not found:
        return None
    report = json.loads(found[0].read_text())
    buckets = report.get(key, [])
    for bucket in buckets:
        low, high = bucket["laps"]
        if low <= laps <= high or (laps > high and bucket is buckets[-1]):
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
    print(json.dumps({"extension": report["buckets"], "compound": report["compound_buckets"]}, indent=1))
    print(f"{report['stints']} stints. Report: {path}")
    return 0
