"""Separate post-study full-rule block cost diagnostic; not a quality benchmark."""
import cProfile
import gc
import hashlib
import json
import os
from pathlib import Path
import platform
import pstats
import time

import numpy as np

from crossed_batches import BatchTrainer
from game import Game


def main():
    base=Path(__file__).resolve().parent
    result={'seed':490054,'warmup_steps':2,'profiled_steps':20,'batch_size':8,
            'platform':platform.platform(),'python':platform.python_version(),'numpy':np.__version__,
            'openblas_threads':os.getenv('OPENBLAS_NUM_THREADS'),
            'not_an_equal_cpu_learning_comparison':True,'methods':[],
            'source_sha256_lf':{n:hashlib.sha256((base/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
                for n in ('crossed_batches.py','recall_training.py','fixed_strategy.py','game.py','profile_crossed_batches.py')}}
    for crossed in (False,True):
        trainer=BatchTrainer(Game(),490054,8,crossed)
        for _ in range(2): trainer.step()
        profiler=cProfile.Profile()
        cpu=time.process_time();profiler.enable()
        for _ in range(20): trainer.step()
        profiler.disable();cpu=time.process_time()-cpu
        stats=pstats.Stats(profiler)
        rows=[]
        for key,(primitive,total,own,cumulative,_) in sorted(stats.stats.items(),key=lambda x:-x[1][2])[:15]:
            rows.append({'file':Path(key[0]).name,'line':key[1],'function':key[2],
                         'calls':total,'primitive_calls':primitive,'instrumented_self_wall_seconds':own,
                         'instrumented_cumulative_wall_seconds':cumulative})
        result['methods'].append({'method':'crossed8' if crossed else 'diagonal8',
            'instrumented_cpu_seconds':cpu,'instrumented_wall_seconds':stats.total_tt,'top_functions':rows})
        del trainer;gc.collect()
    (base/'outputs/batch-profile.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')


if __name__=='__main__':main()
