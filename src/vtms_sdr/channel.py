"""Per-channel configuration for multi-frequency recording."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

__all__ = ["ChannelConfig"]


@dataclass
class ChannelConfig:
    """Configuration for a single recording channel.

    Each channel has its own frequency, modulation, output file,
    and optional DCS code.
    """

    freq: int
    mod: str
    output_path: Path
    audio_format: str = "wav"
    squelch_db: float = -30.0
    dcs_code: int | None = None
    label: str | None = None
