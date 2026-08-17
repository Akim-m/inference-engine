from config import settings
from worker.memory import load_history, append_turn, render_user_turn

CID = "11111111-1111-4111-8111-111111111111"


def _key():
    return f"chat:conv:{CID}"


def test_load_history_unknown_conversation_returns_empty(fake_redis):
    assert load_history(fake_redis, CID, 2800) == []


def test_append_then_load_round_trip(fake_redis):
    append_turn(fake_redis, CID, "q1", "a1")
    assert load_history(fake_redis, CID, 2800) == [
        {"role": "user", "text": "q1"},
        {"role": "assistant", "text": "a1"},
    ]


def test_append_trims_user_and_assistant_text(fake_redis):
    append_turn(fake_redis, CID, "u" * 401, "a" * 800)
    entries = load_history(fake_redis, CID, 100000)
    assert len(entries[0]["text"]) == 400
    assert len(entries[1]["text"]) == 700


def test_char_budget_keeps_newest_first(fake_redis):
    # 3 turns => 6 entries, each text exactly 100 chars.
    for i in range(3):
        append_turn(fake_redis, CID, f"u{i}".ljust(100, "."), f"a{i}".ljust(100, "."))
    kept = load_history(fake_redis, CID, char_budget=250)
    # newest-first accumulation: 100 + 100 = 200 <= 250, next would be 300 > 250.
    assert len(kept) == 2
    # returned in chronological order: turn-2's user then assistant.
    assert kept[0]["text"].startswith("u2")
    assert kept[1]["text"].startswith("a2")


def test_ltrim_caps_total_entries(fake_redis, monkeypatch):
    monkeypatch.setattr(settings, "chat_memory_max_turns", 4)
    for i in range(4):  # 4 turns => 8 entries, capped to the last 4
        append_turn(fake_redis, CID, f"q{i}", f"a{i}")
    assert fake_redis.llen(_key()) == 4
    kept = load_history(fake_redis, CID, 100000)
    # only the two newest exchanges survive the cap, chronological.
    assert [e["text"] for e in kept] == ["q2", "a2", "q3", "a3"]


def test_ttl_set_and_refreshed_on_append(fake_redis):
    append_turn(fake_redis, CID, "q1", "a1")
    assert fake_redis.ttl(_key()) == settings.chat_memory_ttl_seconds
    append_turn(fake_redis, CID, "q2", "a2")
    assert fake_redis.ttl(_key()) == settings.chat_memory_ttl_seconds


def test_render_user_turn_with_image():
    assert render_user_turn("what is this?", had_image=True) == "[shared a medical image] what is this?"


def test_render_user_turn_without_image():
    assert render_user_turn("what is this?", had_image=False) == "what is this?"
