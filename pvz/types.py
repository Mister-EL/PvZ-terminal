from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PlantType(Enum):
    PEASHOOTER = "P"
    SUNFLOWER = "S"
    WALL_NUT = "W"
    CHOMPER = "C"
    SNOW_PEA = "I"
    CHERRY_BOMB = "X"


class ZombieType(Enum):
    NORMAL = "z"
    CONE = "Z"
    BUCKET = "B"
    RUNNER = "r"
    SHIELD = "H"


@dataclass
class Plant:
    plant_type: PlantType
    row: int
    col: int
    hp: float
    last_action_time: float = 0.0
    chewing_until: float = 0.0

    def is_chewing(self, now: float) -> bool:
        return self.plant_type == PlantType.CHOMPER and now < self.chewing_until


@dataclass
class Zombie:
    zombie_type: ZombieType
    row: int
    col: int
    hp: float
    move_progress: float = 0.0
    shield_hp: float = 0.0
    slowed_until: float = 0.0

    @property
    def char(self) -> str:
        return self.zombie_type.value


@dataclass
class Projectile:
    row: int
    col: float
    slows: bool = False
