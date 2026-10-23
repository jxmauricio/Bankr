"""Clip a model reply that started repeating itself.

Some hosts (DeepSeek via OpenRouter, with a large output cap) finish the
answer and then loop on the same closing offer for tens of thousands of
characters. The prompt already asks for ~6 lines; this is the structural
backstop so a stuck sample never reaches the user or the next turn's history.
"""

from __future__ import annotations

import re

# A 6-line money answer is a few hundred characters. Past this, even a
# non-looping ramble is more than the chat UI is built for.
_MAX_CHARS = 2500
_SENTENCE = re.compile(r".+?(?:[.!?](?:\s+|$)|$)", re.S)


def clip_reply(text: str) -> str:
    """Drop a looping tail, then cap overall length at a sentence boundary."""
    if not text:
        return text
    text = _clip_repeated_span(text)
    text = _clip_repeated_sentence(text)
    if len(text) <= _MAX_CHARS:
        return text
    cut = text[:_MAX_CHARS]
    boundary = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "), cut.rfind("\n"))
    if boundary > _MAX_CHARS // 2:
        cut = cut[: boundary + 1]
    return cut.rstrip()


def _clip_repeated_sentence(text: str) -> str:
    seen: set[str] = set()
    pos = 0
    for match in _SENTENCE.finditer(text):
        key = re.sub(r"\s+", " ", match.group()).strip().lower()
        if len(key) >= 48 and key in seen:
            return text[:pos].rstrip()
        if len(key) >= 48:
            seen.add(key)
        pos = match.end()
    return text


def _clip_repeated_span(text: str, span: int = 72) -> str:
    if len(text) < span * 3:
        return text
    seen_at: dict[str, int] = {}
    for i in range(0, len(text) - span + 1):
        window = text[i : i + span]
        if window in seen_at:
            return text[:i].rstrip()
        seen_at[window] = i
    return text
