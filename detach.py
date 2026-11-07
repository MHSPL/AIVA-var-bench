"""Start run_overnight.sh in its own session so it survives this terminal.

Double fork + setsid: the child is reparented to launchd (PPID 1) and leaves
the caller's process group, so a signal to that group cannot reach it.
"""
import os, sys, subprocess, time
log = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "run_detached.log")
if os.fork() > 0:
    time.sleep(1); sys.exit(0)
os.setsid()
if os.fork() > 0:
    os._exit(0)
with open(log, "a") as f:
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    subprocess.run(["caffeinate", "-is", "./run_overnight.sh"], stdout=f, stderr=subprocess.STDOUT)
