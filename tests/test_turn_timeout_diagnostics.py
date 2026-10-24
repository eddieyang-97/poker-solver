"""Timeout diagnostics must never change failure, cleanup or privacy semantics."""
import asyncio
import io
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from poker_spot.execution import CalculationError, Runner, _turn_timeout_snapshot


UNKNOWN = {'cpu_seconds': None, 'vm_peak_bytes': None, 'vm_hwm_bytes': None}
REQUEST = {'board': '2c,3d,4h,8s', 'oop_range': [{'hand': 'KhKd', 'weight': 1}],
           'ip_range': [{'hand': 'AsAd', 'weight': 1}], 'pot_cents': 10000,
           'stack_cents': 10000, 'turn_bet_sizes': [1.0], 'river_bet_sizes': []}


class SnapshotTests(unittest.TestCase):
    def sample(self, stat, status):
        reads = []

        def opened(path, mode):
            self.assertEqual(mode, 'rb')
            reads.append(str(path))
            return io.BytesIO(stat if path.name == 'stat' else status)

        with patch('poker_spot.execution.sys.platform', 'linux'), \
                patch('poker_spot.execution.os.sysconf', return_value=100, create=True), \
                patch.object(Path, 'open', opened):
            result = _turn_timeout_snapshot(123)
        self.assertTrue(all(path.endswith(('123/stat', '123/status', '123\\stat', '123\\status')) for path in reads))
        return result

    def test_numeric_counters_and_parentheses_in_process_name(self):
        stat = ('123 (private ) ( name) S '+'0 '*10+'125 25 '+'0 '*10).encode()
        result = self.sample(stat, b'Name:\tprivate-canary\nVmPeak:\t120000 kB\nVmHWM:\t45000 kB\n')
        self.assertEqual(result, {'cpu_seconds': 1.5, 'vm_peak_bytes': 122880000, 'vm_hwm_bytes': 46080000})
        self.assertNotIn('private', str(result))

    def test_missing_malformed_and_oversize_are_unknown(self):
        for stat, status in ((b'', b''), (b'x'*4097, b'x'*16385),
                             (b'not a stat', b'VmPeak: secret\nVmHWM: -1 kB'),
                             (b'\xff', b'VmPeak: 4 bytes')):
            with self.subTest(stat=stat[:10]):
                self.assertEqual(self.sample(stat, status), UNKNOWN)
        for error in (FileNotFoundError, PermissionError):
            with patch('poker_spot.execution.sys.platform', 'linux'), \
                    patch.object(Path, 'open', side_effect=error):
                self.assertEqual(_turn_timeout_snapshot(123), UNKNOWN)
        for pid in (None, -1, True, '123'):
            self.assertEqual(_turn_timeout_snapshot(pid), UNKNOWN)

    @unittest.skipUnless(sys.platform == 'linux', 'Actual Linux proc counters')
    def test_actual_linux_child_counter_format(self):
        result = _turn_timeout_snapshot(os.getpid())
        self.assertGreaterEqual(result['cpu_seconds'], 0)
        self.assertGreater(result['vm_peak_bytes'], 0)
        self.assertGreater(result['vm_hwm_bytes'], 0)


class TimeoutTests(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_snapshots_before_kill_logs_after_reap_and_recovers(self):
        original = asyncio.create_subprocess_exec
        children, events = [], []

        async def spawn(*args, **kwargs):
            child = await original(sys.executable, '-I', '-c', 'import time; time.sleep(60)', **kwargs)
            children.append(child)
            return child

        def snapshot(pid):
            self.assertEqual(pid, children[0].pid)
            self.assertIsNone(children[0].returncode)
            events.append('snapshot')
            return dict(UNKNOWN)

        def warning(message, *args):
            self.assertIsNotNone(children[0].returncode)
            events.append('reaped_warning')
            text = message % args
            for secret in ('private-canary', 'KhKd', 'AsAd', 'board'):
                self.assertNotIn(secret, text)
            self.assertIn('child_cpu_seconds=None', text)

        runner = Runner(timeout=0.2, turn_pilot=True)
        with patch.dict(os.environ, {'POKER_MCP_TOKEN': 'private-canary'}), \
                patch('poker_spot.execution.asyncio.create_subprocess_exec', side_effect=spawn), \
                patch('poker_spot.execution._turn_timeout_snapshot', side_effect=snapshot), \
                patch('poker_spot.execution.logger.warning', side_effect=warning):
            with self.assertRaises(CalculationError) as caught:
                await runner.run('solve_turn_v1', REQUEST)
        self.assertEqual(caught.exception.code, 'timeout')
        self.assertEqual(str(caught.exception), 'Turn calculation exceeded its wall-clock limit')
        self.assertEqual(events, ['snapshot', 'reaped_warning'])
        self.assertFalse(runner.busy)
        runner.timeout = 20
        result = await runner.run('evaluate_river_call', {
            'board': 'Ks,9s,5h,Td,Ts', 'hero_hand': 'KdQd', 'villain_betting_range': 'AsJh',
            'pot': 505, 'bet': 450})
        self.assertEqual(result['ev_call_minus_fold'], 955)

    async def test_missing_snapshot_still_emits_visible_warning(self):
        with patch('poker_spot.execution._turn_timeout_snapshot', return_value=dict(UNKNOWN)), \
                self.assertLogs('poker_spot.execution', level='WARNING') as records:
            runner = Runner(timeout=0.001, turn_pilot=True)
            with self.assertRaises(CalculationError):
                await runner.run('solve_turn_v1', REQUEST)
        self.assertEqual(len(records.output), 1)
        self.assertIn('turn_timeout', records.output[0])
        self.assertFalse(runner.busy)
