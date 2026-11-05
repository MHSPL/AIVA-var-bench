#!/usr/bin/env python3
"""
Generates the standalone benchmark dashboard (dashboard/index.html).

Reads dashboard/data/benchmark_data.json (written by build_data.py). If that
file is absent, the dataset already embedded in the current index.html is
reused, so the page can be restyled without re-running every model.

The ground-truth label for every cohort variant is also embedded so that
imported result files are scored against the full cohort in the browser.
"""

import base64
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from config import CLASSIFICATION_LABELS
from scripts.metrics import normalize_classification

DATA_FILE = REPO_ROOT / "dashboard" / "data" / "benchmark_data.json"
UNIFIED_FILE = REPO_ROOT / "data" / "erepo_bias_intervar_merged.jsonl"
HTML_OUT = REPO_ROOT / "dashboard" / "index.html"
TEMPLATE_FILE = REPO_ROOT / "dashboard" / "template.html"

DATA_MARKER = "window.BENCHMARK_DATA = "

# Latin subsets of Inter and Source Code Pro (SIL OFL 1.1, see fonts/), embedded
# so the page works offline and exported figures keep the same type.
FONTS_DIR = REPO_ROOT / "dashboard" / "fonts"
FONT_FILES = [("Inter", "Inter-latin.woff2"), ("Source Code Pro", "SourceCodePro-latin.woff2")]
LATIN_RANGE = ("U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, "
               "U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, "
               "U+2215, U+FEFF, U+FFFD")


def load_benchmark_data() -> dict:
    if DATA_FILE.exists():
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    if HTML_OUT.exists():
        html = HTML_OUT.read_text(encoding="utf-8")
        start = html.find(DATA_MARKER)
        if start != -1:
            start += len(DATA_MARKER)
            data, _ = json.JSONDecoder().raw_decode(html, start)
            print(f"{DATA_FILE} not found; reusing dataset embedded in {HTML_OUT.name}")
            return data
    sys.exit(f"No dataset found. Run dashboard/build_data.py first (expected {DATA_FILE}).")


def load_ground_truth_index() -> dict:
    """Map variant id -> index into CLASSIFICATION_LABELS, for the benchmark variant set."""
    from dashboard.build_data import read_variant_set
    variant_set = read_variant_set()
    index = {}
    if not UNIFIED_FILE.exists():
        return index
    with open(UNIFIED_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            if variant_set is not None and item["id"] not in variant_set:
                continue
            label = normalize_classification(item.get("classification", ""))
            if label in CLASSIFICATION_LABELS:
                index[item["id"]] = CLASSIFICATION_LABELS.index(label)
    return index


def font_faces_css() -> str:
    rules = []
    for family, name in FONT_FILES:
        path = FONTS_DIR / name
        if not path.exists():
            continue
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        rules.append(
            f"@font-face{{font-family:'{family}';font-style:normal;font-weight:400 700;font-display:swap;"
            f"src:url(data:font/woff2;base64,{b64}) format('woff2');unicode-range:{LATIN_RANGE}}}"
        )
    return "\n".join(rules)


def data_uri(path: Path, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii") if path.exists() else ""


def to_script_json(obj) -> str:
    # Escape "</" so embedded strings can never close the <script> element.
    return json.dumps(obj, separators=(",", ":")).replace("</", "<\\/")


def main():
    data = load_benchmark_data()
    data["ground_truth_index"] = load_ground_truth_index()

    template = TEMPLATE_FILE.read_text(encoding="utf-8")
    html = template.replace("__FONT_FACES__", font_faces_css())
    assets = REPO_ROOT / "dashboard" / "assets"
    html = html.replace("__MAMIDI_LOGO__", data_uri(assets / "mamidi-logo.png", "image/png"))
    html = html.replace("__MAMIDI_ICON__", data_uri(assets / "mamidi-icon.png", "image/png"))
    html = html.replace("__BENCHMARK_DATA__", to_script_json(data))

    HTML_OUT.write_text(html, encoding="utf-8")
    print(f"Generated standalone dashboard HTML at: {HTML_OUT}")
    print(f"HTML size: {HTML_OUT.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
