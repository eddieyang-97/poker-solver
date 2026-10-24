"""Bounded admission and a wall-clock timeout that kills the computation."""
import asyncio
import json
import logging
import os
from pathlib import Path
import sys
from collections import deque
from time import monotonic

from .validation import validate

logger = logging.getLogger(__name__)


def _turn_timeout_snapshot(pid):
    """Best-effort numeric child counters before kill; never read cmdline/env.

    Missing/exited processes and unsupported platforms remain unknown, not zero.
    These are diagnostic samples, not successful execution/resource receipts.
    """
    result = {'cpu_seconds': None, 'vm_peak_bytes': None, 'vm_hwm_bytes': None}
    if sys.platform != 'linux' or type(pid) is not int or pid <= 0:
        return result

    def bounded_read(name, limit):
        with (Path('/proc')/str(pid)/name).open('rb') as stream:
            data = stream.read(limit+1)
        if len(data) > limit:
            raise ValueError('Oversized proc record')
        return data.decode('ascii')

    try:
        # comm may itself contain spaces or parentheses. The last ')' ends it.
        tail = bounded_read('stat', 4096).rpartition(') ')[2].split()
        ticks = int(tail[11])+int(tail[12])  # fields 14/15, after pid and comm
        rate = os.sysconf('SC_CLK_TCK')
        if ticks >= 0 and rate > 0:
            result['cpu_seconds'] = ticks/rate
    except (OSError, ValueError, IndexError, OverflowError):
        pass
    try:
        fields = {}
        for line in bounded_read('status', 16384).splitlines():
            key, _, value = line.partition(':')
            if key in ('VmPeak', 'VmHWM'):
                count, unit = value.split()
                if unit != 'kB' or not count.isdigit():
                    raise ValueError('Invalid memory counter')
                fields[key] = int(count)*1024
        result['vm_peak_bytes'] = fields.get('VmPeak')
        result['vm_hwm_bytes'] = fields.get('VmHWM')
    except (OSError, ValueError, OverflowError):
        pass
    return result


class CalculationError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class Runner:
    def __init__(self, timeout: float = 20, rate: int = 30, *, turn_pilot: bool = False):
        self.timeout = timeout
        self.rate = min(rate, 30) if turn_pilot else rate
        self.busy = False
        self.starts = deque()
        self.turn_pilot = turn_pilot

    async def run(self, name: str, arguments: dict) -> dict:
        try:
            if name == 'solve_turn_v1' and self.turn_pilot:
                from .turn_pilot import prepare
                args = prepare(arguments)
            else:
                args = validate(name, arguments, hosted=True)
        except (ValueError, TypeError, KeyError):
            raise CalculationError('invalid_input', 'Invalid tool arguments; check schema, ranges and hosted limits') from None
        now = monotonic()
        while self.starts and self.starts[0] < now-60:
            self.starts.popleft()
        if len(self.starts) >= self.rate:
            raise CalculationError('rate_limited', 'Service calculation allowance exhausted; retry after one minute')
        if self.busy:
            raise CalculationError('busy', 'One calculation is already running; retry later')
        self.busy = True
        self.starts.append(now)
        process = None
        try:
            if name == 'solve_turn_v1':
                return await self._run_turn(args)
            # Do not propagate OAuth keys or operator credentials into workers.
            env = {k: v for k, v in os.environ.items() if k.upper() in {
                'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'VIRTUAL_ENV', 'PYTHONPATH'}}
            env.update(OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
            process = await asyncio.create_subprocess_exec(
                sys.executable, '-m', 'poker_spot.worker',
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL, env=env)
            try:
                output, _ = await asyncio.wait_for(
                    process.communicate(json.dumps({'name': name, 'arguments': args}).encode()),
                    timeout=self.timeout)
            except TimeoutError:
                raise CalculationError('timeout', 'Calculation exceeded its wall-clock limit') from None
            if process.returncode:
                raise CalculationError('worker_failed', 'Calculation stopped by worker resource limit or internal error')
            data = json.loads(output)
            if 'error' in data:
                raise CalculationError('invalid_input', data['error'])
            return data['result']
        finally:
            if process is not None and process.returncode is None:
                process.kill()
                await process.wait()
            self.busy = False

    async def _run_turn(self, args):
        """Same admission/rate slot; isolated startup, bounded pipe, deadline through reap."""
        process = None
        timeout_snapshot = None
        started = monotonic()
        try:
            async with asyncio.timeout(min(self.timeout, 20)):
                env = {k: v for k, v in os.environ.items() if k.upper() in {
                    'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP'}}
                env.update(OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
                spawn = asyncio.create_task(asyncio.create_subprocess_exec(
                    sys.executable, '-I', str(Path(__file__).with_name('turn_worker.py')),
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL, env=env))
                try:
                    process = await asyncio.shield(spawn)
                except BaseException:
                    # Cancellation during spawn must not orphan an unassigned child.
                    process = await spawn
                    raise
                body = json.dumps(args, allow_nan=False).encode()
                if len(body) > 16_384:
                    raise CalculationError('invalid_input', 'Turn request exceeds body budget')
                process.stdin.write(body)
                await process.stdin.drain()
                process.stdin.close()
                # Extra byte detects oversize without accumulating unlimited stdout.
                chunks, size = [], 0
                while True:
                    chunk = await process.stdout.read(26_625-size)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > 26_624:
                        raise CalculationError('output_limit', 'Turn worker exceeded output budget')
                await process.wait()
                if process.returncode:
                    raise CalculationError('worker_failed', 'Turn worker stopped by resource limit or internal error')
                data = json.loads(b''.join(chunks))
                if 'error' in data:
                    raise CalculationError(data['error']['code'], data['error']['message'])
                measurement = data['measurement']
                if sys.platform == 'linux' and (
                        measurement['limits'] != {'cpu_seconds': [20, 20], 'address_space_bytes': [384*1024**2]*2}
                        or measurement['budget_enforced'] is not True
                        or measurement['worker_cpu_seconds'] > 20
                        or measurement['memory_bytes']['VmPeak'] > 384*1024**2):
                    raise CalculationError('resource_limit', 'Turn worker budget receipt failed')
                result = data['result']
                result['execution'] = dict(measurement, parent_wall_seconds=monotonic()-started)
                return result
        except TimeoutError:
            timeout_snapshot = _turn_timeout_snapshot(process.pid if process is not None else None)
            raise CalculationError('timeout', 'Turn calculation exceeded its wall-clock limit') from None
        except (json.JSONDecodeError, KeyError, TypeError, BrokenPipeError, ConnectionResetError):
            raise CalculationError('worker_failed', 'Invalid turn worker response') from None
        finally:
            if process is not None and process.returncode is None:
                process.kill()
                await process.wait()
            if timeout_snapshot is not None:
                # WARNING is visible with the documented default Uvicorn logging.
                # Log only after reap; never log arguments, tokens or proc text.
                logger.warning('turn_timeout parent_wall_seconds=%.6f child_cpu_seconds=%s '
                               'child_vm_peak_bytes=%s child_vm_hwm_bytes=%s',
                               monotonic()-started, timeout_snapshot['cpu_seconds'],
                               timeout_snapshot['vm_peak_bytes'], timeout_snapshot['vm_hwm_bytes'])
