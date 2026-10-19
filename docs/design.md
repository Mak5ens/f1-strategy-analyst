# Design direction

Decided with the product owner on 2026-10-15, from screenshots of formula1.com: **the style of the official site, made smoother**, dark only. The design system (LAB-188) set it down: principles, tokens checked for contrast, motion, and a reference page, `/design` (not in the navigation, not indexed).

## Principles

1. **The data first.** A number, a line or a table always holds the main place; decoration (stripes, the faint giant number, gradients) stays behind, under 5 % opacity.
2. **One accent colour.** Red marks the action and the active state. Every other colour is data: a team, a compound, a flag, the fastest lap.
3. **Speed and precision.** Wide titles leaning with the slash, tabular figures that line up, short and sharp motion, never over 0.7 s.
4. **Readable by everyone.** Every text reaches WCAG AA on its surface, measured by `web/src/app/tokens.test.ts`; every chart has its keyboard reading and its table; motion stops when the system asks for less.
5. **No brand element.** No F1, FIA or team logo, font or image: team colours are data, nothing more.

## What we take

| From formula1.com | Here |
| -- | -- |
| Near-black blue-grey page, black bands for navigation | `--background` #15151e, `--band` #0b0b10 (header, hero, tables, footer) |
| Red as the only accent: active tab underline, main button, thin rules | `--primary` #dd1c2b as a fill (white on it 4.9:1), `--primary-text` #ff5a66 as text on the dark surfaces (4.8:1 or more on each) |
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

## Contrast

`web/src/app/tokens.test.ts` reads `globals.css` and measures every text token (foreground, muted, red text, success, warning, destructive, fastest) on every surface (background, band, surface, raised), and the texts on fills (white on red, white on soft and wet tyres, black on medium, hard, intermediate and destructive): each must reach 4.5:1. The red of 2026-10-15, #e8202f, did not as text (3.3:1 on a raised surface) nor under white (4.49:1): the fill went a shade darker, and red text got its own lighter token. The same test fails when a component holds a colour of its own (#rrggbb, rgb(), a fixed white or black).

## Motion

Tokens `--ease-out`, `--duration-fast` (150 ms), `--duration` (260 ms), `--duration-draw` (700 ms). Two motions: `.enter`, a tab's panel or a page's content rising 6 px as it fades in; `.draw`, a highlighted line of a chart drawn from its first lap or round to its last (an SVG path with `pathLength="1"`; a dashed line is not drawn). Hovers fade their colours. Under `prefers-reduced-motion: reduce`, every animation and transition ends at once.

## Conventions

- Colours only through the tokens of `web/src/app/globals.css`, checked by `tokens.test.ts`; a team's colour through the `--team` variable; red text is `text-primary-text`, red fills `bg-primary`.
- Texts only in `web/src/messages/fr.ts`.
- Check every screen at 390 px wide as well as 1440 px: the header puts its navigation on a second row, tables scroll sideways.
