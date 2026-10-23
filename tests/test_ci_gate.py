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
from scripts.profile_ci import summarize
from scripts.compare_ci_evidence import compare

ROOT = Path(__file__).resolve().parents[1]


class CIGateTests(unittest.TestCase):
    def test_evidence_comparison_rejects_semantic_and_limit_changes(self):
        value = {'strategy': [0.3, 0.7], 'ev': 1.25, 'status': 'computed',
                 'metrics': {'wall_seconds': 4, 'limits': {'cpu_seconds': 20}}}
        groups = lambda v: {'fixture': {'report.json': json.dumps(v).encode()}}
        self.assertEqual(compare(groups(value), groups(value))['material_differences'], [])
        for key, changed in (('strategy', [0.4, 0.6]), ('ev', 1.250000000001), ('status', 'failed')):
            with self.subTest(key=key):
                self.assertTrue(compare(groups(value), groups(dict(value, **{key: changed})))['material_differences'])
        measured = deepcopy(value)
        measured['metrics']['wall_seconds'] = 8
        self.assertEqual(compare(groups(value), groups(measured))['material_differences'], [])
        measured['metrics']['limits']['cpu_seconds'] = 40
        self.assertTrue(compare(groups(value), groups(measured))['material_differences'])

    def test_timing_report_separates_critical_path_and_runner_work(self):
        run = dict(id=1, head_sha='a'*40, event='pull_request', html_url='https://example.test',
                   status='completed', conclusion='success', created_at='2026-10-22T12:00:00Z')
        jobs = [dict(id=1, name='one', runner_name='fixture', labels=['ubuntu-latest'], conclusion='success',
                     started_at='2026-10-22T12:00:03Z', completed_at='2026-10-22T12:01:03Z', steps=[]),
                dict(id=2, name='two', runner_name='fixture', labels=['ubuntu-latest'], conclusion='success',
                     started_at='2026-10-22T12:00:03Z', completed_at='2026-10-22T12:02:04Z', steps=[])]
        report = summarize(run, jobs, [dict(id=1, name='fixture', size_in_bytes=123)])
        self.assertEqual(report['initial_queue_seconds'], 3)
        self.assertEqual(report['critical_path_seconds'], 121)
        self.assertEqual(report['created_to_green_seconds'], 124)
        self.assertEqual(report['total_job_seconds'], 181)
        self.assertEqual(report['rounded_runner_minutes_estimate'], 4)
        self.assertEqual(report['total_artifact_bytes'], 123)
        with self.assertRaises(ValueError):
            summarize(dict(run, conclusion='failure'), jobs, [])

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
        expected = deepcopy(contract['checks'])
        for step in expected:
            if step['name'] == 'Independently trained river-subgame decomposition':
                step['run'] = step['run'].replace(' --output', ' --reference-workers 2 --output')
            if step['name'] == 'Static checks':
                step['run'] = step['run'].replace('benchmarks/raise_reference_worker.py\n',
                    'benchmarks/raise_reference_worker.py benchmarks/turn_feasibility.py benchmarks/turn_feasibility_worker.py\n')
        expected.append({'name': 'Full-policy turn feasibility and exact-reuse experiment', 'timeout-minutes': 3,
                         'run': 'python scripts/benchmark_turn_feasibility.py --output .artifacts/turn-feasibility',
                         'env': {'OPENBLAS_NUM_THREADS': '1'}})
        self.assertCountEqual(found, expected)
        expected_artifacts = deepcopy(contract['artifacts'])
        for step in expected_artifacts:
            if step['with']['name'] == 'turn-resource-study':
                step['with']['path'] = ('.artifacts/turn-resources.*\n.artifacts/turn-feasibility.*\n'
                                        '.artifacts/turn-feasibility-policies/\n')
        self.assertCountEqual(artifacts, expected_artifacts)
        # No path filters, feature pushes or main cancellation; latest PR supersedes only its own PR.
        events = workflow.get('on', workflow.get(True))  # YAML 1.1 compatibility
        self.assertEqual(events, {'push': {'branches': ['main']}, 'pull_request': None})
        self.assertEqual(workflow['concurrency'], {
            'group': '${{ github.workflow }}-${{ github.event_name }}-${{ github.event.pull_request.number || github.run_id }}',
            'cancel-in-progress': "${{ github.event_name == 'pull_request' }}"})
        self.assertEqual(workflow['permissions'], {'contents': 'read'})


if __name__ == '__main__':
    unittest.main()
