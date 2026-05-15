"""
Shared helpers for concurrency tests across all apps.
"""

import threading


def _run_workers(worker_fn, count, join_timeout=5):
    """
    Launches `count` barrier-synchronized threads and waits for them to finish.

    Each thread receives (barrier, lock, index) as arguments.
    join_timeout is kept short (5 s) so a deadlock fails fast instead of
    hanging the test suite for 15 s per test.
    """
    barrier = threading.Barrier(count)
    lock = threading.Lock()
    threads = [
        threading.Thread(target=worker_fn, args=(barrier, lock, i))
        for i in range(count)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=join_timeout)
    return threads
