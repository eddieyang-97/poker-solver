"""Controlled, explicitly modified reference build; never a production solver."""
from __future__ import annotations

import base64
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess

from benchmarks.harness import SCALE, evaluate_profile, make_game
from benchmarks.texas import LOOKUP_SHA256, SOURCE_COMMIT, import_policy
from benchmarks.texas_blockers import CHIP_GATE, diagnostic_commands, load_blocker_fixture

CPP = 'src/trainable/DiscountedCfrTrainable.cpp'
PCFR = 'src/solver/PCfrSolver.cpp'
SOURCE_LOOKUP_SHA256_LF = '13e0f4bd3cb99388caec49b36f98b98b70ae30407cbd740d880db65ed4db5e7b'


def experiment_commands():
    return (diagnostic_commands(40000).replace('set_print_interval 1000', 'set_print_interval 4000')
            .replace('set_accuracy 0.001', 'set_accuracy -1'))


def replace_once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('Pinned source instrumentation anchor changed or is ambiguous')
    return text.replace(before, after)


def instrument(trainable, solver):
    """Baseline changes observation only; the second variant changes one multiplier."""
    head, tail = trainable.split('json DiscountedCfrTrainable::dump_strategy(bool with_state)', 1)
    tail = replace_once(tail, 'const vector<float>& average_strategy = this->getAverageStrategy();',
                        'const vector<float> average_strategy = std::getenv("POKER_EXPERIMENT_CURRENT") '
                        '? this->getcurrentStrategyNoCache() : this->getAverageStrategy();')
    baseline = '#include <cstdlib>\n'+head+'json DiscountedCfrTrainable::dump_strategy(bool with_state)'+tail
    variant = replace_once(baseline, 'this->cum_r_plus[index] *= this->theta;',
                            'this->cum_r_plus[index] *= 1.0f; // EXPERIMENT: cumulative history')
    solver = '#include <cstdlib>\n'+solver
    solver = replace_once(solver,
                          '(i % this->print_interval == 0 && i != 0 && i >= this->warmup)',
                          '(((i + 1) % this->print_interval == 0 || i + 1 == this->iteration_number) && i >= this->warmup)')
    anchor = 'float expliotibility = br.printExploitability(tree->getRoot(), i + 1, tree->getRoot()->getPot(), initial_board_long);'
    capture = '''
            const string experiment_prefix = "checkpoint_" + to_string(i + 1);
            { ofstream out(experiment_prefix + "_meta.json");
              out << json{{"iterations", i + 1}, {"exploitability_percent", expliotibility}}; }
            { ofstream out(experiment_prefix + "_average.json"); out << this->dumps(false, 1); }
            setenv("POKER_EXPERIMENT_CURRENT", "1", 1);
            { ofstream out(experiment_prefix + "_current.json"); out << this->dumps(false, 1); }
            unsetenv("POKER_EXPERIMENT_CURRENT");
'''
    solver = replace_once(solver, anchor, anchor+capture)
    return {'baseline_observer': baseline, 'theta_one': variant, 'solver_observer': solver}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    commit = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if commit != SOURCE_COMMIT:
        raise ValueError('Wrong upstream revision')
    subprocess.run(['git', '-C', str(source), 'diff', '--exit-code', 'HEAD'], check=True, capture_output=True)
    lookup = source / 'resources/compairer/card5_dic_sorted.txt'
    if (digest(lookup) not in (LOOKUP_SHA256, SOURCE_LOOKUP_SHA256_LF)
            or hashlib.sha256(lookup.read_bytes().replace(b'\r\n', b'\n')).hexdigest() != SOURCE_LOOKUP_SHA256_LF):
        raise ValueError('Different hand-evaluation table')
    patches = instrument((source / CPP).read_text(encoding='utf-8'), (source / PCFR).read_text(encoding='utf-8'))
    output.mkdir(parents=True, exist_ok=False)
    for name, text in patches.items():
        (output / (name+'.cpp')).write_text(text, encoding='utf-8')
    driver = '''#include <QCoreApplication>
#include "include/tools/CommandLineTool.h"
int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    if (argc != 3) return 2;
    try { CommandLineTool tool("holdem", argv[1]); tool.execFromFile(argv[2]); }
    catch (const std::exception& ex) { std::cerr << ex.what() << std::endl; return 3; }
    return 0;
}
'''
    (output / 'driver.cpp').write_text(driver, encoding='utf-8')
    tracked = subprocess.check_output(['git', '-C', str(source), 'ls-files', 'src'], text=True).splitlines()
    allowed_dirs = {'src', 'src/compairer', 'src/nodes', 'src/ranges', 'src/solver', 'src/tools', 'src/trainable'}
    files = [name for name in tracked if name.endswith('.cpp') and str(Path(name).parent).replace('\\', '/') in allowed_dirs
             and name not in (CPP, PCFR, 'src/console.cpp')]
    files += ['src/runtime/PokerSolver.cpp']
    cmake = ['cmake_minimum_required(VERSION 3.16)', 'project(texas_experiment LANGUAGES CXX)',
             'set(CMAKE_CXX_STANDARD 17)', 'set(CMAKE_POSITION_INDEPENDENT_CODE ON)',
             'find_package(Qt5 REQUIRED COMPONENTS Core)',
             'find_package(OpenMP REQUIRED)', 'add_library(engine STATIC solver_observer.cpp']
    cmake.extend('  "'+str(source / name).replace('\\', '/')+'"' for name in files)
    cmake.extend([')', 'target_include_directories(engine PUBLIC "'+str(source).replace('\\', '/')+'")',
                  'target_link_libraries(engine PUBLIC Qt5::Core OpenMP::OpenMP_CXX)'])
    for name in ('baseline_observer', 'theta_one'):
        cmake.extend([f'add_executable({name} driver.cpp {name}.cpp)', f'target_link_libraries({name} PRIVATE engine)'])
    (output / 'CMakeLists.txt').write_text('\n'.join(cmake)+'\n', encoding='utf-8')
    manifest = {'source_commit': commit, 'source_clean_before_instrumentation': True,
                'lookup_sha256': digest(lookup), 'lookup_sha256_lf': SOURCE_LOOKUP_SHA256_LF,
                'source_sha256': {name: digest(source / name) for name in files+[CPP, PCFR]},
                'header_sha256': {name: digest(source / name) for name in subprocess.check_output(
                    ['git', '-C', str(source), 'ls-files', 'include'], text=True).splitlines()},
                'generated_sha256': {path.name: digest(path) for path in output.iterdir() if path.is_file()},
                'variants': {'baseline_observer': 'Original regret and averaging updates; observation instrumentation only',
                             'theta_one': 'Same instrumentation; only averaging multiplier changed from theta=0.9 to 1.0'},
                'checkpoint_instrumentation': 'Capture source metric, average policy and current policy immediately after the same completed iteration'}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    return manifest


