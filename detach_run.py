#!/usr/bin/env python3
"""
Launch run_overnight.sh in its own session so it outlives this terminal.

nohup alone only blocks SIGHUP; the child stays in the launching process group
and dies if that group is signalled (which is what happens when an editor or
agent session is torn down). start_new_session=True calls setsid(2) in the
child, which macOS has no CLI for, so the job gets a fresh session and process
group and is reparented to launchd.
"""
import os
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.abspath(__file__))
# Which runner to detach; defaults to the original Sonnet/Opus script.
script = sys.argv[1] if len(sys.argv) > 1 else "./run_overnight.sh"
label = os.path.splitext(os.path.basename(script))[0]
log_path = os.path.join(REPO, f"{label}_{time.strftime('%Y%m%d_%H%M%S')}.log")
pid_path = os.path.join(REPO, f"{label}.pid")

with open(log_path, "ab", buffering=0) as log:
    proc = subprocess.Popen(
        ["caffeinate", "-is", script],
        cwd=REPO,
        stdout=log,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,   # setsid(2): new session + process group
        close_fds=True,
    )

with open(pid_path, "w") as f:
    f.write(str(proc.pid) + "\n")

print(f"detached pid : {proc.pid}")
print(f"log          : {log_path}")
print(f"pid file     : {pid_path}")
print()
print("check on it later:")
print(f"  tail -f {log_path}")
print(f"  ps -p $(cat {pid_path})")
print(f"  kill $(cat {pid_path})          # stops it; resume picks up where it left off")
