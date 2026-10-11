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


class ZombieMovementTests(unittest.TestCase):
    def test_eating_does_not_charge_movement(self):
        game = Game(0.2, seed=1)
        game._next_spawn_time = 1000
        zombie = Zombie(ZombieType.NORMAL, 0, 3, 200)
        game.zombies.append(zombie)
        game.grid.set(Plant(PlantType.WALL_NUT, 0, 3, 1200))
        for _ in range(25):
            game.spawn_and_move_zombies()
        game.grid.remove(0, 3)
        game.spawn_and_move_zombies()
        self.assertEqual(zombie.col, 3)
        self.assertAlmostEqual(zombie.move_progress, 0.2)


class PauseTests(unittest.TestCase):
    def test_pause_freezes_simulation_and_planting(self):
        game = Game(0.2)
        game.paused = True
        game.step()
        game.place_selected()
        self.assertEqual(game.time_elapsed, 0)
        self.assertEqual(game.sun, 300)
        self.assertFalse(game.grid.iter_plants())

    def test_pause_does_not_allow_shovel(self):
        game = Game(0.2)
        game.place_selected()
        game.paused = True
        game.dig_up()
        self.assertIsNotNone(game.grid.get(game.cursor_row, game.cursor_col))

    def test_end_freezes_simulation_and_does_not_resume(self):
        game = Game(0.2)
        game.game_over = True
        game.step()
        game.place_selected()
        game.handle_keypress(ord('p'))
        self.assertEqual(game.time_elapsed, 0)
        self.assertFalse(game.grid.iter_plants())
        self.assertFalse(game.paused)


if __name__ == '__main__':
    unittest.main()
