"""Testes para services/preset_manager.py — validacao de nomes e path safety."""

import pytest

from services.preset_manager import validate_preset_name, PresetManager, Preset


# ---------------------------------------------------------------------------
# validate_preset_name
# ---------------------------------------------------------------------------

class TestValidatePresetName:
    def test_valid_simple(self):
        assert validate_preset_name("my_table") == "my_table"

    def test_valid_with_hyphens(self):
        assert validate_preset_name("db-ops-2024") == "db-ops-2024"

    def test_valid_with_dots(self):
        assert validate_preset_name("config.v2") == "config.v2"

    def test_valid_alphanumeric(self):
        assert validate_preset_name("test123") == "test123"

    def test_rejects_empty(self):
        with pytest.raises(ValueError, match="invalido"):
            validate_preset_name("")

    def test_rejects_path_traversal_unix(self):
        with pytest.raises(ValueError):
            validate_preset_name("../../etc/passwd")

    def test_rejects_path_traversal_windows(self):
        with pytest.raises(ValueError):
            validate_preset_name("..\\..\\file")

    def test_rejects_slash(self):
        with pytest.raises(ValueError):
            validate_preset_name("foo/bar")

    def test_rejects_backslash(self):
        with pytest.raises(ValueError):
            validate_preset_name("foo\\bar")

    def test_rejects_colon(self):
        with pytest.raises(ValueError):
            validate_preset_name("a:b")

    def test_rejects_spaces(self):
        with pytest.raises(ValueError):
            validate_preset_name("my table")

    def test_rejects_too_long(self):
        with pytest.raises(ValueError):
            validate_preset_name("a" * 101)

    def test_accepts_max_length(self):
        name = "a" * 100
        assert validate_preset_name(name) == name


# ---------------------------------------------------------------------------
# PresetManager._safe_path
# ---------------------------------------------------------------------------

class TestSafePath:
    def test_valid_name_returns_path(self, tmp_path):
        mgr = PresetManager(str(tmp_path))
        path = mgr._safe_path("my_preset")
        assert path.name == "my_preset.json"
        assert path.parent.resolve() == tmp_path.resolve()

    def test_rejects_traversal(self, tmp_path):
        mgr = PresetManager(str(tmp_path))
        with pytest.raises(ValueError):
            mgr._safe_path("../../etc")


# ---------------------------------------------------------------------------
# Integration: save/load/delete with validation
# ---------------------------------------------------------------------------

class TestPresetManagerWithValidation:
    def test_save_valid(self, tmp_path):
        mgr = PresetManager(str(tmp_path))
        preset = Preset(name="test_preset", schema="db", table="tb")
        path = mgr.save(preset)
        assert path.exists()

    def test_save_invalid_name_raises(self, tmp_path):
        mgr = PresetManager(str(tmp_path))
        preset = Preset(name="../bad", schema="db", table="tb")
        with pytest.raises(ValueError):
            mgr.save(preset)

    def test_load_invalid_name_raises(self, tmp_path):
        mgr = PresetManager(str(tmp_path))
        with pytest.raises(ValueError):
            mgr.load("../../etc")

    def test_delete_invalid_name_raises(self, tmp_path):
        mgr = PresetManager(str(tmp_path))
        with pytest.raises(ValueError):
            mgr.delete("../secret")

    def test_roundtrip(self, tmp_path):
        mgr = PresetManager(str(tmp_path))
        preset = Preset(
            name="roundtrip_test", schema="mydb", table="mytable",
            lookback_value=45, selected_columns=["A", "B"],
        )
        mgr.save(preset)
        loaded = mgr.load("roundtrip_test")
        assert loaded.schema == "mydb"
        assert loaded.table == "mytable"
        assert loaded.lookback_value == 45
        assert loaded.selected_columns == ["A", "B"]

    def test_roundtrip_new_partition_fields(self, tmp_path):
        """Preset com novos campos de particao faz round-trip correto."""
        mgr = PresetManager(str(tmp_path))
        preset = Preset(
            name="partition_test", schema="db", table="tb",
            partition_column="dt_ref",
            partition_format="%Y-%m-%d",
            partition_is_integer=False,
            temporal_axis_column="dt_ref",
            partition_columns=["dt_ref"],
            partition_formats={"dt_ref": "%Y-%m-%d"},
            partition_is_integer_map={"dt_ref": False},
        )
        mgr.save(preset)
        loaded = mgr.load("partition_test")
        assert loaded.partition_format == "%Y-%m-%d"
        assert loaded.partition_is_integer is False
        assert loaded.temporal_axis_column == "dt_ref"
        assert loaded.partition_columns == ["dt_ref"]
        assert loaded.partition_formats == {"dt_ref": "%Y-%m-%d"}
        assert loaded.partition_is_integer_map == {"dt_ref": False}

    def test_load_legacy_preset_without_new_fields(self, tmp_path):
        """Preset antigo (sem novos campos) carrega com defaults."""
        import json
        path = tmp_path / "legacy.json"
        legacy_data = {
            "schema": "db", "table": "tb",
            "partition_column": "dt_ref",
            "date_column": "dt_ref",
            "selected_columns": ["A"],
        }
        path.write_text(json.dumps(legacy_data))
        mgr = PresetManager(str(tmp_path))
        loaded = mgr.load("legacy")
        assert loaded.partition_format is None
        assert loaded.partition_is_integer is False
        assert loaded.temporal_axis_column is None
        assert loaded.partition_columns == []
        assert loaded.partition_formats == {}
        assert loaded.partition_is_integer_map == {}
