"""Reject incomplete fencing evidence and check reproducible percentile results."""
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    'profile_summary', Path(__file__).resolve().parents[1] / 'performance/summarize-frame-profile.py')
summary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(summary)


def frame(total=1, sync='false', wait=0):
    return (f'MOCHA_FRAME elements_ms=0.2 render_ms=0.3 wait_ms={wait} '
            f'queue_ms=0.1 total_ms={total} needs_sync={sync} elements=3')


class ProfileTest(unittest.TestCase):
    def test_nearest_rank_small_samples_and_wait_counts(self):
        result = summary.summarize('\n'.join([frame(1), frame(20, 'true', 3)]), 'sample')
        self.assertEqual(result['cpu_wait_frames'], 1)
        self.assertEqual(result['total_ms'], {'mean': 10.5, 'p50': 1, 'p95': 20, 'p99': 20, 'max': 20})
        self.assertEqual(result['over_16_65ms'], 1)
        self.assertEqual(result['wait_ms']['mean'], 1.5)

    def test_nearest_rank_boundary(self):
        result = summary.summarize('\n'.join(frame(i) for i in range(1, 101)), 'sample')
        self.assertEqual(result['total_ms']['p95'], 95)
        self.assertEqual(result['total_ms']['p99'], 99)

    def test_truncated_record_cannot_imply_no_cpu_wait(self):
        for line in (frame().split(' needs_sync=')[0], frame().replace('wait_ms=0 ', ''),
                     frame(sync='unknown'), frame(wait='nan'), frame(wait='-1'),
                     frame().replace('total_ms=1', 'total_ms=1.2.3')):
            with self.subTest(line=line), self.assertRaisesRegex(ValueError, 'sample:2:'):
                summary.summarize('unrelated log\n' + line, 'sample')

    def test_ansi_logs_and_scientific_notation(self):
        result = summary.summarize('\x1b[32m' + frame(wait='1e-3') + '\x1b[0m', 'sample')
        self.assertEqual(result['wait_ms']['mean'], .001)

    def test_empty_log_is_not_a_pass(self):
        with self.assertRaisesRegex(ValueError, 'No frames'):
            summary.summarize('unrelated log', 'sample')


if __name__ == '__main__':
    unittest.main()
