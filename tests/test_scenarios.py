from types import SimpleNamespace
import unittest

from pvz.game import Game
from pvz.types import PlantType, ZombieType


def scenario(**changes):
    values = dict(id='test', name='Проверка', seed=7, sun=200,
                  waves=(SimpleNamespace(number=1, duration=1.0, spawns=(
                      SimpleNamespace(time=0.4, row=1, zombie='NORMAL'),)),),
                  allowed_plants=('PEASHOOTER', 'SUNFLOWER'), modifiers={})
    values.update(changes)
    return SimpleNamespace(**values)


class ScenarioTests(unittest.TestCase):
    def test_finite_wave_has_deterministic_spawn_and_victory(self):
        game = Game(0.2, scenario=scenario())
        game.step()
        self.assertFalse(game.zombies)
        game.step()
        self.assertEqual([(z.row, z.zombie_type) for z in game.zombies], [(1, ZombieType.NORMAL)])
        game.zombies.clear()
        for _ in range(3):
            game.step()
        self.assertTrue(game.victory)
        self.assertTrue(game.game_over)
        self.assertEqual(game.wave_number, 1)

    def test_allowed_plants_and_initial_sun(self):
        game = Game(0.2, scenario=scenario())
        self.assertEqual(game.sun, 200)
        game.selected = PlantType.CHOMPER
        game.place_selected()
        self.assertFalse(game.grid.iter_plants())
        self.assertEqual(game.sun, 200)

    def test_scenario_setup_and_cost_modifier(self):
        game = Game(0.2, scenario=scenario(modifiers={
            'preplanted': ({'row': 0, 'col': 0, 'plant': 'SUNFLOWER'},),
            'plant_cost_multiplier': 0.5}))
        self.assertEqual(game.grid.get(0, 0).plant_type, PlantType.SUNFLOWER)
        game.place_selected()
        self.assertEqual(game.sun, 150)

    def test_difficulty_changes_health_and_attack_without_changing_timeline(self):
        games = [Game(0.2, scenario=scenario(), difficulty=d) for d in ('easy', 'normal', 'hard')]
        for game in games:
            game.step()
            game.step()
        health = [game.zombies[0].hp for game in games]
        self.assertLess(health[0], health[1])
        self.assertLess(health[1], health[2])

    def test_unknown_difficulty_and_invalid_tick_are_rejected(self):
        for tick in (0, -1, float('inf'), float('nan')):
            with self.assertRaises(ValueError):
                Game(tick)
        with self.assertRaises(ValueError):
            Game(0.2, difficulty='impossible')
