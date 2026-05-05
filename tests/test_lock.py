"""Tests for the advisory file lock module."""

import fcntl
import os
import multiprocessing
import time

from rlsbl.lock import acquire_lock, release_lock, rlsbl_lock


def test_lock_file_created(tmp_path, monkeypatch):
    """acquire_lock creates .rlsbl/lock if it doesn't exist."""
    monkeypatch.chdir(tmp_path)

    acquire_lock()
    try:
        lock_path = tmp_path / ".rlsbl" / "lock"
        assert lock_path.exists()
    finally:
        release_lock()


def test_nonblocking_acquire_fails_when_held(tmp_path, monkeypatch):
    """A second non-blocking flock attempt raises when the lock is already held."""
    monkeypatch.chdir(tmp_path)

    acquire_lock()
    try:
        # Manually try a second non-blocking acquire on the same lock file
        lock_path = os.path.join(str(tmp_path), ".rlsbl", "lock")
        fd2 = open(lock_path, "w")
        try:
            fcntl.flock(fd2, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # If we get here, the lock wasn't actually exclusive (shouldn't happen)
            assert False, "Expected BlockingIOError but lock was acquired"
        except (OSError, BlockingIOError):
            # Expected: lock is held by acquire_lock()
            pass
        finally:
            fd2.close()
    finally:
        release_lock()


def test_release_allows_reacquire(tmp_path, monkeypatch):
    """After release_lock(), a new non-blocking acquire succeeds."""
    monkeypatch.chdir(tmp_path)

    acquire_lock()
    release_lock()

    # Should be able to acquire again without blocking
    lock_path = os.path.join(str(tmp_path), ".rlsbl", "lock")
    fd = open(lock_path, "w")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Success: lock is free
        fcntl.flock(fd, fcntl.LOCK_UN)
    except (OSError, BlockingIOError):
        assert False, "Lock should be free after release_lock()"
    finally:
        fd.close()


def test_context_manager(tmp_path, monkeypatch):
    """rlsbl_lock context manager acquires and releases correctly."""
    monkeypatch.chdir(tmp_path)

    with rlsbl_lock():
        lock_path = os.path.join(str(tmp_path), ".rlsbl", "lock")
        assert os.path.exists(lock_path)

        # Lock should be held inside the context
        fd = open(lock_path, "w")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            assert False, "Lock should be held inside context manager"
        except (OSError, BlockingIOError):
            pass
        finally:
            fd.close()

    # Lock should be free after exiting the context
    fd = open(lock_path, "w")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)
    except (OSError, BlockingIOError):
        assert False, "Lock should be free after context manager exits"
    finally:
        fd.close()


def _child_acquire(lock_dir, result_queue):
    """Helper for multiprocessing test: try non-blocking acquire in a child process."""
    lock_path = os.path.join(lock_dir, ".rlsbl", "lock")
    # Wait for lock file to exist
    for _ in range(50):
        if os.path.exists(lock_path):
            break
        time.sleep(0.01)

    fd = open(lock_path, "w")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result_queue.put("acquired")
        fcntl.flock(fd, fcntl.LOCK_UN)
    except (OSError, BlockingIOError):
        result_queue.put("blocked")
    finally:
        fd.close()


def test_cross_process_lock(tmp_path, monkeypatch):
    """Lock held in parent process blocks a child process from acquiring it."""
    monkeypatch.chdir(tmp_path)

    acquire_lock()
    try:
        result_queue = multiprocessing.Queue()
        child = multiprocessing.Process(
            target=_child_acquire,
            args=(str(tmp_path), result_queue),
        )
        child.start()
        child.join(timeout=5)

        assert not result_queue.empty()
        result = result_queue.get()
        assert result == "blocked", f"Child should be blocked but got: {result}"
    finally:
        release_lock()
