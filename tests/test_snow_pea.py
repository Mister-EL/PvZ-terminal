import unittest
from pvz.game import Game
from pvz.types import Plant, PlantType, Projectile, ZombieType


class SnowPeaTests(unittest.TestCase):
    def test_ice_projectile_slows_movement_for_four_seconds(self):
        game = Game(0.2)
        game._next_spawn_time = 1000
        zombie = game.create_zombie(ZombieType.NORMAL, 0)
        zombie.col = 2
        game.zombies.append(zombie)
        game.projectiles.append(Projectile(0, 1, slows=True))
        game.move_projectiles()
        self.assertEqual(zombie.hp, 180)
        self.assertEqual(zombie.slowed_until, 4.0)
        for _ in range(18):
            game.spawn_and_move_zombies()
        self.assertEqual(zombie.col, 2)
        game.time_elapsed = 4
        for _ in range(9):
            game.spawn_and_move_zombies()
        self.assertEqual(zombie.col, 1)

    def test_shield_blocks_freeze(self):
        game = Game(0.2)
        zombie = game.create_zombie(ZombieType.SHIELD, 0)
        zombie.col = 2
        game.zombies.append(zombie)
        game.projectiles.append(Projectile(0, 1, slows=True))
        game.move_projectiles()
        self.assertEqual(zombie.slowed_until, 0)

    def test_snow_plant_fires_ice_projectile(self):
        game = Game(0.2)
        game.grid.set(Plant(PlantType.SNOW_PEA, 0, 0, 300))
        game.zombies.append(game.create_zombie(ZombieType.NORMAL, 0))
        game.time_elapsed = 0.8
        game.handle_attacks()
        self.assertEqual(len(game.projectiles), 1)
        self.assertTrue(game.projectiles[0].slows)
