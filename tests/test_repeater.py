import unittest
from pvz.game import Game
from pvz.types import Plant, PlantType, ZombieType


class RepeaterTests(unittest.TestCase):
    def test_repeater_fires_two_peas_and_waits_for_next_burst(self):
        game = Game(0.2)
        game.grid.set(Plant(PlantType.REPEATER, 0, 0, 300))
        zombie = game.create_zombie(ZombieType.NORMAL, 0)
        zombie.col = 2
        game.zombies.append(zombie)
        game.time_elapsed = 0.8
        game.handle_attacks()
        self.assertEqual(len(game.projectiles), 2)
        game.move_projectiles()
        self.assertEqual(zombie.hp, 160)
        game.time_elapsed = 1.0
        game.handle_attacks()
        self.assertFalse(game.projectiles)

    def test_repeater_does_not_fire_into_empty_lane(self):
        game = Game(0.2)
        game.grid.set(Plant(PlantType.REPEATER, 0, 0, 300))
        game.time_elapsed = 10
        game.handle_attacks()
        self.assertFalse(game.projectiles)
