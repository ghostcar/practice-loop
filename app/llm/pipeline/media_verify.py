"""LLM media verification (ADR-075, Step 7) — фото-оценка через vision-модель.

Типы проверок:
- ``code_match`` — на фото код; LLM сравнивает с ожидаемым (обычно HMAC-код
  VerificationChallenge). LLM читает код на изображении и отвечает, совпадает
  ли он с ожидаемым (без раскрытия ожидаемого в ответе).
- ``chastity_closed`` — на фото устройство/замок; LLM оценивает, закрыт ли
  замок (belt/device visibly locked).

Контракт безопасности:
- фото загружается из приватного upload-хранилища только владельцем;
- ожидаемый код НЕ хранится plaintext (в БД только HMAC); в промпт идёт
  plaintext (нужен для сравнения), но это тот же запрос владельца;
- verdict LLM — вспомогательное доказательство; авторитетное завершение —
  HMAC-вызов. Auto-consume challenge возможен только по явному запросу.
- модель vision: openrouter/openai/gpt-4o-mini (дёшево, подтверждена через
  Omniroute); если провайдер не vision — вернёт 400, и мы вернём unclear.
"""

from __future__ import annotations

import base64
import logging
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.llm import client
from app.llm.repair import parse_llm_json
from app.models.llm_config import LLMProviderConfig
from app.models.media import MediaAsset, MediaVerificationResult

logger = logging.getLogger(__name__)

VALID_TYPES = ("code_match", "chastity_closed")

SYSTEM_PROMPT = """\
You are a careful photo verification assistant for a private personal system.
You look at ONE photo and answer a single verification question with JSON.

Rules:
1. Be honest — if the photo is unclear, blurry, or the object is not visible,
   say verdict "unclear" with low confidence.
2. Never invent details that are not visible in the photo.
3. Do not describe intimate content explicitly; describe only what is needed
   to justify the verdict (e.g. "code visible", "lock appears closed").
4. Output ONLY JSON in this exact shape:
{{
  "verdict": "match" | "mismatch" | "unclear",
  "confidence": 0-100,
  "reasoning": "<1-2 sentences>"
}}
"""

_CODE_MATCH_PROMPT = (
    "The photo should show a verification code. "
    "Expected code: {expected}. "
    "Does the code shown in the photo match the expected code? "
    "Compare character by character. If the code is unreadable, verdict=unclear."
)

# Для challenge-based проверки: LLM читает код с фото, сервер сверяет HMAC.
_READ_CODE_PROMPT = (
    "The photo should show a verification code. "
    "Read the code exactly as shown, character by character. "
    "If the code is unreadable or not visible, set read_code to null.\n"
    'Response JSON: {{"read_code": "<code or null>", "confidence": 0-100, "reasoning": "..."}}'
)

_CHASTITY_PROMPT = (
    "The photo should show a chastity/lock device. "
    "Is the device visibly closed and locked? "
    "If the device/status is not visible, verdict=unclear."
)


def _image_to_data_url(file_path: str) -> str | None:
    """Load an image from the private upload store and return a data URL."""
    if not file_path or not file_path.startswith("/uploads/"):
        return None
    rel = file_path[len("/uploads/") :]
    base = Path(settings.upload_dir).resolve()
    candidate = (base / rel).resolve()
    if not str(candidate).startswith(str(base) + "/"):
        return None
    if not candidate.is_file():
        return None
    data = candidate.read_bytes()
    mime = "image/jpeg"
    if candidate.suffix.lower() == ".png":
        mime = "image/png"
    elif candidate.suffix.lower() == ".webp":
        mime = "image/webp"
    elif candidate.suffix.lower() == ".gif":
        mime = "image/gif"
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def _user_prompt(verification_type: str, expected_code: str | None, read_mode: bool = False) -> str:
    if verification_type == "chastity_closed":
        return _CHASTITY_PROMPT
    if read_mode:
        return _READ_CODE_PROMPT
    return _CODE_MATCH_PROMPT.format(expected=expected_code or "")


