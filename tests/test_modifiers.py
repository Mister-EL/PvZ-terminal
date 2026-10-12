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


class NoMowerTests(unittest.TestCase):
    def test_disabled_mowers_lose_on_the_first_breach(self):
        game = Game(.1, scenario=scenario(no_mowers=True))
        self.assertEqual(game.lawnmowers, [False] * 5)
        zombie = game.create_zombie(ZombieType.NORMAL, 2)
        zombie.col = -1
        game.zombies.append(zombie)
        game.check_loss()
        self.assertTrue(game.game_over)
        self.assertEqual(game.game_over_reason, 'Game Over')
        self.assertEqual(game.lawnmowers_used, 0)
        self.assertEqual(game.zombies_killed, 0)

    def test_explicit_false_and_default_keep_the_emergency_save(self):
        for modifiers in ({}, {'no_mowers': False}):
            game = Game(.1, scenario=scenario(**modifiers))
            zombie = game.create_zombie(ZombieType.NORMAL, 2)
            zombie.col = -1
            game.zombies.append(zombie)
            game.check_loss()
            self.assertFalse(game.game_over)
            self.assertEqual(game.lawnmowers_used, 1)
            self.assertEqual(game.zombies_killed, 1)

    def test_validator_requires_boolean(self):
        for value in (1, 0, 'false', None):
            with self.subTest(value=value), self.assertRaises(ContentError):
                scenario(no_mowers=value)


class BlockedCellTests(unittest.TestCase):
    def test_blocked_placement_does_not_spend_sun_or_start_cooldown(self):
        game = Game(.1, scenario=scenario(blocked_cells=[{'row': 2, 'col': 3}]))
        self.assertEqual(game.blocked_cells, frozenset({(2, 3)}))
        sun = game.sun
        self.assertFalse(place(game, PlantType.PEASHOOTER, 2, 3))
        self.assertIn('закрыта', game.planting_error())
        self.assertEqual(game.sun, sun)
        self.assertEqual(game.cooldown_remaining(PlantType.PEASHOOTER), 0)
        self.assertTrue(place(game, PlantType.PEASHOOTER, 2, 2))

    def test_zombies_can_cross_a_blocked_planting_cell(self):
        game = Game(.1, scenario=scenario(blocked_cells=[{'row': 2, 'col': 3}]))
        zombie = game.create_zombie(ZombieType.NORMAL, 2)
        zombie.col, zombie.move_progress = 4, 3.6
        game.zombies.append(zombie)
        game.step()
        self.assertEqual(zombie.col, 3)

    def test_default_has_no_blocked_cells_and_input_cannot_mutate_scenario(self):
        self.assertFalse(Game(.1, scenario=scenario()).blocked_cells)
        source = [{'row': 2, 'col': 3}]
        stage = scenario(blocked_cells=source)
        source[0]['col'] = 4
        self.assertEqual(Game(.1, scenario=stage).blocked_cells, frozenset({(2, 3)}))

    def test_validator_rejects_collisions_and_out_of_lawn_cells(self):
        for cells in ({}, [{'row': 5, 'col': 0}], [{'row': 0, 'col': 9}], [{'row': True, 'col': 0}], [{'row': 1, 'col': 1}, {'row': 1, 'col': 1}], [{'row': 0, 'col': 0, 'extra': True}]):
            with self.subTest(cells=cells), self.assertRaises(ContentError):
                scenario(blocked_cells=cells)
        with self.assertRaises(ContentError):
            scenario(blocked_cells=[{'row': 1, 'col': 1}], preplanted=[{'row': 1, 'col': 1, 'plant': 'SUNFLOWER'}])


class SkySunIntervalTests(unittest.TestCase):
    def test_custom_interval_arrives_exactly_at_the_boundary(self):
        game = Game(.2, scenario=scenario(sky_sun_interval=3))
        self.assertEqual(game.sky_sun_interval, 3)
        for _ in range(14):
            game.step()
        self.assertEqual(game.sun, 500)
        game.step()
        self.assertEqual(game.sun, 525)

    def test_custom_interval_is_independent_of_ui_tick(self):
        for tick in (.05, .2, .5, 4):
            with self.subTest(tick=tick):
                game = Game(tick, scenario=scenario(sky_sun_interval=3))
                for _ in range(round(12 / tick)):
                    game.step()
                self.assertEqual(game.sun, 600)
                self.assertEqual(game.sun_generated, 100)

    def test_disabling_passive_income_wins_over_custom_interval(self):
        game = Game(1, scenario=scenario(sky_sun_interval=1, passive_sun=False))
        for _ in range(10):
            game.step()
        self.assertEqual(game.sun, 500)

    def test_default_remains_eight_seconds(self):
        game = Game(1, scenario=scenario())
        self.assertEqual(game.sky_sun_interval, 8)
        for _ in range(8):
            game.step()
        self.assertEqual(game.sun, 525)

    def test_validator_bounds_interval_and_rejects_nonfinite_values(self):
        for value in (0, 121, True, float('nan'), float('inf'), '3'):
            with self.subTest(value=value), self.assertRaises(ContentError):
                scenario(sky_sun_interval=value)
        self.assertEqual(scenario(sky_sun_interval=2.5).modifiers['sky_sun_interval'], 2.5)


if __name__ == '__main__':
    unittest.main()
