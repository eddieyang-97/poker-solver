"""Isolated release-gate failure injection; never alters main or calls Render."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

import yaml

from scripts.ci_gate import REQUIRED_JOBS, require_success

ROOT = Path(__file__).resolve().parents[1]


class CIGateTests(unittest.TestCase):
    def test_actual_cli_fails_closed_for_every_required_job_and_result(self):
        good = {name: {'result': 'success'} for name in REQUIRED_JOBS}
        require_success(good)
        cases = [None, {}, [], dict(good, unexpected={'result': 'success'})]
        for name in REQUIRED_JOBS:
            missing = deepcopy(good)
            del missing[name]
            cases.append(missing)
            # GitHub reports a timed-out job as failure. Also reject unexpected states.
            for state in ('failure', 'cancelled', 'skipped', 'timed_out', 'neutral', None, 'pending'):
                cases.append(dict(good, **{name: {'result': state}}))
            cases.append(dict(good, **{name: {}}))
        for case in [good, *cases]:
            with self.subTest(needs=case):
                child = subprocess.run([sys.executable, str(ROOT/'scripts/ci_gate.py')],
                                       env=dict(os.environ, NEEDS_JSON=json.dumps(case)),
                                       capture_output=True, timeout=10)
                self.assertEqual(child.returncode, 0 if case == good else 1, child.stderr)
        for raw in ('', '{', 'false'):
            child = subprocess.run([sys.executable, str(ROOT/'scripts/ci_gate.py')],
                                   env=dict(os.environ, NEEDS_JSON=raw), capture_output=True, timeout=10)
            self.assertEqual(child.returncode, 1)

    def test_workflow_preserves_every_gate_and_artifact_and_exact_test_context(self):
        workflow = yaml.safe_load((ROOT/'.github/workflows/ci.yml').read_text())
        jobs = workflow['jobs']
        self.assertEqual(set(jobs), {*REQUIRED_JOBS, 'test'})
        aggregate = jobs['test']
        self.assertEqual(aggregate['name'], 'test')
        self.assertEqual(aggregate['if'], '${{ always() }}')
        self.assertEqual(set(aggregate['needs']), set(REQUIRED_JOBS))
        self.assertEqual(aggregate['steps'][-1]['run'], 'python scripts/ci_gate.py')
        self.assertEqual(aggregate['steps'][-1]['env'], {'NEEDS_JSON': '${{ toJSON(needs) }}'})
        contract = json.loads((ROOT/'tests/fixtures/ci-gates.json').read_text())
        found = []
        artifacts = []
        for name in REQUIRED_JOBS:
            job = jobs[name]
            self.assertEqual(job['runs-on'], 'ubuntu-latest')
            self.assertFalse(set(job) & {'if', 'continue-on-error', 'needs'})
            for step in job['steps']:
                self.assertNotIn('continue-on-error', step)
                if 'run' in step and step['run'] != 'pip install -r requirements-dev.txt':
                    self.assertNotIn('if', step)
                    found.append(step)
                if step.get('uses') == 'actions/upload-artifact@v4':
                    self.assertEqual(step['if'], 'always()')
                    artifacts.append(step)
        self.assertCountEqual(found, contract['checks'])
        self.assertCountEqual(artifacts, contract['artifacts'])
        # No path filters, feature pushes or main cancellation; latest PR supersedes only its own PR.
        events = workflow.get('on', workflow.get(True))  # YAML 1.1 compatibility
        self.assertEqual(events, {'push': {'branches': ['main']}, 'pull_request': None})
        self.assertEqual(workflow['concurrency'], {
            'group': '${{ github.workflow }}-${{ github.event_name }}-${{ github.event.pull_request.number || github.run_id }}',
            'cancel-in-progress': "${{ github.event_name == 'pull_request' }}"})
        self.assertEqual(workflow['permissions'], {'contents': 'read'})


if __name__ == '__main__':
    unittest.main()
