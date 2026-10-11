import unittest
from pvz.game import Game
from pvz.types import Plant, PlantType, Projectile, ZombieType


class CombatEdgeTests(unittest.TestCase):
    def test_zombie_moving_into_occupied_projectile_cell_cannot_evade(self):
        game = Game(0.05)
        game._next_spawn_time = 1000
        zombie = game.create_zombie(ZombieType.NORMAL, 0)
        zombie.col = 6
        zombie.move_progress = 3.59
        game.zombies.append(zombie)
        game.projectiles.append(Projectile(0, 5.5))
        game.step()
        self.assertEqual(zombie.col, 5)
        game.step()
        self.assertEqual(zombie.hp, 180)
        self.assertFalse(game.projectiles)

    def test_chomper_bypasses_shield_and_chews_before_second_target(self):
        game = Game(0.2)
        game.grid.set(Plant(PlantType.CHOMPER, 0, 1, 300))
        targets = [game.create_zombie(ZombieType.SHIELD, 0) for _ in range(2)]
        for target in targets:
            target.col = 1
        game.zombies = targets[:]
        game.handle_attacks()
        self.assertEqual(len(game.zombies), 1)
        self.assertEqual(game.zombies_killed, 1)
        game.time_elapsed = 3.9
        game.handle_attacks()
        self.assertEqual(len(game.zombies), 1)
        game.time_elapsed = 4
        game.update_timers()
        game.handle_attacks()
        self.assertFalse(game.zombies)

    def test_nearest_target_hits_even_when_list_order_is_reversed(self):
        game = Game(1)
        far = game.create_zombie(ZombieType.NORMAL, 0)
        near = game.create_zombie(ZombieType.NORMAL, 0)
        far.col, near.col = 5, 2
        game.zombies = [far, near]
        game.projectiles.append(Projectile(0, 0))
        game.move_projectiles()
        self.assertEqual(near.hp, 180)
        self.assertEqual(far.hp, 200)
