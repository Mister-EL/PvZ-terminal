import unittest
from pvz.game import Game
from pvz.types import Plant, PlantType


class DoubleSunflowerTests(unittest.TestCase):
    def test_double_sunflower_harvests_twice_as_much(self):
        game = Game(0.2)
        game.grid.set(Plant(PlantType.DOUBLE_SUNFLOWER, 0, 0, 250))
        game.time_elapsed = 4.0
        game.generate_sun()
        self.assertEqual(game.sun, 350)
        self.assertEqual(game.sun_generated, 50)

    def test_double_sunflower_requires_larger_investment(self):
        game = Game(0.2)
        self.assertGreater(game.plant_cost(PlantType.DOUBLE_SUNFLOWER), game.plant_cost(PlantType.SUNFLOWER))
        game.selected = PlantType.DOUBLE_SUNFLOWER
        self.assertTrue(game.place_selected())
        self.assertEqual(game.sun, 175)
