"""archdoc.chrome: a Chrome run is judged by its output, not its exit. Each
case uses a stand-in shell script, so no browser is needed."""
import os
import time

from archdoc import chrome

DOM = lambda out, err: "</html>" in out


def fake(tmp_path, body, name="fake-chrome"):
    exe = tmp_path / name
    exe.write_text(f"#!/bin/sh\n{body}\n")
    exe.chmod(0o755)
    return exe


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_complete_output_then_a_hang_is_used_at_once_and_the_group_killed(tmp_path):
    """Chrome prints the DOM, then hangs on shutdown with a helper still
    running: the output is used as soon as it is complete, and the whole
    process group (the helper too) is killed."""
    pidfile = tmp_path / "helper.pid"
    exe = fake(tmp_path, f"sleep 60 & echo $! > {pidfile}\n"
                         "echo '<html><body>done</body></html>'\nsleep 60")
    started = time.monotonic()
    r = chrome.run([exe], done=DOM, timeout=30)
    assert time.monotonic() - started < 10
    assert r.complete and not r.timed_out and r.code is None
    assert "done" in r.stdout
    helper = int(pidfile.read_text())
    for _ in range(50):
        if not alive(helper):
            break
        time.sleep(0.1)
    assert not alive(helper)


def test_complete_output_survives_a_teardown_watchdog_exit(tmp_path):
    exe = fake(tmp_path, "echo '<html></html>'\n"
                         "echo 'Teardown watchdog expired; recording dump and terminating.' >&2\nexit 2")
    r = chrome.run([exe], done=lambda out, err: "</html>" in out and "watchdog" in err, timeout=30)
    assert r.complete


def test_output_split_across_writes_is_seen_whole(tmp_path):
    exe = fake(tmp_path, "printf '<html><body>part</bo'\nsleep 1\nprintf 'dy></ht'\nsleep 1\necho 'ml>'\nsleep 60")
    r = chrome.run([exe], done=DOM, timeout=30)
    assert r.complete and r.stdout.strip() == "<html><body>part</body></html>"


def test_incomplete_output_reports_the_exit_and_stderr(tmp_path):
    exe = fake(tmp_path, "echo '<html><body>'\necho 'Failed to create a ProcessSingleton' >&2\nexit 21")
    r = chrome.run([exe], done=DOM, timeout=30)
    assert not r.complete and not r.timed_out and r.code == 21
    assert r.why() == "exited 21"
    assert "ProcessSingleton" in r.stderr and "ProcessSingleton" in r.output


def test_a_clean_exit_without_complete_output_is_incomplete(tmp_path):
    r = chrome.run([fake(tmp_path, "exit 0")], done=DOM, timeout=30)
    assert not r.complete and r.code == 0
    assert r.why() == "exited without complete output"


def test_a_hang_without_output_is_killed_at_the_timeout(tmp_path):
    exe = fake(tmp_path, "echo starting >&2\nsleep 60")
    started = time.monotonic()
    r = chrome.run([exe], done=DOM, timeout=1)
    assert time.monotonic() - started < 10
    assert not r.complete and r.timed_out and r.code is None
    assert r.why() == "did not exit within 1s"
    assert "starting" in r.stderr


def test_find_honours_chrome_path(monkeypatch, tmp_path):
    exe = fake(tmp_path, "exit 0")
    monkeypatch.setenv("CHROME_PATH", str(exe))
    assert chrome.find() == exe
