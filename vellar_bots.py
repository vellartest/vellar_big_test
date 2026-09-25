# vellar_bots.py
import random
from vellar_core import VellarGame, RESOURCES, QUESTS, BUILDINGS, Player

BOT_PRESETS = [
    {"name":"🤖 Торговец Лёва",  "strategy":"trader"},
    {"name":"🤖 Строитель Гоша", "strategy":"builder"},
    {"name":"🤖 Пират Соня",     "strategy":"aggressive"},
    {"name":"🤖 Скопидом Эдик",  "strategy":"hoarder"},
]

class BotBrain:
    def __init__(self, game: VellarGame):
        self.game = game

    def spawn_all(self):
        for preset in BOT_PRESETS:
            n = preset["name"]
            if n in self.game.players: continue
            p = Player(name=n, is_bot=True, strategy=preset["strategy"], balance=5000)
            self.game.players[n] = p

    def tick(self):
        for name, p in list(self.game.players.items()):
            if not p.is_bot: continue
            try: self._act(name, p)
            except Exception: continue

    def _act(self, name, p):
        strat = p.strategy
        if not p.territories and p.balance >= 1000:
            self._try_buy_territory(name, p)
        self._try_upgrade(name, p, strat)
        self._try_build(name, p, strat)
        if strat in ("trader", "hoarder"):
            self._try_sell_surplus(name, p)
            self._try_buy_bargain(name, p)
        else:
            self._try_sell_surplus(name, p)
        self._try_quests(name, p)
        if strat == "aggressive":
            self._try_raid(name, p)
        self._try_vote(name, p, strat)
        self._try_alliance(name, p, strat)

    def _try_buy_territory(self, name, p):
        free = [t for t in self.game.territories if not t.owner]
        if not free: return
        if p.strategy == "aggressive":
            target = max(free, key=lambda t: t.price)
        elif p.strategy == "hoarder":
            target = min(free, key=lambda t: t.price)
        else:
            target = random.choice(free)
        if p.balance >= target.price:
            self.game.buy_territory(name, target.id)

    def _try_upgrade(self, name, p, strat):
        for tid in p.territories:
            t = self.game._territory(tid)
            if not t: continue
            for i, b in enumerate(t.businesses):
                cost = b.upgrade_cost()
                threshold = {"builder":2.0, "trader":3.0,
                             "aggressive":1.5, "hoarder":5.0}.get(strat, 3.0)
                if b.level < b.spec["max_level"] and p.balance > cost * threshold:
                    if random.random() < 0.5:
                        self.game.upgrade(name, tid, i)

    def _try_build(self, name, p, strat):
        prefer = {"builder":["school","bank","market","hospital"],
                  "trader":["market","bank","hospital","school"],
                  "aggressive":["hospital","bank","school","market"],
                  "hoarder":["bank","market","hospital","school"]}[strat]
        for tid in p.territories:
            t = self.game._territory(tid)
            if not t or t.building: continue
            for key in prefer:
                if p.balance > BUILDINGS[key]["cost"] * 1.5:
                    self.game.build(name, tid, key)
                    return

    def _try_sell_surplus(self, name, p):
        for r, amt in list(p.resources.items()):
            if amt <= 20: continue
            sell = amt - 20
            price = max(1, int(RESOURCES[r].price * 1.05))
            if any(o.seller == name and o.resource == r
                   for o in self.game.market_orders): continue
            self.game.place_order(name, r, sell, price)

    def _try_buy_bargain(self, name, p):
        for o in list(self.game.market_orders):
            if o.seller == name: continue
            r = RESOURCES[o.resource]
            if o.price_per_unit < r.base_price * 0.9:
                amount = min(o.amount, max(1, p.balance // (o.price_per_unit * 2)))
                if amount > 0 and p.balance >= amount * o.price_per_unit:
                    self.game.buy_order(name, o.id, amount)

    def _try_quests(self, name, p):
        for q in QUESTS:
            if q.id in p.completed_quests: continue
            if all(p.resources.get(r,0) >= n for r,n in q.need.items()):
                self.game.complete_quest(name, q.id)
                return

    def _try_raid(self, name, p):
        if self.game.tick - p.last_raid_tick < 5: return
        targets = []
        for t in self.game.territories:
            if not t.owner or t.owner == name: continue
            d = self.game.players.get(t.owner)
            if not d: continue
            if p.alliance and p.alliance == d.alliance: continue
            ap = p.total_power(self.game.territories) + 1
            dp = d.total_power([t]) + 1
            chance = ap / (ap + dp)
            if chance > 0.55: targets.append((t, chance))
        if targets and random.random() < 0.4:
            t,_ = random.choice(targets)
            self.game.raid(name, t.id)

    def _try_vote(self, name, p, strat):
        if not p.territories: return
        for v in self.game.votes.values():
            if v.closed or name in v.votes_for or name in v.votes_against: continue
            side = "against" if strat in ("builder","trader","aggressive") else "for"
            self.game.cast_vote(name, v.id, side)

    def _try_alliance(self, name, p, strat):
        if p.alliance: return
        if strat == "aggressive":
            if random.random() < 0.03:
                self.game.create_alliance(name, f"Клан {name[-6:]}")
        else:
            for title, al in self.game.alliances.items():
                if al.leader != name and self.game.players[al.leader].is_bot:
                    self.game.invite_alliance(al.leader, name)
                    self.game.accept_alliance(name, title)
                    break
