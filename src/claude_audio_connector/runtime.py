from __future__ import annotations

import os
from pathlib import Path


def _runtime_prefix() -> str:
    return os.getenv("CLAUDE_AUDIO_RUNTIME_PREFIX") or f"claude-audio.{os.getuid()}"


def runtime_dir() -> Path:
    return Path(os.getenv("CLAUDE_AUDIO_RUNTIME_DIR", "/tmp"))


def runtime_path(suffix: str) -> str:
    return str(runtime_dir() / f"{_runtime_prefix()}.{suffix}")


def socket_path() -> str:
    return os.getenv("CLAUDE_AUDIO_SOCKET") or runtime_path("sock")
