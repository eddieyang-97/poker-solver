"""Bounded admission and a wall-clock timeout that kills the computation."""
import asyncio
import json
import os
import sys
from collections import deque
from time import monotonic

from .validation import validate


class CalculationError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class Runner:
    def __init__(self, timeout: float = 20, rate: int = 30):
        self.timeout = timeout
        self.rate = rate
        self.busy = False
        self.starts = deque()

    async def run(self, name: str, arguments: dict) -> dict:
        try:
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
