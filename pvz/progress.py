"""Local, versioned progress without names, contacts or account identifiers."""
from __future__ import annotations

import hashlib
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Iterable

SCHEMA_VERSION = 1
MAX_FILE_BYTES = 1_048_576
MAX_SCENARIOS = 256
MAX_COUNTER = 1_000_000_000_000
MAX_DURATION = 10_000_000.0
DIFFICULTY_IDS = frozenset(('easy', 'normal', 'hard'))
STAT_NAMES = ('kills', 'plants_placed', 'plants_lost', 'lawnmowers_used', 'sun_generated')
_ID_PATTERN = re.compile(r'[a-z0-9][a-z0-9-]{0,79}\Z')


class ProgressError(ValueError):
    """Progress is invalid or saving would replace an unverified file."""


def _empty_progress() -> dict[str, Any]:
    return {'version': SCHEMA_VERSION, 'results': {}, 'achievements': []}


def _counter(value: Any) -> bool:
    return type(value) is int and 0 <= value <= MAX_COUNTER


def _duration(value: Any, *, cumulative: bool = False) -> bool:
    limit = MAX_COUNTER if cumulative else MAX_DURATION
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= limit


def _valid_id(value: Any) -> bool:
    return isinstance(value, str) and _ID_PATTERN.fullmatch(value) is not None


def _validate_stats(stats: Any) -> None:
    if not isinstance(stats, dict) or set(stats) != {*STAT_NAMES, 'duration'}:
        raise ProgressError('Invalid progress statistics')
    if not all(_counter(stats[name]) for name in STAT_NAMES) or not _duration(stats['duration'], cumulative=True):
        raise ProgressError('Progress statistics exceed limits')


def _validate_progress(data: Any) -> None:
    if not isinstance(data, dict) or set(data) != {'version', 'results', 'achievements'}:
        raise ProgressError('Invalid progress structure')
    if type(data['version']) is not int or data['version'] != SCHEMA_VERSION:
        raise ProgressError('Unsupported progress version')
    results = data['results']
    if not isinstance(results, dict) or len(results) > MAX_SCENARIOS:
        raise ProgressError('Too many saved scenarios')
    for scenario_id, difficulties in results.items():
        if not _valid_id(scenario_id) or not isinstance(difficulties, dict) or not difficulties:
            raise ProgressError('Invalid saved scenario')
        if not set(difficulties) <= DIFFICULTY_IDS:
            raise ProgressError('Invalid saved difficulty')
        for result in difficulties.values():
            expected = {'attempts', 'wins', 'best_score', 'best_duration', 'best_run', 'totals'}
            if not isinstance(result, dict) or set(result) != expected:
                raise ProgressError('Invalid saved result')
            if not _counter(result['attempts']) or result['attempts'] < 1:
                raise ProgressError('Invalid attempt count')
            if not _counter(result['wins']) or result['wins'] > result['attempts']:
                raise ProgressError('Invalid victory count')
            if not _counter(result['best_score']):
                raise ProgressError('Invalid best score')
            best_duration = result['best_duration']
            if (best_duration is None) != (result['wins'] == 0):
                raise ProgressError('Winning duration is missing or contradictory')
            if best_duration is not None and not _duration(best_duration):
                raise ProgressError('Invalid winning duration')
            _validate_stats(result['totals'])
            run = result['best_run']
            if not isinstance(run, dict) or set(run) != {*STAT_NAMES, 'duration', 'score', 'victory'}:
                raise ProgressError('Invalid best run')
            _validate_stats({name: run[name] for name in (*STAT_NAMES, 'duration')})
            if not _duration(run['duration']) or not _counter(run['score']) or type(run['victory']) is not bool:
                raise ProgressError('Invalid best run values')
            if run['score'] != result['best_score']:
                raise ProgressError('Best run and score disagree')
    achievements = data['achievements']
    if not isinstance(achievements, list) or len(achievements) > 64:
        raise ProgressError('Invalid achievement list')
    if any(not _valid_id(item) for item in achievements) or len(set(achievements)) != len(achievements):
        raise ProgressError('Invalid achievement identifiers')


class ProgressStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.data = _empty_progress()
        self.load_error: str | None = None
        self._fingerprint: str | None = None
        self._writable = True

    @staticmethod
    def _fingerprint_bytes(raw: bytes) -> str:
        return hashlib.sha256(raw).hexdigest()

    def _read_bytes(self) -> bytes | None:
        if self.path.is_symlink():
            raise ProgressError('Progress path must not be a symbolic link')
        try:
            with self.path.open('rb') as source:
                raw = source.read(MAX_FILE_BYTES + 1)
        except FileNotFoundError:
            return None
        if len(raw) > MAX_FILE_BYTES:
            raise ProgressError('Progress file exceeds size limit')
        return raw

    def load(self) -> 'ProgressStore':
        self.data = _empty_progress()
        self.load_error = None
        self._fingerprint = None
        self._writable = True
        try:
            raw = self._read_bytes()
            if raw is not None:
                self._fingerprint = self._fingerprint_bytes(raw)
                data = json.loads(raw)
                _validate_progress(data)
                self.data = data
        except (OSError, UnicodeError, ValueError, RecursionError) as error:
            self.load_error = str(error)
            self._writable = False
        return self

    def best_result(self, scenario_id: str, difficulty: str = "normal") -> dict[str, Any] | None:
        result = self.data['results'].get(scenario_id, {}).get(difficulty)
        return deepcopy(result) if result is not None else None

    def is_completed(self, scenario_id: str, difficulty: str = "normal") -> bool:
        result = self.data['results'].get(scenario_id, {}).get(difficulty)
        return bool(result and result['wins'] > 0)

    def unlocked_campaign(self, scenarios: Iterable[Any], difficulty: str = "normal") -> tuple[str, ...]:
        if difficulty not in DIFFICULTY_IDS:
            raise ProgressError('Invalid campaign difficulty')
        ids = [scenario if isinstance(scenario, str) else scenario.id for scenario in scenarios]
        if any(not _valid_id(item) for item in ids) or len(set(ids)) != len(ids):
            raise ProgressError('Invalid campaign sequence')
        unlocked = []
        for scenario_id in ids:
            unlocked.append(scenario_id)
            if not self.is_completed(scenario_id, difficulty):
                break
        return tuple(unlocked)

    def record_result(self, scenario_id: str, difficulty: str, *, victory: bool,
                      score: int, duration: float, kills: int = 0,
                      plants_placed: int = 0, plants_lost: int = 0,
                      lawnmowers_used: int = 0, sun_generated: int = 0) -> tuple[str, ...]:
        if not self._writable:
            raise ProgressError('Original progress was not verified; recording is disabled')
        if not _valid_id(scenario_id) or difficulty not in DIFFICULTY_IDS:
            raise ProgressError('Invalid scenario or difficulty')
        if type(victory) is not bool or not _counter(score) or not _duration(duration):
            raise ProgressError('Invalid match result')
        stats = {'kills': kills, 'plants_placed': plants_placed, 'plants_lost': plants_lost,
                 'lawnmowers_used': lawnmowers_used, 'sun_generated': sun_generated,
                 'duration': float(duration)}
        _validate_stats(stats)
        if lawnmowers_used > 5:
            raise ProgressError('Match statistics are contradictory')
        staged = deepcopy(self.data)
        difficulties = staged['results'].setdefault(scenario_id, {})
        result = difficulties.get(difficulty)
        run = {**stats, 'score': score, 'victory': victory}
        if result is None:
            result = {'attempts': 0, 'wins': 0, 'best_score': score, 'best_duration': None,
                      'best_run': run, 'totals': {name: 0 for name in (*STAT_NAMES, 'duration')}}
            difficulties[difficulty] = result
        result['attempts'] += 1
        result['wins'] += int(victory)
        if score > result['best_score'] or (score == result['best_score'] and duration < result['best_run']['duration']):
            result['best_score'] = score
            result['best_run'] = run
        if victory and (result['best_duration'] is None or duration < result['best_duration']):
            result['best_duration'] = float(duration)
        for name in (*STAT_NAMES, 'duration'):
            result['totals'][name] += stats[name]
        _validate_progress(staged)
        self.data = staged
        return ()

    def record_game(self, game) -> tuple[str, ...]:
        if not game.game_over:
            raise ProgressError('A running match cannot be recorded')
        if game.game_over_reason == "Выход":
            return ()
        scenario_id = game.scenario.id if game.scenario else 'survival'
        return self.record_result(scenario_id, game.difficulty, victory=game.victory,
                                  score=game.score, duration=game.time_elapsed,
                                  kills=game.zombies_killed, plants_placed=game.plants_placed,
                                  plants_lost=game.plants_lost, lawnmowers_used=game.lawnmowers_used,
                                  sun_generated=game.sun_generated)

    def save(self) -> None:
        if not self._writable:
            raise ProgressError('Original progress was not verified; saving is disabled')
        _validate_progress(self.data)
        raw = (json.dumps(self.data, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')
        if len(raw) > MAX_FILE_BYTES:
            raise ProgressError('Progress file exceeds size limit')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        current = self._read_bytes()
        current_fingerprint = self._fingerprint_bytes(current) if current is not None else None
        if current_fingerprint != self._fingerprint:
            raise ProgressError('Progress changed outside this session; reload before saving')
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(mode='wb', prefix='.pvz-progress-', suffix='.tmp', dir=self.path.parent, delete=False) as target:
                temporary_path = Path(target.name)
                target.write(raw)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary_path, self.path)
            temporary_path = None
            self._fingerprint = self._fingerprint_bytes(raw)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
