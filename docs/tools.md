# Race analysis tools

The numbers of a debrief never come from a model: the agent calls these tools, which compute on the race data lake ([schema](data-schema.md)), and the model only explains their results.
Each tool is a `core.tools.Tool`: a typed input (Pydantic), a typed output, and a JSON schema for tool calling (`tool.openai_schema()`).
`f1.tools.catalog(RaceData(connect()))` returns them all, bound to the lake.

```python
from f1.data import connect
from f1.tools import RaceData, catalog

tools = {tool.name: tool for tool in catalog(RaceData(connect()))}
tools["pit_cycle"].run({"season": 2024, "round": 13, "driver": "NOR", "rival": "PIA", "driver_stop": 2})
```

Every input takes `season`, `round` and `session` (`R` race by default, `S` sprint), and drivers as three-letter codes.
A request the data cannot answer (unknown driver, stop or stint, session not ingested) raises `ToolError` with a message that says what exists: the agent can show it or ask the user, it never gets a made-up number.
Times are seconds, rounded to the millisecond.

## Definitions shared by the tools

- **Gap at the line**: the time between two drivers crossing the line at the end of the same lap, from `laps.lap_end_session_s`. Positive: the driver is behind. It needs no lap time, so in- and out-laps and missing timings do not break it.
- **Clean lap**: green flag for the whole lap (`track_status` exactly `1`), not lap 1, not an in- or out-lap, not deleted, with a lap time. Only clean laps say something about pace.
- **Neutralized lap**: a safety car (`4`), red flag (`5`) or VSC (`6`, `7`) at some point of the lap.

## gap_between_drivers

Gap between `driver` and `reference_driver` at the end of each lap both completed, between `from_lap` and `to_lap` (optional).

Output: per lap, `gap_s`, `lap_delta_s` (change on that lap: positive, the driver lost time) and both positions; then `first_gap_s`, `final_gap_s` and `gained_s` (positive: the driver gained).

Limits: a lapped driver crosses the line of lap n a lap later than the leader, so the gap includes that lap.

## stint_degradation

Tyre wear of each stint of a driver (or one `stint`): the slope of lap time against tyre age, by least squares on the clean laps.

- **Fuel correction** (assumption): the car gets lighter by about 1.8 kg of fuel per lap, worth about 0.035 s per kg, so about **0.06 s per lap** (`fuel_effect_s_per_lap`, between 0 and 0.2). Each lap time gets back the fuel effect since lap 1, which compares laps at equal weight. Without it, the fuel burnt hides part of the wear: `raw_slope_s_per_lap` is also returned to show the difference.
- **Outliers**: a clean lap more than 3% slower than the stint median is left out (traffic, a mistake, a yellow flag the track status missed).
- At least **5 clean laps**, or the slope is `None` with a `note`.

Output per stint: compound, laps, `laps_used`, `excluded` (laps left out by reason), `degradation_s_per_lap`, `raw_slope_s_per_lap`, `r_squared`, `median_lap_s`.

Limits: the slope also contains track evolution (the track gets faster as rubber builds up), and a driver managing tyres or stuck behind another car shows less wear than the tyre has. A low `r_squared` says the laps are too scattered for the slope to mean much.

## pit_stop_loss

What each stop of a driver (or one `stop_number`) cost.

- `pit_lane_time_s`: pit entry line to pit exit line (FastF1, OpenF1 if missing); `stationary_time_s`: car stopped in the box (OpenF1).
- `in_and_out_laps_s`: from the line before the in-lap to the end of the out-lap.
- `reference_lap_s`: median of the clean laps up to 5 laps before the in-lap and 5 laps after the out-lap.
- **`time_lost_s` = `in_and_out_laps_s` − 2 × `reference_lap_s`**: the time lost against two normal laps, which is what decides an undercut. It is larger than the pit lane time minus the time to drive past the pit lane, because the in- and out-laps include slowing down, cold tyres and traffic.
- `neutralized`: a safety car, VSC or red flag during the in- or out-lap; such a stop costs much less, and is not comparable with the others. `red_flag`: tyres changed while the race was stopped.

## pit_cycle

Undercut or overcut between `driver` and `rival`: `driver_stop` (1 by default) against `rival_stop` (the rival's stop closest in laps if omitted).

- `lap_before`: the lap before the first of the two in-laps; `lap_after`: the out-lap of the later stopper. Both stops happen in between.
- `gap_before_s`, `gap_after_s`, `gained_s` (positive: the driver gained), positions before and after.
- `kind`: `undercut` if the driver stopped first, `overcut` if later, `same_lap`.
- `driver_passed_rival` / `rival_passed_driver`: the order at the line changed.
- `neutralized`: a safety car, VSC or red flag between the two laps; the stops were cheap and the gain says little about strategy.

Limits: the gain also includes what happened on track between the stops (traffic, a battle, a mistake). The tool measures the result of the pit cycle, not its cause; the debrief says which.

## neutralizations

Safety car, VSC and red flag periods of a session, from the race control messages.

- Safety car: from "SAFETY CAR DEPLOYED" to "SAFETY CAR IN THIS LAP" (racing resumes on the next lap).
- VSC: from "VIRTUAL SAFETY CAR DEPLOYED" or "VSC DEPLOYED" to "... ENDING".
- Red flag: from the red flag to "STANDING START", "ROLLING START", or a safety car deployed to lead the restart. A red flag closes a safety car still open.
- The chequered flag closes anything still open (`ended_by_finish`).

Output: per period, `kind`, `start_lap`, `end_lap`, `start_utc`, `end_utc`, `duration_s`; then the counts.

Limits: a start behind the safety car (wet race) has no "DEPLOYED" message, so those laps are not a period; the laps' `track_status` still shows them. The message forms were checked on 2024 to 2026.

## Tests

- `tests/unit/test_tools.py`: a synthetic 10-lap race whose every number is computed by hand, plus the error messages and the tool calling schemas.
- `tests/integration/test_tools_reference.py`: four real races against public race reports. The 2024 Hungarian GP (Norris's undercut on Piastri at the second stops; Piastri wins by 2.141 s), the 2024 São Paulo GP (VSC, safety car, red flag, rolling restart, safety car), the 2025 Australian GP (three safety cars) and the 2025 Italian GP (Norris's 5.9 s stop lets Piastri out ahead; low tyre wear).
