"""YAML frequency preset profiles for vtms-sdr.

Loads named presets from a YAML file so users can run
``vtms-sdr record --preset nascar`` instead of typing all flags.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .utils import VALID_MODULATIONS

__all__ = [
    "find_preset_file",
    "get_preset",
    "load_presets",
]

# File names to search in CWD, in priority order.
_DEFAULT_FILENAMES = ("presets.yaml", "vtms-sdr.yaml")


def load_presets(path: str | Path) -> dict[str, dict]:
    """Load and validate preset profiles from a YAML file.

    Args:
        path: Path to the YAML file.

    Returns:
        Dict mapping preset name to its settings dict.

    Raises:
        FileNotFoundError: If path does not exist.
        ValueError: If YAML is invalid or presets are malformed.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Preset file not found: {path}")

    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in {path}: {e}") from e

    if not isinstance(data, dict) or "presets" not in data:
        raise ValueError(f"Preset file must contain a top-level 'presets' key: {path}")

    presets = data["presets"]
    if not presets:
        raise ValueError(f"No presets defined in {path}")

    # Validate each preset
    for name, settings in presets.items():
        _validate_preset(name, settings)

    return presets


def _validate_preset(name: str, settings: dict) -> None:
    """Validate a single preset's settings.

    Raises:
        ValueError: If required fields are missing or values are invalid.
    """
    if not isinstance(settings, dict) or "freq" not in settings:
        raise ValueError(f"Preset '{name}' must have a 'freq' field")

    mod = settings.get("mod")
    if mod is not None and mod.lower() not in VALID_MODULATIONS:
        raise ValueError(
            f"Preset '{name}': invalid mod '{mod}'. Must be one of {VALID_MODULATIONS}"
        )

    gain = settings.get("gain")
    if gain is not None:
        if not (
            isinstance(gain, (int, float))
            or (isinstance(gain, str) and gain.lower() == "auto")
        ):
            raise ValueError(
                f"Preset '{name}': gain must be numeric or 'auto', "
                f"got {type(gain).__name__}"
            )

    squelch = settings.get("squelch")
    if squelch is not None and not isinstance(squelch, (int, float)):
        raise ValueError(
            f"Preset '{name}': squelch must be numeric, got {type(squelch).__name__}"
        )

    ppm = settings.get("ppm")
    if ppm is not None and not isinstance(ppm, (int, float)):
        raise ValueError(
            f"Preset '{name}': ppm must be numeric, got {type(ppm).__name__}"
        )

    label = settings.get("label")
    if label is not None and not isinstance(label, str):
        raise ValueError(
            f"Preset '{name}': label must be a string, got {type(label).__name__}"
        )

    dcs_code = settings.get("dcs_code")
    if dcs_code is not None:
        if not isinstance(dcs_code, int):
            raise ValueError(
                f"Preset '{name}': dcs_code must be an integer, "
                f"got {type(dcs_code).__name__}"
            )
        from .dcs import DCS_CODES

        if dcs_code not in DCS_CODES:
            raise ValueError(
                f"Preset '{name}': dcs_code {dcs_code} is not a valid standard DCS code"
            )


def get_preset(presets: dict[str, dict], name: str) -> dict:
    """Retrieve a single preset by name.

    Args:
        presets: Dict of presets as returned by load_presets().
        name: Preset name (case-sensitive).

    Returns:
        Settings dict for the named preset.

    Raises:
        KeyError: If the preset name does not exist.
    """
    if name not in presets:
        raise KeyError(
            f"Preset '{name}' not found. "
            f"Available presets: {', '.join(sorted(presets.keys()))}"
        )
    return presets[name]


def find_preset_file(search_dir: Path | None = None) -> Path | None:
    """Search for a default preset file in the given directory.

    Looks for ``presets.yaml`` then ``vtms-sdr.yaml`` in *search_dir*
    (defaults to CWD).

    Returns:
        Path to the first matching file, or None if none found.
    """
    if search_dir is None:
        search_dir = Path.cwd()

    for filename in _DEFAULT_FILENAMES:
        candidate = search_dir / filename
        if candidate.exists():
            return candidate

    return None
