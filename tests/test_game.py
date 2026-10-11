import unittest

from pvz.game import Game
from pvz.types import Plant, PlantType, Projectile, Zombie, ZombieType


class ProjectileTests(unittest.TestCase):
    def game_with_target(self, tick=0.2):
        game = Game(tick, seed=1)
        game._next_spawn_time = 1000
        target = Zombie(ZombieType.NORMAL, 0, 2, 200)
        game.zombies.append(target)
        return game, target

    def test_new_shot_hits_adjacent_zombie(self):
        game, target = self.game_with_target()
        game.grid.set(Plant(PlantType.PEASHOOTER, 0, 1, 300))
        for _ in range(5):
            game.step()
        self.assertEqual(target.hp, 180)

    def test_projectile_speed_depends_on_seconds(self):
        positions = []
        for tick, count in ((0.1, 2), (0.2, 1)):
            game = Game(tick)
            game.projectiles.append(Projectile(0, 0))
            for _ in range(count):
                game.move_projectiles()
            positions.append(game.projectiles[0].col)
        self.assertEqual(positions[0], positions[1])

    def test_large_tick_cannot_skip_target(self):
        game, target = self.game_with_target(tick=1.0)
        game.projectiles.append(Projectile(0, 0))
        game.move_projectiles()
        self.assertEqual(target.hp, 180)
        self.assertFalse(game.projectiles)


if __name__ == '__main__':
    unittest.main()
