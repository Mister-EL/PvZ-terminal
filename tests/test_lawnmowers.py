import unittest
from pvz.game import Game
from pvz.types import Zombie, ZombieType


class LawnmowerTests(unittest.TestCase):
    def test_one_mower_clears_entire_breached_lane_only(self):
        game = Game(0.2)
        game.zombies = [Zombie(ZombieType.NORMAL, 1, -1, 200),
                        Zombie(ZombieType.BUCKET, 1, 8, 700),
                        Zombie(ZombieType.NORMAL, 2, 8, 200)]
        game.check_loss()
        self.assertFalse(game.game_over)
        self.assertEqual([z.row for z in game.zombies], [2])
        self.assertFalse(game.lawnmowers[1])
        self.assertEqual(game.lawnmowers_used, 1)
        self.assertEqual(game.zombies_killed, 2)
        self.assertEqual(game.score, 4)

    def test_second_breach_in_same_lane_is_game_over(self):
        game = Game(0.2)
        game.zombies.append(Zombie(ZombieType.NORMAL, 1, -1, 200))
        game.check_loss()
        game.zombies.append(Zombie(ZombieType.NORMAL, 1, -1, 200))
        game.check_loss()
        self.assertTrue(game.game_over)
        self.assertFalse(game.victory)
