"""Cross-process-safe JSON persistence for ~/.codec/*.json (Cross-Platform Windows/Linux/macOS)"""
from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from typing import Any, Iterator

try:
    import fcntl
except ImportError:
    fcntl = None


def atomic_write_json(
    path: Any,
    data: Any,
    *,
    default: Any = None,
    sort_keys: bool = False,
) -> None:
    """Atomically write `data` as JSON to `path` (tmp + fsync + replace, 0600)."""
    path = str(path)
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, default=default, sort_keys=sort_keys)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


@contextmanager
def file_lock(path: Any) -> Iterator[None]:
    """Exclusive cross-process lock on `<path>.lock` for the duration of the block."""
    path = str(path)
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    lock_file = None
    try:
        lock_file = open(path + ".lock", "w")
        if fcntl:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        if lock_file is not None:
            if fcntl:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass
            try:
                lock_file.close()
            except Exception:
                pass


def read_modify_write(
    path: Any,
    mutate_fn,
    *,
    default_factory=dict,
    default: Any = None,
    sort_keys: bool = False,
) -> Any:
    """Read JSON from `path`, run `mutate_fn(data)`, write result atomically under lock."""
    path = str(path)
    with file_lock(path):
        data = None
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = None
        if data is None:
            data = default_factory()
        result = mutate_fn(data)
        atomic_write_json(path, data, default=default, sort_keys=sort_keys)
        return result
