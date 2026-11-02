"""Fresh-process first-request latency, separately from the stress workload."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from run_analysis_research import distribution, peak_rss
from streaming_analysis import Analyzer, canonical, source_hashes


def main():
    base = Path(__file__).parent
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', action='store_true')
    args = parser.parse_args()
    snapshot = base/'outputs/analysis-model.json'
    if args.worker:
        start = time.perf_counter()
        analyzer = Analyzer(snapshot.read_bytes())
        loaded = time.perf_counter()
        answer = analyzer.analyze([4, 4, 4, 2, 3], 1, [{'quantity':3, 'face':6, 'mode':'fly'}], analyzer.model_id)
        print(json.dumps({'load_seconds':loaded-start, 'first_query_seconds':time.perf_counter()-loaded,
                          'status':answer['status'], 'model_id':analyzer.model_id,
                          'result_sha256':hashlib.sha256(canonical(answer)).hexdigest(), 'peak_memory':peak_rss()}))
        return
    rows = []
    for _ in range(5):
        start = time.perf_counter()
        value = json.loads(subprocess.check_output([sys.executable, __file__, '--worker'], text=True))
        value['fresh_process_first_response_seconds'] = time.perf_counter()-start
        rows.append(value)
    if len({r['result_sha256'] for r in rows}) != 1 or any(r['status'] != 'ok' for r in rows):
        raise AssertionError('Fresh-process first request is not reproducible/supported')
    result = {'snapshot_sha256':hashlib.sha256(snapshot.read_bytes()).hexdigest(),
              'source_sha256_lf':{**source_hashes(), **{
                  name:hashlib.sha256((base/name).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
                  for name in (Path(__file__).name, 'run_analysis_research.py')}},
              'samples':rows, 'first_response_seconds':distribution([r['fresh_process_first_response_seconds'] for r in rows]),
              'meaning':'local process startup + imports + snapshot load + first supported query + output + process exit; no network/provider latency'}
    (base/'outputs/cold-query.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps(result['first_response_seconds']))


if __name__ == '__main__':
    main()
