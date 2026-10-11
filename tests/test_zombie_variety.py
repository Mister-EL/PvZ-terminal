import unittest
from pvz.game import Game
from pvz.types import Projectile, Zombie, ZombieType


class ZombieVarietyTests(unittest.TestCase):
    def test_runner_moves_twice_as_fast_with_less_health(self):
        game = Game(0.2)
        game._next_spawn_time = 1000
        normal = game.create_zombie(ZombieType.NORMAL, 0)
        runner = game.create_zombie(ZombieType.RUNNER, 1)
        game.zombies = [normal, runner]
        for _ in range(9):
            game.spawn_and_move_zombies()
        self.assertEqual(normal.col, 8)
        self.assertEqual(runner.col, 7)
        self.assertLess(runner.hp, normal.hp)

    def test_shield_absorbs_projectiles_and_spill_reaches_health(self):
        game = Game(0.2)
        zombie = game.create_zombie(ZombieType.SHIELD, 0)
        zombie.col = 2
        game.zombies.append(zombie)
        starting_hp = zombie.hp
        zombie.shield_hp = 10
        game.projectiles.append(Projectile(0, 1))
        game.move_projectiles()
        self.assertEqual(zombie.shield_hp, 0)
        self.assertEqual(zombie.hp, starting_hp - 10)
