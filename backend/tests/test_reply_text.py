"""A looping closing offer is clipped; a normal money answer is left alone."""

from app.agent.reply_text import clip_reply
from app.agent.providers import OpenRouterAgentClient
from app.services.chat_service import MAX_HISTORY_CHARS, _history_content


def test_clip_reply_keeps_a_short_answer():
    reply = (
        "By month-end you typically bank about **$2,487** a month.\n\n"
        "- May +$3,604 · Jun +$1,409 · Jul +$6,832\n\n"
        "September went negative. Worth watching whether Oct ends in the red."
    )
    assert clip_reply(reply) == reply


def test_clip_reply_drops_a_repeated_closing_offer():
    offer = (
        "That's a confident pace; I can set up the goal so it's tracked. "
        "Want a monthly cap on a category instead? I can stand up a Shopping cap so big one-offs flag earlier. "
        "Give me a number and I'll draft it. "
    )
    head = (
        "By month-end you typically bank about **$2,487** a month "
        "(average of the last 5 full months, May–Sep).\n\n"
        "The backlog is healthy; the monthly pace is slipping. "
    )
    looping = head + offer * 12
    clipped = clip_reply(looping)
    assert len(clipped) < 800
    assert clipped.startswith("By month-end you typically bank")
    assert clipped.count("Give me a number and I'll draft it.") <= 1
    assert "so it's tracked." in clipped  # first copy of the offer can stay


def test_clip_reply_caps_a_long_non_looping_ramble():
    sentence = "Here is another distinct observation about this month's cash flow numbered {}."
    ramble = " ".join(sentence.format(i) for i in range(80))
    clipped = clip_reply(ramble)
    assert len(clipped) <= 2500
    assert clipped.startswith("Here is another distinct observation")
    assert clipped.endswith(".")


def test_history_content_trims_a_looping_past_reply():
    blob = "x" * (MAX_HISTORY_CHARS + 500)
    trimmed = _history_content(blob)
    assert len(trimmed) <= MAX_HISTORY_CHARS + 1  # ellipsis
    assert trimmed.endswith("…")


def test_openrouter_default_output_cap_is_a_short_reply(monkeypatch):
    client = OpenRouterAgentClient(api_key="key", model="some/model")
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        from types import SimpleNamespace

        message = SimpleNamespace(
            content="hi",
            tool_calls=None,
            model_dump=lambda exclude_none=True: {"role": "assistant", "content": "hi"},
        )
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    monkeypatch.setattr(client._client.chat.completions, "create", fake_create)
    client.run_turn("system", [], [{"role": "user", "content": "hello"}], lambda n, a: {})
    assert captured["max_tokens"] == 1024
