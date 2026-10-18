# Design direction

Decided with the product owner on 2026-10-15, from screenshots of formula1.com: **the style of the official site, made smoother**, dark only. Animations come with milestone 6.

## What we take

| From formula1.com | Here |
| -- | -- |
| Near-black blue-grey page, black bands for navigation | `--background` #15151e, `--band` #0b0b10 (header, hero, tables, footer) |
| Red as the only accent: active tab underline, main button, thin rules | `--primary` #e8202f |
| Heavy, wide, upper-case titles | `.display`: Archivo at width 125, weight 800 |
| Big numbers under small labels (driver statistics) | `.figures` (tabular numbers) for every timing, gap and lap |
| Results tables on a black panel, small upper-case headers, thin rules, a team dot | `PublishedTable` |
| Cards and hero bands in a team's colour | `DebriefCard`: the team's colour fading into the card, from the API's `colour` |
| The driver's number, huge, behind the photo | The round number, huge and faint, where a photo would be |
| The red double slash | `.slash`, the app's signature, red or in the team's colour |
| Tyre strategy charts, the fastest lap in purple | `StrategyChart`: the compounds' broadcast colours (`--soft`, `--medium`, `--hard`...), a used set striped; `--fastest` |

## What "smoother" means

- No halftone or hatching everywhere: one faint stripe pattern in the home hero, soft gradients elsewhere.
- Rounded corners (12 px), more space between sections, short transitions on hover.

## What we never take

The repo is public (CLAUDE.md): no F1, FIA or team logos, no Formula1 Display font, no driver photos or car images. Team colours are data, used to tell teams apart (`src/f1/display.py`, FastF1's plotting colours). Fonts are Archivo and Inter, both under the SIL Open Font License, served by `next/font`.

## Conventions

- Colours only through the tokens of `web/src/app/globals.css`; a team's colour through the `--team` variable.
- Texts only in `web/src/messages/fr.ts`.
- Check every screen at 390 px wide as well as 1440 px: the header puts its navigation on a second row, tables scroll sideways.
