#!/usr/bin/env python3
"""
Lightweight Local Server for AIVA Variant Benchmark Dashboard.

Provides:
- Zero-dependency HTTP static file server
- Dynamic REST API for dashboard data (`/api/data`)
- Live background job monitoring endpoint (`/api/live`)
- On-demand benchmark data refresh endpoint (`/api/refresh`)
- Model management (`POST /api/models/remove|restore|import`): changes are
  written to the model registry (dashboard/models.tsv) and imported_results/,
  then the dataset and index.html are rebuilt

Usage:
    python dashboard/server.py             # Starts server on port 8050
    python dashboard/server.py --port 3000 # Custom port
"""

import argparse
import glob
import http.server
import json
import os
import re
import socketserver
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
from dashboard.registry import PROVIDERS, read_registry, set_status, upsert  # noqa: E402
DASHBOARD_DIR = REPO_ROOT / "dashboard"
DATA_FILE = DASHBOARD_DIR / "data" / "benchmark_data.json"
LEGACY_EXCLUDED_FILE = DASHBOARD_DIR / "excluded_models.txt"
IMPORTED_DIR = REPO_ROOT / "imported_results"
MAX_UPLOAD_BYTES = 200 * 1024 * 1024


def rebuild() -> subprocess.CompletedProcess:
    """Rebuild the dataset, then regenerate index.html from it."""
    python_bin = "/tmp/aiva_env/bin/python3" if os.path.exists("/tmp/aiva_env/bin/python3") else sys.executable
    env = os.environ.copy()
    env["MPLCONFIGDIR"] = "/tmp/mpl_cache"
    res = subprocess.run([python_bin, str(DASHBOARD_DIR / "build_data.py")], cwd=str(REPO_ROOT), env=env, capture_output=True, text=True)
    if res.returncode == 0:
        res = subprocess.run([python_bin, str(DASHBOARD_DIR / "generate_html.py")], cwd=str(REPO_ROOT), env=env, capture_output=True, text=True)
    return res


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def clear_legacy_exclusion(key: str) -> None:
    keys = [k for k in (line.strip() for line in read_lines(LEGACY_EXCLUDED_FILE)) if k and k != key]
    if LEGACY_EXCLUDED_FILE.exists():
        LEGACY_EXCLUDED_FILE.write_text("".join(k + "\n" for k in keys), encoding="utf-8")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:60] or "model"


