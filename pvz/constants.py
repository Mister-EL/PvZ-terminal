from __future__ import annotations

from typing import Dict

from .types import PlantType, ZombieType

GRID_WIDTH = 9
GRID_HEIGHT = 5

PROJECTILE_SPEED_CELLS_PER_SECOND = 5.0
# Compatibility for external code that imported the old constant.
PROJECTILE_SPEED_CELLS_PER_TICK = 1
PROJECTILE_DAMAGE = 20

PEASHOOTER_INTERVAL = 0.8
SUNFLOWER_INTERVAL = 4.0
SKY_SUN_INTERVAL = 8.0
SUN_AMOUNT = 25
CHOMPER_CHEW_TIME = 4.0
ZOMBIE_MOVE_INTERVAL = 3.6

SUN_START = 300

STATUS_LINE_TEMPLATE = (
    "Солнце:{sun} | Счёт:{score} | Выбор:{sel} | 1:P 2:S 3:W 4:C | "
    "WASD курсор, Пробел посадка, R выкопать, P пауза, Q выход"
)

MESSAGE_DURATION = 2.0

PLANT_COSTS: Dict[PlantType, int] = {
    PlantType.PEASHOOTER: 100,
    PlantType.SUNFLOWER: 50,
    PlantType.WALL_NUT: 50,
    PlantType.CHOMPER: 150,
}

PLANT_COOLDOWNS: Dict[PlantType, float] = {
    PlantType.PEASHOOTER: 1.0,
    PlantType.SUNFLOWER: 1.0,
    PlantType.WALL_NUT: 2.0,
    PlantType.CHOMPER: 7.0,
}

PLANT_HEALTH: Dict[PlantType, int] = {
    PlantType.PEASHOOTER: 300,
    PlantType.SUNFLOWER: 200,
    PlantType.WALL_NUT: 1200,
    PlantType.CHOMPER: 300,
}

ZOMBIE_HEALTH: Dict[ZombieType, int] = {
    ZombieType.NORMAL: 200,
    ZombieType.CONE: 400,
    ZombieType.BUCKET: 700,
    ZombieType.RUNNER: 130,
    ZombieType.SHIELD: 380,
}

ZOMBIE_DPS: Dict[ZombieType, float] = {
    ZombieType.NORMAL: 20.0,
    ZombieType.CONE: 30.0,
    ZombieType.BUCKET: 40.0,
    ZombieType.RUNNER: 15.0,
    ZombieType.SHIELD: 25.0,
}

ZOMBIE_SCORE: Dict[ZombieType, int] = {
    ZombieType.NORMAL: 1,
    ZombieType.CONE: 2,
    ZombieType.BUCKET: 3,
    ZombieType.RUNNER: 2,
    ZombieType.SHIELD: 3,
}

DIFFICULTIES = {
    "easy": {"health": 0.75, "damage": 0.75, "speed": 0.85, "spawn": 1.25},
    "normal": {"health": 1.0, "damage": 1.0, "speed": 1.0, "spawn": 1.0},
    "hard": {"health": 1.25, "damage": 1.2, "speed": 1.15, "spawn": 0.8},
}

ZOMBIE_MOVE_INTERVALS = {kind: ZOMBIE_MOVE_INTERVAL for kind in ZombieType}
ZOMBIE_MOVE_INTERVALS[ZombieType.RUNNER] = ZOMBIE_MOVE_INTERVAL / 2
SHIELD_HEALTH = 180
ZOMBIE_NAMES = {
    ZombieType.NORMAL: "Обычный", ZombieType.CONE: "Конус",
    ZombieType.BUCKET: "Ведро", ZombieType.RUNNER: "Бегун", ZombieType.SHIELD: "Щитоносец",
}