def analyze(execution):
    if (execution['build']['source_commit'] != SOURCE_COMMIT
            or execution['build']['lookup_sha256'] not in (LOOKUP_SHA256, SOURCE_LOOKUP_SHA256_LF)
            or execution['build']['lookup_sha256_lf'] != SOURCE_LOOKUP_SHA256_LF
            or execution['fixture'] != load_blocker_fixture()):
        raise ValueError('Wrong experiment source')
    game = make_game(load_blocker_fixture())
    rows = []
    policies = {}
    iterations = [p['iterations'] for p in execution['variants']['baseline_observer']['checkpoints']]
    if iterations not in (list(range(4000, 40001, 4000)), [4000, 40000]):
        raise ValueError('Incomplete/misaligned checkpoint sequence')
    for variant in ('baseline_observer', 'theta_one'):
        data = execution['variants'][variant]
        if data['input_commands'] != experiment_commands():
            raise ValueError('Different experiment game or training budget')
        if [p['iterations'] for p in data['checkpoints']] != iterations:
            raise ValueError('Incomplete/misaligned checkpoint sequence')
        for point in data['checkpoints']:
            if not math.isfinite(point['exploitability_percent']):
                raise ValueError('Nonfinite source convergence metric')
            for policy_type in ('average', 'current'):
                policy = import_policy(game, point[policy_type])
                policies[(variant, point['iterations'], policy_type)] = policy
                evaluated = evaluate_profile(game, policy)
                source_gap = 2*game.base_pot/SCALE*point['exploitability_percent']/100
                row = {'variant': variant, 'iterations': point['iterations'], 'policy': policy_type,
                       'oop_ev': evaluated['root'][0], 'nashconv': evaluated['gap'],
                       'status': 'PASS' if evaluated['gap'] <= CHIP_GATE else 'FAIL'}
                if policy_type == 'average':
                    row['same_checkpoint_source_nashconv'] = source_gap
                    row['source_vs_independent_gap_delta'] = abs(source_gap-evaluated['gap'])
                rows.append(row)
    current_delta = 0.0
    for iteration in iterations:
        left = policies[('baseline_observer', iteration, 'current')]
        right = policies[('theta_one', iteration, 'current')]
        for side in (0, 1):
            if set(left[side]) != set(right[side]):
                raise ValueError('Different training tree')
            for key, (tokens, matrix) in left[side].items():
                if tokens != right[side][key][0]:
                    raise ValueError('Different current-policy action order')
                for a, b in zip(matrix, right[side][key][1], strict=True):
                    current_delta = max(current_delta, *(abs(x-y) for x, y in zip(a, b, strict=True)))
    final = {r['variant']: r for r in rows if r['iterations'] == 40000 and r['policy'] == 'average'}
    return {'gate_chips': CHIP_GATE, 'iterations_checked': iterations, 'rows': rows,
            'max_current_policy_difference_between_variants': current_delta,
            'final_average_nashconv': {k: r['nashconv'] for k, r in final.items()},
            'averaging_effect_observed_with_matching_current_policies':
            current_delta <= 1e-9 and final['theta_one']['nashconv'] < final['baseline_observer']['nashconv'],
            'scope': 'Controlled modified reference experiment, not a replacement baseline or production change'}


