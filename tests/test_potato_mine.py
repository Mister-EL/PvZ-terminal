import unittest
from pvz.game import Game
from pvz.types import PlantType, ZombieType


class PotatoMineTests(unittest.TestCase):
    def test_mine_arms_then_explodes_in_its_lane_only(self):
        game = Game(0.2)
        game.selected = PlantType.POTATO_MINE
        game.cursor_row, game.cursor_col = 2, 3
        game.place_selected()
        for row, col in ((2, 3), (2, 4), (1, 3), (2, 5)):
            zombie = game.create_zombie(ZombieType.NORMAL, row)
            zombie.col = col
            game.zombies.append(zombie)
        game.time_elapsed = 11.8
        game.handle_attacks()
        self.assertEqual(len(game.zombies), 4)
        game.time_elapsed = 12
        game.handle_attacks()
        self.assertEqual([(z.row, z.col) for z in game.zombies], [(1, 3), (2, 5)])
        self.assertIsNone(game.grid.get(2, 3))

    def test_armed_mine_waits_for_contact(self):
        game = Game(0.2)
        game.selected = PlantType.POTATO_MINE
        game.place_selected()
        zombie = game.create_zombie(ZombieType.NORMAL, game.cursor_row)
        zombie.col = game.cursor_col + 1
        game.zombies.append(zombie)
        game.time_elapsed = 12
        game.handle_attacks()
        self.assertEqual(len(game.zombies), 1)
        self.assertIsNotNone(game.grid.get(game.cursor_row, game.cursor_col))
