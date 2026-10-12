"""Validated, deterministic campaign and challenge configuration.

Scenario data stays independent of the simulation so the catalogue can be
inspected and checked without starting curses or importing gameplay enums.
"""
from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
import json
import math
import re
from types import MappingProxyType
from typing import Any, Mapping

PLANT_KEYS = frozenset({
    "PEASHOOTER", "SUNFLOWER", "WALL_NUT", "CHOMPER", "SNOW_PEA",
    "CHERRY_BOMB", "REPEATER", "POTATO_MINE", "DOUBLE_SUNFLOWER",
})
ZOMBIE_KEYS = frozenset({"NORMAL", "CONE", "BUCKET", "RUNNER", "SHIELD"})
_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_MAX_DURATION = 7200.0


class ContentError(ValueError):
    """A scenario is malformed or cannot be played on the 5 by 9 lawn."""


@dataclass(frozen=True)
class Spawn:
    time: float
    row: int
    zombie: str


@dataclass(frozen=True)
class Wave:
    number: int
    duration: float
    spawns: tuple[Spawn, ...]


@dataclass(frozen=True)
class Scenario:
    id: str
    name: str
    seed: int
    sun: int
    waves: tuple[Wave, ...]
    allowed_plants: tuple[str, ...]
    modifiers: Mapping[str, object]
    kind: str = "campaign"
    chapter: str = ""
    order: int = 0
    description: str = ""
    objective: str = ""

    @property
    def duration(self) -> float:
        """Minimum duration; the final wave still needs to be cleared."""
        return sum(wave.duration for wave in self.waves)

    @property
    def zombie_count(self) -> int:
        return sum(len(wave.spawns) for wave in self.waves)


def _fail(where: str, message: str) -> None:
    raise ContentError(f"{where}: {message}")


def _object(value: Any, where: str, fields: set[str], required: set[str]) -> dict:
    if not isinstance(value, dict):
        _fail(where, "expected an object")
    unknown = set(value) - fields
    missing = required - set(value)
    if unknown:
        _fail(where, f"unknown fields: {', '.join(sorted(unknown))}")
    if missing:
        _fail(where, f"missing fields: {', '.join(sorted(missing))}")
    return value


