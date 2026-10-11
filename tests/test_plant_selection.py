import unittest
from types import SimpleNamespace
from pvz.constants import PLANT_COSTS, PLANT_COOLDOWNS, PLANT_HEALTH, PLANT_NAMES, PLANT_DESCRIPTIONS
from pvz.game import Game
from pvz.types import PlantType


class PlantSelectionTests(unittest.TestCase):
    def test_all_nine_slots_are_selectable_in_survival(self):
        game = Game(0.2)
        for slot, kind in enumerate(PlantType, 1):
            game.handle_keypress(ord(str(slot)))
            self.assertEqual(game.selected, kind)
            self.assertIn(kind, PLANT_NAMES)
            self.assertIn(kind, PLANT_DESCRIPTIONS)
            self.assertIn(kind, PLANT_HEALTH)
            self.assertIn(kind, PLANT_COSTS)
            self.assertIn(kind, PLANT_COOLDOWNS)

    def test_restricted_scenario_selects_first_available_plant(self):
        scenario = SimpleNamespace(seed=1, sun=300, waves=(), allowed_plants=('WALL_NUT', 'POTATO_MINE'), modifiers={})
        game = Game(0.2, scenario=scenario)
        self.assertEqual(game.selected, PlantType.WALL_NUT)
        self.assertFalse(game.select_plant_type(1))
        self.assertEqual(game.selected, PlantType.WALL_NUT)
        self.assertTrue(game.select_plant_type(8))
        self.assertEqual(game.selected, PlantType.POTATO_MINE)
