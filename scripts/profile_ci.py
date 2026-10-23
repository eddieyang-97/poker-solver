"""Read-only public Actions timeline/artifact receipts; no tokens or settings writes."""
import argparse
from datetime import datetime
import json
import math
from pathlib import Path
from urllib.request import Request, urlopen


def seconds(start, end):
    return (datetime.fromisoformat(end.replace('Z', '+00:00'))-
            datetime.fromisoformat(start.replace('Z', '+00:00'))).total_seconds()


def summarize(run, jobs, artifacts):
    if run['status'] != 'completed' or run['conclusion'] != 'success':
        raise ValueError('Timing comparison requires a completed successful run')
    rows = []
    for job in jobs:
        if job['conclusion'] != 'success':
            raise ValueError('Every measured job must succeed')
        rows.append({'id': job['id'], 'name': job['name'], 'runner_name': job['runner_name'],
                     'labels': job['labels'], 'started_at': job['started_at'], 'completed_at': job['completed_at'],
                     'queue_seconds': seconds(job.get('created_at', run['created_at']), job['started_at']),
                     'created_to_start_seconds': seconds(run['created_at'], job['started_at']),
                     'seconds': seconds(job['started_at'], job['completed_at']),
                     'setup_install_seconds': sum(seconds(s['started_at'], s['completed_at']) for s in job['steps']
                                                 if s['name'] in ('Set up job', 'Run actions/checkout@v4',
                                                                  'Run actions/setup-python@v5',
                                                                  'Run pip install -r requirements-dev.txt')
                                                 and s.get('started_at') and s.get('completed_at')),
                     'steps': [{'name': s['name'], 'conclusion': s['conclusion'],
                                'seconds': seconds(s['started_at'], s['completed_at'])}
                               for s in job['steps'] if s.get('started_at') and s.get('completed_at')]})
    start = min(j['started_at'] for j in jobs)
    end = max(j['completed_at'] for j in jobs)
    return {'run_id': run['id'], 'head_sha': run['head_sha'], 'event': run['event'],
            'url': run['html_url'], 'created_at': run['created_at'],
            'first_job_start': start, 'last_job_end': end,
            'initial_queue_seconds': seconds(run['created_at'], start),
            'critical_path_seconds': seconds(start, end),
            'created_to_green_seconds': seconds(run['created_at'], end),
            'total_job_seconds': sum(j['seconds'] for j in rows),
            'rounded_runner_minutes_estimate': sum(math.ceil(j['seconds']/60) for j in rows),
            'billing_caveat': 'Job wall-time estimate, not account billing; aggregate dependency wait is excluded from job duration',
            'jobs': rows, 'artifacts': [{'id': a['id'], 'name': a['name'], 'size_in_bytes': a['size_in_bytes'],
                                       'digest': a.get('digest')} for a in artifacts],
            'total_artifact_bytes': sum(a['size_in_bytes'] for a in artifacts)}


def fetch(path):
    request = Request('https://api.github.com/'+path, headers={'Accept': 'application/vnd.github+json',
                                                             'User-Agent': 'poker-solver-ci-study'})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default='eddieyang-97/poker-solver')
    parser.add_argument('--run', type=int, action='append', required=True)
    parser.add_argument('--output', type=Path, default=Path('.artifacts/ci-profile'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    summaries = []
    for identity in args.run:
        base = f'repos/{args.repo}/actions/runs/{identity}'
        raw = {'run': fetch(base), 'jobs': fetch(base+'/jobs?per_page=100'),
               'artifacts': fetch(base+'/artifacts?per_page=100')}
        if len(raw['jobs']['jobs']) != raw['jobs']['total_count'] or len(raw['artifacts']['artifacts']) != raw['artifacts']['total_count']:
            raise ValueError('Incomplete pagination; refuse partial timing/evidence report')
        summary = summarize(raw['run'], raw['jobs']['jobs'], raw['artifacts']['artifacts'])
        (args.output/f'{identity}.raw.json').write_text(json.dumps(raw, indent=2)+'\n', encoding='utf-8')
        summaries.append(summary)
        print(f'{identity}: {summary["critical_path_seconds"]}s job critical path; '
              f'{summary["initial_queue_seconds"]}s initial queue; '
              f'{summary["rounded_runner_minutes_estimate"]} estimated runner minutes; '
              f'{len(summary["artifacts"])} artifacts / {summary["total_artifact_bytes"]} bytes')
    (args.output/'summary.json').write_text(json.dumps(summaries, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
