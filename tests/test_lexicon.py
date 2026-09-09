from __future__ import annotations

from yjs_tools.journal.lexicon import (
    backfill_queries,
    detect_language,
    expand_query,
    should_resolve_remote,
)


def test_sensor_expands_to_sensing():
    expansion = expand_query("sensor")
    assert expansion.language == "en"
    assert "sensor" in expansion.tokens
    assert "sensors" in expansion.tokens
    assert "sensing" in expansion.tokens
    assert should_resolve_remote(expansion, "auto")
    assert should_resolve_remote(expansion, "topic")
    assert not should_resolve_remote(expansion, "name")
    assert not should_resolve_remote(expand_query("nature"), "auto")


def test_chinese_sensor_maps_to_english():
    expansion = expand_query("传感器")
    assert detect_language("传感器") == "zh"
    assert "sensor" in expansion.tokens
    assert "sensors" in expansion.tokens
    assert "sensing" in expansion.tokens
    assert expansion.note
    assert "sensor" in expansion.note
    venues = backfill_queries(expansion)
    assert "IEEE Sensors" in venues
    assert "Sensor Review" in venues
    assert "Measurement Science and Technology" in venues
