import unittest
from pvz.game import Game
from pvz.types import Plant, PlantType


class SimulationClockTests(unittest.TestCase):
    def snapshot_after_twenty_seconds(self, tick, steps):
        game = Game(tick, seed=27)
        for row in range(5):
            game.grid.set(Plant(PlantType.PEASHOOTER, row, 1, 300))
        for _ in range(steps):
            game.step()
        return (game.time_elapsed, game.sun, game.score,
                [(z.row, z.col, z.hp, round(z.move_progress, 5)) for z in game.zombies],
                [(p.row, round(p.col, 5)) for p in game.projectiles])

    def test_tick_size_does_not_change_seeded_combat(self):
        expected = self.snapshot_after_twenty_seconds(0.1, 200)
        for tick, steps in ((0.2, 100), (0.5, 40), (0.04, 500), (0.025, 800)):
            self.assertEqual(expected, self.snapshot_after_twenty_seconds(tick, steps))

    def test_large_tick_stops_exactly_when_game_ends(self):
        from types import SimpleNamespace
        scenario = SimpleNamespace(seed=1, sun=0, waves=(), allowed_plants=(), modifiers={})
        game = Game(2.0, scenario=scenario)
        game.step()
        self.assertTrue(game.victory)
        self.assertLessEqual(game.time_elapsed, 0.1)
