import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from classes.event_tracker import TurnTracker

from classes.models import ActiveBattleTurn, Battle, BattleReport
from classes.types import RawTurnLog
from utils.parse import log_turns

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

event_tracker = TurnTracker()


@app.post("/logs")
async def post_logs(raw_logs: list[RawTurnLog], tasks: BackgroundTasks):
    def process():
        turns, is_new_battle = log_turns(raw_logs)
        for t in turns:
            event_tracker.insert_turn(t)

    tasks.add_task(process)


@app.get("/ids")
def get_ids():
    pks = list(btl.pk for btl in Battle.select(Battle.pk))
    return pks


@app.get("/reports/{id}")
def get_reports(id: str):
    reports: list[BattleReport] = (
        BattleReport.select().join(Battle).where(Battle.pk == id)
    )
    result: dict[str, BattleReport] = {rpt.type: rpt.data for rpt in reports}
    return result


@app.get("/events/{id}")
def get_events(id: str):
    battle: Battle | None = Battle.get_or_none(Battle.pk == id)

    if battle is None:
        raise HTTPException(404)
    elif battle.active:
        events = [turn.events for turn in ActiveBattleTurn.select()]
    else:
        events = battle.data

    return events


@app.post("/search/logs")
def post_search_logs():
    pass


@app.websocket("/ws/events")
async def ws_events(ws: WebSocket):
    # Send client next event index
    await ws.accept()
    await ws.send_json(dict(type="NEXT_INDEX", index=event_tracker.next_idx))

    # Respond to event requests
    while True:
        request = await ws.receive_json()
        event = await event_tracker.get_turn(request["index"])
        await ws.send_json(dict(type="EVENT", data=event))


if __name__ == "__main__":
    uvicorn.run(
        "run_server:app",
        host="0.0.0.0",
        port=9999,
        workers=1,
        log_level="debug",
        reload=True,
    )
