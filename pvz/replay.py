"""Versioned input replays, expressed in simulation time rather than wall time.

The format contains no names, paths or free-text metadata. A replay records
ordinary input attempts, so an unaffordable planting attempt is valid too.
Determinism requires the same game version and scenario data.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Callable, TYPE_CHECKING

from .constants import DIFFICULTIES, SIMULATION_STEP
from .types import PlantType

if TYPE_CHECKING:
    from .game import Game

SCHEMA_VERSION = 1
MAX_DURATION = 7200.0
MAX_ACTIONS = 100_000
MAX_FILE_BYTES = 8 * 1024 * 1024
ACTION_KINDS = frozenset({"move", "select", "plant", "dig", "pause", "resume", "quit"})
DIRECTIONS = {"up": "w", "down": "s", "left": "a", "right": "d"}
_SCENARIO_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


class ReplayError(ValueError):
    """The recording is malformed, unsupported or cannot be reproduced."""


@dataclass(frozen=True)
class ReplayAction:
    time: float
    kind: str
    direction: str | None = None
    plant: str | None = None

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {"time": self.time, "kind": self.kind}
        if self.direction is not None:
            result["direction"] = self.direction
        if self.plant is not None:
            result["plant"] = self.plant
        return result


@dataclass(frozen=True)
class Replay:
    seed: int
    scenario: str | None
    difficulty: str
    duration: float
    actions: tuple[ReplayAction, ...]
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version, "seed": self.seed,
            "scenario": self.scenario, "difficulty": self.difficulty,
            "duration": self.duration,
            "actions": [action.to_dict() for action in self.actions],
        }


def _object(value: Any, fields: set[str], required: set[str], where: str) -> dict:
    if not isinstance(value, dict) or any(type(key) is not str for key in value):
        raise ReplayError(f"{where}: expected an object with string keys")
    if set(value) - fields:
        raise ReplayError(f"{where}: unknown fields")
    if required - set(value):
        raise ReplayError(f"{where}: missing fields")
    return value


def _time(value: Any, where: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= MAX_DURATION:
        raise ReplayError(f"{where}: expected finite simulation time in 0..{MAX_DURATION:g}")
    step = round(value / SIMULATION_STEP)
    canonical = round(step * SIMULATION_STEP, 10)
    if abs(value - canonical) > 1e-8:
        raise ReplayError(f"{where}: time must align with the {SIMULATION_STEP:g}s simulation step")
    return canonical


def _action(value: Any, where: str) -> ReplayAction:
    value = _object(value, {"time", "kind", "direction", "plant"}, {"time", "kind"}, where)
    kind = value["kind"]
    if type(kind) is not str or kind not in ACTION_KINDS:
        raise ReplayError(f"{where}: unknown input action")
    extra = set(value) - {"time", "kind"}
    expected = {"direction"} if kind == "move" else ({"plant"} if kind == "select" else set())
    if extra != expected:
        raise ReplayError(f"{where}: incorrect arguments for {kind}")
    direction, plant = value.get("direction"), value.get("plant")
    if kind == "move" and (type(direction) is not str or direction not in DIRECTIONS):
        raise ReplayError(f"{where}: unknown direction")
    if kind == "select" and (type(plant) is not str or plant not in PlantType.__members__):
        raise ReplayError(f"{where}: unknown plant")
    return ReplayAction(_time(value["time"], where + ".time"), kind, direction, plant)


def _timeline(action: ReplayAction, previous: float, paused: bool, ended: bool) -> tuple[bool, bool]:
    if ended:
        raise ReplayError("actions cannot follow quit")
    if action.time < previous:
        raise ReplayError("actions must be ordered by simulation time")
    if paused and action.time != previous:
        raise ReplayError("simulation time cannot advance while paused")
    if action.kind == "pause":
        if paused:
            raise ReplayError("cannot pause an already paused game")
        paused = True
    elif action.kind == "resume":
        if not paused:
            raise ReplayError("cannot resume a running game")
        paused = False
    return paused, action.kind == "quit"


def parse_replay(data: Any) -> Replay:
    """Validate a JSON-compatible object and return immutable canonical data."""
    fields = {"schema_version", "seed", "scenario", "difficulty", "duration", "actions"}
    data = _object(data, fields, fields, "replay")
    if type(data["schema_version"]) is not int or data["schema_version"] != SCHEMA_VERSION:
        raise ReplayError("unsupported replay schema_version")
    seed = data["seed"]
    if type(seed) is not int or not 0 <= seed <= 2_147_483_647:
        raise ReplayError("seed must be an integer in 0..2147483647")
    scenario = data["scenario"]
    if scenario is not None and (type(scenario) is not str or len(scenario) > 80 or not _SCENARIO_ID.fullmatch(scenario)):
        raise ReplayError("scenario must be a safe identifier or null")
    difficulty = data["difficulty"]
    if type(difficulty) is not str or difficulty not in DIFFICULTIES:
        raise ReplayError("unknown difficulty")
    duration = _time(data["duration"], "duration")
    raw = data["actions"]
    if not isinstance(raw, list) or len(raw) > MAX_ACTIONS:
        raise ReplayError(f"actions must be a list of at most {MAX_ACTIONS} inputs")
    actions = tuple(_action(item, f"actions[{index}]") for index, item in enumerate(raw))
    previous, paused, ended = 0.0, False, False
    for action in actions:
        paused, ended = _timeline(action, previous, paused, ended)
        previous = action.time
    if duration < previous or ((paused or ended) and duration != previous):
        raise ReplayError("duration is inconsistent with the input timeline")
    return Replay(seed, scenario, difficulty, duration, actions)


class ReplayRecorder:
    """Collect semantic inputs before applying them to a live Game."""

    def __init__(self, seed: int, *, scenario: str | None = None, difficulty: str = "normal") -> None:
        header = parse_replay({"schema_version": SCHEMA_VERSION, "seed": seed,
                               "scenario": scenario, "difficulty": difficulty,
                               "duration": 0, "actions": []})
        self.seed, self.scenario, self.difficulty = header.seed, header.scenario, header.difficulty
        self._actions: list[ReplayAction] = []
        self._paused = self._ended = False

    def record(self, time: float, kind: str, *, direction: str | None = None, plant: str | None = None) -> ReplayAction:
        if len(self._actions) >= MAX_ACTIONS:
            raise ReplayError("recording has reached its input limit")
        data: dict[str, object] = {"time": time, "kind": kind}
        if direction is not None:
            data["direction"] = direction
        if plant is not None:
            data["plant"] = plant
        action = _action(data, "action")
        previous = self._actions[-1].time if self._actions else 0.0
        paused, ended = _timeline(action, previous, self._paused, self._ended)
        self._actions.append(action)
        self._paused, self._ended = paused, ended
        return action

    def finish(self, duration: float) -> Replay:
        return parse_replay({"schema_version": SCHEMA_VERSION, "seed": self.seed,
                             "scenario": self.scenario, "difficulty": self.difficulty,
                             "duration": duration,
                             "actions": [action.to_dict() for action in self._actions]})


def _unique_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReplayError("duplicate JSON fields are not allowed")
        result[key] = value
    return result


def load_replay(path: str | Path) -> Replay:
    """Read a bounded UTF-8 JSON file without accepting duplicate fields."""
    try:
        with Path(path).open("rb") as handle:
            raw = handle.read(MAX_FILE_BYTES + 1)
        if len(raw) > MAX_FILE_BYTES:
            raise ReplayError("replay file exceeds the size limit")
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ReplayError("cannot read replay JSON") from exc
    return parse_replay(data)


def save_replay(replay: Replay, path: str | Path) -> None:
    """Atomically create a new replay file; never replace an existing path."""
    checked = parse_replay(replay.to_dict())
    raw = (json.dumps(checked.to_dict(), ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    if len(raw) > MAX_FILE_BYTES:
        raise ReplayError("replay file exceeds the size limit")
    destination = Path(path)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=destination.parent, prefix=".pvz-replay-", delete=False) as handle:
            temporary = handle.name
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        # link is an atomic no-replace operation even if another writer races us.
        os.link(temporary, destination)
    except FileExistsError as exc:
        raise ReplayError("destination already exists; replay was not overwritten") from exc
    except OSError as exc:
        raise ReplayError("cannot save replay file") from exc
    finally:
        if temporary is not None:
            os.unlink(temporary)


@dataclass(frozen=True)
class ReplayResult:
    game: Game
    stats: dict[str, object]


def game_stats(game: Game) -> dict[str, object]:
    """Summarize an outcome and fingerprint its observable simulation state."""
    if game.victory:
        outcome = "victory"
    elif game.game_over:
        outcome = "quit" if game.game_over_reason == "Выход" else "defeat"
    else:
        outcome = "paused" if game.paused else "in_progress"
    stats: dict[str, object] = {
        "outcome": outcome, "elapsed": game.time_elapsed, "score": game.score,
        "sun": game.sun, "wave": game.wave_number, "waves": game.wave_total,
        "zombies_killed": game.zombies_killed, "plants_placed": game.plants_placed,
        "plants_lost": game.plants_lost, "lawnmowers_used": game.lawnmowers_used,
        "sun_generated": game.sun_generated,
    }
    state = {
        "stats": stats, "seed": game.seed, "difficulty": game.difficulty,
        "scenario": game.scenario.id if game.scenario else None,
        "cursor": [game.cursor_row, game.cursor_col], "selected": game.selected.name,
        "lawnmowers": game.lawnmowers,
        "cooldowns": {plant.name: game.cooldown_remaining(plant) for plant in PlantType},
        "plants": [[p.plant_type.name, p.row, p.col, p.hp, p.last_action_time, p.chewing_until]
                   for p in game.grid.iter_plants()],
        "zombies": [[z.zombie_type.name, z.row, z.col, z.hp, z.move_progress, z.shield_hp, z.slowed_until]
                    for z in game.zombies],
        "projectiles": [[p.row, p.col, p.slows] for p in game.projectiles],
    }
    canonical = json.dumps(state, sort_keys=True, separators=(",", ":"), allow_nan=False)
    stats["state_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return stats


def _resolve_scenario(identifier: str, loader: Callable[[str], Any] | None) -> Any:
    if loader is None:
        try:
            from .content import load_scenario
        except ImportError as exc:
            raise ReplayError("scenario catalogue is unavailable") from exc
        loader = load_scenario
    try:
        scenario = loader(identifier)
    except (ValueError, OSError) as exc:
        raise ReplayError(f"cannot load scenario: {identifier}") from exc
    if getattr(scenario, "id", None) != identifier:
        raise ReplayError("scenario loader returned a different identifier")
    return scenario


def play_replay(replay: Replay, *, scenario_loader: Callable[[str], Any] | None = None,
                on_step: Callable[[Game], None] | None = None) -> ReplayResult:
    """Run legal inputs headlessly with fixed simulation slices.

    Inputs sharing a timestamp retain their file order. The optional callback
    observes the initial game and every simulated step; it must not mutate it.
    Natural victory or defeat ends playback early. Inputs after that end are
    rejected instead of being silently discarded.
    """
    from .game import Game

    checked = parse_replay(replay.to_dict())
    scenario = _resolve_scenario(checked.scenario, scenario_loader) if checked.scenario else None
    try:
        game = Game(SIMULATION_STEP, seed=checked.seed,
                    difficulty=checked.difficulty, scenario=scenario)
    except (ValueError, KeyError, AttributeError, TypeError) as exc:
        raise ReplayError("scenario cannot be initialized by the current game") from exc
    if on_step:
        on_step(game)
    current_step = 0

    def advance(target: int) -> None:
        nonlocal current_step
        while current_step < target and not game.game_over:
            if game.paused:
                raise ReplayError("simulation cannot advance while paused")
            game.step()
            current_step = round(game.time_elapsed / SIMULATION_STEP)
            if on_step:
                on_step(game)

    for action in checked.actions:
        advance(round(action.time / SIMULATION_STEP))
        if game.game_over:
            raise ReplayError("recorded input follows the end of the game")
        if action.kind == "select":
            slot = list(PlantType).index(PlantType[action.plant]) + 1
            game.select_plant_type(slot)
        elif action.kind == "move":
            game.handle_keypress(ord(DIRECTIONS[action.direction]))
        elif action.kind == "plant":
            game.place_selected()
        elif action.kind == "dig":
            game.dig_up()
        elif action.kind in ("pause", "resume"):
            game.handle_keypress(ord("p"))
        else:
            game.handle_keypress(ord("q"))
    advance(round(checked.duration / SIMULATION_STEP))
    return ReplayResult(game, game_stats(game))
