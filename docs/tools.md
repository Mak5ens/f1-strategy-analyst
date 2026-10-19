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

## find_race

The round, the sessions in the data and the drivers (code, name, team, in finishing order) of a Grand Prix of a season, named in English or French ("Italian Grand Prix", "Italie", "Monza"). The other tools take a round and three-letter codes, a question gives names: a model asked for the round of the 2025 Italian Grand Prix answered 14, for the 16th. A name it does not know gets the list of the season's Grands Prix.

## session_result

The official classification of a race, sprint, qualifying or sprint qualifying (`session` `R`, `S`, `Q`, `SQ`): position (a number, or `R` retired...), driver, name, team, grid (races), status, gap to the winner (lead lap only), the winner's race time, laps, Q1 to Q3 times (qualifying); and the fastest lap not deleted by the stewards. It reads the `results` table: no computation, but the numbers a debrief quotes most.

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
- `neutralized`: a safety car, VSC or red flag during the in- or out-lap; such a stop costs much less, and is not comparable with the others. `red_flag`: tyres changed while the race was stopped; such a stop has no `time_lost_s`, since its two laps hold the stoppage (a debrief once quoted 1,539 s "lost" at São Paulo 2024).

## pit_cycle

Undercut or overcut between `driver` and `rival`: `driver_stop` (1 by default) against `rival_stop` (the rival's stop closest in laps if omitted).

- `lap_before`: the lap before the first of the two in-laps; `lap_after`: the out-lap of the later stopper. Both stops happen in between.
- `gap_before_s`, `gap_after_s`, `gained_s` (positive: the driver gained), positions before and after.
- `first_to_stop`, `ahead_before`, `ahead_after`, and `outcome` from the side of whoever came out ahead: `undercut_worked` (the first to stop passed the other), `overcut_worked` (the later one did), `same_lap_swap`, `order_held`. `summary` says it in one sentence with the names and the gain. A field from the `driver`'s side only (the former `kind`) led a model to call the winner's undercut an overcut whenever it asked about the loser (LAB-201).
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

## key_moments

The moments that made a race (LAB-204), found and ranked by code: the "top 5" debrief tells them. Not in the baseline's catalog: the agent's theme adds it beside `penalties`, `race_strategies` and `race_weather`.

| Kind | What code finds | Measure |
| -- | -- | -- |
| `start` | Places gained or lost between the grid and the end of lap 1 (2 or more; a pit lane start is left out) | places |
| `overtakes` | Passes on track: at the end of lap n, a driver is ahead of one who was ahead at the end of lap n-1, neither stopped on either lap, and the lap saw no safety car, VSC or red flag | passes, their laps and who was passed |
| `pit_cycle` | Two drivers who stopped on different laps, within 15 laps, without a neutralization, and swapped places (`pit_cycle` with `undercut_worked` or `overcut_worked`) | seconds gained on the rival |
| `neutralized_stop` | A stop under a safety car or VSC that cost 5 s less than the median green flag stop | seconds saved, places before and after the neutralization |
| `slow_stop` | A stop that cost 5 s more than the stops made within 3 laps under the same conditions (the race's when fewer than 3): a slow stop, an off on the in-lap | extra seconds, places before and after |
| `strategy` | A driver whose number of stops differs from most drivers', and who gained 2 places or more from the grid. A tyre change under a red flag is not a stop: at São Paulo 2024, Verstappen made none before the red flag | stops, usual stops, places from the grid |
| `setback` | 2 places or more lost on one green flag lap without a stop: an off, a spin, a problem | places |
| `retirement` | A driver out of the race | the place held on the last lap |

**Ranking** (an editorial rule, never a model's): a moment is worth the championship points it moved, as if the race had ended there (`Worth`), plus a tenth of a point per place, which orders the moments outside the points and breaks ties. A pass for the lead is worth 7.1; a gain from 15th to 10th, 1.5. A slow stop counts the points of the places it lost, times the share of the extra time in the stop's cost. A retirement is worth the points of the place held, plus a tenth per car behind. At most 2 moments of a kind and 2 of a driver among the 5.

Checked on the reference races: Hungary 2024 gives Norris losing the lead at the start, Piastri passing him back on lap 68 and Norris's undercut on lap 45; Australia 2025, Piastri's off on his in-lap (92 s lost, 2nd to 15th) first; São Paulo 2024, Verstappen and Gasly changing tyres for free under the red flag.

Limits: the data says how many places or seconds, not why (the reading says so). A position handed back by team order (Hungary 2024, lap 68) is a pass like any other. Penalties are not moments yet: whether one changed the result needs the classification before it, which the data does not hold.

## Strategy simulation (LAB-213)

`f1.tools.simulation.simulate_strategy`, behind the GP page's « Simulateur » tab (`GET /races/{season}/{round}/simulation?driver=&stops=&rival=`): the same stops on other laps, each stint keeping its tyres. Not a tool of the agent, so its refusals are in French.

- **By difference**: it projects the difference between the strategy asked and the one raced, lap by lap, and adds it to the times the driver set. What both share (the driver's level, the fuel, the laps under a safety car, the race's traffic) cancels out.
- **A lap under a neutralization**: no difference, since the safety car set the lap.
- **Any other lap**: the difference of the two stints' fuel-corrected lines at that lap, from `degradation.fit`: lap time = intercept + degradation × tyre age − 0.06 × (lap − 1).
- **The stops' cost moves with them**: the median of the driver's green-flag stops (`pit_stop_loss`), or the median of the race's stops under a neutralization when the new in- or out-lap is neutralized. With none measured, it refuses.
- **Refused**: a stint under 5 clean laps (no line), a number of stops other than the one raced, in-laps out of order.

**Validation** (`just simulation-validate 2025`, `f1.evals.simulation`, report in `evals/reports/simulation-2025.json`): on 748 race stints of 2025 with at least 15 clean laps, the line fitted on the first 60 % of the clean laps projects the following ones. The table gives the error on the time of the laps extended.

| Laps extended | Median error | 90 % under | Bias |
| --: | --: | --: | --: |
| 1 to 5 | 0.8 s | 3.1 s | −0.2 s |
| 6 to 10 | 3.1 s | 8.3 s | −0.9 s |
| 11 to 20 | 5.7 s | 15.4 s | −0.9 s |

The bias is negative: tyres wear faster late in a stint than a line says, so a longer stint is projected too fast. The page shows the error of the longest extension next to each projection. It says the model cannot conclude when the difference is smaller than the median error.

## Duel of two drivers (LAB-212)

Not a tool of the agent: `f1.duels.duel` computes the duel page's numbers (`GET /duels`), from two queries on the season (results, then the two drivers' race laps). Every gap is the first driver's time less the second's: negative, the first was faster.

- **Qualifying**: the best laps of the last part both reached (Q3, else Q2, else Q1), from the results. The one ahead is the one with the better place. When the results have the places but not the times (Miami 2025 in the lake), the places count and the gap stays empty.
- **Race**: the places at the end (every driver who started, classified or not) and the points of the weekend, races and sprints, so that they add up to the championship's. A race neither finished classified (both retired, both disqualified) counts for nobody.
- **Pace**: the median gap on the laps both covered clean, the same lap of the same race (`is_clean`: not lap 1, no stop, green flag all lap, not deleted, a lap time). Under 5 such laps, no pace.
- **Season**: who was ahead how often in qualifying and in the race, the points, and the medians of the qualifying and pace gaps.

A round a driver did not race has no gap there, rather than one made up.

## Tests

- `tests/unit/test_tools.py`: a synthetic 10-lap race whose every number is computed by hand, plus the error messages and the tool calling schemas. `tests/unit/test_moments.py`: a synthetic 6-lap race for `key_moments`, each score computed by hand.
- `tests/integration/test_tools_reference.py`: four real races against public race reports. The 2024 Hungarian GP (Norris's undercut on Piastri at the second stops; Piastri wins by 2.141 s), the 2024 São Paulo GP (VSC, safety car, red flag, rolling restart, safety car), the 2025 Australian GP (three safety cars) and the 2025 Italian GP (Norris's 5.9 s stop lets Piastri out ahead; low tyre wear).
