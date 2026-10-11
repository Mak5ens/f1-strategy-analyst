# FIA corpus

The retrieval pipeline answers rulebook questions ("could this penalty be served at the pit stop?") from two kinds of FIA documents, indexed in Qdrant by `just corpus`.
This page covers the ingestion (LAB-145); the search on top of it (query rewriting, reranking, abstention) is LAB-186.

```bash
just corpus 2025                              # regulations and stewards' decisions of a season
just corpus 2024 2025 2026 --regulations-only
just corpus 2026 --decisions-only --refresh   # fetch the FIA's document lists again (new decisions)
```

## Sources

| Document | Where | What is indexed |
| -- | -- | -- |
| Sporting regulations | [fia.com, Formula 1 regulations](https://www.fia.com/regulation/category/110) | Per season, the **last issue** published: 2024 Issue 7, 2025 Issue 5, 2026 Section B Issue 9 at the time of writing |
| Stewards' decisions | [fia.com, documents of each Grand Prix](https://www.fia.com/documents/championships/fia-formula-one-world-championship-14) | Every `Decision` and `Infringement` document of the season's Grands Prix, tests excluded; not the classifications, summons, notes or deleted lap time lists |

The documents belong to the FIA. They are downloaded to `.cache/fia/` (ignored by Git) and never committed, and only their text, cut into chunks, goes into the local index.
fia.com's `robots.txt` asks for 10 seconds between requests: the client waits that long between any two calls and gives its name and the repository's URL as user agent.
Each document is downloaded once: the first run over three seasons takes a few hours, later runs only fetch what is new.

The list of a Grand Prix's documents is loaded by the page with Drupal AJAX (`POST /decision-document-list/ajax/<event>`); the client makes the same call.

## Structure: parents and children

Chunks follow the structure of the text, never a fixed size.

**Regulations.** Two layouts:

| Seasons | Parent (context for the model) | Child (unit of search) |
| -- | -- | -- |
| 2024, 2025 | Article: `55) SAFETY CAR` | Paragraph: `55.1`, `55.2`... |
| 2026 | Section: `B5.13 Safety Car (SC)`, under `ARTICLE B5: ...` | Paragraph: `B5.13.1`... |

- Running headers and footers are removed: a line found on 60% of the pages or more (digits ignored) is not content.
- The contents pages and the appendices (entry form, fees, podium ceremony) are skipped.
- A paragraph longer than 1,400 characters (the `embed` model reads 512 tokens) is cut at its lettered items, then at sentences: keys `30.5#1`, `30.5#2`.
- A parent longer than 8,000 characters is cut into groups of consecutive paragraphs (`10~1`, `10~2`): the context sent to the model stays bounded.
- Each child starts with where it comes from, which helps both the search and the reader of a citation: `2025 Formula 1 Sporting Regulations, Article 55.1, Safety car:`.
- Paragraph numbers must go up: a line of text that starts with one ("10.1 which...") stays in the paragraph it belongs to.

**Stewards' decisions.** The parent is the whole decision, without the standard paragraph on the right of appeal and the stewards' names. Children:

- `summary`: who (car, driver, team), session, fact, infringement and decision: answers "what penalty did X get";
- `reason#1`...: the stewards' reasons: answers "why".

A decision not in the usual form (on a whole session, a correction) is kept as text.

## Metadata

| Field | Regulations | Decisions |
| -- | -- | -- |
| `season`, `doc_type`, `doc_id`, `url`, `document_title` | yes | yes |
| `issue`, `published` | issue number and date | date of the decision |
| `article`, `parent_article`, `title`, `page` | `55.1`, `55`, `Safety car`, page of the PDF | |
| `grand_prix`, `round` | | `Italian Grand Prix`, `16` (from FastF1's schedule, to join the race data) |
| `session`, `car_number`, `driver_name`, `competitor`, `penalty` | | from the form |
| `cited_articles` | | `33.4 (Sporting Regulations)`, `12.2.1 i) (International Sporting Code)` |
| `content_hash` | yes | yes |

Payload indexes on `season`, `doc_type`, `grand_prix`, `round`, `article` and `doc_id` make filters fast: a question about 2026 is filtered on `season = 2026` before any vector is compared, so it can never get an article of 2025.

## Index

Two Qdrant collections, built by `core.retrieval.index.HybridIndex`:

- `fia_chunks`: one point per child, with two named vectors: `dense` (768 dimensions, the gateway's `embed` alias, for meaning) and `bm25` (sparse, computed locally with fastembed, for exact terms such as "55.1", "VSC" or "DRS"; Qdrant applies the IDF at search time);
- `fia_parents`: one point per parent, no vectors, fetched by id from a child's `parent_id`.

Point ids derive from the document and the chunk key (`sporting-regulations-2025` / `55.1`), so they stay the same from one issue of the regulations to the next.
`content_hash` covers the text, the embedding models and an index version: on each run, only chunks whose hash changed are embedded, the others only get their payload updated (a new issue number), and chunks that disappeared are deleted.
Rerunning `just corpus` without change computes no embedding.

## Choices and limits

- **No LlamaIndex.** The structure comes from the FIA's numbering, which a generic PDF reader does not know, and the index needs control over ids, hashes and named vectors for the incremental sync and for the ablation study of LAB-186. pypdf extracts the text; the rest is about 400 lines of code, tested.
- **One issue per season.** The last issue is the rulebook as it stood at the end of the season; a change during the season (2024: seven issues) is not visible. Indexing every issue with its validity dates is possible on the same structure (filter on the issue in force on the race date).
- **The International Sporting Code** and the Race Director's event notes are cited by decisions but not indexed.
- **Tables** of the regulations (component allocations) come out of the PDF as loose cells: searchable by their words, not readable as tables.
- The list of a Grand Prix's documents is cached: run with `--refresh` after a race weekend to pick up the latest decisions.
