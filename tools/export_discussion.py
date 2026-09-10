#!/usr/bin/env python3
"""Export conversation transcript from Antigravity CLI to a clean Markdown file.

Usage:
    python3 tools/export_discussion.py [--since 2026-09-10T07:00:00] [--out docs/discussions/2026-09-10_KINKOS_FULL_DIALOGUE.md]
"""

import argparse
import json
import os
import re
from datetime import datetime, timezone

CONV_ID = "91cc328f-3022-47ca-8591-0a1d57034861"
DEFAULT_TRANSCRIPT = f"/home/roman/.gemini/antigravity-cli/brain/{CONV_ID}/.system_generated/logs/transcript_full.jsonl"


def clean_user_content(text: str) -> str:
    """Strip XML-like wrapper tags from user input."""
    text = re.sub(r"<ADDITIONAL_METADATA>.*?</ADDITIONAL_METADATA>", "", text, flags=re.DOTALL)
    text = re.sub(r"<CONTEXT_SUMMARY>.*?</CONTEXT_SUMMARY>", "", text, flags=re.DOTALL)
    # Extract content inside <USER_REQUEST> if present
    matches = re.findall(r"<USER_REQUEST>(.*?)</USER_REQUEST>", text, flags=re.DOTALL)
    if matches:
        text = "\n\n".join(m.strip() for m in matches if m.strip())
    else:
        text = re.sub(r"</?USER_REQUEST>", "", text)
    return text.strip()


def export_discussion(transcript_path: str, output_path: str, since: str | None = None) -> None:
    if not os.path.exists(transcript_path):
        raise FileNotFoundError(f"Transcript not found: {transcript_path}")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    dialogue = []
    seen_texts = set()

    with open(transcript_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
            except Exception:
                continue

            created_at = entry.get("created_at", "")
            if since and created_at < since:
                continue

            step_type = entry.get("type", "")
            content = entry.get("content", "")
            if not content:
                continue

            if step_type == "USER_INPUT":
                cleaned = clean_user_content(content)
                if cleaned and cleaned not in seen_texts:
                    seen_texts.add(cleaned)
                    dialogue.append({
                        "role": "Владелец (User)",
                        "time": created_at,
                        "content": cleaned
                    })
            elif step_type == "PLANNER_RESPONSE":
                content_str = content.strip()
                # Skip tool-only or trivial intermediate outputs
                if len(content_str) > 120 and content_str not in seen_texts:
                    seen_texts.add(content_str)
                    dialogue.append({
                        "role": "Antigravity (Архитектор)",
                        "time": created_at,
                        "content": content_str
                    })

    # Write Markdown
    with open(output_path, "w", encoding="utf-8") as out:
        out.write("# Стенограмма проектирования: Концепция KinkOS, BDSM-ядро и архитектура\n\n")
        out.write(f"> **Дата генерации:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
        out.write(f"> **Источник данных:** `{transcript_path}`\n")
        out.write(f"> **Сессия с отметки:** `{since or 'начало лога'}`\n")
        out.write(f"> **Всего раундов диалога:** {len(dialogue)}\n\n")
        out.write("---\n\n")

        for idx, turn in enumerate(dialogue, start=1):
            role = turn["role"]
            time_val = turn["time"]
            text = turn["content"]

            if "Владелец" in role:
                out.write(f"### 👤 {idx}. {role} `[{time_val}]`\n\n")
                out.write(f"{text}\n\n")
            else:
                out.write(f"### 🤖 {idx}. {role} `[{time_val}]`\n\n")
                out.write(f"{text}\n\n")
            out.write("---\n\n")

    print(f"Successfully exported {len(dialogue)} messages to {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export transcript to markdown")
    parser.add_argument("--transcript", default=DEFAULT_TRANSCRIPT, help="Path to transcript_full.jsonl")
    parser.add_argument("--out", default="docs/discussions/2026-09-10_KINKOS_FULL_DIALOGUE.md", help="Output path")
    parser.add_argument("--since", default="2026-09-10T07:00:00", help="Filter messages starting from ISO timestamp")
    args = parser.parse_args()

    export_discussion(args.transcript, args.out, args.since)