def _integer(value: Any, where: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        _fail(where, f"expected integer in {low}..{high}")
    return value


def _number(value: Any, where: str, low: float, high: float) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        _fail(where, f"expected finite number in {low:g}..{high:g}")
    return float(value)


def _text(value: Any, where: str, maximum: int, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value.strip()) or len(value) > maximum:
        _fail(where, f"expected {'optional ' if empty else ''}text up to {maximum} characters")
    if any(ord(char) < 32 for char in value):
        _fail(where, "control characters are not allowed")
    return value


def _key(value: Any, where: str, keys: frozenset[str]) -> str:
    if not isinstance(value, str) or value not in keys:
        _fail(where, "unknown gameplay key")
    return value


def _modifiers(value: Any, allowed: tuple[str, ...], sun: int) -> Mapping[str, object]:
    where = "modifiers"
    fields = {"passive_sun", "sun_cap", "time_limit", "preplanted", "bonus_sun_per_wave", "plant_cost_multiplier", "max_plants", "no_mowers", "blocked_cells"}
    data = _object(value, where, fields, set())
    result: dict[str, object] = {}
    if "passive_sun" in data:
        if type(data["passive_sun"]) is not bool:
            _fail(where, "passive_sun must be boolean")
        result["passive_sun"] = data["passive_sun"]
    if "no_mowers" in data:
        if type(data["no_mowers"]) is not bool:
            _fail(where, "no_mowers must be boolean")
        result["no_mowers"] = data["no_mowers"]
    if "sun_cap" in data:
        cap = data["sun_cap"]
        if cap is not None:
            cap = _integer(cap, "modifiers.sun_cap", 25, 10000)
            if sun > cap:
                _fail(where, "starting sun exceeds sun_cap")
        result["sun_cap"] = cap
    if "time_limit" in data:
        limit = data["time_limit"]
        result["time_limit"] = None if limit is None else _number(limit, "modifiers.time_limit", 1, _MAX_DURATION)
    if "bonus_sun_per_wave" in data:
        result["bonus_sun_per_wave"] = _integer(data["bonus_sun_per_wave"], "modifiers.bonus_sun_per_wave", 0, 10000)
    if "plant_cost_multiplier" in data:
        result["plant_cost_multiplier"] = _number(data["plant_cost_multiplier"], "modifiers.plant_cost_multiplier", 0.25, 4)
    if "max_plants" in data:
        result["max_plants"] = _integer(data["max_plants"], "modifiers.max_plants", 1, 45)
    blocked: set[tuple[int, int]] = set()
    if "blocked_cells" in data:
        cells = data["blocked_cells"]
        if not isinstance(cells, list) or len(cells) > 45:
            _fail(where, "blocked_cells must be a list of at most 45 cells")
        parsed_cells = []
        for index, item in enumerate(cells):
            item_where = f"modifiers.blocked_cells[{index}]"
            item = _object(item, item_where, {"row", "col"}, {"row", "col"})
            row = _integer(item["row"], item_where + ".row", 0, 4)
            col = _integer(item["col"], item_where + ".col", 0, 8)
            if (row, col) in blocked:
                _fail(item_where, "duplicate blocked cell")
            blocked.add((row, col))
            parsed_cells.append(MappingProxyType({"row": row, "col": col}))
        result["blocked_cells"] = tuple(parsed_cells)
    if "preplanted" in data:
        plants = data["preplanted"]
        if not isinstance(plants, list) or len(plants) > 45:
            _fail(where, "preplanted must be a list of at most 45 plants")
        occupied: set[tuple[int, int]] = set()
        planted = []
        for index, item in enumerate(plants):
            item_where = f"modifiers.preplanted[{index}]"
            item = _object(item, item_where, {"row", "col", "plant"}, {"row", "col", "plant"})
            row = _integer(item["row"], item_where + ".row", 0, 4)
            col = _integer(item["col"], item_where + ".col", 0, 8)
            plant = _key(item["plant"], item_where + ".plant", PLANT_KEYS)
            if plant not in allowed:
                _fail(item_where, "preplanted plant must belong to allowed_plants")
            if (row, col) in occupied:
                _fail(item_where, "cell is already occupied")
            if (row, col) in blocked:
                _fail(item_where, "preplanted cell is blocked")
            occupied.add((row, col))
            planted.append(MappingProxyType({"row": row, "col": col, "plant": plant}))
        if len(planted) > result.get("max_plants", 45):
            _fail(where, "preplanted count exceeds max_plants")
        result["preplanted"] = tuple(planted)
    return MappingProxyType(result)


def parse_scenario(data: Any) -> Scenario:
    """Parse and validate one JSON-compatible object; no random state is used."""
    required = {"id", "name", "seed", "sun", "waves", "allowed_plants", "modifiers"}
    fields = required | {"schema_version", "kind", "chapter", "order", "description", "objective"}
    data = _object(data, "scenario", fields, required)
    if data.get("schema_version", 1) != 1 or type(data.get("schema_version", 1)) is not int:
        _fail("scenario", "unsupported schema_version")
    scenario_id = _text(data["id"], "id", 80)
    if not _ID.fullmatch(scenario_id):
        _fail("id", "use lowercase letters, digits and single hyphens")
    plants = data["allowed_plants"]
    if not isinstance(plants, list) or not 1 <= len(plants) <= len(PLANT_KEYS):
        _fail("allowed_plants", "expected a non-empty plant list")
    allowed = tuple(_key(plant, "allowed_plants", PLANT_KEYS) for plant in plants)
    if len(set(allowed)) != len(allowed):
        _fail("allowed_plants", "duplicate plants")
    sun = _integer(data["sun"], "sun", 0, 10000)
    modifiers = _modifiers(data["modifiers"], allowed, sun)
    raw_waves = data["waves"]
    if not isinstance(raw_waves, list) or not 1 <= len(raw_waves) <= 32:
        _fail("waves", "expected 1..32 waves")
    waves = []
    for index, raw_wave in enumerate(raw_waves):
        where = f"waves[{index}]"
        raw_wave = _object(raw_wave, where, {"number", "duration", "spawns"}, {"number", "duration", "spawns"})
        number = _integer(raw_wave["number"], where + ".number", 1, 32)
        if number != index + 1:
            _fail(where, "wave numbers must be consecutive from 1")
        duration = _number(raw_wave["duration"], where + ".duration", 1, _MAX_DURATION)
        raw_spawns = raw_wave["spawns"]
        if not isinstance(raw_spawns, list) or not 1 <= len(raw_spawns) <= 1000:
            _fail(where, "expected 1..1000 spawns")
        spawns = []
        previous_time = -1.0
        for spawn_index, spawn in enumerate(raw_spawns):
            spawn_where = f"{where}.spawns[{spawn_index}]"
            spawn = _object(spawn, spawn_where, {"time", "row", "zombie"}, {"time", "row", "zombie"})
            at = _number(spawn["time"], spawn_where + ".time", 0, duration)
            if at < previous_time:
                _fail(spawn_where, "spawns must be sorted by time")
            previous_time = at
            spawns.append(Spawn(at, _integer(spawn["row"], spawn_where + ".row", 0, 4), _key(spawn["zombie"], spawn_where + ".zombie", ZOMBIE_KEYS)))
        waves.append(Wave(number, duration, tuple(spawns)))
    if sum(wave.duration for wave in waves) > _MAX_DURATION:
        _fail("waves", "total duration exceeds 7200 seconds")
    if sum(len(wave.spawns) for wave in waves) > 1000:
        _fail("waves", "total spawn count exceeds 1000")
    limit = modifiers.get("time_limit")
    if limit is not None and limit < sum(wave.duration for wave in waves):
        _fail("modifiers.time_limit", "must allow all waves to finish")
    kind = data.get("kind", "campaign")
    if kind not in ("campaign", "challenge"):
        _fail("kind", "expected campaign or challenge")
    return Scenario(
        id=scenario_id, name=_text(data["name"], "name", 100),
        seed=_integer(data["seed"], "seed", 0, 2147483647), sun=sun,
        waves=tuple(waves), allowed_plants=allowed, modifiers=modifiers,
        kind=kind, chapter=_text(data.get("chapter", ""), "chapter", 100, empty=True),
        order=_integer(data.get("order", 0), "order", 0, 10000),
        description=_text(data.get("description", ""), "description", 500, empty=True),
        objective=_text(data.get("objective", ""), "objective", 300, empty=True),
    )


def load_scenario(scenario_id: str) -> Scenario:
    """Load a bundled scenario by a safe identifier, never by a filesystem path."""
    if not isinstance(scenario_id, str) or not _ID.fullmatch(scenario_id) or len(scenario_id) > 80:
        raise ContentError("invalid scenario id")
    resource = resources.files("pvz.data").joinpath(scenario_id + ".json")
    if not resource.is_file():
        raise ContentError(f"unknown scenario: {scenario_id}")
    try:
        scenario = parse_scenario(json.loads(resource.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ContentError(f"invalid JSON in {scenario_id}") from exc
    if scenario.id != scenario_id:
        raise ContentError(f"filename and scenario id differ: {scenario_id}")
    return scenario


def list_scenarios(kind: str | None = None) -> tuple[Scenario, ...]:
    """Return the catalogue in declared play order, with id as a stable tie-break."""
    if kind not in (None, "campaign", "challenge"):
        raise ContentError("kind must be campaign or challenge")
    scenarios = (
        load_scenario(resource.name[:-5])
        for resource in resources.files("pvz.data").iterdir()
        if resource.name.endswith(".json") and resource.is_file()
    )
    return tuple(sorted((item for item in scenarios if kind is None or item.kind == kind), key=lambda item: (item.order, item.id)))


def campaign_chapters() -> dict[str, tuple[Scenario, ...]]:
    """Group ordered campaign stages for menus without duplicating a manifest."""
    result: dict[str, list[Scenario]] = {}
    for scenario in list_scenarios("campaign"):
        result.setdefault(scenario.chapter, []).append(scenario)
    return {chapter: tuple(items) for chapter, items in result.items()}
