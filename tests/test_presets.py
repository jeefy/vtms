"""Tests for vtms_sdr.presets - YAML frequency preset profiles."""

import pytest
import yaml
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_PRESET_YAML = """\
presets:
  nascar:
    freq: "462.5625M"
    mod: fm
    gain: 40
    squelch: -35
    label: "SPOTTER"
  pit-crew:
    freq: "464.500M"
    mod: fm
    squelch: -30
    label: "PIT"
  minimal:
    freq: "146.52M"
"""


def _write_yaml(path: Path, content: str) -> Path:
    path.write_text(content)
    return path


# ---------------------------------------------------------------------------
# Tests: load_presets
# ---------------------------------------------------------------------------


class TestLoadPresets:
    """Tests for loading preset YAML files."""

    def test_load_valid_yaml(self, tmp_path):
        from vtms_sdr.presets import load_presets

        yaml_path = _write_yaml(tmp_path / "presets.yaml", VALID_PRESET_YAML)
        presets = load_presets(yaml_path)

        assert "nascar" in presets
        assert "pit-crew" in presets
        assert "minimal" in presets

    def test_load_returns_dict(self, tmp_path):
        from vtms_sdr.presets import load_presets

        yaml_path = _write_yaml(tmp_path / "presets.yaml", VALID_PRESET_YAML)
        presets = load_presets(yaml_path)

        assert isinstance(presets, dict)
        assert isinstance(presets["nascar"], dict)

    def test_load_nonexistent_file_raises(self, tmp_path):
        from vtms_sdr.presets import load_presets

        with pytest.raises(FileNotFoundError):
            load_presets(tmp_path / "no_such_file.yaml")

    def test_load_invalid_yaml_raises(self, tmp_path):
        from vtms_sdr.presets import load_presets

        yaml_path = _write_yaml(tmp_path / "bad.yaml", "{{{{ not yaml")
        with pytest.raises(ValueError, match="[Ii]nvalid YAML"):
            load_presets(yaml_path)

    def test_load_missing_presets_key_raises(self, tmp_path):
        from vtms_sdr.presets import load_presets

        yaml_path = _write_yaml(
            tmp_path / "no_key.yaml", "something_else:\n  foo: bar\n"
        )
        with pytest.raises(ValueError, match="presets"):
            load_presets(yaml_path)

    def test_load_empty_presets_raises(self, tmp_path):
        from vtms_sdr.presets import load_presets

        yaml_path = _write_yaml(tmp_path / "empty.yaml", "presets:\n")
        with pytest.raises(ValueError, match="[Ee]mpty|[Nn]o presets"):
            load_presets(yaml_path)


# ---------------------------------------------------------------------------
# Tests: get_preset
# ---------------------------------------------------------------------------


class TestGetPreset:
    """Tests for retrieving a single preset by name."""

    def test_get_existing_preset(self, tmp_path):
        from vtms_sdr.presets import load_presets, get_preset

        yaml_path = _write_yaml(tmp_path / "presets.yaml", VALID_PRESET_YAML)
        presets = load_presets(yaml_path)
        preset = get_preset(presets, "nascar")

        assert preset["freq"] == "462.5625M"
        assert preset["mod"] == "fm"
        assert preset["gain"] == 40
        assert preset["squelch"] == -35
        assert preset["label"] == "SPOTTER"

    def test_get_minimal_preset(self, tmp_path):
        """Preset with only freq should work; optional fields absent."""
        from vtms_sdr.presets import load_presets, get_preset

        yaml_path = _write_yaml(tmp_path / "presets.yaml", VALID_PRESET_YAML)
        presets = load_presets(yaml_path)
        preset = get_preset(presets, "minimal")

        assert preset["freq"] == "146.52M"
        assert "mod" not in preset
        assert "gain" not in preset

    def test_get_nonexistent_preset_raises(self, tmp_path):
        from vtms_sdr.presets import load_presets, get_preset

        yaml_path = _write_yaml(tmp_path / "presets.yaml", VALID_PRESET_YAML)
        presets = load_presets(yaml_path)

        with pytest.raises(KeyError, match="unknown_preset"):
            get_preset(presets, "unknown_preset")

    def test_get_preset_case_sensitive(self, tmp_path):
        """Preset names should be case-sensitive."""
        from vtms_sdr.presets import load_presets, get_preset

        yaml_path = _write_yaml(tmp_path / "presets.yaml", VALID_PRESET_YAML)
        presets = load_presets(yaml_path)

        with pytest.raises(KeyError):
            get_preset(presets, "NASCAR")


# ---------------------------------------------------------------------------
# Tests: validate_preset
# ---------------------------------------------------------------------------


