"""Атомарная запись артефактов H5 (та же конвенция, что у shadow/gate/release)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def write_bytes_atomic(data: bytes, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
