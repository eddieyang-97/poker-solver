import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReviewCLITests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, 'scripts/review_hand.py', *map(str, args)], cwd=ROOT,
                              text=True, capture_output=True, timeout=15)

    def test_prose_and_json_requests_agree_and_receipts_are_not_invented(self):
        plans = []
        for name in ('hand-review.json', 'hand-review.txt'):
            process = self.run_cli(ROOT/'examples'/name, '--scenarios', ROOT/'examples/hand-review-scenarios.json')
            self.assertEqual(process.returncode, 0, process.stderr)
            plan = json.loads(process.stdout)
            self.assertEqual(plan['status'], 'not_run')
            self.assertTrue(all('result' not in q for q in plan['queries']))
            plans.append(plan['queries'])
        self.assertEqual(plans[0], plans[1])

    def test_invalid_correction_and_missing_ranges_fail_before_dispatch(self):
        for args in (('--set', '/streets/0/actions/2/to=20'), ('--run',)):
            process = self.run_cli(ROOT/'examples/hand-review.json', *args)
            self.assertEqual(process.returncode, 2)
            self.assertEqual(json.loads(process.stderr)['status'], 'not_run')

    def test_output_files_retain_plan_and_ambiguity_is_not_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory)/'review'
            process = self.run_cli(ROOT/'examples/hand-review.txt', '--scenarios',
                                   ROOT/'examples/hand-review-scenarios.json', '--output', prefix)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(json.loads(prefix.with_suffix('.json').read_text())['status'], 'not_run')
            self.assertIn('not solver-verified', prefix.with_suffix('.md').read_text())
            raw = Path(directory)/'ambiguous.txt'
            raw.write_text('UTG raises\n', encoding='utf-8')
            process = self.run_cli(raw, '--run')
            self.assertEqual(process.returncode, 2)
            self.assertEqual(json.loads(process.stdout)['execution'], 'not_run')


if __name__ == '__main__':
    unittest.main()
