"""Testes para serialização/deserialização de column profiles em presets."""

from core.models.column_profile import ColumnProfile
from core.models.enums import SemanticType
from services.preset_manager import serialize_profiles, deserialize_profiles

_serialize_profiles = serialize_profiles
_deserialize_profiles = deserialize_profiles


def _make_profile(**kwargs) -> ColumnProfile:
    defaults = dict(
        column_name="col1",
        athena_type="bigint",
        inferred_semantic_type=SemanticType.NUMERIC,
        total_count=1000,
        non_null_count=990,
        distinct_count=500,
        null_ratio=0.01,
        distinct_ratio=0.505,
        numeric_cast_ratio=1.0,
        sample_values=["100", "200", "300"],
        warnings=[],
    )
    defaults.update(kwargs)
    return ColumnProfile(**defaults)


class TestSerializeProfiles:
    def test_roundtrip_basic(self):
        profiles = [_make_profile()]
        serialized = _serialize_profiles(profiles)
        restored = _deserialize_profiles(serialized)
        assert len(restored) == 1
        assert restored[0].column_name == "col1"
        assert restored[0].inferred_semantic_type == SemanticType.NUMERIC
        assert restored[0].total_count == 1000

    def test_roundtrip_with_override(self):
        profiles = [_make_profile(
            user_override_type=SemanticType.CATEGORICAL_LOW_CARDINALITY,
        )]
        serialized = _serialize_profiles(profiles)
        restored = _deserialize_profiles(serialized)
        assert restored[0].user_override_type == SemanticType.CATEGORICAL_LOW_CARDINALITY
        assert restored[0].effective_type == SemanticType.CATEGORICAL_LOW_CARDINALITY

    def test_roundtrip_no_override(self):
        profiles = [_make_profile()]
        serialized = _serialize_profiles(profiles)
        restored = _deserialize_profiles(serialized)
        assert restored[0].user_override_type is None
        assert restored[0].effective_type == SemanticType.NUMERIC

    def test_multiple_profiles(self):
        profiles = [
            _make_profile(column_name="col1", inferred_semantic_type=SemanticType.NUMERIC),
            _make_profile(column_name="col2", inferred_semantic_type=SemanticType.CATEGORICAL_LOW_CARDINALITY),
            _make_profile(column_name="col3", inferred_semantic_type=SemanticType.IDENTIFIER),
        ]
        serialized = _serialize_profiles(profiles)
        restored = _deserialize_profiles(serialized)
        assert len(restored) == 3
        assert [p.column_name for p in restored] == ["col1", "col2", "col3"]
        assert restored[1].inferred_semantic_type == SemanticType.CATEGORICAL_LOW_CARDINALITY

    def test_empty_list(self):
        assert _serialize_profiles([]) == []
        assert _deserialize_profiles([]) == []

    def test_preserves_metrics(self):
        p = _make_profile(
            null_ratio=0.15,
            distinct_ratio=0.8,
            numeric_cast_ratio=0.95,
            sample_values=["a", "b"],
            warnings=["Low cardinality"],
        )
        serialized = _serialize_profiles([p])
        restored = _deserialize_profiles(serialized)[0]
        assert restored.null_ratio == 0.15
        assert restored.distinct_ratio == 0.8
        assert restored.numeric_cast_ratio == 0.95
        assert restored.sample_values == ["a", "b"]
        assert restored.warnings == ["Low cardinality"]

    def test_json_serializable(self):
        """Serialized profiles must be JSON-safe (no custom objects)."""
        import json
        profiles = [_make_profile(user_override_type=SemanticType.IDENTIFIER)]
        serialized = _serialize_profiles(profiles)
        # Must not raise
        json_str = json.dumps(serialized)
        assert '"identifier"' in json_str
