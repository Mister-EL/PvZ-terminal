"""Local, versioned progress without names, contacts or account identifiers."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Any

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
