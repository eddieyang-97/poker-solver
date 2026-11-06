"""Pre-study cost calibration on the first declared #58 axis target only."""
import hashlib
import json
from pathlib import Path
import platform
import time
from types import SimpleNamespace

from bounded_response import ResponseSearch
from game import Game
from guidance import ProbabilityGuide
from recall_training import RecallPolicy
from response_refinement import CachedRecallModel, ResponsePlan, ReplayLimit, exact_response_value
from run_fixed_strategy import peak_memory

BASE=Path(__file__).resolve().parent


def main():
    files=('calibrate_response_refinement.py','response_refinement.py','bounded_response.py',
           'recall_training.py','fixed_strategy.py','game.py','guidance.py','run_fixed_strategy.py')
    result={'purpose':'cost/parity calibration, not target selection','target':'axis / 490061 / 60 CPU seconds',
            'source_sha256_lf':{n:hashlib.sha256((BASE/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for n in files},
            'platform':platform.platform(),'python':platform.python_version(),'status':'running','runs':[]}
    receipt=json.loads((BASE/'outputs/axis-batches.json').read_text())
    row=next(r for r in receipt['full_runs'] if r['method']=='axis' and r['seed']==490061)['checkpoints'][-1]
    artifact=row['policy'];path=BASE/'outputs'/artifact['file']
    if hashlib.sha256(path.read_bytes()).hexdigest()!=artifact['sha256']: raise ValueError('Target file differs')
    result['target_file']=artifact
    game=Game();guide=ProbabilityGuide(game);target=RecallPolicy.load(game,path)
    start,cpu=time.perf_counter(),time.process_time()
    def save():
        result['wall_seconds'],result['cpu_seconds']=time.perf_counter()-start,time.process_time()-cpu
        result['peak_process_memory']=peak_memory()
        (BASE/'outputs/response-calibration.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
    save()
    try:
        uncached=SimpleNamespace(target=target,actions=target.actions)
        cached=CachedRecallModel(target)
        incumbents={}
        for name,model,depth in (('uncached',uncached,1),('cached',cached,1),('cached',cached,2)):
            for seat in (0,1):
                w,c=time.perf_counter(),time.process_time()
                search=ResponseSearch(game,guide,model,seat,depth,32,
                                      incumbent=incumbents.get(seat) if depth==2 else None)
                bound=search.solve()
                record={'model':name,**bound,'search_wall_seconds':time.perf_counter()-w,'search_cpu_seconds':time.process_time()-c}
                if depth==1:
                    baseline=row['quality']['seats'][seat]
                    if max(abs(bound[k]-baseline[k]) for k in ('lower','upper'))>1e-10: raise AssertionError('Historical baseline changed')
                if name=='cached': incumbents[seat]=search
                plan=ResponsePlan.from_search(search,artifact['probabilities_sha256'])
                if depth==2:
                    record['plan']=plan.save(BASE/f'outputs/response-calibration-seat{seat}.json')
                    try: record['exact_replay']={'status':'completed',**exact_response_value(game,target,plan,node_limit=100000,seconds=10)}
                    except ReplayLimit as error:
                        record['exact_replay']={'status':'budget_exceeded','reason':str(error),'stats':error.stats,
                                                'wall_seconds':error.wall_seconds,'cpu_seconds':error.cpu_seconds}
                    if record['exact_replay']['status']=='completed' and abs(record['exact_replay']['value']-bound['lower'])>1e-10:
                        raise AssertionError('Exact replay mismatch')
                result['runs'].append(record);save()
                print(json.dumps({'model':name,'seat':seat,'depth':depth,'CPU':record['search_cpu_seconds'],
                                  'lower':bound['lower'],'upper':bound['upper'],'replay':record.get('exact_replay')}),flush=True)
        result['status']='completed'
    except (Exception,KeyboardInterrupt) as error:
        result['status'],result['failure']='incomplete',f'{type(error).__name__}: {error}'
        raise
    finally:save()


if __name__=='__main__':main()
