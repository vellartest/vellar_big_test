# test_vellar.py
import pytest
from pathlib import Path
from vellar_core import VellarGame, RESOURCES, BUILDINGS, QUESTS
from vellar_bots import BotBrain

@pytest.fixture
def game(tmp_path, monkeypatch):
    monkeypatch.setattr(VellarGame, "AUTOSAVE_PATH", tmp_path / "save.json")
    return VellarGame()

def test_register_and_login(game):
    assert game.register("Alice", "pass123") == "OK"
    assert game.login("Alice", "pass123")
    assert game.login("Alice", "wrong") is None

def test_duplicate_name(game):
    game.register("Alice", "pass123")
    assert game.register("Alice", "pass456") != "OK"

def test_short_password(game):
    assert game.register("Bob", "1") != "OK"

def test_buy_territory(game):
    game.register("Alice", "pass123")
    p = game.players["Alice"]; p.balance = 10000
    assert "Куплена" in game.buy_territory("Alice", 1)
    assert game.territories[0].owner == "Alice"

def test_buy_too_expensive(game):
    game.register("Alice", "pass123")
    game.players["Alice"].balance = 10
    assert "Нужно" in game.buy_territory("Alice", 5)

def test_upgrade_business(game):
    game.register("Alice", "pass123")
    p = game.players["Alice"]; p.balance = 10000
    game.buy_territory("Alice", 1)
    b = game.territories[0].businesses[0]
    before = b.level
    assert "Уровень" in game.upgrade("Alice", 1, 0)
    assert b.level == before + 1

def test_upgrade_max_level(game):
    game.register("Alice", "pass123")
    p = game.players["Alice"]; p.balance = 10**9
    game.buy_territory("Alice", 1)
    b = game.territories[0].businesses[0]
    for _ in range(b.spec["max_level"] - 1):
        game.upgrade("Alice", 1, 0)
    assert game.upgrade("Alice", 1, 0) == "Максимум"

def test_build(game):
    game.register("Alice", "pass123")
    p = game.players["Alice"]; p.balance = 10000
    game.buy_territory("Alice", 1)
    assert "Построено" in game.build("Alice", 1, "school")
    assert game.territories[0].building == "school"

def test_build_twice(game):
    game.register("Alice", "pass123")
    p = game.players["Alice"]; p.balance = 10**6
    game.buy_territory("Alice", 1)
    game.build("Alice", 1, "school")
    assert "Уже есть" in game.build("Alice", 1, "bank")

def test_hire(game):
    game.register("A", "pass123"); game.register("B", "pass123")
    game.players["A"].balance = 10000
    game.buy_territory("A", 1)
    assert "Нанят" in game.hire("A", "B", 1, 50)
    assert game.players["B"].job == 1

def test_market_order_and_buy(game):
    game.register("A","pass123"); game.register("B","pass123")
    game.players["A"].add_resource("wood", 100)
    o = game.place_order("A", "wood", 50, 10)
    oid = int(o.split("#")[1])
    assert "Куплено" in game.buy_order("B", oid, 30)
    assert game.players["B"].resources["wood"] == 30

def test_market_price_moves(game):
    game.register("A","pass123")
    game.players["A"].add_resource("wood", 1000)
    base = RESOURCES["wood"].current_price
    game.place_order("A", "wood", 1000, 5)
    assert RESOURCES["wood"].current_price < base

def test_take_loan(game):
    game.register("A","pass123")
    p = game.players["A"]
    r = game.take_loan("A", 1000, 10)
    assert "Кредит" in r
    assert p.balance == 1500 + 1000

def test_loan_over_limit(game):
    game.register("A","pass123")
    assert "Лимит" in game.take_loan("A", 4000, 10)

def test_vote(game):
    game.register("A","pass123")
    game.players["A"].balance = 10000
    game.buy_territory("A", 1)
    v = game.propose_vote("A", "income_tax", 0.15)
    vid = int(v.split("#")[1])
    game.cast_vote("A", vid, "for")
    for _ in range(5): game.tick_economy()
    assert game.state.income_tax == 0.15

def test_raid_cooldown(game, monkeypatch):
    game.register("A","pass123"); game.register("B","pass123")
    game.players["A"].balance = 10**6; game.players["B"].balance = 10**6
    game.buy_territory("A", 1); game.buy_territory("B", 2)
    monkeypatch.setattr("vellar_core.random.random", lambda: 0.0)
    assert "Успех" in game.raid("A", 2)
    assert "Кулдаун" in game.raid("A", 2)

def test_alliance_flow(game):
    game.register("A","pass123"); game.register("B","pass123")
    assert "Альянс" in game.create_alliance("A", "Солнце")
    assert "Приглашение" in game.invite_alliance("A", "B")
    assert "Альянсе" in game.accept_alliance("B", "Солнце")
    assert game.players["B"].alliance == "Солнце"

def test_history_records_tick(game):
    game.register("A", "pass123")
    game.tick_economy(); game.tick_economy()
    assert len(game.tick_marks) >= 2
    assert len(game.treasury_history) >= 2

def test_bots_spawn(game):
    bots = BotBrain(game); bots.spawn_all()
    bot_players = [p for p in game.players.values() if p.is_bot]
    assert len(bot_players) == 4

def test_bots_take_turn(game):
    bots = BotBrain(game); bots.spawn_all()
    for p in game.players.values():
        if p.is_bot: p.balance = 10**6
    before = len([t for t in game.territories if t.owner])
    for _ in range(10): bots.tick()
    after = len([t for t in game.territories if t.owner])
    assert after > before

def test_save_and_load(game, monkeypatch):
    game.register("Alice", "pass123")
    game.players["Alice"].balance = 10**6
    game.buy_territory("Alice", 1)
    game.players["Alice"].add_resource("wood", 42)
    game.save()
    monkeypatch.setattr(VellarGame, "AUTOSAVE_PATH", game.AUTOSAVE_PATH)
    g2 = VellarGame()
    assert "Alice" in g2.players
    assert g2.players["Alice"].resources.get("wood") == 42
