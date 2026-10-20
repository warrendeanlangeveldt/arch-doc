"""Headless Chrome, run so that finished work is never lost to its shutdown.

Under load from other Chrome processes, headless Chrome can finish its work
(write the screenshot, print the DOM) and then hang on shutdown, or exit
non-zero when its teardown watchdog expires. Its exit code therefore says
nothing reliable about the work. ``run`` judges a run by its output instead:

- Chrome runs in its own process group, so it and every helper it starts
  can be killed together.
- Its stdout and stderr are read as they stream. Once the caller's ``done``
  test says the output is complete, the group is killed and the output is
  used, whatever Chrome would have done next.
- A run that ends, or reaches its timeout, without complete output is
  returned as incomplete, with everything Chrome printed, for the caller
  to report.

``find`` locates Chrome or Chromium: ``CHROME_PATH`` when set, then the macOS
application, then the usual names on ``PATH``.
"""
from __future__ import annotations

import codecs
import os
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

TIMEOUT = 120
"""Seconds a run may take before its process group is killed."""

MAC_APP = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
NAMES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome")


def find() -> Path | None:
    """Chrome or Chromium, or None when neither is installed."""
    env = os.environ.get("CHROME_PATH")
    if env:
        return Path(env)
    if MAC_APP.exists():
        return MAC_APP
    for name in NAMES:
        p = shutil.which(name)
        if p:
            return Path(p)
    return None


@dataclass(frozen=True)
class Run:
    """One Chrome run, judged by its output."""
    complete: bool          # ``done`` accepted the output
    code: int | None        # exit code; None when the group was killed
    timed_out: bool         # killed at the timeout without complete output
    stdout: str
    stderr: str
    timeout: float

    @property
    def output(self) -> str:
        """Everything Chrome printed, stdout then stderr."""
        return self.stdout + self.stderr

    def why(self) -> str:
        """Why the run did not complete, for a failure message."""
        if self.timed_out:
            return f"did not exit within {self.timeout:g}s"
        if self.code is not None and self.code != 0:
            return f"exited {self.code}"
        return "exited without complete output"


def run(args: list[str], done: Callable[[str, str], bool], timeout: float = TIMEOUT) -> Run:
    """Run Chrome with ``args`` (the executable first). ``done(stdout,
    stderr)`` is asked, as output arrives and once the run ends, whether
    the output so far is complete; the first yes ends the run."""
    proc = subprocess.Popen([str(a) for a in args], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            stdin=subprocess.DEVNULL, start_new_session=True)
    texts = {"out": [], "err": []}
    ended = {"out": False, "err": False}
    changed = threading.Condition()

    def read(name: str, pipe) -> None:
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        fd = pipe.fileno()
        while True:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                chunk = b""
            with changed:
                if chunk:
                    texts[name].append(decoder.decode(chunk))
                else:
                    texts[name].append(decoder.decode(b"", final=True))
                    ended[name] = True
                changed.notify_all()
            if not chunk:
                return

    readers = [threading.Thread(target=read, args=("out", proc.stdout), daemon=True),
               threading.Thread(target=read, args=("err", proc.stderr), daemon=True)]
    for t in readers:
        t.start()

    def joined() -> tuple[str, str]:
        return "".join(texts["out"]), "".join(texts["err"])

    deadline = time.monotonic() + timeout
    complete = timed_out = False
    with changed:
        while True:
            out, err = joined()
            if done(out, err):
                complete = True
                break
            if all(ended.values()):
                break                                   # both pipes closed: Chrome has gone
            left = deadline - time.monotonic()
            if left <= 0:
                timed_out = True
                break
            changed.wait(min(left, 0.5))

    killed = complete or timed_out
    if killed:
        _kill_group(proc)
    try:
        code = proc.wait(timeout=10)
    except subprocess.TimeoutExpired:                   # not even SIGKILL: report it as killed
        _kill_group(proc)
        code = None
    for t in readers:
        t.join(timeout=5)
    out, err = joined()
    if not complete:
        complete = done(out, err)                       # the last of the output, drained after the end
    for pipe in (proc.stdout, proc.stderr):
        try:
            pipe.close()
        except OSError:
            pass
    return Run(complete=complete, code=None if killed else code, timed_out=timed_out and not complete,
               stdout=out, stderr=err, timeout=timeout)


def _kill_group(proc: subprocess.Popen, within: float = 3.0) -> None:
    """Kill the process group until it is empty. One signal is not enough:
    a process forked while the signal is delivered (Chrome starting a
    helper as it is killed) escapes it and keeps the output pipes open."""
    end = time.monotonic() + within
    while True:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            return                                      # no process left in the group
        proc.poll()                                     # reap the leader, so it stops counting
        if time.monotonic() > end:
            return
        time.sleep(0.05)


__all__ = ["MAC_APP", "Run", "TIMEOUT", "find", "run"]
