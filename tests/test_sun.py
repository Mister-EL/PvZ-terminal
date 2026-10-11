import unittest
from types import SimpleNamespace
from pvz.game import Game
from pvz.types import Plant, PlantType


class EconomyTests(unittest.TestCase):
    def test_sky_sun_arrives_at_intervals(self):
        game = Game(0.2)
        game._next_spawn_time = 1000
        for _ in range(40):
            game.step()
        self.assertEqual(game.sun, 325)

    def test_sky_sun_can_be_disabled_and_cap_applies_to_harvest(self):
        scenario = SimpleNamespace(seed=1, sun=190, waves=(), allowed_plants=('SUNFLOWER',),
                                   modifiers={'passive_sun': False, 'sun_cap': 200})
        game = Game(0.2, scenario=scenario)
        game.grid.set(Plant(PlantType.SUNFLOWER, 0, 0, 200))
        game.time_elapsed = 8
        game.generate_sun()
        self.assertEqual(game.sun, 200)

    def test_sunflower_catches_up_when_a_tick_crosses_multiple_intervals(self):
        game = Game(0.2)
        game.grid.set(Plant(PlantType.SUNFLOWER, 0, 0, 200))
        game.time_elapsed = 9
        game.generate_sun()
        self.assertEqual(game.sun, 375)  # two harvests plus one sky drop

    def test_messages_expire_using_simulated_time(self):
        game = Game(0.2)
        game.show_message('test')
        game.time_elapsed = 3
        game.update_timers()
        self.assertEqual(game.current_message(), '')