class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DASHBOARD_DIR), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            self.path = "/index.html"
            return super().do_GET()

        elif path in ("/api/data", "/data/benchmark_data.json"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            if DATA_FILE.exists():
                with open(DATA_FILE, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.wfile.write(json.dumps({"error": "Data not found. Run build_data.py first."}).encode())
            return

        elif path == "/api/live":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            live_status = self.get_live_job_status()
            self.wfile.write(json.dumps(live_status, indent=2).encode())
            return

        elif path == "/api/refresh":
            print("[Server] Rebuilding dataset and index.html...")
            res = rebuild()
            if res.returncode != 0 or not DATA_FILE.exists():
                return self.send_json({"status": "error", "log": res.stderr[-4000:]}, 500)
            return self.send_json(json.loads(DATA_FILE.read_text(encoding="utf-8")))

        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in ("/api/models/remove", "/api/models/restore", "/api/models/import"):
            return self.send_json({"error": "Not found"}, 404)
        # Only accept requests from pages served by this server.
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).hostname not in ("localhost", "127.0.0.1", "::1"):
            return self.send_json({"error": "Forbidden"}, 403)
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_UPLOAD_BYTES:
            return self.send_json({"error": "File too large"}, 413)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self.send_json({"error": "Invalid JSON"}, 400)

        if path == "/api/models/import":
            name = str(body.get("name") or "").strip()
            content = body.get("content") or ""
            if not name or not content:
                return self.send_json({"error": "name and content are required"}, 400)
            key = "imported_" + slugify(name)
            # Keep an existing key when the name matches a registered model.
            for row in read_registry():
                if row["name"].lower() == name.lower():
                    key = row["key"]
            is_array = content.lstrip().startswith("[")
            rel = f"imported_results/{key}.{'json' if is_array else 'jsonl'}"
            IMPORTED_DIR.mkdir(exist_ok=True)
            (REPO_ROOT / rel).write_text(content, encoding="utf-8")
            provider = str(body.get("provider") or "Other")
            existing = next((r for r in read_registry() if r["key"] == key), {})
            upsert({
                "key": key,
                "name": name,
                "provider": provider if provider in PROVIDERS else "Other",
                "method": existing.get("method") or "Imported",
                "path": rel,
                "format": "json_array" if is_array else "jsonl",
                "color": existing.get("color", ""),
                "color_dark": existing.get("color_dark", ""),
                "status": "active",
                "section": existing.get("section", ""),
            })
            clear_legacy_exclusion(key)
        else:
            key = str(body.get("key") or "").strip()
            if not re.fullmatch(r"[A-Za-z0-9_\-]+", key):
                return self.send_json({"error": "Invalid model key"}, 400)
            restore = path.endswith("restore")
            if not set_status(key, "active" if restore else "removed"):
                return self.send_json({"error": f"{key} is not in dashboard/models.tsv"}, 404)
            if restore:
                clear_legacy_exclusion(key)

        print(f"[Server] {path} {key}: rebuilding dataset and index.html...")
        res = rebuild()
        if res.returncode != 0 or not DATA_FILE.exists():
            return self.send_json({"error": "Rebuild failed", "log": res.stderr[-4000:]}, 500)
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        data["changed_key"] = key
        return self.send_json(data)

    def send_json(self, obj, status: int = 200):
        payload = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def get_live_job_status(self):
        jobs = {}
        for job_name, pid_file, log_pattern, target_total in [
            ("Sonnet 5.5 Re-Run", "run_overnight_sonnet.pid", "run_overnight_sonnet_*.log", 5760),
            ("Opus 5.5 Re-Run", "run_overnight_opus.pid", "run_overnight_opus_*.log", 8387),
        ]:
            pid_path = REPO_ROOT / pid_file
            pid = None
            is_active = False
            if pid_path.exists():
                try:
                    pid = int(pid_path.read_text().strip())
                    # Check if pid is alive
                    os.kill(pid, 0)
                    is_active = True
                except (PermissionError, ProcessLookupError, OSError):
                    # In sandbox or permission error, check if log was updated recently
                    is_active = True

            logs = sorted(glob.glob(str(REPO_ROOT / log_pattern)))
            latest_log = logs[-1] if logs else ""
            progress = 0
            latest_line = ""

            if latest_log and os.path.exists(latest_log):
                try:
                    with open(latest_log, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            if "Progress:" in line:
                                match = re.search(r"Progress:\s*(\d+)/(\d+)", line)
                                if match:
                                    progress = int(match.group(1))
                                    latest_line = line.strip()
                except Exception:
                    pass

            jobs[job_name] = {
                "pid": pid,
                "status": "Running" if is_active else "Stopped",
                "progress_count": progress,
                "target_total": target_total,
                "progress_pct": round(progress / target_total * 100, 1) if target_total else 0,
                "latest_log": latest_line,
            }
        return jobs


def run_server(port: int = 8050, host: str = "127.0.0.1"):
    handler = DashboardHandler
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer((host, port), handler) as httpd:
        print("\n" + "=" * 70)
        print("AIVA Variant Benchmark dashboard")
        print("=" * 70)
        print(f" Dashboard URL : http://localhost:{port}")
        print(f" Data API      : http://localhost:{port}/api/data")
        print(f" Live Monitor  : http://localhost:{port}/api/live")
        print(f" Refresh API   : http://localhost:{port}/api/refresh")
        print("=" * 70)
        print("Press Ctrl+C to stop the server.\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")
            httpd.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AIVA Benchmark Dashboard Server")
    parser.add_argument("--port", type=int, default=8050, help="Port to bind (default: 8050)")
    parser.add_argument("--host", default="127.0.0.1", help="Interface to bind (default: 127.0.0.1; the server can modify files)")
    args = parser.parse_args()
    run_server(args.port, args.host)
