"""Verify spark_config.py exports all expected constants and structures."""
from pxh.spark_config import (
    SIMILARITY_THRESHOLD, EXPRESSION_COOLDOWN_S, SALIENCE_THRESHOLD,
    _FREE_WILL_WEIGHT, WEATHER_INTERVAL_S,
    SPARK_ANGLES, TOPIC_SEEDS,
    _SPARK_REFLECTION_PREFIX, _SPARK_REFLECTION_SUFFIX,
    MOOD_TO_SOUND, MOOD_TO_EMOTE,
)

def test_constants_are_numeric():
    assert isinstance(SIMILARITY_THRESHOLD, float)
    assert isinstance(EXPRESSION_COOLDOWN_S, (int, float))
    assert isinstance(SALIENCE_THRESHOLD, float)
    assert isinstance(_FREE_WILL_WEIGHT, float)
    assert isinstance(WEATHER_INTERVAL_S, (int, float))

def test_angles_is_nonempty_list():
    assert isinstance(SPARK_ANGLES, list)
    assert len(SPARK_ANGLES) >= 20

def test_topic_seeds_is_nonempty_list():
    assert isinstance(TOPIC_SEEDS, list)
    assert len(TOPIC_SEEDS) >= 50

def test_reflection_prefix_is_string():
    assert isinstance(_SPARK_REFLECTION_PREFIX, str)
    assert "SPARK" in _SPARK_REFLECTION_PREFIX

def test_reflection_suffix_is_string():
    assert isinstance(_SPARK_REFLECTION_SUFFIX, str)
    assert "JSON" in _SPARK_REFLECTION_SUFFIX

def test_mood_to_sound_is_dict():
    assert isinstance(MOOD_TO_SOUND, dict)
    assert "curious" in MOOD_TO_SOUND

def test_mood_to_emote_is_dict():
    assert isinstance(MOOD_TO_EMOTE, dict)
    assert "curious" in MOOD_TO_EMOTE
