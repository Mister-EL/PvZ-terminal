import unittest
from pvz.game import Game
from pvz.types import PlantType, ZombieType


class CherryBombTests(unittest.TestCase):
    def test_bomb_waits_then_clears_three_by_three_without_harming_other_plants(self):
        game = Game(0.2)
        game.cursor_row, game.cursor_col = 2, 3
        game.selected = PlantType.CHERRY_BOMB
        self.assertTrue(game.place_selected())
        for row, col in ((1, 2), (3, 4), (2, 5)):
            zombie = game.create_zombie(ZombieType.BUCKET, row)
            zombie.col = col
            game.zombies.append(zombie)
        game.time_elapsed = 1.0
        game.handle_attacks()
        self.assertEqual(len(game.zombies), 3)
        game.time_elapsed = 1.2
        game.handle_attacks()
        self.assertEqual([(z.row, z.col) for z in game.zombies], [(2, 5)])
        self.assertIsNone(game.grid.get(2, 3))
        self.assertEqual(game.zombies_killed, 2)

    def test_bomb_bypasses_shield(self):
        game = Game(0.2)
        game.selected = PlantType.CHERRY_BOMB
        game.place_selected()
        zombie = game.create_zombie(ZombieType.SHIELD, game.cursor_row)
        zombie.col = game.cursor_col
        game.zombies.append(zombie)
        game.time_elapsed = 1.2
        game.handle_attacks()
        self.assertFalse(game.zombies)