class TestValidatePreset:
    """Tests for preset validation."""

    def test_missing_freq_raises(self, tmp_path):
        from vtms_sdr.presets import load_presets

        bad_yaml = "presets:\n  broken:\n    mod: fm\n"
        yaml_path = _write_yaml(tmp_path / "bad.yaml", bad_yaml)

        with pytest.raises(ValueError, match="freq"):
            load_presets(yaml_path)

    def test_invalid_mod_raises(self, tmp_path):
        from vtms_sdr.presets import load_presets

        bad_yaml = 'presets:\n  broken:\n    freq: "146.52M"\n    mod: cw\n'
        yaml_path = _write_yaml(tmp_path / "bad.yaml", bad_yaml)

        with pytest.raises(ValueError, match="[Mm]od"):
            load_presets(yaml_path)

    def test_valid_optional_fields_accepted(self, tmp_path):
        """All valid optional fields should pass validation."""
        from vtms_sdr.presets import load_presets

        good_yaml = """\
presets:
  full:
    freq: "146.52M"
    mod: am
    gain: 20.5
    squelch: -50
    label: "TEST"
"""
        yaml_path = _write_yaml(tmp_path / "good.yaml", good_yaml)
        presets = load_presets(yaml_path)
        assert "full" in presets


class TestValidatePresetTypes:
    """Test type validation for optional preset fields."""

    def test_invalid_gain_type_raises(self, tmp_path):
        from vtms_sdr.presets import load_presets

        data = {"presets": {"bad": {"freq": "146.52M", "gain": [1, 2, 3]}}}
        p = tmp_path / "presets.yaml"
        p.write_text(yaml.dump(data))
        with pytest.raises(ValueError, match="gain"):
            load_presets(p)

    def test_invalid_squelch_type_raises(self, tmp_path):
        from vtms_sdr.presets import load_presets

        data = {"presets": {"bad": {"freq": "146.52M", "squelch": "loud"}}}
        p = tmp_path / "presets.yaml"
        p.write_text(yaml.dump(data))
        with pytest.raises(ValueError, match="squelch"):
            load_presets(p)

    def test_invalid_ppm_type_raises(self, tmp_path):
        from vtms_sdr.presets import load_presets

        data = {"presets": {"bad": {"freq": "146.52M", "ppm": "five"}}}
        p = tmp_path / "presets.yaml"
        p.write_text(yaml.dump(data))
        with pytest.raises(ValueError, match="ppm"):
            load_presets(p)

    def test_valid_gain_auto_accepted(self, tmp_path):
        from vtms_sdr.presets import load_presets

        data = {"presets": {"ok": {"freq": "146.52M", "gain": "auto"}}}
        p = tmp_path / "presets.yaml"
        p.write_text(yaml.dump(data))
        result = load_presets(p)
        assert "ok" in result

    def test_valid_gain_numeric_accepted(self, tmp_path):
        from vtms_sdr.presets import load_presets

        data = {"presets": {"ok": {"freq": "146.52M", "gain": 40.2}}}
        p = tmp_path / "presets.yaml"
        p.write_text(yaml.dump(data))
        result = load_presets(p)
        assert "ok" in result


# ---------------------------------------------------------------------------
# Tests: find_preset_file
# ---------------------------------------------------------------------------


class TestFindPresetFile:
    """Tests for default preset file discovery."""

    def test_finds_presets_yaml_in_cwd(self, tmp_path):
        from vtms_sdr.presets import find_preset_file

        _write_yaml(tmp_path / "presets.yaml", VALID_PRESET_YAML)
        result = find_preset_file(search_dir=tmp_path)

        assert result is not None
        assert result.name == "presets.yaml"

    def test_returns_none_when_no_file(self, tmp_path):
        from vtms_sdr.presets import find_preset_file

        result = find_preset_file(search_dir=tmp_path)
        assert result is None

    def test_finds_vtms_sdr_yaml_in_cwd(self, tmp_path):
        from vtms_sdr.presets import find_preset_file

        _write_yaml(tmp_path / "vtms-sdr.yaml", VALID_PRESET_YAML)
        result = find_preset_file(search_dir=tmp_path)

        assert result is not None
        assert result.name == "vtms-sdr.yaml"

    def test_prefers_presets_yaml_over_vtms_sdr_yaml(self, tmp_path):
        """presets.yaml should take priority."""
        from vtms_sdr.presets import find_preset_file

        _write_yaml(tmp_path / "presets.yaml", VALID_PRESET_YAML)
        _write_yaml(tmp_path / "vtms-sdr.yaml", VALID_PRESET_YAML)
        result = find_preset_file(search_dir=tmp_path)

        assert result.name == "presets.yaml"
