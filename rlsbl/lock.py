"""Advisory file lock to prevent concurrent rlsbl operations.

Uses fcntl.flock on .rlsbl/lock to ensure only one rlsbl process
(release, scaffold, etc.) mutates project state at a time.
"""

import atexit
import fcntl
import os
import sys
from contextlib import contextmanager

# Module-level fd so the lock persists for the process lifetime
_lock_fd = None


def acquire_lock():
    """Acquire an exclusive advisory lock on .rlsbl/lock.

    If another process holds the lock, prints a waiting message and
    blocks until the lock is available. Returns early if already locked
    (prevents fd leak on double-acquire).
    """
    global _lock_fd

    # Guard against double-acquire: if already holding the lock, return early
    if _lock_fd is not None:
        return

    lock_dir = ".rlsbl"
    os.makedirs(lock_dir, exist_ok=True)
    lock_path = os.path.join(lock_dir, "lock")

    _lock_fd = open(lock_path, "w")

    try:
        # Try non-blocking first to detect contention
        fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, BlockingIOError):
        # Another process holds the lock -- inform user and wait
        print("Another rlsbl process is running. Waiting...", file=sys.stderr)
        fcntl.flock(_lock_fd, fcntl.LOCK_EX)

    atexit.register(release_lock)


def release_lock():
    """Release the advisory lock, close the file descriptor, and remove the lock file."""
    global _lock_fd

    if _lock_fd is not None:
        lock_path = _lock_fd.name
        fcntl.flock(_lock_fd, fcntl.LOCK_UN)
        _lock_fd.close()
        _lock_fd = None
        # Remove the lock file so it doesn't leave an untracked file
        # that dirties the working tree for subsequent operations.
        try:
            os.unlink(lock_path)
        except FileNotFoundError:
            pass


@contextmanager
def rlsbl_lock():
    """Context manager that acquires the lock on enter and releases on exit."""
    acquire_lock()
    try:
        yield
    finally:
        release_lock()