def _parse_verdict(raw: str) -> tuple[str, int, str]:
    """Parse LLM JSON → (verdict, confidence, reasoning). Defaults to unclear."""
    try:
        parsed = parse_llm_json(raw, is_last_attempt=True)
    except Exception:
        return "unclear", 0, ""
    if not isinstance(parsed, dict):
        return "unclear", 0, ""
    verdict = str(parsed.get("verdict", "unclear")).strip().lower()
    if verdict not in ("match", "mismatch", "unclear"):
        verdict = "unclear"
    try:
        confidence = int(parsed.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0
    confidence = max(0, min(100, confidence))
    reasoning = str(parsed.get("reasoning", ""))[:2000]
    return verdict, confidence, reasoning


async def verify_media_with_llm(
    db: AsyncSession,
    user_id: uuid.UUID,
    llm_config: LLMProviderConfig,
    media: MediaAsset,
    verification_type: str,
    expected_code: str | None = None,
    locale: str = "en",
    challenge=None,
    ocr_info: dict | None = None,
) -> MediaVerificationResult:
    """Run an LLM photo-evaluation and persist the result row.

    Expected code is NOT persisted plaintext — only its HMAC.

    When ``challenge`` (VerificationChallenge) is provided for ``code_match``,
    the LLM is asked to READ the code from the photo and the server compares
    it against the challenge HMAC (constant-time). The verdict is then
    server-derived (HMAC is the authority); the LLM is the OCR reader.

    When ``ocr_info`` is provided (ADR-181), it's logged in reasoning for audit.
    """
    if verification_type not in VALID_TYPES:
        raise ValueError(f"Unsupported verification_type: {verification_type}")

    read_mode = verification_type == "code_match" and challenge is not None

    image_url = _image_to_data_url(media.file_path)
    if image_url is None:
        raise FileNotFoundError("Media file not found on disk")

    user_prompt = _user_prompt(verification_type, expected_code, read_mode=read_mode)
    if locale:
        user_prompt += f"\nRespond in {locale} language."

    result = await client.call_llm(
        config=llm_config,
        system_prompt=SYSTEM_PROMPT,
        user_message=user_prompt,
        json_mode=True,
        images=[image_url],
    )
    raw = result.get("content", "")

    from app.services.media import compute_code_hmac, verify_code_constant_time

    expected_hmac = None
    verdict: str
    confidence: int
    reasoning: str

    if read_mode and challenge is not None:
        # Сервер — авторитет: HMAC-сверка прочитанного LLM кода.
        try:
            parsed = parse_llm_json(raw, is_last_attempt=True)
        except Exception:
            parsed = {}
        if not isinstance(parsed, dict):
            parsed = {}
        read_code = str(parsed.get("read_code") or "").strip()
        try:
            confidence = int(parsed.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0
        confidence = max(0, min(100, confidence))
        reasoning = str(parsed.get("reasoning", ""))[:2000]
        expected_hmac = challenge.code_hmac
        if not read_code:
            verdict = "unclear"
        elif verify_code_constant_time(read_code, challenge.code_hmac):
            verdict = "match"
        else:
            verdict = "mismatch"
    else:
        verdict, confidence, reasoning = _parse_verdict(raw)
        if verification_type == "code_match" and expected_code:
            expected_hmac = compute_code_hmac(expected_code)

    row = MediaVerificationResult(
        owner_id=user_id,
        media_id=media.id,
        verification_type=verification_type,
        expected_code_hmac=expected_hmac,
        verdict=verdict,
        confidence=confidence,
        reasoning=reasoning or None,
        llm_model=llm_config.model_name,
    )
    db.add(row)

    usage = result.get("usage", {})
    llm_config.total_tokens += usage.get("total_tokens", 0)
    llm_config.total_cost += usage.get("cost", 0.0)
    db.add(llm_config)
    await db.flush()
    return row


async def find_active_challenge(
    db: AsyncSession,
    user_id: uuid.UUID,
    owner_type: str,
    owner_ref_id: uuid.UUID,
) -> object | None:
    """Find an active VerificationChallenge for the given owner (if any)."""
    from datetime import UTC, datetime

    from app.models.media import VerificationChallenge
    from app.timeutils import as_utc

    result = await db.execute(
        select(VerificationChallenge).where(
            VerificationChallenge.owner_id == user_id,
            VerificationChallenge.owner_type == owner_type,
            VerificationChallenge.owner_ref_id == owner_ref_id,
            VerificationChallenge.state == "active",
        )
    )
    challenge = result.scalar_one_or_none()
    if challenge is None:
        return None
    now = datetime.now(UTC)
    expires = as_utc(challenge.expires_at)
    if expires < now:
        challenge.state = "expired"
        await db.flush()
        return None
    return challenge
