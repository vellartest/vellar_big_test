# vellar_core.py
import random, json, hashlib, secrets
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Set
from pathlib import Path

# ==================== РЕСУРСЫ ====================
@dataclass
class Resource:
    key: str; name: str; base_price: int; current_price: float = 0.0
    def __post_init__(self):
        if self.current_price == 0.0: self.current_price = float(self.base_price)
    @property
    def price(self) -> int: return max(1, round(self.current_price))

RESOURCES: Dict[str, Resource] = {
    "wood":     Resource("wood",     "Древесина",    5),
    "stone":    Resource("stone",    "Камень",       7),
    "iron":     Resource("iron",     "Железо",       15),
    "oil":      Resource("oil",      "Нефть",        40),
    "gold_ore": Resource("gold_ore", "Золотая руда", 80),
    "crystal":  Resource("crystal",  "Кристалл",     150),
}

# ==================== БИЗНЕСЫ ====================
BUSINESS_TYPES = {
    "small":  {"name":"Малый бизнес",   "base_income":25,   "max_workers":2,
               "upgrade_cost":300,   "max_level":5,  "produces":["wood","stone"]},
    "medium": {"name":"Средний бизнес", "base_income":180,  "max_workers":5,
               "upgrade_cost":2500,  "max_level":7,  "produces":["iron","oil"]},
    "large":  {"name":"Крупный бизнес", "base_income":1500, "max_workers":15,
               "upgrade_cost":20000, "max_level":10, "produces":["gold_ore","crystal"]},
}

@dataclass
class Business:
    biz_type: str
    level: int = 1
    owner: Optional[str] = None
    workers: List[str] = field(default_factory=list)
    @property
    def spec(self): return BUSINESS_TYPES[self.biz_type]
    def income(self, bonus=0.0):
        return int(self.spec["base_income"]*(1+0.35*(self.level-1))*(1+bonus))
    def upgrade_cost(self): return int(self.spec["upgrade_cost"]*self.level)
    def power(self): return self.level*(1+0.5*len(self.workers))
    def produce(self, spec=None, bonus=0.0):
        wf = (1+0.5*len(self.workers))*(1+bonus)
        return {r: int(random.randint(1,3)*self.level*wf*(1.5 if spec==r else 1.0))
                for r in self.spec["produces"]}

# ==================== ПОСТРОЙКИ ====================
BUILDINGS = {
    "bank":     {"name":"Банк",     "cost":3000, "desc":"+50% к лимиту кредита"},
    "school":   {"name":"Школа",    "cost":2500, "desc":"+25% к добыче и доходу"},
    "hospital": {"name":"Больница", "cost":2000, "desc":"-50% потерь от рейдов"},
    "market":   {"name":"Рынок",    "cost":1500, "desc":"-2% налог с продаж"},
}

# ==================== ТЕРРИТОРИЯ ====================
@dataclass
class Territory:
    id: int; name: str; price: int; specialization: str
    owner: Optional[str] = None
    businesses: List[Business] = field(default_factory=list)
    building: Optional[str] = None

# ==================== ИГРОК ====================
@dataclass
class Player:
    name: str
    password_hash: str = ""
    salt: str = ""
    balance: int = 1500
    resources: Dict[str,int] = field(default_factory=dict)
    territories: List[int] = field(default_factory=list)
    job: Optional[int] = None
    salary: int = 0
    completed_quests: List[int] = field(default_factory=list)
    votes: Dict[int,str] = field(default_factory=dict)
    last_raid_tick: int = -999
    alliance: Optional[str] = None
    is_bot: bool = False
    strategy: str = "human"

    def add_resource(self, r, amt): self.resources[r] = self.resources.get(r,0) + amt
    def take_resource(self, r, amt):
        if self.resources.get(r,0) < amt: return False
        self.resources[r] -= amt
        if self.resources[r] == 0: del self.resources[r]
        return True
    def total_power(self, territories):
        p = 0.0
        for tid in self.territories:
            t = next((x for x in territories if x.id == tid), None)
            if t: p += sum(b.power() for b in t.businesses)
        return p
    def total_wealth(self, territories):
        w = self.balance
        for r,a in self.resources.items():
            if r in RESOURCES: w += a * RESOURCES[r].price
        for tid in self.territories:
            t = next((x for x in territories if x.id == tid), None)
            if t: w += t.price
        return w

