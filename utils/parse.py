import json
from classes.models import ActiveBattleTurn, Battle, BattleReport
from classes.reporters import Reporters
from classes.types import RawTurnLog, Turn
from config import paths
from javascript import require

ParserModule = require("../classes/parser.js")
PARSERS = [ParserModule.PARSERS[x] for x in ParserModule.PARSERS]


def parse_events(lines: list[str], batch_size=1000):
    batches = [lines[i : i + batch_size] for i in range(0, len(lines), batch_size)]
    batches_parsed = [json.loads(ParserModule.parse_events(batch)) for batch in batches]
    events = [ev for batch in batches_parsed for ev in batch]

    return events


def parse_turns(raw_logs: list[RawTurnLog]) -> tuple[list[Turn], list[str]]:
    # Sort by time
    raw_sorted = [
        log
        for idx, log in sorted(
            enumerate(raw_logs), key=lambda pair: pair[1].time or pair[0]
        )
    ]

    # Parse into events
    events = parse_events([line for turn in raw_sorted for line in turn.lines])

    # Regroup into Turns
    rejects: list[str] = []
    turns: list[Turn] = []
    for raw_log in raw_logs:
        turns.append(Turn(events=[], time=raw_log.time))
        for line in raw_log.lines:
            ev = events.pop(0)
            if ev:
                turns[-1]["events"].append(ev)
            else:
                rejects.append(line)

    return turns, rejects


def get_active_battle(
    round_start_event: dict | None = None,
) -> tuple[Battle, BattleReport | None, bool]:
    is_new_battle = False

    def flush_active_turns(active_battle: Battle):
        turns = [
            dict(events=t.events, time=t.time, meta=t.meta)
            for t in ActiveBattleTurn.select().order_by(ActiveBattleTurn.pk)
        ]
        active_battle.data = turns

        ActiveBattleTurn.delete().execute()
        active_battle.save()

    def create_new_battle():
        # Compress old battle data
        Battle.update(active=False).execute()
        battle = Battle.create(active=True)

        nonlocal is_new_battle
        is_new_battle = True

        return battle

    # Get or create latest battle
    active_battle = Battle.get_or_none(Battle.active == True)
    if active_battle is None:
        active_battle = create_new_battle()

    # Get latest battle info
    active_report = (
        BattleReport.select().join(Battle).where(Battle.pk == active_battle.pk).first()
    )

    # If we have info to create or update a report...
    if ev := round_start_event:
        if active_report is None:
            # If no existing report, create one
            active_report = BattleReport.create(
                type="meta",
                data=dict(
                    battle_type=ev["battle_type"],
                    last_round=ev["current"],
                    max_rounds=ev["max"],
                    time=0,
                ),
                battle=active_battle,
            )
        else:
            # Else check if event is for a new battle
            # TODO: revisit handling empty active_report
            is_earlier_round = (
                active_report.data.get("last_round", True)
                or ev["current"] < active_report.data["last_round"]
            )
            is_different_type = (
                active_report.data.get("battle_type", True)
                or ev["battle_type"] != active_report.data["battle_type"]
            )
            is_different_round_max = (
                active_report.data.get("max_rounds", True)
                or ev["max"] != active_report.data["max_rounds"]
            )

            if is_different_type or is_different_round_max or is_earlier_round:
                # Event is for new battle, so create battle / report
                flush_active_turns(active_battle)
                active_battle = create_new_battle()
                active_report = BattleReport.create(
                    type="meta",
                    data=dict(
                        battle_type=ev["battle_type"],
                        last_round=ev["current"],
                        max_rounds=ev["max"],
                    ),
                    battle=active_battle,
                )
            else:
                # Event is for current battle so update battle report
                active_report.data["last_round"] = ev["current"]
                active_report.save()

    return active_battle, active_report, is_new_battle


def log_turns(raw_logs: list[RawTurnLog]) -> tuple[list[Turn], bool]:
    """
    Get or create new Battle. Then add turns to it. Then run Reporter's.

    Assumptions:
        -> All raw_logs are for the same battle
        -> At least one log starts with a ROUND_START event
        -> All timestamps are monotonically increasing, for turns within the same battle
    """

    # Parse logs
    [turns, unparsed] = parse_turns(raw_logs)

    for line in unparsed:
        print(f"WARNING: Failed to parse line [{line}]")

    # Get or create active battle
    round_start = next(
        (
            ev
            for turn in turns
            for ev in turn["events"]
            if ev and ev["event_type"] == "ROUND_START"
        ),
        None,
    )
    active_battle, active_report, is_new_battle = get_active_battle(round_start)
    active_battle.unparsed += unparsed
    active_battle.save()

    if is_new_battle:
        active_battle.time = turns[0]["time"]
        active_battle.save()

    # Append events to db
    for turn in turns:
        ActiveBattleTurn.create(
            events=turn["events"],
            time=turn["time"] - active_battle.time,
            battle=active_battle,
        )

    # Append events to file
    out_file = paths.BATTLE_LOG_DIR / f"{active_battle.pk}.hv"
    with open(out_file, "a") as file:
        if is_new_battle:
            battle_data = dict(pk=active_battle.pk, time=active_battle.time)
            file.write(json.dumps(battle_data) + "\n")

        result = [t.json() for t in raw_logs]
        file.write("\n".join(result) + "\n")

    # Update reporters
    for cls in Reporters.values():
        rptr = cls.get(active_battle) or cls.create(active_battle)

        for turn in turns:
            rptr.next_turn(turn)

        rptr.save()

    # Finalize old reporters
    if is_new_battle:
        inactive = (
            BattleReport.select()
            .where(BattleReport.finalized == False)
            .join(Battle)
            .where(Battle.pk != active_battle.pk)
        )
        inactive = [
            Reporters[report.type](report)
            for report in inactive
            if report.type != "meta"
        ]

        for rptr in inactive:
            rptr.finalize()

    return turns, is_new_battle


def log_from_file(raw_logs: list[RawTurnLog], battle: Battle):
    # Parse logs
    [turns, unparsed] = parse_turns(raw_logs)
    for line in unparsed:
        print(f"WARNING: Failed to parse line [{line}]")

    #
    battle.unparsed += unparsed
    battle.data = [
        dict(events=turn["events"], time=turn["time"] - battle.time) for turn in turns
    ]
    battle.save()

    # Update reporters
    for cls in Reporters.values():
        rptr = cls.create(battle)

        for turn in turns:
            rptr.next_turn(turn)

        rptr.finalize()
        rptr.save()


def purge_battle(id: str):
    Battle.delete().where(Battle.pk == id)
    ActiveBattleTurn.delete().where(ActiveBattleTurn.battle.pk == id)
    BattleReport.delete().where(BattleReport.battle.pk == id)
