import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pvz.content import list_scenarios
from pvz.game import Game
from pvz.recording import MatchRecording
from pvz.replay import game_stats, load_replay, play_replay
from pvz.ui import TerminalApp


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

    def app_for_directory(self, directory):
        app = object.__new__(TerminalApp)
        app.seed, app.tick_seconds, app.difficulty = 11, .2, 'normal'
        app.record_dir, app.progress = directory, None
        games, alerts = [], []
        def play(game, recording):
            games.append(game)
            for key in '2 w1 ':
                app.apply_input(game, ord(key), recording)
                game.step()
            app.apply_input(game, ord('q'), recording)
        app.play = play
        app.message = lambda title, lines: alerts.append(title)
        return app, games, alerts

    def test_session_quit_saves_exact_playback_without_overwriting_other_matches(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary) / 'records'
            app, games, alerts = self.app_for_directory(directory)
            app.session()
            first, = directory.glob('*.json')
            original = first.read_bytes()
            self.assertEqual(play_replay(load_replay(first)).stats, game_stats(games[0]))
            app.session()
            self.assertEqual(len(list(directory.glob('*.json'))), 2)
            self.assertEqual(first.read_bytes(), original)
            self.assertFalse(alerts)

    def test_unavailable_record_directory_preserves_existing_file_and_match(self):
        with TemporaryDirectory() as temporary:
            target = Path(temporary) / 'protected-file'
            target.write_text('existing contents', encoding='utf-8')
            app, games, alerts = self.app_for_directory(target)
            app.session()
            self.assertEqual(target.read_text(encoding='utf-8'), 'existing contents')
            self.assertEqual(games[0].game_over_reason, 'Выход')
            self.assertEqual(alerts, ['Повтор не записан'])