def markdown(report):
    lines = ['# TexasSolver controlled averaging experiment', '',
             'Independent evaluation of separately identified source-build policies. '
             'The unmodified release failures remain recorded separately.', '',
             '| Variant | Completed iterations | OOP average EV | Average NashConv | '
             'Current NashConv | Source/average gap delta | Average status |',
             '| --- | --- | --- | --- | --- | --- | --- |']
    rows = report['analysis']['rows']
    for row in rows:
        if row['policy'] != 'average':
            continue
        current = next(r for r in rows if r['variant'] == row['variant']
                       and r['iterations'] == row['iterations'] and r['policy'] == 'current')
        lines.append(f'| {row["variant"]} | {row["iterations"]:,} | {row["oop_ev"]:.8f} | '
                     f'{row["nashconv"]:.8f} | {current["nashconv"]:.8f} | '
                     f'{row["source_vs_independent_gap_delta"]:.8f} | {row["status"]} |')
    analysis = report['analysis']
    lines += ['', f'Unchanged convergence gate: {CHIP_GATE:.2f} chips.', '',
              'Maximum sampled current-policy difference between variants: '
              f'{analysis["max_current_policy_difference_between_variants"]:.12g}.', '',
              'Averaging effect observed with matching sampled current policies: '
              f'{analysis["averaging_effect_observed_with_matching_current_policies"]}.', '',
              'This is one fixture and one controlled change, not a general fix or reference acceptance.']
    return '\n'.join(lines)+'\n'


def run(source, prepared, build, output):
    source, prepared, build, output = map(lambda p: Path(p).resolve(), (source, prepared, build, output))
    output.mkdir(parents=True, exist_ok=False)
    execution = {'build': json.loads((prepared / 'manifest.json').read_text()),
                 'fixture': load_blocker_fixture(),
                 'platform': platform.platform(), 'compiler': subprocess.check_output(['c++', '--version'], text=True),
                 'variants': {}}
    for name, expected in execution['build']['generated_sha256'].items():
        if digest(prepared / name) != expected:
            raise ValueError('Generated build inputs changed after preparation')
    for name, expected in (execution['build']['source_sha256'] | execution['build']['header_sha256']).items():
        if digest(source / name) != expected:
            raise ValueError('Upstream build inputs changed after preparation')
    text = experiment_commands()
    for variant in ('baseline_observer', 'theta_one'):
        work = output / variant
        work.mkdir()
        (work / 'input.txt').write_text(text)
        binary = build / variant
        result = subprocess.run([str(binary), str(source / 'resources'), str(work / 'input.txt')],
                                cwd=work, capture_output=True, timeout=120, check=True)
        points = []
        for iteration in range(4000, 40001, 4000):
            prefix = work / f'checkpoint_{iteration}'
            point = json.loads(prefix.with_name(prefix.name+'_meta.json').read_text())
            for policy_type in ('average', 'current'):
                point[policy_type] = json.loads(prefix.with_name(prefix.name+'_'+policy_type+'.json').read_text())
            points.append(point)
        final = json.loads((work / 'strategy.json').read_text())
        execution['variants'][variant] = {'binary_sha256': digest(binary), 'input_commands': text,
                                          'checkpoints': points, 'post_statistics_final_policy': final,
                                          'log': (result.stdout+result.stderr).decode(errors='replace')}
    (output / 'execution.json').write_text(json.dumps(execution, indent=2)+'\n')
    report = {'execution': execution, 'analysis': analyze(execution)}
    (output / 'experiment.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    (output / 'experiment.md').write_text(markdown(report), encoding='utf-8')
    print(json.dumps(report['analysis'], indent=2))
    # Archive small selected raw checkpoints in logs too, without binaries/source.
    selected = json.loads(json.dumps(report))
    for variant in selected['execution']['variants'].values():
        variant['checkpoints'] = [p for p in variant['checkpoints'] if p['iterations'] in (4000, 40000)]
    encoded = base64.b64encode(json.dumps(selected).encode()).decode()
    for start in range(0, len(encoded), 4000):
        print('POKER_EXPERIMENT_EVIDENCE_CHUNK:'+encoded[start:start+4000])
    return report
