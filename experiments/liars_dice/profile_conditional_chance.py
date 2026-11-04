"""Small post-study diagnostic; instrumented wall time is not the CPU benchmark."""
import cProfile
import hashlib
import json
import os
from pathlib import Path
import platform
import pstats
import time

from conditional_chance import ConditionalTrainer
from game import Game


def main():
    base=Path(__file__).resolve().parent
    trainer=ConditionalTrainer(Game(),490044)
    for _ in range(2): trainer.step()
    profiler=cProfile.Profile()
    c=time.process_time();profiler.enable()
    for _ in range(20): trainer.step()
    profiler.disable();cpu=time.process_time()-c
    stats=pstats.Stats(profiler)
    rows=[]
    for key,(primitive,total,own,cumulative,_) in sorted(stats.stats.items(),key=lambda x:-x[1][2])[:15]:
        rows.append({'file':Path(key[0]).name,'line':key[1],'function':key[2],
                     'calls':total,'primitive_calls':primitive,'instrumented_self_wall_seconds':own,
                     'instrumented_cumulative_wall_seconds':cumulative})
    result={'seed':490044,'warmup_steps':2,'profiled_steps':20,'platform':platform.platform(),
            'python':platform.python_version(),'openblas_threads':os.getenv('OPENBLAS_NUM_THREADS'),
            'source_sha256_lf':{n:hashlib.sha256((base/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
                                for n in ('conditional_chance.py','recall_training.py','game.py','profile_conditional_chance.py')},
            'instrumented_cpu_seconds':cpu,'instrumented_wall_seconds':stats.total_tt,
            'not_an_equal_cpu_learning_comparison':True,'top_functions':rows}
    (base/'outputs/conditional-profile.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')


if __name__=='__main__':main()
