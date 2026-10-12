"""Content checks run without curses or the simulation's evolving enums."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from pvz.content import ContentError, campaign_chapters, list_scenarios, load_scenario, parse_scenario


def valid_data():
    return {
        "schema_version": 1, "id": "test-level", "name": "Test level",
        "seed": 42, "sun": 300, "allowed_plants": ["PEASHOOTER", "SUNFLOWER"],
        "modifiers": {"passive_sun": False, "sun_cap": 500,
                      "preplanted": [{"row": 0, "col": 0, "plant": "SUNFLOWER"}]},
        "waves": [{"number": 1, "duration": 30,
                   "spawns": [{"time": 15, "row": 0, "zombie": "NORMAL"}]}],
    }


class ContentValidationTests(unittest.TestCase):
    def test_parse_preserves_timeline_and_metadata(self):
        data = valid_data()
        data.update(kind="challenge", chapter="Economy", order=7, objective="Save sun")
        scenario = parse_scenario(data)
        self.assertEqual((scenario.id, scenario.seed, scenario.duration, scenario.zombie_count), ("test-level", 42, 30, 1))
        self.assertEqual(scenario.waves[0].spawns[0].row, 0)
        self.assertEqual(scenario.objective, "Save sun")
        self.assertEqual(scenario.modifiers["preplanted"][0]["plant"], "SUNFLOWER")

    def test_result_does_not_share_mutable_input(self):
        data = valid_data()
        scenario = parse_scenario(data)
        data["modifiers"]["preplanted"][0]["row"] = 4
        data["waves"][0]["spawns"][0]["time"] = 25
        self.assertEqual(scenario.modifiers["preplanted"][0]["row"], 0)
        self.assertEqual(scenario.waves[0].spawns[0].time, 15)
        with self.assertRaises(TypeError):
            scenario.modifiers["passive_sun"] = True
        with self.assertRaises(TypeError):
            scenario.modifiers["preplanted"][0]["row"] = 2

    def test_rejects_unsafe_ids_and_unknown_resources(self):
        for scenario_id in ("../level", "a/b", "", "UPPER", "a--b", "x" * 81, "unknown-resource"):
            with self.subTest(scenario_id=scenario_id), self.assertRaises(ContentError):
                load_scenario(scenario_id)

    def test_rejects_invalid_content(self):
        mutations = [
            lambda d: d.update(extra=True),
            lambda d: d.update(schema_version=True),
            lambda d: d.update(seed=True),
            lambda d: d.update(sun=-1),
            lambda d: d.update(name="bad\nname"),
            lambda d: d.update(kind="other"),
            lambda d: d.update(allowed_plants=["SUNFLOWER", "SUNFLOWER"]),
            lambda d: d.update(allowed_plants=["UNKNOWN"]),
            lambda d: d["waves"][0].update(number=2),
            lambda d: d["waves"][0].update(duration=float("nan")),
            lambda d: d["waves"][0]["spawns"][0].update(time=31),
            lambda d: d["waves"][0]["spawns"][0].update(row=5),
            lambda d: d["waves"][0]["spawns"][0].update(row=True),
            lambda d: d["waves"][0]["spawns"][0].update(zombie="UNKNOWN"),
            lambda d: d["waves"][0]["spawns"].append({"time": 1, "row": 0, "zombie": "NORMAL"}),
            lambda d: d["modifiers"].update(passive_sun=1),
            lambda d: d["modifiers"].update(sun_cap=100),
            lambda d: d["modifiers"].update(time_limit=29),
            lambda d: d["modifiers"].update(plant_cost_multiplier=0),
            lambda d: d["modifiers"].update(unknown=True),
            lambda d: d["modifiers"]["preplanted"].append({"row": 0, "col": 0, "plant": "SUNFLOWER"}),
            lambda d: d["modifiers"]["preplanted"][0].update(col=9),
            lambda d: d["modifiers"]["preplanted"][0].update(plant="CHOMPER"),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                data = deepcopy(valid_data())
                mutate(data)
                with self.assertRaises(ContentError):
                    parse_scenario(data)

    def test_empty_catalogue_is_supported(self):
        self.assertIsInstance(list_scenarios(), tuple)
        self.assertIsInstance(campaign_chapters(), dict)
        with self.assertRaises(ContentError):
            list_scenarios("other")

    def test_every_bundled_scenario_has_a_unique_order_and_stable_reload(self):
        scenarios = list_scenarios()
        self.assertEqual(len({item.id for item in scenarios}), len(scenarios))
        self.assertEqual(len({item.order for item in scenarios}), len(scenarios))
        self.assertEqual(len({item.seed for item in scenarios}), len(scenarios))
        fingerprints = {
            (item.sun, item.allowed_plants, item.waves, repr(dict(item.modifiers)))
            for item in scenarios
        }
        self.assertEqual(len(fingerprints), len(scenarios), "gameplay duplicates differ only in metadata")
        for scenario in scenarios:
            with self.subTest(scenario=scenario.id):
                self.assertEqual(load_scenario(scenario.id), scenario)
                self.assertGreaterEqual(scenario.waves[0].spawns[0].time, 15)
                self.assertTrue(scenario.description)
                self.assertTrue(scenario.objective)


class ScenarioPlayabilityTests(unittest.TestCase):
    def test_every_scenario_has_a_legal_winning_replay_at_supported_ticks(self):
        # The fixture uses the public planting API: no health, sun, grid or
        # enemy state is injected after construction. This catches balance
        # changes that turn an otherwise valid JSON stage into a dead end.
        from pvz.game import Game
        from pvz.types import PlantType

        folder = Path(__file__).resolve().parents[1] / "docs" / "scenarios" / "solutions"
        scenarios = list_scenarios()
        self.assertEqual({item.id for item in scenarios}, {item.stem for item in folder.glob("*.json")})
        for scenario in scenarios:
            fixture = json.loads((folder / (scenario.id + ".json")).read_text(encoding="utf-8"))
            self.assertEqual(fixture["scenario"], scenario.id)
            self.assertEqual(fixture["schema_version"], 1)
            self.assertEqual(fixture["difficulty"], "normal")
            actions = fixture["actions"]
            self.assertTrue(actions, "a route must perform real player actions")
            self.assertEqual([action["time"] for action in actions], sorted(action["time"] for action in actions))
            for tick in (0.05, 0.1, 0.2, 0.5):
                with self.subTest(scenario=scenario.id, tick=tick):
                    game = Game(tick, scenario=scenario, difficulty=fixture["difficulty"])
                    index = 0
                    while not game.game_over and game.time_elapsed <= scenario.duration + 180:
                        while index < len(actions) and actions[index]["time"] <= game.time_elapsed + 1e-9:
                            action = actions[index]
                            index += 1
                            self.assertEqual(set(action), {"time", "plant", "row", "col"})
                            self.assertIn(action["plant"], scenario.allowed_plants)
                            game.selected = PlantType[action["plant"]]
                            game.cursor_row = action["row"]
                            game.cursor_col = action["col"]
                            error = game.planting_error()
                            self.assertTrue(game.place_selected(), f"illegal action {action}: {error}")
                        game.step()
                    self.assertTrue(game.victory, game.game_over_reason)
                    self.assertEqual(game.zombies_killed, scenario.zombie_count)
                    self.assertEqual(game.lawnmowers_used, 0)
                    self.assertFalse(game.zombies)
                    self.assertEqual(index, len(actions))


if __name__ == "__main__":
    unittest.main()
