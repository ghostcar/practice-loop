"""JSON repair pipeline: json_repair → regex → 3 retries → error.

Per AGENTS.md §3.2:
1. json.loads
2. json_repair
3. Regex extraction from markdown block
4. After 3 consecutive failures → return error (caller shows "Retry" button)
"""

import json
import re

from json_repair import repair_json


class JsonRepairError(Exception):
    """JSON could not be repaired after all attempts."""

    pass


def parse_llm_json(raw_content: str, is_last_attempt: bool = False) -> dict | list:
    """Parse LLM output as JSON, trying multiple repair strategies.

    Each call tries: json.loads → json_repair → regex extraction.
    The caller is expected to re-call the LLM for a fresh response and retry.

    Args:
        raw_content: Raw string from the LLM.
        is_last_attempt: If True, raises JsonRepairError on failure (no more retries).

    Returns:
        Parsed JSON dict or list.

    Raises:
        JsonRepairError: When is_last_attempt=True and all strategies fail.
        ValueError: When is_last_attempt=False (caller should retry with fresh LLM response).
    """
    content = raw_content.strip()

    errors: list[str] = []

    # Strategy 1: direct json.loads
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        errors.append(f"json.loads: {e}")

    # Strategy 2: json_repair
    try:
        repaired = repair_json(content)
        result = json.loads(repaired)
        if isinstance(result, dict | list):
            return result
        errors.append(f"json_repair: returned {type(result).__name__}, expected dict or list")
    except Exception as e:
        errors.append(f"json_repair: {e}")

    # Strategy 3: regex extract from markdown code block
    try:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
        if match:
            extracted = match.group(1).strip()
            result = json.loads(extracted)
            if isinstance(result, dict | list):
                return result
            errors.append(f"regex(md): returned {type(result).__name__}, expected dict or list")
        # Try to find any JSON object in the text
        match = re.search(r"\{[\s\S]*\}", content)
        if match:
            extracted = match.group(0).strip()
            repaired = repair_json(extracted)
            result = json.loads(repaired)
            if isinstance(result, dict):
                return result
            errors.append(f"regex(obj): returned {type(result).__name__}, expected dict")
    except Exception as e:
        errors.append(f"regex: {e}")

    # All strategies failed
    if is_last_attempt:
        raise JsonRepairError(f"Failed to parse LLM JSON on final attempt. Errors: {'; '.join(errors)}")

    raise ValueError(f"Parse failed. Errors: {'; '.join(errors)}")
