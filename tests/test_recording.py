import unittest

from pvz.content import list_scenarios
from pvz.game import Game
from pvz.recording import MatchRecording
from pvz.replay import game_stats, play_replay


class LiveRecordingTests(unittest.TestCase):
    def test_live_match_and_playback_have_identical_final_state(self):
        for tick in (.05, .2, .5):
            with self.subTest(tick=tick):
                game = Game(tick, 71)
                recording = MatchRecording(game)
                for key in "2 w1 sdr ":
                    recording.handle_keypress(ord(key))
                    game.step()
                recording.handle_keypress(ord("p"))
                for _ in range(10):
                    game.step()
                recording.handle_keypress(ord("P"))
                for _ in range(80):
                    game.step()
                recording.handle_keypress(ord("q"))
                result = play_replay(recording.finish())
                self.assertEqual(result.stats, game_stats(game))

    def test_disallowed_selection_and_unknown_input_do_not_change_replay(self):
        scenario = next(s for s in list_scenarios()
                        if 'POTATO_MINE' not in s.allowed_plants)
        game = Game(.2, scenario=scenario)
        recording = MatchRecording(game)
        recording.handle_keypress(ord("8"))
        recording.handle_keypress(-1)
        recording.handle_keypress(ord("q"))
        self.assertEqual([a.kind for a in recording.finish().actions], ["quit"])
        self.assertEqual(play_replay(recording.finish()).stats, game_stats(game))

    def test_input_after_end_is_ignored(self):
        game = Game(.2, 1)
        recording = MatchRecording(game)
        recording.handle_keypress(ord("q"))
        recording.handle_keypress(ord("w"))
        self.assertEqual(len(recording.finish().actions), 1)
