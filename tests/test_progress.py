import json
from types import SimpleNamespace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pvz.progress import MAX_FILE_BYTES, ProgressError, ProgressStore


class TempProgressTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / 'progress.json'


class PersistenceTests(TempProgressTestCase):
    def test_missing_progress_has_empty_schema_and_roundtrips(self):
        store = ProgressStore(self.path).load()
        self.assertIsNone(store.load_error)
        self.assertEqual(store.data['version'], 1)
        store.save()
        restored = ProgressStore(self.path).load()
        self.assertEqual(restored.data, store.data)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_corrupt_progress_is_preserved_and_write_is_blocked(self):
        for raw in (b'{bad', b'{"version":9,"results":{},"achievements":[]}', b'\xff'):
            self.path.write_bytes(raw)
            store = ProgressStore(self.path).load()
            self.assertIsNotNone(store.load_error)
            self.assertEqual(store.data['results'], {})
            with self.assertRaises(ProgressError):
                store.save()
            self.assertEqual(self.path.read_bytes(), raw)

    def test_failed_atomic_replace_keeps_previous_file_and_cleans_temporary(self):
        store = ProgressStore(self.path).load()
        store.save()
        previous = self.path.read_bytes()
        store.data['achievements'].append('first-victory')
        with patch('pvz.progress.os.replace', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                store.save()
        self.assertEqual(self.path.read_bytes(), previous)
        self.assertEqual(list(self.path.parent.glob('.pvz-progress-*')), [])

    def test_external_change_is_not_overwritten(self):
        store = ProgressStore(self.path).load()
        store.save()
        outsider = b'{"version":1,"results":{},"achievements":["external"]}'
        self.path.write_bytes(outsider)
        with self.assertRaises(ProgressError):
            store.save()
        self.assertEqual(self.path.read_bytes(), outsider)

    def test_oversized_file_and_symbolic_link_are_rejected(self):
        self.path.write_bytes(b'x' * (MAX_FILE_BYTES + 1))
        self.assertIsNotNone(ProgressStore(self.path).load().load_error)
        target = self.path.parent / 'original.json'
        target.write_text('original')
        link = self.path.parent / 'linked.json'
        link.symlink_to(target)
        store = ProgressStore(link).load()
        self.assertIsNotNone(store.load_error)
        with self.assertRaises(ProgressError):
            store.save()
        self.assertEqual(target.read_text(), 'original')

    def test_unexpected_personal_fields_are_rejected(self):
        self.path.write_text(json.dumps({'version': 1, 'results': {}, 'achievements': [], 'email': 'personal'}))
        self.assertIsNotNone(ProgressStore(self.path).load().load_error)


class ResultTests(TempProgressTestCase):
    def test_results_keep_score_and_fastest_winning_duration_per_difficulty(self):
        store = ProgressStore(self.path).load()
        store.record_result('campaign-01', 'normal', victory=False, score=12, duration=90, kills=12)
        store.record_result('campaign-01', 'normal', victory=True, score=8, duration=80, kills=8)
        store.record_result('campaign-01', 'normal', victory=True, score=10, duration=70, kills=10)
        store.record_result('campaign-01', 'hard', victory=True, score=20, duration=120, kills=20)
        store.save()
        restored = ProgressStore(self.path).load()
        result = restored.best_result('campaign-01', 'normal')
        self.assertEqual((result['attempts'], result['wins'], result['best_score'], result['best_duration']), (3, 2, 12, 70))
        self.assertEqual(result['totals']['kills'], 30)
        self.assertEqual(restored.best_result('campaign-01', 'hard')['best_score'], 20)
        result['wins'] = 99
        self.assertEqual(restored.best_result('campaign-01', 'normal')['wins'], 2)

    def test_invalid_stats_leave_existing_progress_unchanged(self):
        store = ProgressStore(self.path).load()
        store.record_result('test', 'normal', victory=True, score=1, duration=20)
        previous = json.dumps(store.data, sort_keys=True)
        invalid = ({'duration': float('nan')}, {'score': -1}, {'plants_lost': -1}, {'lawnmowers_used': 6})
        for changes in invalid:
            values = {'victory': True, 'score': 1, 'duration': 20, **changes}
            with self.assertRaises(ProgressError):
                store.record_result('test', 'normal', **values)
            self.assertEqual(json.dumps(store.data, sort_keys=True), previous)

    def test_record_game_ignores_quit_and_rejects_running_match(self):
        store = ProgressStore(self.path).load()
        game = SimpleNamespace(game_over=False)
        with self.assertRaises(ProgressError):
            store.record_game(game)
        game.game_over = True
        game.game_over_reason = 'Выход'
        self.assertEqual(store.record_game(game), ())
        self.assertEqual(store.data['results'], {})

    def test_record_game_maps_only_gameplay_fields(self):
        store = ProgressStore(self.path).load()
        game = SimpleNamespace(game_over=True, game_over_reason='Победа', scenario=SimpleNamespace(id='test'),
            difficulty='normal', victory=True, score=10, time_elapsed=120,
            zombies_killed=10, plants_placed=5, plants_lost=1, lawnmowers_used=0, sun_generated=400)
        store.record_game(game)
        store.save()
        self.assertEqual(store.best_result('test')['wins'], 1)
        raw = self.path.read_text()
        self.assertNotIn('email', raw)
        self.assertNotIn('timestamp', raw)
        self.assertNotIn('seed', raw)

    def test_losses_of_preplanted_plants_are_valid_statistics(self):
        store = ProgressStore(self.path).load()
        store.record_result('preplanted-test', 'normal', victory=False, score=0, duration=20,
                            plants_placed=0, plants_lost=5)
        self.assertEqual(store.best_result('preplanted-test')['totals']['plants_lost'], 5)


class CampaignUnlockTests(TempProgressTestCase):
    def test_first_level_available_and_victory_opens_next(self):
        store = ProgressStore(self.path).load()
        sequence = ['campaign-01', 'campaign-02', 'campaign-03']
        self.assertEqual(store.unlocked_campaign(sequence), ('campaign-01',))
        store.record_result('campaign-01', 'normal', victory=True, score=1, duration=20)
        store.save()
        restored = ProgressStore(self.path).load()
        self.assertTrue(restored.is_completed('campaign-01'))
        self.assertEqual(restored.unlocked_campaign(sequence), ('campaign-01', 'campaign-02'))

    def test_defeat_and_other_difficulty_do_not_unlock_levels(self):
        store = ProgressStore(self.path).load()
        sequence = [SimpleNamespace(id='campaign-01'), SimpleNamespace(id='campaign-02')]
        store.record_result('campaign-01', 'normal', victory=False, score=1, duration=20)
        store.record_result('campaign-01', 'hard', victory=True, score=1, duration=20)
        self.assertEqual(store.unlocked_campaign(sequence), ('campaign-01',))
        self.assertEqual(store.unlocked_campaign(sequence, 'hard'), ('campaign-01', 'campaign-02'))

    def test_completed_later_stage_cannot_skip_an_unfinished_stage(self):
        store = ProgressStore(self.path).load()
        store.record_result('campaign-03', 'normal', victory=True, score=1, duration=20)
        self.assertEqual(store.unlocked_campaign(['campaign-01', 'campaign-02', 'campaign-03', 'campaign-04']), ('campaign-01',))
        self.assertEqual(store.unlocked_campaign([]), ())
        with self.assertRaises(ProgressError):
            store.unlocked_campaign(['campaign-01', 'campaign-01'])


class LifetimeStatisticsTests(TempProgressTestCase):
    def test_statistics_aggregate_matches_without_counting_one_stage_twice(self):
        store = ProgressStore(self.path).load()
        store.record_result('campaign-01', 'normal', victory=True, score=1, duration=20,
                            kills=4, plants_placed=3, sun_generated=100)
        store.record_result('campaign-01', 'hard', victory=True, score=2, duration=30,
                            kills=6, plants_placed=4, plants_lost=1, sun_generated=150)
        store.record_result('survival', 'normal', victory=False, score=3, duration=50,
                            kills=10, lawnmowers_used=2, sun_generated=200)
        stats = store.lifetime_stats()
        self.assertEqual(stats, dict(kills=20, plants_placed=7, plants_lost=1,
            lawnmowers_used=2, sun_generated=450, duration=100.0, attempts=3, wins=2, completed_scenarios=1))
        stats['kills'] = 10000
        self.assertEqual(store.lifetime_stats()['kills'], 20)
        store.save()
        restored = ProgressStore(self.path).load()
        self.assertEqual(restored.lifetime_stats()['wins'], 2)


class AchievementTests(TempProgressTestCase):
    def test_achievements_follow_actual_match_stats_and_are_awarded_once(self):
        store = ProgressStore(self.path).load()
        defeat = store.record_result('campaign-01', 'normal', victory=False, score=1, duration=90,
            kills=8, plants_placed=5, sun_generated=999)
        self.assertEqual(defeat, ())
        earned = store.record_result('campaign-01', 'normal', victory=True, score=8, duration=90,
            kills=8, plants_placed=5, sun_generated=1000)
        self.assertEqual(earned, ('first-victory', 'untouched-lawn', 'careful-gardener', 'sun-farmer'))
        repeated = store.record_result('campaign-01', 'normal', victory=True, score=8, duration=90,
            kills=8, plants_placed=5, sun_generated=1000)
        self.assertEqual(repeated, ())
        store.save()
        self.assertEqual(ProgressStore(self.path).load().achievements, earned)

    def test_mower_and_plant_losses_prevent_clean_defense_achievements(self):
        store = ProgressStore(self.path).load()
        earned = store.record_result('challenge-test', 'normal', victory=True, score=8, duration=90,
            kills=8, plants_placed=5, plants_lost=1, lawnmowers_used=1)
        self.assertEqual(earned, ('first-victory',))

    def test_hunter_and_survival_thresholds(self):
        store = ProgressStore(self.path).load()
        store.record_result('survival', 'normal', victory=False, score=99, duration=299, kills=99)
        self.assertNotIn('zombie-hunter', store.achievements)
        self.assertNotIn('survivor', store.achievements)
        earned = store.record_result('survival', 'normal', victory=False, score=1, duration=300, kills=1)
        self.assertEqual(earned, ('zombie-hunter', 'survivor'))

    def test_campaign_completion_counts_distinct_stages(self):
        store = ProgressStore(self.path).load()
        for number in range(1, 15):
            for difficulty in ('normal', 'hard'):
                store.record_result(f'campaign-{number:02}', difficulty, victory=True, score=1, duration=20, kills=1)
        self.assertNotIn('campaign-veteran', store.achievements)
        self.assertIn('hard-winner', store.achievements)
        earned = store.record_result('campaign-15', 'normal', victory=True, score=1, duration=20, kills=1)
        self.assertEqual(earned, ('campaign-veteran',))

    def test_unknown_achievement_in_file_is_preserved_as_invalid(self):
        raw = json.dumps({'version': 1, 'results': {}, 'achievements': ['made-up']}).encode()
        self.path.write_bytes(raw)
        store = ProgressStore(self.path).load()
        self.assertIsNotNone(store.load_error)
        with self.assertRaises(ProgressError):
            store.save()
        self.assertEqual(self.path.read_bytes(), raw)
