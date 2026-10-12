import copy
import json
from pathlib import Path
import tempfile
import unittest

from pvz.replay import ReplayError, ReplayRecorder, load_replay, parse_replay, save_replay
from pvz.replay import game_stats, play_replay


def recording(**changes):
    data = dict(schema_version=1, seed=42, scenario=None, difficulty="normal",
                duration=1.0, actions=[
                    {"time": 0, "kind": "select", "plant": "SUNFLOWER"},
                    {"time": 0, "kind": "plant"},
                    {"time": 1, "kind": "move", "direction": "down"},
                ])
    data.update(changes)
    return data


class ReplayFormatTests(unittest.TestCase):
    def test_versioned_roundtrip_preserves_order_of_simultaneous_inputs(self):
        replay = parse_replay(recording())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "party.json"
            save_replay(replay, path)
            self.assertEqual(load_replay(path), replay)
        self.assertEqual([action.kind for action in replay.actions[:2]], ["select", "plant"])

    def test_recorder_freezes_completed_recording_and_failed_input_is_not_appended(self):
        recorder = ReplayRecorder(27, scenario="first-wave", difficulty="easy")
        recorder.record(0, "move", direction="left")
        first = recorder.finish(0)
        with self.assertRaises(ReplayError):
            recorder.record(0.025, "plant")
        recorder.record(0.05, "plant")
        self.assertEqual(len(first.actions), 1)
        self.assertEqual(len(recorder.finish(0.05).actions), 2)

    def test_unknown_metadata_and_state_edit_commands_are_rejected(self):
        for data in (recording(player="name"), recording(actions=[{"time": 0, "kind": "set-sun", "sun": 10000}])):
            with self.subTest(data=data), self.assertRaises(ReplayError):
                parse_replay(data)

    def test_invalid_header_values_are_rejected(self):
        for changes in (dict(schema_version=True), dict(schema_version=2),
                        dict(seed=None), dict(seed=True), dict(seed=-1),
                        dict(seed=2147483648), dict(difficulty="cheat"),
                        dict(scenario="../secret"), dict(scenario="\n"),
                        dict(duration=float("nan")), dict(duration=float("inf")),
                        dict(duration=True), dict(duration=7200.05), dict(duration=0.025)):
            with self.subTest(changes=changes), self.assertRaises(ReplayError):
                parse_replay(recording(**changes))

    def test_action_arguments_and_unordered_time_are_rejected(self):
        for actions in ([{"time": 0, "kind": "move", "direction": "diagonal"}],
                        [{"time": 0, "kind": "select", "plant": "MAGIC"}],
                        [{"time": 0, "kind": "plant", "sun": 1000}],
                        [{"time": 0, "kind": "move"}],
                        [{"time": 0.025, "kind": "dig"}],
                        [{"time": 1, "kind": "dig"}, {"time": 0, "kind": "plant"}]):
            with self.subTest(actions=actions), self.assertRaises(ReplayError):
                parse_replay(recording(actions=actions))

    def test_pause_resume_share_simulation_time_and_order(self):
        actions = [{"time": 0.5, "kind": "pause"},
                   {"time": 0.5, "kind": "move", "direction": "left"},
                   {"time": 0.5, "kind": "resume"}]
        self.assertEqual(len(parse_replay(recording(actions=actions)).actions), 3)
        invalid = copy.deepcopy(actions)
        invalid[2]["time"] = 0.55
        with self.assertRaises(ReplayError):
            parse_replay(recording(actions=invalid))
        for action in ("resume", "pause"):
            entries = [{"time": 0, "kind": action}]
            if action == "pause":
                entries *= 2
            with self.assertRaises(ReplayError):
                parse_replay(recording(actions=entries))

    def test_duration_cannot_run_past_pause_quit_or_before_last_input(self):
        for kind in ("quit", "pause", "dig"):
            with self.subTest(kind=kind), self.assertRaises(ReplayError):
                parse_replay(recording(duration=0 if kind == "dig" else 1,
                                       actions=[{"time": 0.5, "kind": kind}]))
        with self.assertRaises(ReplayError):
            parse_replay(recording(actions=[{"time": 0, "kind": "quit"}, {"time": 0, "kind": "dig"}]))

    def test_saving_never_overwrites_existing_file_or_leaves_staging_files(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "party.json"
            path.write_text("protected", encoding="utf-8")
            with self.assertRaises(ReplayError):
                save_replay(parse_replay(recording()), path)
            self.assertEqual(path.read_text(), "protected")
            self.assertEqual(list(Path(folder).iterdir()), [path])

    def test_duplicate_json_keys_invalid_utf8_and_excessive_size_are_rejected(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "party.json"
            payload = json.dumps(recording()).replace('"seed": 42', '"seed": 42, "seed": 7')
            for raw in (payload.encode(), b"\xff", b"["):
                path.write_bytes(raw)
                with self.assertRaises(ReplayError):
                    load_replay(path)
            path.write_text(json.dumps(recording()))
            with patch("pvz.replay.MAX_FILE_BYTES", 10), self.assertRaises(ReplayError):
                load_replay(path)

    def test_input_count_limit(self):
        from unittest.mock import patch
        with patch("pvz.replay.MAX_ACTIONS", 1), self.assertRaises(ReplayError):
            parse_replay(recording())


class ReplayPlaybackTests(unittest.TestCase):
    def test_repeated_playback_has_identical_final_stats_and_does_not_open_curses(self):
        replay = parse_replay(recording(duration=30))
        first, second = play_replay(replay), play_replay(replay)
        self.assertEqual(first.stats, second.stats)
        self.assertEqual(first.stats["elapsed"], 30)
        self.assertEqual(first.stats["plants_placed"], 1)
        self.assertEqual(len(first.stats["state_sha256"]), 64)
        self.assertIsNone(first.game._stdscr)

    def test_real_player_controls_match_replay_at_a_different_ui_tick(self):
        from pvz.game import Game
        actions = [{"time": 0, "kind": "select", "plant": "SUNFLOWER"},
                   {"time": 0, "kind": "plant"},
                   {"time": 1, "kind": "move", "direction": "down"},
                   {"time": 1, "kind": "plant"}]
        replay = parse_replay(recording(duration=20, actions=actions))
        manual = Game(0.2, seed=42)
        manual.handle_keypress(ord("2"))
        manual.handle_keypress(ord(" "))
        for _ in range(5):
            manual.step()
        manual.handle_keypress(ord("s"))
        manual.handle_keypress(ord(" "))
        for _ in range(95):
            manual.step()
        self.assertEqual(game_stats(manual), play_replay(replay).stats)

    def test_failed_planting_and_digging_respect_economy_and_cooldown(self):
        actions = [{"time": 0, "kind": "plant"},
                   {"time": 0, "kind": "move", "direction": "right"},
                   {"time": 0, "kind": "plant"},
                   {"time": 0, "kind": "move", "direction": "left"},
                   {"time": 0.05, "kind": "dig"}]
        result = play_replay(parse_replay(recording(duration=0.05, actions=actions)))
        self.assertEqual(result.stats["plants_placed"], 1)
        self.assertEqual(result.stats["sun"], 200)
        self.assertFalse(result.game.grid.iter_plants())

    def test_cursor_moves_are_clamped_to_the_real_lawn(self):
        actions = [{"time": 0, "kind": "move", "direction": direction}
                   for direction in (["up"] * 10 + ["left"] * 10)]
        game = play_replay(parse_replay(recording(duration=0, actions=actions))).game
        self.assertEqual((game.cursor_row, game.cursor_col), (0, 0))

    def test_pause_blocks_planting_and_shovel_until_resume(self):
        actions = [{"time": 0, "kind": "pause"}, {"time": 0, "kind": "plant"},
                   {"time": 0, "kind": "resume"}, {"time": 0, "kind": "plant"},
                   {"time": 0, "kind": "pause"}, {"time": 0, "kind": "dig"}]
        result = play_replay(parse_replay(recording(duration=0, actions=actions)))
        self.assertEqual(result.stats["outcome"], "paused")
        self.assertEqual(result.stats["elapsed"], 0)
        self.assertEqual(result.stats["plants_placed"], 1)
        self.assertIsNotNone(result.game.grid.get(2, 1))

    def test_quit_reports_outcome_without_advancing_an_extra_tick(self):
        result = play_replay(parse_replay(recording(duration=0.15, actions=[{"time": 0.15, "kind": "quit"}])))
        self.assertEqual(result.stats["outcome"], "quit")
        self.assertEqual(result.stats["elapsed"], 0.15)

    def test_callback_observes_initial_state_and_each_simulation_step(self):
        observed = []
        play_replay(parse_replay(recording(duration=0.15, actions=[])),
                    on_step=lambda game: observed.append(game.time_elapsed))
        self.assertEqual(observed, [0, 0.05, 0.1, 0.15])

    @staticmethod
    def scenario_loader(identifier):
        from types import SimpleNamespace
        return SimpleNamespace(id=identifier, seed=7, sun=200,
                               waves=(SimpleNamespace(number=1, duration=1.0,
                                      spawns=(SimpleNamespace(time=0.1, row=2, zombie="NORMAL"),)),),
                               allowed_plants=("PEASHOOTER",), modifiers={})

    def test_scenario_uses_recorded_seed_difficulty_and_restricted_roster(self):
        replay = parse_replay(recording(scenario="test-wave", difficulty="hard", seed=27,
                                       actions=[{"time": 0, "kind": "select", "plant": "SUNFLOWER"},
                                                {"time": 0, "kind": "plant"}]))
        result = play_replay(replay, scenario_loader=self.scenario_loader)
        self.assertEqual(result.game.seed, 27)
        self.assertEqual(result.game.difficulty, "hard")
        self.assertEqual(result.game.grid.get(2, 1).plant_type.name, "PEASHOOTER")
        self.assertEqual(result.game.zombies[0].hp, 250)

    def test_natural_victory_stops_playback_before_requested_duration(self):
        replay = parse_replay(recording(scenario="test-wave", duration=60,
                                       actions=[{"time": 0, "kind": "plant"}]))
        result = play_replay(replay, scenario_loader=self.scenario_loader)
        self.assertEqual(result.stats["outcome"], "victory")
        self.assertEqual(result.stats["zombies_killed"], 1)
        self.assertLess(result.stats["elapsed"], 60)

    def test_inputs_after_natural_game_end_and_wrong_scenario_are_rejected(self):
        replay = parse_replay(recording(scenario="test-wave", duration=60,
                                       actions=[{"time": 0, "kind": "plant"}, {"time": 60, "kind": "dig"}]))
        with self.assertRaises(ReplayError):
            play_replay(replay, scenario_loader=self.scenario_loader)
        with self.assertRaises(ReplayError):
            play_replay(replay, scenario_loader=lambda _: self.scenario_loader("different-id"))

    def test_directly_constructed_replay_is_validated_before_simulation(self):
        from dataclasses import replace
        with self.assertRaises(ReplayError):
            play_replay(replace(parse_replay(recording()), seed=True))


if __name__ == "__main__":
    unittest.main()
