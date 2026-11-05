"""Pinned independent OpenSpiel training/BR reproduction and recall inventory.

Optional development environment only. No hosted/runtime dependency or import.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import time
import zipfile

import numpy as np

from fixed_strategy import GraphCFR, TinyDudo, normalize, tree_increments
from one_face import evaluate
from recall_inventory import inventory


BASE = Path(__file__).resolve().parent
SOURCES = ('fixed_strategy.py','recall_inventory.py','run_fixed_strategy.py','game.py','one_face.py')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_hashes():
    return {n:hashlib.sha256((BASE/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for n in SOURCES}


def peak_memory():
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [('cb',wintypes.DWORD),('faults',wintypes.DWORD)] + [
                (n,ctypes.c_size_t) for n in ('peak_working_set','working_set','peak_paged',
                'paged','peak_nonpaged','nonpaged','pagefile','peak_pagefile')]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.WinDLL('kernel32',use_last_error=True)
        psapi = ctypes.WinDLL('psapi',use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(counters),counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return {'bytes':counters.peak_working_set,'kind':'Windows process peak working set'}
    import resource
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {'bytes':value*(1 if platform.system() == 'Darwin' else 1024),'kind':'process ru_maxrss'}


def info_key(game, hand, history):
    return str(game.hands[hand])+''.join(f' {a//game.sides+1}-{a%game.sides+1}' for a in history)


def cpp_action(game, action):
    return 2*game.sides if action == -1 else action


def public_histories(game):
    yield ()
    def walk(h):
        for a in game.actions(h):
            if a != -1:
                child = h+(a,)
                yield child
                yield from walk(child)
    yield from walk(())


def parity_check(spiel, game):
    """Exhaust all chance histories/actions/payoffs using separate game engines."""
    root = spiel.new_initial_state()
    expected_chance = [(i,1/game.sides) for i in range(game.sides)]
    if root.chance_outcomes() != expected_chance:
        raise AssertionError('First chance mismatch')
    checked = {'private_pairs':0,'decision_states':0,'terminal_states':0}
    def walk(state, hands, history):
        player = len(history)%2
        if state.current_player() != player:
            raise AssertionError('Actor mismatch')
        if state.information_state_string() != info_key(game,hands[player],history):
            raise AssertionError('Own-information mismatch')
        expected = sorted(cpp_action(game,a) for a in game.actions(history))
        if state.legal_actions() != expected:
            raise AssertionError('Legal action mismatch')
        checked['decision_states'] += 1
        for a in game.actions(history):
            child = state.child(cpp_action(game,a))
            if a == -1:
                value = game.payoff(history,hands,player)
                if not child.is_terminal() or child.returns() != [value,-value]:
                    raise AssertionError('Terminal utility mismatch')
                checked['terminal_states'] += 1
            else:
                walk(child,hands,history+(a,))
    for a in range(game.sides):
        first = root.child(a)
        if first.chance_outcomes() != expected_chance:
            raise AssertionError('Second chance mismatch')
        for b in range(game.sides):
            checked['private_pairs'] += 1
            walk(first.child(b),(a,b),())
    return checked


def table_from_policy(game, policy):
    return {info_key(game,t,h):[(cpp_action(game,a),float(p)) for a,p in
            zip(game.actions(h),policy(len(h)%2,t,h))]
            for h in public_histories(game) for t in range(game.sides)}


def policy_from_cpp(game, policy):
    def call(player, hand, history):
        row = dict(policy.get_state_policy(info_key(game,hand,history)))
        return [row[cpp_action(game,a)] for a in game.actions(history)]
    return call


def compare_evaluation(pyspiel, spiel, game, table, keep_table=False):
    policy = pyspiel.TabularPolicy(table)
    ours = evaluate(game,policy_from_cpp(game,policy))
    external_nc = pyspiel.nash_conv(spiel,policy)
    external_ev = pyspiel.expected_returns(spiel.new_initial_state(),policy,-1,True)[0]
    error = max(abs(ours['nashconv']-external_nc),abs(ours['ev_p0']-external_ev))
    if error > 1e-10:
        raise AssertionError(f'Independent evaluation mismatch: {error}')
    result = {'tuple_tree':ours,'openspiel_nashconv':external_nc,'openspiel_ev_p0':external_ev,
              'maximum_error':error,'policy_sha256':hashlib.sha256(
                  json.dumps(table,sort_keys=True,separators=(',',':')).encode()).hexdigest()}
    if keep_table:
        result['full_history_policy_table'] = table
    return result


def run_case(pyspiel, sides, iterations):
    game = TinyDudo(sides)
    spiel = pyspiel.load_game(f'liars_dice(numdice=1,dice_sides={sides},bidding_rule=reset-face)')
    result = {'sides':sides,'dice_per_player':1,'iterations':iterations,
              'rules_parity':parity_check(spiel,game),'trainers':[]}
    start, cpu = time.perf_counter(),time.process_time()
    external = pyspiel.CFRSolver(spiel)
    for _ in range(iterations):
        external.evaluate_and_update_policy()
    elapsed, cpu_elapsed = time.perf_counter()-start,time.process_time()-cpu
    policy = external.average_policy()
    table = table_from_policy(game,policy_from_cpp(game,policy))
    measured = compare_evaluation(pyspiel,spiel,game,table,sides == 3)
    if measured['openspiel_nashconv'] > .06:
        raise AssertionError('Independent perfect-recall baseline has not converged to the declared tiny-game gate')
    result['trainers'].append({'name':'OpenSpiel C++ CFR (independent alternating trainer)',
                               'wall_seconds':elapsed,'cpu_seconds':cpu_elapsed,'evaluation':measured})
    for recall in (None,1,2):
        solver = GraphCFR(game,recall)
        start, cpu = time.perf_counter(),time.process_time()
        checkpoints = []
        for t in range(1,iterations+1):
            solver.step()
            if t in (1,10,100,iterations):
                # Evaluation happens outside recorded training cost.
                elapsed = time.perf_counter()-start
                cpu_elapsed = time.process_time()-cpu
                value = evaluate(game,solver.policy)
                checkpoints.append({'iterations':t,**value})
                start, cpu = time.perf_counter()-elapsed,time.process_time()-cpu_elapsed
        elapsed, cpu_elapsed = time.perf_counter()-start,time.process_time()-cpu
        table = table_from_policy(game,solver.policy)
        measured = compare_evaluation(pyspiel,spiel,game,table,sides == 3)
        if recall is None and measured['openspiel_nashconv'] > .06:
            raise AssertionError('Graph perfect-recall baseline has not converged to the declared tiny-game gate')
        result['trainers'].append({'name':'fixed-strategy cumulative graph CFR',
            'recall':recall,'public_states':len(solver.graph.keys),
            'infosets':len(solver.graph.keys)*sides,
            'estimated_array_bytes':solver.estimated_array_bytes,
            'wall_seconds':elapsed,'cpu_seconds':cpu_elapsed,'checkpoints':checkpoints,'evaluation':measured})
        print(f'sides={sides} recall={recall} NashConv={measured["openspiel_nashconv"]:.8f}',flush=True)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--iterations',type=int,default=1000)
    parser.add_argument('--sides',type=int,nargs='+',default=[3,6],choices=range(2,7))
    parser.add_argument('--wheel',type=Path,required=True,help='Pinned wheel used for this isolated installation')
    parser.add_argument('--output',type=Path,default=BASE/'outputs/fixed-strategy.json')
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error('Positive iteration count required')
    import open_spiel
    import pyspiel
    if importlib.metadata.version('open_spiel') != '2.0.2':
        raise ValueError('Reference must be pinned OpenSpiel 2.0.2')
    package = Path(open_spiel.__file__).parent
    provenance = {'version':'2.0.2','license':'Apache-2.0','wheel':args.wheel.name,
                  'wheel_sha256':digest(args.wheel),'pyspiel_binary_sha256':digest(pyspiel.__file__),
                  'packaged_source_sha256':{n:digest(package/n) for n in (
                      'games/liars_dice/liars_dice.cc','games/liars_dice/liars_dice.h',
                      'algorithms/cfr.cc','algorithms/cfr.h','algorithms/best_response.cc',
                      'algorithms/tabular_exploitability.cc')},
                  'dependencies':{n:importlib.metadata.version(n) for n in
                                  ('numpy','scipy','attrs','absl-py','ml-collections','PyYAML')}}
    # A supplied wheel is provenance only if its evaluated binary/sources match
    # this installation. Do not merely hash an arbitrary caller-provided file.
    with zipfile.ZipFile(args.wheel) as archive:
        members = [n for n in archive.namelist() if n.endswith(Path(pyspiel.__file__).name)]
        if len(members) != 1 or hashlib.sha256(archive.read(members[0])).hexdigest() != provenance['pyspiel_binary_sha256']:
            raise ValueError('Reference wheel does not match installed pyspiel')
        for name, expected in provenance['packaged_source_sha256'].items():
            if hashlib.sha256(archive.read('open_spiel/'+name)).hexdigest() != expected:
                raise ValueError('Reference wheel source mismatch')
    report = {'status':'running','algorithm':'simultaneous signed cumulative frozen-strategy graph CFR',
              'not_a_reproduction_of':'paper Algorithm 2 visit-normalized regret update',
              'sampling':'none: enumerate all tiny-game deals exactly; deterministic training',
              'environment':{'platform':platform.platform(),'python':platform.python_version(),
                             'processor':platform.processor(),'openblas_threads':os.getenv('OPENBLAS_NUM_THREADS')},
              'source_sha256_lf':source_hashes(),'external_reference':provenance,
              'house_rule_inventory':inventory(),'cases':[]}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    def save():
        args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    save()
    start,cpu = time.perf_counter(),time.process_time()
    try:
        # Independent scalar recurrence probe with a fixed nonuniform policy.
        rng = np.random.default_rng(490001)
        errors = []
        for recall in (None,1,2):
            solver = GraphCFR(TinyDudo(3),recall)
            strategies = [normalize(rng.random(r.shape)) for r in solver.regrets]
            dag = solver.increments(strategies)
            tree = tree_increments(solver.game,solver.graph,strategies)
            error = max(abs(dag[2]-tree[2]),max(float(np.max(np.abs(a-b)))
                        for aa,bb in zip(dag[:2],tree[:2]) for a,b in zip(aa,bb)))
            if error > 1e-12:
                raise AssertionError('Graph/tree update mismatch')
            errors.append({'recall':recall,'seed':490001,'maximum_error':error})
        report['scalar_recurrence_checks'] = errors
        for sides in args.sides:
            report['cases'].append(run_case(pyspiel,sides,args.iterations))
            save()
        if source_hashes() != report['source_sha256_lf']:
            raise RuntimeError('Source changed during experiment')
        report['status'] = 'completed'
    except Exception as exc:
        report['status'],report['failure'] = 'failed',f'{type(exc).__name__}: {exc}'
        raise
    finally:
        report['wall_seconds'] = time.perf_counter()-start
        report['cpu_seconds'] = time.process_time()-cpu
        report['peak_process_memory'] = peak_memory()
        save()


if __name__ == '__main__':
    main()