# ==================== АЛЬЯНС ====================
@dataclass
class Alliance:
    id: int; name: str; leader: str
    members: Set[str] = field(default_factory=set)
    treasury: int = 0
    invites: Set[str] = field(default_factory=set)
    last_raid_tick: int = -999

# ==================== ГОСУДАРСТВО ====================
@dataclass
class State:
    treasury: int = 20000
    income_tax: float = 0.10
    sales_tax: float = 0.05
    salary_tax: float = 0.05
    total_collected: int = 0

@dataclass
class Vote:
    id: int; topic: str; new_value: float
    votes_for: Set[str] = field(default_factory=set)
    votes_against: Set[str] = field(default_factory=set)
    ticks_left: int = 5
    closed: bool = False

@dataclass
class StateOrder:
    id: int; resource: str; amount: int; price_per_unit: int; expires_in: int = 4

# ==================== РЫНОК / БАНК ====================
@dataclass
class Order:
    id: int; seller: str; resource: str; amount: int; price_per_unit: int

@dataclass
class Loan:
    id: int; borrower: str; principal: int; total_due: int
    payment_per_tick: int; ticks_left: int

# ==================== КВЕСТЫ ====================
@dataclass
class Quest:
    id: int; title: str; need: Dict[str,int]; reward_money: int
    reward_resources: Dict[str,int] = field(default_factory=dict)

QUESTS = [
    Quest(1,"Первая поставка",   {"wood":20},     200,  {"stone":5}),
    Quest(2,"Металлургия",       {"iron":30},     800,  {"oil":5}),
    Quest(3,"Нефтяной контракт", {"oil":25},      1500, {"crystal":1}),
    Quest(4,"Золотая жила",      {"gold_ore":15}, 4000, {"crystal":3}),
]

# ==================== ЯДРО ====================
def _hash(pwd, salt): return hashlib.sha256((salt+pwd).encode()).hexdigest()

