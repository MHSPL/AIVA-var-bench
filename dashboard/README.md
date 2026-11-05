# AIVA Bench dashboard

`index.html` is a self-contained page: open it directly, serve it with
GitHub Pages, or run the local server for editing.

Two sections: **Variant Classification** (everything below) and **Variant
Ranking** (`#ranking`, an empty state until ranking results are added).

## Adding a model

1. Put the results file in the repository (AIVA JSONL output, or a Claude
   Code JSON array).
2. Add one line to `models.tsv` (tab-separated):

   | column | example |
   |---|---|
   | key | `aiva_gpt_sol` |
   | name | `AIVA-GPT-Sol` |
   | provider | `Anthropic`, `OpenAI`, `Google`, `Rule-based` or `Other` |
   | method | `AIVA agent` |
   | path | `Results_GPT_Sol_Analysis/sol_full.jsonl` |
   | format | `jsonl`, `json_array`, or `auto` (by extension) |
   | color | optional; empty takes the provider's next colour |
   | color_dark | optional lighter colour for the dark theme |
   | status | `active`, or `removed` to hide the model |
   | section | leaderboard section: `aiva`, `agent` (Claude Code, Antigravity, …) or `automated` (rule-based); empty derives it |

3. Rebuild and commit:

   ```bash
   python scripts/update_dashboard.py
   git add dashboard/models.tsv dashboard/index.html <results file>
   ```

`.gitignore` excludes `*.json` and `*.jsonl` by default; add a `!path`
exception for the new results file, or commit it with `git add -f`.

## Benchmark variant set

The dashboard is built on the variants listed in
`data/aiva_bench_variants_v1.tsv` (2,894 of the 8,387 cohort variants), written
once by `scripts/build_variant_set.py` from the reference classifiers named in
its header. `build_data.py` restricts every view to this list, and browser
imports are scored against it. The list stays fixed as models are added;
delete the file to build on the whole cohort, or write a new version on purpose.

## Local server

```bash
python dashboard/server.py
```

Serves the page at http://localhost:8050 and enables the Models dialog
(remove and restore write `status` in `models.tsv`), "Import results" with
"Save to the repository" (writes `imported_results/` and a `models.tsv` row),
and "Rebuild data". Each change rebuilds `index.html`; commit and push to
publish it.

## Theme and fonts

Colours and type follow mamidi.ai: Inter and Source Code Pro, deep green
text, a beige page and an orange accent; the dark theme uses the site's deep
green. The fonts' Latin subsets are in `fonts/` (SIL Open Font License 1.1,
licence texts alongside) and `generate_html.py` embeds them, so the page
works offline and exported SVG and TIFF figures keep the same type. The
Mamidi Health emblem in the header and browser tab comes from `assets/`.
