import copy
import json
from pathlib import Path
import tempfile
import unittest

from pvz.replay import ReplayError, ReplayRecorder, load_replay, parse_replay, save_replay


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


if __name__ == "__main__":
    unittest.main()
