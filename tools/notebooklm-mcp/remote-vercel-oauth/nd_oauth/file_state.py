from __future__ import annotations

import os
from pathlib import Path


class FileOAuthStateStore:
    """Mirror OAuth JSON between a disposable runtime path and durable storage.

    Railway mounts the durable volume under /data. Writes use an atomic replace
    so a process interruption cannot leave a partially-written registry file.
    """

    def __init__(self, persistent_path: str | Path) -> None:
        self.persistent_path = Path(persistent_path)

    def restore(self, local_path: Path) -> bool:
        if not self.persistent_path.exists():
            return False
        raw = self.persistent_path.read_bytes()
        local_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        local_path.write_bytes(raw)
        local_path.chmod(0o600)
        return True

    def persist(self, local_path: Path) -> None:
        raw = local_path.read_bytes()
        target = self.persistent_path
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = target.with_name(f".{target.name}.tmp-{os.getpid()}")
        try:
            tmp.write_bytes(raw)
            tmp.chmod(0o600)
            os.replace(tmp, target)
            target.chmod(0o600)
        finally:
            if tmp.exists():
                tmp.unlink()
