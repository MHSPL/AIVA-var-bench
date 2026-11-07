#!/usr/bin/env python3
"""
CLI helper to refresh dashboard data whenever new model results are added.

Usage:
    python scripts/update_dashboard.py
"""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILD_SCRIPT = REPO_ROOT / "dashboard" / "build_data.py"
GEN_HTML_SCRIPT = REPO_ROOT / "dashboard" / "generate_html.py"

python_bin = "/tmp/aiva_env/bin/python3" if os.path.exists("/tmp/aiva_env/bin/python3") else sys.executable
env = os.environ.copy()
env["MPLCONFIGDIR"] = "/tmp/mpl_cache"

print("[Dashboard Updater] Scanning for new model results and rebuilding dataset...")
res = subprocess.run([python_bin, str(BUILD_SCRIPT)], cwd=str(REPO_ROOT), env=env)
if res.returncode != 0:
    print(f"[Dashboard Updater] Failed during data build with exit code {res.returncode}", file=sys.stderr)
    sys.exit(res.returncode)

print("[Dashboard Updater] Re-generating standalone dashboard HTML (index.html)...")
res2 = subprocess.run([python_bin, str(GEN_HTML_SCRIPT)], cwd=str(REPO_ROOT), env=env)
if res2.returncode == 0:
    print("[Dashboard Updater] Dashboard updated. Reload the page, or serve it with: python dashboard/server.py")
else:
    print(f"[Dashboard Updater] Failed during HTML generation with exit code {res2.returncode}", file=sys.stderr)
    sys.exit(res2.returncode)
