"""Regression checks for scenario restrictions through the public game API."""
import unittest

from pvz.content import ContentError, parse_scenario
from pvz.game import Game
from pvz.types import PlantType, ZombieType


def scenario(**modifiers):
    return parse_scenario({
        'id': 'modifier-check', 'name': 'Modifier check', 'seed': 91, 'sun': 500,
        'allowed_plants': [p.name for p in PlantType], 'modifiers': modifiers,
        'waves': [{'number': 1, 'duration': 60, 'spawns': [{'time': 30, 'row': 2, 'zombie': 'NORMAL'}]}],
    })


def place(game, plant, row, col):
    game.selected = plant
    game.cursor_row, game.cursor_col = row, col
    return game.place_selected()


class PlantLimitTests(unittest.TestCase):
    def test_limit_counts_preplanted_and_failed_placement_preserves_state(self):
        game = Game(.1, scenario=scenario(max_plants=2, preplanted=[{'row': 0, 'col': 0, 'plant': 'SUNFLOWER'}]))
        self.assertTrue(place(game, PlantType.PEASHOOTER, 0, 1))
        sun = game.sun
        self.assertFalse(place(game, PlantType.WALL_NUT, 0, 2))
        self.assertIn('лимит', game.planting_error())
        self.assertEqual(game.sun, sun)
        self.assertEqual(game.cooldown_remaining(PlantType.WALL_NUT), 0)
        self.assertEqual(game.plants_placed, 1)
        self.assertEqual(len(list(game.grid.iter_plants())), 2)

    def test_shovel_frees_a_slot(self):
        game = Game(.1, scenario=scenario(max_plants=1))
        self.assertTrue(place(game, PlantType.WALL_NUT, 0, 0))
        game.dig_up()
        self.assertTrue(place(game, PlantType.PEASHOOTER, 1, 0))

    def test_bomb_disappearing_frees_slot_automatically(self):
        game = Game(.1, scenario=scenario(max_plants=1))
        self.assertTrue(place(game, PlantType.CHERRY_BOMB, 1, 6))
        for _ in range(13):
            game.step()
        self.assertFalse(list(game.grid.iter_plants()))
        self.assertTrue(place(game, PlantType.PEASHOOTER, 2, 0))

    def test_validator_rejects_unusable_limits(self):
        for limit in (0, 46, True, 2.5):
            with self.subTest(limit=limit), self.assertRaises(ContentError):
                scenario(max_plants=limit)
        with self.assertRaises(ContentError):
            scenario(max_plants=1, preplanted=[{'row': 0, 'col': 0, 'plant': 'SUNFLOWER'}, {'row': 1, 'col': 0, 'plant': 'SUNFLOWER'}])


if __name__ == '__main__':
    unittest.main()
