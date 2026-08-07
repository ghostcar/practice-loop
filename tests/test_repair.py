"""Unit tests for JSON repair pipeline."""

import pytest

from app.llm.repair import JsonRepairError, parse_llm_json


class TestJsonRepair:
    """Test the JSON repair pipeline strategies."""

    def test_valid_json(self):
        """Direct parse with valid JSON."""
        result = parse_llm_json('{"key": "value", "num": 42}')
        assert result == {"key": "value", "num": 42}

    def test_trailing_comma(self):
        """json_repair handles trailing commas."""
        result = parse_llm_json('{"key": "value",}')
        assert result == {"key": "value"}

    def test_unquoted_keys(self):
        """json_repair handles unquoted keys."""
        result = parse_llm_json('{key: "value"}')
        assert result == {"key": "value"}

    def test_missing_quotes(self):
        """json_repair handles missing quotes."""
        result = parse_llm_json('{"key": value}')
        assert result == {"key": "value"}

    def test_single_quotes(self):
        """json_repair handles single quotes."""
        result = parse_llm_json("{'key': 'value'}")
        assert result == {"key": "value"}

    def test_markdown_code_block(self):
        """Regex extracts JSON from markdown block."""
        content = '```json\n{"entity_id": "abc", "entity_name": "Test"}\n```'
        result = parse_llm_json(content)
        assert result["entity_id"] == "abc"
        assert result["entity_name"] == "Test"

    def test_markdown_no_lang(self):
        """Regex extracts from markdown without language."""
        content = '```\n{"x": 1}\n```'
        result = parse_llm_json(content)
        assert result == {"x": 1}

    def test_embedded_json_object(self):
        """Regex finds JSON object in text."""
        content = 'Here is my choice: {"result": "ok"} Hope that works!'
        result = parse_llm_json(content)
        assert result == {"result": "ok"}

    def test_nested_json(self):
        """Handles nested objects."""
        content = '{"outer": {"inner": [1, 2, 3]}}'
        result = parse_llm_json(content)
        assert result == {"outer": {"inner": [1, 2, 3]}}

    def test_list_response(self):
        """Handles list responses."""
        content = '[{"a": 1}, {"b": 2}]'
        result = parse_llm_json(content)
        assert result == [{"a": 1}, {"b": 2}]

    def test_last_attempt_raises(self):
        """is_last_attempt=True raises JsonRepairError on failure."""
        with pytest.raises(JsonRepairError):
            parse_llm_json("this is just plain text with no json structure", is_last_attempt=True)

    def test_non_last_attempt_raises_value_error(self):
        """is_last_attempt=False raises ValueError on failure."""
        with pytest.raises(ValueError):
            parse_llm_json("this is just plain text with no json structure")

    def test_empty_string(self):
        """Empty string raises on last attempt."""
        with pytest.raises(JsonRepairError):
            parse_llm_json("", is_last_attempt=True)