class VellarGame:
    MAX_DEBT = 5000
    AUTOSAVE_PATH = Path("vellar_save.json")
    HISTORY_LEN = 120

    def __init__(self):
        self.players: Dict[str,Player] = {}
        self.territories: List[Territory] = []
        self.alliances: Dict[str,Alliance] = {}
        self.state = State()
        self.market_orders: List[Order] = []
        self.state_orders: List[StateOrder] = []
        self.loans: Dict[int,Loan] = {}
        self.votes: Dict[int,Vote] = {}
        self.tick = 0
        self.log: List[str] = []
        self._oid = self._lid = self._vid = self._soid = self._aid = 1

        self.price_history: Dict[str, deque] = {k: deque(maxlen=self.HISTORY_LEN)
                                                 for k in RESOURCES}
        self.treasury_history: deque = deque(maxlen=self.HISTORY_LEN)
        self.power_history: Dict[str, deque] = {}
        self.wealth_history: Dict[str, deque] = {}
        self.total_wealth_history: deque = deque(maxlen=self.HISTORY_LEN)
        self.vote_history: List[dict] = []
        self.raid_history: List[dict] = []
        self.tick_marks: deque = deque(maxlen=self.HISTORY_LEN)

        if not self._load():
            self._init_world()
        self._seed_history()

    def _seed_history(self):
        if not self.tick_marks:
            self._record_history()

    def _init_world(self):
        seeds = [
            ("Северный округ",      800, "wood"),
            ("Порт Аврора",        1500, "stone"),
            ("Промзона-7",         4000, "iron"),
            ("Нефтяное плато",     9000, "oil"),
            ("Золотые холмы",     20000, "gold_ore"),
            ("Кристальная долина",35000, "crystal"),
        ]
        for i,(n,p,s) in enumerate(seeds, start=1):
            biz = Business("small") if i<=2 else Business("medium") if i<=4 else Business("large")
            self.territories.append(Territory(i,n,p,s,None,[biz],None))

    def _log(self, msg):
        self.log.append(msg)
        if len(self.log) > 200: self.log = self.log[-200:]

    def register(self, name, password):
        name = name.strip()[:24]
        if not name or len(password) < 4: return "Имя непустое, пароль минимум 4 символа"
        if name in self.players: return "Имя занято"
        salt = secrets.token_hex(8)
        self.players[name] = Player(name=name, salt=salt, password_hash=_hash(password, salt))
        self._log(f"🎉 {name} зарегистрировался")
        return "OK"

    def login(self, name, password):
        p = self.players.get(name.strip()[:24])
        if not p or p.is_bot: return None
        if _hash(password, p.salt) != p.password_hash: return None
        return secrets.token_urlsafe(24)

    def buy_territory(self, name, tid):
        p,t = self.players[name], self._territory(tid)
        if not t: return "Не найдена"
        if t.owner: return "Уже куплена"
        if p.balance < t.price: return f"Нужно {t.price}💰"
        p.balance -= t.price; t.owner = name; p.territories.append(t.id)
        for b in t.businesses: b.owner = name
        self._log(f"🏞 {name} купил «{t.name}» за {t.price}💰")
        return f"Куплена «{t.name}»"

    def upgrade(self, name, tid, idx):
        t = self._territory(tid)
        if not t or t.owner != name: return "Не ваша территория"
        if not (0 <= idx < len(t.businesses)): return "Нет такого бизнеса"
        b = t.businesses[idx]
        if b.level >= b.spec["max_level"]: return "Максимум"
        cost = b.upgrade_cost()
        if self.players[name].balance < cost: return f"Нужно {cost}💰"
        self.players[name].balance -= cost; b.level += 1
        self._log(f"⬆ {name}: бизнес в «{t.name}» → lvl{b.level}")
        return f"Уровень {b.level}"

    def build(self, name, tid, key):
        t = self._territory(tid)
        if not t or t.owner != name: return "Не ваша территория"
        if key not in BUILDINGS: return "Нет такой постройки"
        if t.building: return f"Уже есть {BUILDINGS[t.building]['name']}"
        cost = BUILDINGS[key]["cost"]
        if self.players[name].balance < cost: return f"Нужно {cost}💰"
        self.players[name].balance -= cost; t.building = key
        self._log(f"🏗 {name} построил {BUILDINGS[key]['name']} в «{t.name}»")
        return f"Построено: {BUILDINGS[key]['name']}"

    def hire(self, employer, worker, tid, salary):
        w = self.players.get(worker); t = self._territory(tid)
        if not w: return "Работник не найден"
        if not t or t.owner != employer: return "Не ваша территория"
        if w.job is not None: return "Уже трудоустроен"
        for b in t.businesses:
            if len(b.workers) < b.spec["max_workers"]:
                b.workers.append(worker); w.job = t.id; w.salary = salary
                self._log(f"👔 {employer} нанял {worker} за {salary}💰/тик")
                return "Нанят"
        return "Нет мест"

    def quit_job(self, name):
        p = self.players[name]
        if p.job is None: return "Вы не работаете"
        for t in self.territories:
            for b in t.businesses:
                if name in b.workers: b.workers.remove(name)
        p.job = None; p.salary = 0
        return "Уволен"

    def place_order(self, seller, resource, amount, price):
        p = self.players[seller]
        if resource not in RESOURCES or amount <= 0 or price <= 0: return "Некорректно"
        if not p.take_resource(resource, amount): return "Недостаточно"
        o = Order(self._oid, seller, resource, amount, price); self._oid += 1
        self.market_orders.append(o)
        RESOURCES[resource].current_price *= (1 - 0.0005*amount)
        self._log(f"📜 {seller} выставил {amount} {RESOURCES[resource].name} по {price}💰")
        return f"Ордер #{o.id}"

    def cancel_order(self, name, oid):
        for o in self.market_orders:
            if o.id == oid and o.seller == name:
                self.players[name].add_resource(o.resource, o.amount)
                self.market_orders.remove(o); return "Снят"
        return "Не найден"

    def buy_order(self, buyer, oid, amount):
        for o in self.market_orders:
            if o.id != oid: continue
            if o.seller == buyer: return "Своё не покупают"
            amount = min(amount, o.amount)
            total = amount * o.price_per_unit
            b = self.players[buyer]
            if b.balance < total: return "Мало средств"
            tax_rate = self.state.sales_tax
            for t in self.territories:
                if t.owner == o.seller and t.building == "market":
                    tax_rate = max(0, tax_rate - 0.02); break
            tax = int(total * tax_rate)
            b.balance -= total
            self.players[o.seller].balance += (total - tax)
            self.state.treasury += tax; self.state.total_collected += tax
            b.add_resource(o.resource, amount)
            RESOURCES[o.resource].current_price *= (1 + 0.001*amount)
            o.amount -= amount
            if o.amount == 0: self.market_orders.remove(o)
            self._log(f"💸 {buyer} купил {amount} {RESOURCES[o.resource].name} у {o.seller}")
            return f"Куплено {amount} за {total}💰"
        return "Ордер не найден"

    def take_loan(self, name, amount, ticks):
        if ticks not in (5,10,20) or amount <= 0: return "Сроки: 5/10/20"
        limit = self.MAX_DEBT
        for tid in self.players[name].territories:
            t = self._territory(tid)
            if t and t.building == "bank": limit = int(limit*1.5); break
        total = int(amount * (1 + 0.01*ticks))
        debt = sum(l.total_due for l in self.loans.values() if l.borrower == name)
        if debt + total > limit: return f"Лимит {limit}💰"
        pay = max(1, total // ticks)
        loan = Loan(self._lid, name, amount, total, pay, ticks); self._lid += 1
        self.loans[loan.id] = loan
        self.players[name].balance += amount
        self._log(f"🏦 {name} взял кредит {amount}💰 / {ticks} тиков")
        return f"Кредит #{loan.id}: к возврату {total}💰"

    def complete_quest(self, name, qid):
        q = next((x for x in QUESTS if x.id == qid), None)
        p = self.players[name]
        if not q or qid in p.completed_quests: return "Недоступен"
        for r,n in q.need.items():
            if p.resources.get(r,0) < n: return f"Не хватает {RESOURCES[r].name}"
        for r,n in q.need.items(): p.take_resource(r,n)
        p.balance += q.reward_money
        for r,n in q.reward_resources.items(): p.add_resource(r,n)
        p.completed_quests.append(qid)
        self._log(f"✅ {name} выполнил «{q.title}»")
        return f"+{q.reward_money}💰"

    def propose_vote(self, name, topic, value):
        p = self.players[name]
        if not p.territories: return "Только владельцы территорий"
        if topic not in ("income_tax","sales_tax","salary_tax"): return "Неверная тема"
        if not (0 <= value <= 0.5): return "Диапазон [0; 0.5]"
        v = Vote(self._vid, topic, value); self._vid += 1
        self.votes[v.id] = v
        self._log(f"🗳 {name}: {topic} → {value*100:.1f}%")
        return f"Голосование #{v.id}"

    def cast_vote(self, name, vid, side):
        v = self.votes.get(vid); p = self.players[name]
        if not v or v.closed: return "Закрыто"
        if not p.territories: return "Только владельцы"
        if side not in ("for","against"): return "Сторона: for/against"
        v.votes_for.discard(name); v.votes_against.discard(name)
        (v.votes_for if side=="for" else v.votes_against).add(name)
        p.votes[vid] = side
        return "Голос учтён"

    def raid(self, attacker, tid):
        t = self._territory(tid)
        if not t or not t.owner: return "Цель без владельца"
        if t.owner == attacker: return "Своё не атакуют"
        a = self.players[attacker]; d = self.players[t.owner]
        if a.alliance and a.alliance == d.alliance: return "Нельзя атаковать союзника"
        if self.tick - a.last_raid_tick < 5:
            return f"Кулдаун: {5-(self.tick-a.last_raid_tick)}"
        ap = a.total_power(self.territories) + 1
        dp = d.total_power([t]) + 1
        chance = ap / (ap + dp)
        a.last_raid_tick = self.tick
        if random.random() < chance:
            loot = int(d.balance * 0.15)
            if t.building == "hospital": loot //= 2
            d.balance -= loot; a.balance += loot
            b = random.choice(t.businesses)
            if b.level > 1: b.level -= 1
            self.raid_history.append({"tick":self.tick,"attacker":attacker,
                                      "defender":t.owner,"territory":t.name,
                                      "success":True,"loot":loot})
            self._log(f"⚔ {attacker} разграбил «{t.name}» (+{loot}💰)")
            return f"Успех! +{loot}💰"
        else:
            fine = int(a.balance * 0.05)
            a.balance -= fine; d.balance += fine
            self.raid_history.append({"tick":self.tick,"attacker":attacker,
                                      "defender":t.owner,"territory":t.name,
                                      "success":False,"fine":fine})
            self._log(f"🛡 {d.name} отбил атаку {attacker}")
            return f"Провал. Штраф {fine}💰"

    def create_alliance(self, name, title):
        title = title.strip()[:24]
        if not title or title in self.alliances: return "Имя занято/пусто"
        p = self.players[name]
        if p.alliance: return "Уже в альянсе"
        al = Alliance(self._aid, title, name, {name}, 0); self._aid += 1
        self.alliances[title] = al; p.alliance = title
        self._log(f"🤝 {name} основал альянс «{title}»")
        return f"Альянс «{title}»"

    def invite_alliance(self, leader, target):
        al = self.alliances.get(self.players[leader].alliance or "")
        if not al or al.leader != leader: return "Только лидер"
        if target not in self.players or self.players[target].alliance: return "Нет/занят"
        al.invites.add(target)
        self._log(f"✉ {leader} пригласил {target} в «{al.name}»")
        return "Приглашение отправлено"

    def accept_alliance(self, name, title):
        al = self.alliances.get(title)
        if not al or name not in al.invites: return "Нет приглашения"
        if self.players[name].alliance: return "Уже в альянсе"
        al.invites.discard(name); al.members.add(name)
        self.players[name].alliance = title
        self._log(f"🤝 {name} вступил в «{title}»")
        return f"В альянсе «{title}»"

    def leave_alliance(self, name):
        p = self.players[name]
        if not p.alliance: return "Вы не в альянсе"
        al = self.alliances.get(p.alliance)
        if not al: p.alliance = None; return "OK"
        if al.leader == name:
            for m in al.members: self.players[m].alliance = None
            del self.alliances[al.name]
            self._log(f"❌ Альянс «{al.name}» распущен")
            return "Альянс распущен"
        al.members.discard(name); p.alliance = None
        return "Вы вышли"

    def donate_alliance(self, name, amount):
        p = self.players[name]
        al = self.alliances.get(p.alliance or "")
        if not al or amount <= 0 or p.balance < amount: return "Некорректно"
        p.balance -= amount; al.treasury += amount
        self._log(f"💝 {name} внёс {amount}💰 в «{al.name}»")
        return f"Внесено {amount}💰"

    def alliance_raid(self, name, tid):
        p = self.players[name]; al = self.alliances.get(p.alliance or "")
        if not al or al.leader != name: return "Только лидер альянса"
        if len(al.members) < 2: return "Нужно ≥2 участников"
        t = self._territory(tid)
        if not t or not t.owner: return "Цель без владельца"
        if t.owner in al.members: return "Свой"
        if self.tick - al.last_raid_tick < 10:
            return f"Кулдаун: {10-(self.tick-al.last_raid_tick)}"
        power = sum(self.players[m].total_power(self.territories) for m in al.members)+1
        dp = self.players[t.owner].total_power([t])+1
        chance = power / (power + dp)
        al.last_raid_tick = self.tick
        if random.random() < chance:
            loot = int(self.players[t.owner].balance * 0.25)
            if t.building == "hospital": loot //= 2
            self.players[t.owner].balance -= loot
            al.treasury += loot
            b = random.choice(t.businesses)
            b.level = max(1, b.level - 2)
            self._log(f"⚔⚔ Альянс «{al.name}» разграбил «{t.name}» (+{loot}💰)")
            return f"Успех альянса! +{loot}💰 в казну"
        else:
            fine = int(al.treasury * 0.10)
            al.treasury -= fine
            self.players[t.owner].balance += fine
            self._log(f"🛡 Альянс «{al.name}» провалил рейд")
            return f"Провал. Штраф {fine}💰 из казны"

    def fulfill_state_order(self, name, soid, amount):
        so = next((x for x in self.state_orders if x.id == soid), None)
        if not so: return "Не найден"
        p = self.players[name]
        amount = min(amount, so.amount)
        if p.resources.get(so.resource,0) < amount:
            return f"Не хватает {RESOURCES[so.resource].name}"
        total = amount * so.price_per_unit
        if self.state.treasury < total: return "Казна пуста"
        p.take_resource(so.resource, amount)
        p.balance += total; self.state.treasury -= total
        so.amount -= amount
        if so.amount == 0: self.state_orders.remove(so)
        self._log(f"🏛 {name} сдал {amount} {RESOURCES[so.resource].name} → +{total}💰")
        return f"+{total}💰"

    def tick_economy(self):
        self.tick += 1
        for t in self.territories:
            if not t.owner: continue
            owner = self.players[t.owner]
            school = 0.25 if t.building == "school" else 0.0
            for b in t.businesses:
                income = b.income(school)
                itax = int(income * self.state.income_tax)
                owner.balance += income - itax
                self.state.treasury += itax; self.state.total_collected += itax
                for wname in list(b.workers):
                    w = self.players[wname]
                    if owner.balance >= w.salary:
                        owner.balance -= w.salary
                        stax = int(w.salary * self.state.salary_tax)
                        w.balance += w.salary - stax
                        self.state.treasury += stax; self.state.total_collected += stax
                    else:
                        b.workers.remove(wname); w.job = None; w.salary = 0
                for r,amt in b.produce(t.specialization, school).items():
                    owner.add_resource(r, amt)

        for lid, loan in list(self.loans.items()):
            b = self.players[loan.borrower]
            pay = min(loan.payment_per_tick, loan.total_due)
            if b.balance >= pay:
                b.balance -= pay; loan.total_due -= pay
                self.state.treasury += pay; self.state.total_collected += pay
            else:
                loan.total_due += int(pay*0.1)
            loan.ticks_left -= 1
            if loan.total_due <= 0: del self.loans[lid]
            elif loan.ticks_left <= 0: loan.ticks_left = 5

        for r in RESOURCES.values():
            r.current_price += (r.base_price - r.current_price) * 0.15
            r.current_price = max(r.base_price*0.3, min(r.base_price*3.0, r.current_price))

        for v in self.votes.values():
            if v.closed: continue
            v.ticks_left -= 1
            if v.ticks_left <= 0:
                passed = len(v.votes_for) > len(v.votes_against)
                if passed: setattr(self.state, v.topic, v.new_value)
                self.vote_history.append({
                    "tick": self.tick, "topic": v.topic, "value": v.new_value,
                    "for": len(v.votes_for), "against": len(v.votes_against),
                    "passed": passed,
                })
                self._log(("🗳 Принято" if passed else "🗳 Отклонено") + f": {v.topic}")
                v.closed = True

        if self.tick % 3 == 0 and self.state.treasury > 3000:
            r_key = random.choice(list(RESOURCES.keys()))
            r = RESOURCES[r_key]
            price = int(r.current_price * 1.2)
            amount = max(5, int(2000/price))
            if amount*price <= self.state.treasury:
                so = StateOrder(self._soid, r_key, amount, price, 4)
                self._soid += 1; self.state_orders.append(so)
                self._log(f"🏛 Госзаказ #{so.id}: {amount} {r.name} по {price}💰")

        for so in list(self.state_orders):
            so.expires_in -= 1
            if so.expires_in <= 0: self.state_orders.remove(so)

        self._record_history()
        self.save()

    def _record_history(self):
        self.tick_marks.append(self.tick)
        for k,r in RESOURCES.items():
            self.price_history[k].append(r.price)
        self.treasury_history.append(self.state.treasury)
        total_w = 0
        for n,p in self.players.items():
            pw = p.total_power(self.territories)
            w  = p.total_wealth(self.territories)
            self.power_history.setdefault(n, deque(maxlen=self.HISTORY_LEN)).append(pw)
            self.wealth_history.setdefault(n, deque(maxlen=self.HISTORY_LEN)).append(w)
            total_w += w
        self.total_wealth_history.append(total_w)

    def analytics(self) -> dict:
        return {
            "ticks": list(self.tick_marks),
            "prices": {k: list(v) for k,v in self.price_history.items()},
            "resource_names": {k: r.name for k,r in RESOURCES.items()},
            "resource_base": {k: r.base_price for k,r in RESOURCES.items()},
            "treasury": list(self.treasury_history),
            "total_wealth": list(self.total_wealth_history),
            "power": {n: list(v) for n,v in self.power_history.items()},
            "wealth": {n: list(v) for n,v in self.wealth_history.items()},
            "votes": self.vote_history[-30:],
            "raids": self.raid_history[-30:],
        }

    def snapshot(self, for_player=None):
        res = {k: {"name":r.name, "base":r.base_price, "price":r.price}
               for k,r in RESOURCES.items()}
        ter = []
        for t in self.territories:
            ter.append({
                "id":t.id, "name":t.name, "price":t.price,
                "spec":t.specialization, "spec_name":RESOURCES[t.specialization].name,
                "owner":t.owner, "building":t.building,
                "building_info": BUILDINGS[t.building] if t.building else None,
                "businesses":[{
                    "type":b.biz_type, "name":b.spec["name"], "level":b.level,
                    "workers":b.workers, "max_workers":b.spec["max_workers"],
                    "income":b.income(), "upgrade_cost":b.upgrade_cost()
                } for b in t.businesses],
            })
        pl = {n:{"balance":p.balance, "resources":p.resources,
                 "territories":p.territories, "job":p.job, "salary":p.salary,
                 "completed":p.completed_quests, "alliance":p.alliance,
                 "is_bot":p.is_bot, "strategy":p.strategy,
                 "power":p.total_power(self.territories),
                 "wealth":p.total_wealth(self.territories)}
              for n,p in self.players.items()}
        alls = {title:{"name":al.name, "leader":al.leader,
                       "members":list(al.members), "treasury":al.treasury}
                for title, al in self.alliances.items()}
        my_invites = []
        if for_player and for_player in self.players:
            for al in self.alliances.values():
                if for_player in al.invites: my_invites.append(al.name)
        return {
            "tick": self.tick, "resources": res, "territories": ter, "players": pl,
            "alliances": alls, "my_invites": my_invites, "buildings": BUILDINGS,
            "state": asdict(self.state),
            "market": [asdict(o) for o in self.market_orders],
            "state_orders": [asdict(so) for so in self.state_orders],
            "loans": [asdict(l) for l in self.loans.values()],
            "votes": [{"id":v.id,"topic":v.topic,"value":v.new_value,
                       "for":list(v.votes_for),"against":list(v.votes_against),
                       "ticks_left":v.ticks_left,"closed":v.closed}
                      for v in self.votes.values()],
            "quests": [{"id":q.id,"title":q.title,"need":q.need,"reward":q.reward_money}
                       for q in QUESTS],
            "log": self.log[-40:],
            "you": for_player,
        }

    def save(self, path=None):
        path = path or self.AUTOSAVE_PATH
        data = {
            "tick": self.tick,
            "_oid": self._oid, "_lid": self._lid, "_vid": self._vid,
            "_soid": self._soid, "_aid": self._aid,
            "state": asdict(self.state),
            "prices": {k: r.current_price for k,r in RESOURCES.items()},
            "players": {
                n: {**{k:v for k,v in asdict(p).items() if k != "votes"},
                    "votes": {str(k):v for k,v in p.votes.items()}}
                for n,p in self.players.items()
            },
            "territories": [
                {**asdict(t), "businesses": [asdict(b) for b in t.businesses]}
                for t in self.territories
            ],
            "alliances": {
                title: {**asdict(al), "members": list(al.members),
                        "invites": list(al.invites)}
                for title, al in self.alliances.items()
            },
            "market_orders": [asdict(o) for o in self.market_orders],
            "state_orders":  [asdict(so) for so in self.state_orders],
            "loans": [asdict(l) for l in self.loans.values()],
            "votes": [
                {**asdict(v),
                 "votes_for": list(v.votes_for),
                 "votes_against": list(v.votes_against)}
                for v in self.votes.values()
            ],
            "history": {
                "ticks": list(self.tick_marks),
                "prices": {k: list(v) for k,v in self.price_history.items()},
                "treasury": list(self.treasury_history),
                "power": {n: list(v) for n,v in self.power_history.items()},
                "wealth": {n: list(v) for n,v in self.wealth_history.items()},
                "total_wealth": list(self.total_wealth_history),
                "votes": self.vote_history[-50:],
                "raids": self.raid_history[-50:],
            },
            "log": self.log[-50:],
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def _load(self) -> bool:
        path = self.AUTOSAVE_PATH
        if not path.exists(): return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return False
        self.tick = data.get("tick", 0)
        self._oid = data.get("_oid",1); self._lid = data.get("_lid",1)
        self._vid = data.get("_vid",1); self._soid = data.get("_soid",1)
        self._aid = data.get("_aid",1)
        self.state = State(**data["state"])
        for k,v in data.get("prices",{}).items():
            if k in RESOURCES: RESOURCES[k].current_price = v
        self.players = {}
        for n,pd in data["players"].items():
            pd["votes"] = {int(k):v for k,v in pd.get("votes",{}).items()}
            self.players[n] = Player(**pd)
        self.territories = []
        for td in data["territories"]:
            bizs = [Business(**b) for b in td.pop("businesses")]
            self.territories.append(Territory(**td, businesses=bizs))
        self.alliances = {}
        for title,ad in data.get("alliances",{}).items():
            ad["members"] = set(ad["members"]); ad["invites"] = set(ad["invites"])
            self.alliances[title] = Alliance(**ad)
        self.market_orders = [Order(**o) for o in data.get("market_orders",[])]
        self.state_orders  = [StateOrder(**o) for o in data.get("state_orders",[])]
        self.loans = {l["id"]: Loan(**l) for l in data.get("loans",[])}
        self.votes = {}
        for vd in data.get("votes",[]):
            vd["votes_for"] = set(vd["votes_for"])
            vd["votes_against"] = set(vd["votes_against"])
            self.votes[vd["id"]] = Vote(**vd)
        h = data.get("history", {})
        self.tick_marks = deque(h.get("ticks", []), maxlen=self.HISTORY_LEN)
        for k,v in h.get("prices",{}).items():
            self.price_history[k] = deque(v, maxlen=self.HISTORY_LEN)
        self.treasury_history = deque(h.get("treasury",[]), maxlen=self.HISTORY_LEN)
        self.total_wealth_history = deque(h.get("total_wealth",[]), maxlen=self.HISTORY_LEN)
        self.power_history = {n: deque(v, maxlen=self.HISTORY_LEN)
                              for n,v in h.get("power",{}).items()}
        self.wealth_history = {n: deque(v, maxlen=self.HISTORY_LEN)
                               for n,v in h.get("wealth",{}).items()}
        self.vote_history = h.get("votes", [])
        self.raid_history = h.get("raids", [])
        self.log = data.get("log", [])
        self._log(f"💾 Загружено сохранение (тик {self.tick})")
        return True

    def _territory(self, tid):
        return next((t for t in self.territories if t.id == tid), None)
