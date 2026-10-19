# Changelog

## [0.6.0](https://github.com/Mak5ens/f1-strategy-analyst/compare/v0.5.0...v0.6.0) (2026-10-19)


### Features

* **agent:** debriefs prepared after each race, with its top 5 moments (LAB-204) ([#31](https://github.com/Mak5ens/f1-strategy-analyst/issues/31)) ([c5174c4](https://github.com/Mak5ens/f1-strategy-analyst/commit/c5174c4174849136711a84b1c3b4ea4349239209))
* **agent:** debriefs that explain the race, their meaning checked (LAB-207) ([#30](https://github.com/Mak5ens/f1-strategy-analyst/issues/30)) ([d0ea883](https://github.com/Mak5ens/f1-strategy-analyst/commit/d0ea883e08925e7f499a08443972da474066892d))
* **agent:** questions on a published debrief, answered and checked by code (LAB-205) ([#28](https://github.com/Mak5ens/f1-strategy-analyst/issues/28)) ([b938f1b](https://github.com/Mak5ens/f1-strategy-analyst/commit/b938f1b2bae2abd61b94719b67999c93af53f6f7))
* **evals:** the agent against the baseline, and the review's acceptance rate (LAB-154) ([#32](https://github.com/Mak5ens/f1-strategy-analyst/issues/32)) ([6f6acae](https://github.com/Mak5ens/f1-strategy-analyst/commit/6f6acae8f89f6e5bee9ed847357cc95470b33552))
* **web:** a debrief's point opens the chart of the numbers it cites (LAB-189) ([#37](https://github.com/Mak5ens/f1-strategy-analyst/issues/37)) ([bf96cc6](https://github.com/Mak5ens/f1-strategy-analyst/commit/bf96cc694fcd20ca2334917ff68c7c306b092aa7))
* **web:** debrief API and the analyst's screens (LAB-152) ([#24](https://github.com/Mak5ens/f1-strategy-analyst/issues/24)) ([d5065a4](https://github.com/Mak5ens/f1-strategy-analyst/commit/d5065a4f039b948f06e380d02ba270fca99c13cc))
* **web:** duel of two drivers over a season, measured by code (LAB-212) ([#39](https://github.com/Mak5ens/f1-strategy-analyst/issues/39)) ([c6760b8](https://github.com/Mak5ens/f1-strategy-analyst/commit/c6760b8ec505a50aed130d0685d96c5bcf2004a7))
* **web:** free question on the home page, routed by code (LAB-206) ([#29](https://github.com/Mak5ens/f1-strategy-analyst/issues/29)) ([ac53121](https://github.com/Mak5ens/f1-strategy-analyst/commit/ac53121b82329164e8431e333ed33d3c6d502c02))
* **web:** Grand Prix pages and season calendar read from the lake (LAB-202) ([#25](https://github.com/Mak5ens/f1-strategy-analyst/issues/25)) ([acd2f7f](https://github.com/Mak5ens/f1-strategy-analyst/commit/acd2f7fc9236da44f7ed5f20dc5eb0a13b27288d))
* **web:** Next.js front skeleton with a client generated from the API's OpenAPI, and ADR-026 (LAB-187) ([#22](https://github.com/Mak5ens/f1-strategy-analyst/issues/22)) ([568e795](https://github.com/Mak5ens/f1-strategy-analyst/commit/568e7951ea99e19592eba2bf97eb2b7327f4bb30))
* **web:** strategy simulator, the same stops on other laps, with its measured error (LAB-213) ([#40](https://github.com/Mak5ens/f1-strategy-analyst/issues/40)) ([c129915](https://github.com/Mak5ens/f1-strategy-analyst/commit/c1299155f99a82bf7cb148aa3e89eb3a906a82e0))
* **web:** the race lap by lap, positions and gaps charts (LAB-189) ([#34](https://github.com/Mak5ens/f1-strategy-analyst/issues/34)) ([b379e29](https://github.com/Mak5ens/f1-strategy-analyst/commit/b379e2919525a590baa20ea6558db5161ba022c2))
* **web:** the race's pace per stint and its chronology linked to the FIA's texts (LAB-189) ([#36](https://github.com/Mak5ens/f1-strategy-analyst/issues/36)) ([eb7cb1c](https://github.com/Mak5ens/f1-strategy-analyst/commit/eb7cb1c02446934f49eacf6022ab33f8516ca713))


### Bug Fixes

* **web:** tyre compounds said by their letter and name, not by colour alone (LAB-189) ([#38](https://github.com/Mak5ens/f1-strategy-analyst/issues/38)) ([6310063](https://github.com/Mak5ens/f1-strategy-analyst/commit/6310063d6d43e8e98886b796c62b46b125acdb05))

## [0.5.0](https://github.com/Mak5ens/f1-strategy-analyst/compare/v0.4.0...v0.5.0) (2026-10-15)


### Features

* **agent:** controlled LangGraph debrief agent with three human stops, and ADR-025 (LAB-151) ([#21](https://github.com/Mak5ens/f1-strategy-analyst/issues/21)) ([c99695a](https://github.com/Mak5ens/f1-strategy-analyst/commit/c99695a8407ce674d08f460ea3874f26dc9789bf))
* **evals:** model comparison on the test set, and ADR-012 (LAB-150) ([#19](https://github.com/Mak5ens/f1-strategy-analyst/issues/19)) ([0f6e699](https://github.com/Mak5ens/f1-strategy-analyst/commit/0f6e69972ad3507b804cca1f0d5af851faac4ae3))

## [0.4.0](https://github.com/Mak5ens/f1-strategy-analyst/compare/v0.3.0...v0.4.0) (2026-10-15)


### Features

* add the evaluation harness and measure the baseline on the test set (LAB-148) ([#13](https://github.com/Mak5ens/f1-strategy-analyst/issues/13)) ([9a5dce8](https://github.com/Mak5ens/f1-strategy-analyst/commit/9a5dce8d49021a389fc8b7cb94064a391b476d92))
* **evals:** rich and correct strategy references (LAB-201) ([#15](https://github.com/Mak5ens/f1-strategy-analyst/issues/15)) ([91325b7](https://github.com/Mak5ens/f1-strategy-analyst/commit/91325b77bc4c41414834d674312147ecfd9a1bf6))

## [0.3.0](https://github.com/Mak5ens/f1-strategy-analyst/compare/v0.2.0...v0.3.0) (2026-10-14)


### Features

* add the naive reference system with tools and checked numbers (LAB-147) ([#12](https://github.com/Mak5ens/f1-strategy-analyst/issues/12)) ([f300517](https://github.com/Mak5ens/f1-strategy-analyst/commit/f3005173bd64343a9832ee4ff41943290c08126f))
* build the evaluation dataset, 411 cases in seven families with their origin (LAB-146) ([#10](https://github.com/Mak5ens/f1-strategy-analyst/issues/10)) ([7582556](https://github.com/Mak5ens/f1-strategy-analyst/commit/75825560b8e4e5af400fe66c556ce1b43a3daa81))

## [0.2.0](https://github.com/Mak5ens/f1-strategy-analyst/compare/v0.1.0...v0.2.0) (2026-10-14)


### Features

* add deterministic race analysis tools (LAB-144) ([#5](https://github.com/Mak5ens/f1-strategy-analyst/issues/5)) ([0c5ed2e](https://github.com/Mak5ens/f1-strategy-analyst/commit/0c5ed2e796920d06a3ffc3132f3e05ffe8608edb))
* answer questions on the FIA rules with a production retrieval pipeline (LAB-186) ([#7](https://github.com/Mak5ens/f1-strategy-analyst/issues/7)) ([3981562](https://github.com/Mak5ens/f1-strategy-analyst/commit/398156200b03d6f69e2a86e03db0e0f60f8ecaac))
* index the FIA regulations and stewards' decisions in Qdrant (LAB-145) ([#6](https://github.com/Mak5ens/f1-strategy-analyst/issues/6)) ([adcd772](https://github.com/Mak5ens/f1-strategy-analyst/commit/adcd772216743aa6a711061b28c8243663c17ed1))
* ingest race data from FastF1, OpenF1 and Jolpica-F1 into a Parquet lake on S3 (LAB-143) ([#4](https://github.com/Mak5ens/f1-strategy-analyst/issues/4)) ([50b4292](https://github.com/Mak5ens/f1-strategy-analyst/commit/50b42924a174f138f8a04171233f16c255ee78a1))
* set up the Python project with a reusable core and the F1 theme (LAB-142) ([#3](https://github.com/Mak5ens/f1-strategy-analyst/issues/3)) ([ed60988](https://github.com/Mak5ens/f1-strategy-analyst/commit/ed609885397f6996939bd94e4db858d03f21dc2c))
* summarize every session of a season as jobs on the platform's queue (LAB-196) ([#8](https://github.com/Mak5ens/f1-strategy-analyst/issues/8)) ([140a6c4](https://github.com/Mak5ens/f1-strategy-analyst/commit/140a6c405fa065ad8248437d0f69f10123fc20c8))
