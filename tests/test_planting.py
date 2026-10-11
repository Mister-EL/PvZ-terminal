import unittest
from pvz.game import Game
from pvz.types import PlantType


class PlantingTests(unittest.TestCase):
    def test_cooldown_is_visible_and_expired_at_boundary(self):
        game = Game(0.2)
        self.assertTrue(game.place_selected())
        game.cursor_col = 2
        self.assertAlmostEqual(game.cooldown_remaining(PlantType.PEASHOOTER), 1.0)
        self.assertEqual(game.planting_error(), 'перезарядка: 1.0 с')
        self.assertFalse(game.place_selected())
        game.time_elapsed = 1.0
        self.assertEqual(game.cooldown_remaining(PlantType.PEASHOOTER), 0)
        self.assertTrue(game.place_selected())
        self.assertEqual(game.plants_placed, 2)

    def test_failed_plant_does_not_spend_sun_or_start_cooldown(self):
        game = Game(0.2)
        game.sun = 0
        self.assertFalse(game.place_selected())
        self.assertEqual(game.cooldown_remaining(game.selected), 0)
        self.assertEqual(game.plants_placed, 0)

    def test_invalid_cursor_cannot_plant(self):
        game = Game(0.2)
        game.cursor_row = -1
        self.assertFalse(game.place_selected())
        self.assertFalse(game.grid.iter_plants())
