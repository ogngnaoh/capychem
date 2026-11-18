"""Keep scientific descendants bounded by the lifetime of their owning worker.

The worker holds this process's stdin open. On a crash (including SIGKILL), EOF
is delivered by the OS and all scientific descendants are terminated. No PID
files or guesses about reused process IDs are needed.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading


def main() -> int:
    command = sys.argv[1:]
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        raise SystemExit("A scientific subprocess command is required")
    stopping = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    signal.signal(signal.SIGINT, lambda *_: stopping.set())
    process = subprocess.Popen(
        command, stdin=subprocess.DEVNULL, start_new_session=os.name == "posix"
    )

    def parent_lifetime() -> None:
        # A daemon thread must not hold Python's buffered-stdin lock while the
        # interpreter shuts down after an ordinary successful child exit.
        os.read(sys.stdin.fileno(), 1)
        stopping.set()

    threading.Thread(target=parent_lifetime, daemon=True).start()
    try:
        while process.poll() is None and not stopping.wait(0.1):
            pass
        if process.poll() is None:
            try:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGTERM)
                else:
                    process.terminate()
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
        return process.wait()
    finally:
        # Also remove descendants that outlived a normally exiting child.
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
