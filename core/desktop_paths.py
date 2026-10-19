"""Resolve user-specific desktop paths across redirected Windows profiles."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def _windows_desktop_path() -> Optional[Path]:
    """Return the Shell's Desktop directory, including OneDrive redirection."""
    try:
        import ctypes

        path_buffer = ctypes.create_unicode_buffer(260)
        result = ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, path_buffer)
        if result == 0 and path_buffer.value:
            return Path(path_buffer.value)
    except (AttributeError, OSError):
        pass
    return None


def desktop_path() -> Path:
    """Return the actual Desktop folder, falling back to ``~/Desktop``."""
    if os.name == "nt":
        resolved = _windows_desktop_path()
        if resolved is not None:
            return resolved
    return Path.home() / "Desktop"
