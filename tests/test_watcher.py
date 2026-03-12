"""Tests for the Watch Folder pipeline — stabilizer + race-condition guard."""
from __future__ import annotations

import threading
from pathlib import Path


# ── FileStabilizer unit tests ─────────────────────────────────────────────────

def test_stabilizer_fires_on_complete_file(tmp_path, qtbot):
    """A fully-written file should trigger file_ready exactly once."""
    from watcher.file_stabilizer import FileStabilizer

    stab = FileStabilizer()
    target = tmp_path / "complete.jpg"
    target.write_bytes(b"\xff\xd8\xff" + b"\x00" * 1024)

    with qtbot.waitSignal(stab.file_ready, timeout=5000) as blocker:
        stab.watch(str(target))

    assert blocker.args[0] == str(target)


def test_stabilizer_ignores_tmp_files(tmp_path, qtbot):
    """Files with .tmp extension should be silently skipped."""
    from watcher.file_stabilizer import FileStabilizer

    stab = FileStabilizer()
    fired: list[str] = []
    stab.file_ready.connect(fired.append)

    tmp_file = tmp_path / "writing.tmp"
    tmp_file.write_bytes(b"partial")
    stab.watch(str(tmp_file))
    # File should be rejected before watch() even enters _poll;
    # give a short window to confirm nothing fires.
    qtbot.wait(800)

    assert fired == []


def test_stabilizer_zero_byte_file_not_released(tmp_path, qtbot):
    """A zero-byte file should not trigger file_ready until content arrives."""
    from watcher.file_stabilizer import FileStabilizer

    stab = FileStabilizer()
    empty_file = tmp_path / "empty.jpg"
    empty_file.write_bytes(b"")
    stab.watch(str(empty_file))

    # Confirm no signal yet
    qtbot.wait(600)

    # Now write content and expect the signal
    with qtbot.waitSignal(stab.file_ready, timeout=5000) as blocker:
        empty_file.write_bytes(b"\xff\xd8" + b"\x00" * 512)

    assert blocker.args[0] == str(empty_file)


def test_no_duplicate_dispatch(tmp_path, qtbot):
    """Calling watch() twice for the same path should dispatch once."""
    from watcher.file_stabilizer import FileStabilizer

    stab = FileStabilizer()
    fired: list[str] = []
    stab.file_ready.connect(fired.append)

    target = tmp_path / "doc.jpg"
    target.write_bytes(b"\xff\xd8" + b"\x00" * 512)

    # First call triggers the stabilizer; second should be a no-op
    with qtbot.waitSignal(stab.file_ready, timeout=5000):
        stab.watch(str(target))
        stab.watch(str(target))  # duplicate — must NOT add a second thread

    # Allow a brief window for any spurious second signal
    qtbot.wait(600)
    assert len(fired) == 1


def test_race_condition_five_simultaneous_files(tmp_path, qtbot):
    """5 simultaneous file writes should each trigger exactly one file_ready."""
    from watcher.file_stabilizer import FileStabilizer

    stab = FileStabilizer()
    fired: list[str] = []
    lock = threading.Lock()
    done_event = threading.Event()
    expected = 5

    def on_ready(p: str) -> None:
        with lock:
            fired.append(p)
            if len(fired) == expected:
                done_event.set()

    stab.file_ready.connect(on_ready)

    def write_and_watch(i: int) -> None:
        f = tmp_path / f"doc_{i:03d}.jpg"
        f.write_bytes(b"\xff\xd8" + b"\x00" * (512 * (i + 1)))
        stab.watch(str(f))

    threads = [threading.Thread(target=write_and_watch, args=(i,)) for i in range(expected)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Process Qt events while waiting for all stabilizers
    deadline = 6.0
    import time
    t0 = time.monotonic()
    while not done_event.is_set() and (time.monotonic() - t0) < deadline:
        qtbot.wait(200)

    assert len(fired) == expected, f"Expected {expected} signals, got {len(fired)}"
    assert len(set(fired)) == expected, "Duplicate paths detected"
