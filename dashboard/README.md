# AIVA Bench dashboard

`index.html` is a self-contained page: open it directly, serve it with
GitHub Pages, or run the local server for editing.

Two sections: **Variant Classification** (everything below) and **Variant
Ranking** (`#ranking`, an empty state until ranking results are added).

Variant Classification has three tabs:

- **Leaderboard**: F1 by expert class and disease category with models
  grouped by section (AIVA, Agents, Automated), the accuracy-against-safety
  scatter, and the pairwise agreement heatmap. "Choose models" filters all three.
- **Confusion matrices**: per model, with precision and recall by class.
- **ACMG criteria**: share of variants citing each criterion, pathogenic
  evidence above benign evidence.

**Download variants (CSV)** in the header exports every benchmark variant
(gene, HGVS, variant key, disease, category, expert panel, expert
classification, criteria and points) with two columns per model: its
classification and the ACMG criteria it cited, as the model wrote them
(strength modifiers kept, e.g. `PM2_Supporting`). Models imported in the
browser are included; their criteria come from `aiva_criteria`, `criteria`,
or Claude Code's `criteria.met`.

## Adding a model

1. Put the results file in the repository (AIVA JSONL output, or a Claude
   Code JSON array).
2. Add one line to `models.tsv` (tab-separated):

   | column | example |
   |---|---|
   | key | `aiva_gpt_sol` |
   | name | `GPT-6.1 Sol` (the model name only; the section shows how it was run) |
   | provider | `Anthropic`, `OpenAI`, `Google`, `Rule-based` or `Other` |
   | method | `AIVA agent` |
   | path | `Results_GPT_Sol_Analysis/sol_full.jsonl` |
   | format | `jsonl`, `json_array`, or `auto` (by extension) |
   | color | optional; empty takes the next unused colour of the model palette |
   | color_dark | optional dark-theme colour; empty takes the palette's pair for `color` |
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

`data/aiva_bench_variants_v1_input.jsonl` is the classifier input for the same
2,894 variants (`python scripts/build_variant_input.py`): id, variation,
variation_original, variant_key, gene_symbol, disease, mode_of_inheritance,
genome_build (GRCh37) and expert_panel, with no expert classification or
criteria. Run a new model on it, then add the results file to `models.tsv`.

## Local server

```bash
python dashboard/server.py
```

Serves the page at http://localhost:8050 and enables the Models dialog
(remove and restore write `status` in `models.tsv`), "Import results" with
"Save to the repository" (writes `imported_results/` and a `models.tsv` row),
and "Rebuild data". Each change rebuilds `index.html`; commit and push to
publish it.

## Model colours

Each model has one colour, used in every chart, table, legend and swatch. The
colours come from the Wes Anderson palettes (`PALETTE` in `registry.py`, from
the wesanderson R package) and are fixed per model in `models.tsv`; models
added later, including browser imports, take the next unused palette entry.
In the dark theme, colours below 3:1 contrast on the dark surface use a
lighter step of the same hue.

Models are named without their method, so a model run through AIVA and
through Claude Code shares a name (e.g. Opus 5.5). The leaderboard's section
columns tell them apart; elsewhere, where both appear together, the method is
added in brackets, e.g. "Opus 5.5 (Claude Code)".

## Theme and fonts

Colours and type follow mamidi.ai: Inter and Source Code Pro, deep green
text, a beige page and an orange accent; the dark theme uses the site's deep
green. The fonts' Latin subsets are in `fonts/` (SIL Open Font License 1.1,
licence texts alongside) and `generate_html.py` embeds them, so the page
works offline and exported SVG and TIFF figures keep the same type. The
Mamidi Health emblem in the header and browser tab comes from `assets/`.
