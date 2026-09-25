# vellar_server.py
import asyncio, json
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from vellar_core import VellarGame
from vellar_bots import BotBrain

app = FastAPI()
game = VellarGame()
bots = BotBrain(game)
tokens: dict[str,str] = {}

class Connections:
    def __init__(self): self.ws: dict[str,WebSocket] = {}
    async def add(self, name, ws): self.ws[name] = ws
    def remove(self, name): self.ws.pop(name, None)

conns = Connections()

class AuthIn(BaseModel):
    name: str
    password: str

@app.post("/api/register")
async def api_register(body: AuthIn):
    r = game.register(body.name, body.password)
    if r != "OK": return JSONResponse({"ok":False,"error":r}, status_code=400)
    token = game.login(body.name, body.password)
    tokens[token] = body.name.strip()[:24]
    return {"ok":True, "token":token, "name":body.name.strip()[:24]}

@app.post("/api/login")
async def api_login(body: AuthIn):
    token = game.login(body.name, body.password)
    if not token: return JSONResponse({"ok":False,"error":"Неверные данные"}, status_code=401)
    tokens[token] = body.name.strip()[:24]
    return {"ok":True, "token":token, "name":body.name.strip()[:24]}

@app.get("/api/analytics")
async def api_analytics():
    return game.analytics()

async def push_state():
    for name, ws in list(conns.ws.items()):
        try: await ws.send_json({"type":"state", "data": game.snapshot(name)})
        except Exception: conns.remove(name)

@app.get("/")
async def index():
    return HTMLResponse(Path("index.html").read_text(encoding="utf-8"))

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    name = None
    try:
        hello = json.loads(await ws.receive_text())
        token = hello.get("token","")
        name = tokens.get(token)
        if not name or name not in game.players:
            await ws.send_json({"type":"error","msg":"Токен недействителен"})
            await ws.close(); return
        await conns.add(name, ws)
        await ws.send_json({"type":"joined","name":name})
        await push_state()

        while True:
            msg = json.loads(await ws.receive_text())
            a = msg.get("action"); r = "?"
            if   a == "buy_territory":   r = game.buy_territory(name, int(msg["tid"]))
            elif a == "upgrade":         r = game.upgrade(name, int(msg["tid"]), int(msg["idx"]))
            elif a == "build":           r = game.build(name, int(msg["tid"]), msg["building"])
            elif a == "hire":            r = game.hire(name, msg["worker"], int(msg["tid"]), int(msg["salary"]))
            elif a == "quit_job":        r = game.quit_job(name)
            elif a == "place_order":     r = game.place_order(name, msg["resource"], int(msg["amount"]), int(msg["price"]))
            elif a == "cancel_order":    r = game.cancel_order(name, int(msg["oid"]))
            elif a == "buy_order":       r = game.buy_order(name, int(msg["oid"]), int(msg["amount"]))
            elif a == "take_loan":       r = game.take_loan(name, int(msg["amount"]), int(msg["ticks"]))
            elif a == "quest":           r = game.complete_quest(name, int(msg["qid"]))
            elif a == "propose_vote":    r = game.propose_vote(name, msg["topic"], float(msg["value"]))
            elif a == "cast_vote":       r = game.cast_vote(name, int(msg["vid"]), msg["side"])
            elif a == "raid":            r = game.raid(name, int(msg["tid"]))
            elif a == "state_order":     r = game.fulfill_state_order(name, int(msg["soid"]), int(msg["amount"]))
            elif a == "create_alliance": r = game.create_alliance(name, msg["title"])
            elif a == "invite_alliance": r = game.invite_alliance(name, msg["target"])
            elif a == "accept_alliance": r = game.accept_alliance(name, msg["title"])
            elif a == "leave_alliance":  r = game.leave_alliance(name)
            elif a == "donate_alliance": r = game.donate_alliance(name, int(msg["amount"]))
            elif a == "alliance_raid":   r = game.alliance_raid(name, int(msg["tid"]))
            elif a == "force_save":      game.save(); r = "Сохранено"
            else: r = f"Неизвестное действие: {a}"

            await ws.send_json({"type":"info", "msg":r, "action":a})
            await push_state()
    except WebSocketDisconnect:
        if name: conns.remove(name)
    except Exception as e:
        try: await ws.send_json({"type":"error","msg":str(e)})
        except: pass

async def ticker():
    bots.spawn_all()
    while True:
        await asyncio.sleep(30)
        game.tick_economy()
        bots.tick()
        await push_state()

@app.on_event("startup")
async def startup():
    asyncio.create_task(ticker())

@app.on_event("shutdown")
async def shutdown():
    game.save()
