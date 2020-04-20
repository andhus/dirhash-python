from __future__ import print_function, division

import json
import os
import subprocess

from statistics import median, mean

from dirhash import __version__


BENCHMARK_ROOT = os.path.abspath(
    os.path.join(__file__, os.pardir)
)

TEST_CASES = {
    'flat_8_128MB': {'depth': 0, 'num_files': 2**3, 'file_size': 2**27},
    'flat_1k_1MB': {'depth': 0, 'num_files': 2**10, 'file_size': 2**20},
    'flat_32k_32kB': {'depth': 0, 'num_files': 2**15, 'file_size': 2**15},
    'nested_1k_1MB': {'depth': 8, 'num_files': 2**10, 'file_size': 2**20},
    'nested_32k_32kB': {'depth': 8, 'num_files': 2**15, 'file_size': 2**15},
}


def int_chunks(x, n):
    base = x // n
    remain = x % n
    chunks = [base] * n
    for i in range(remain):
        chunks[i] += 1

    return chunks


def write_file_tree(dirpath, depth, num_files, file_size, branch_factor=2):
    assert num_files >= branch_factor ** depth
    os.mkdir(dirpath)
    if depth == 0:
        fill = len(str(num_files))
        for i in range(num_files):
            filepath = os.path.join(dirpath, 'f_' + str(i).rjust(fill, '0'))
            with open(filepath, 'wb') as f:
                f.write(os.urandom(file_size))
    else:
        fill = len(str(branch_factor))
        for i, num_files_branch in enumerate(int_chunks(num_files, branch_factor)):
            dirpath_branch = os.path.join(dirpath, 'd_' + str(i).rjust(fill, '0'))
            write_file_tree(
                dirpath_branch,
                depth - 1,
                num_files_branch,
                file_size,
                branch_factor
            )


def require_test_cases():
    test_cases_root = os.path.join(BENCHMARK_ROOT, 'test_cases')
    if not os.path.exists(test_cases_root):
        os.mkdir(test_cases_root)
    test_case_paths = []
    for name, kwargs in TEST_CASES.items():
        test_case_path = os.path.join(test_cases_root, name)
        if not os.path.exists(test_case_path):
            print('creating test case: {}: {}'.format(name, kwargs))
            write_file_tree(test_case_path, **kwargs)
        test_case_paths.append(test_case_path)

    return test_case_paths


def time_shell(cmd, runs=1, repetitions=1, setup=None):
    time_cmd = "time for i in {{1..{rep}}}; do {cmd}; done".format(
        cmd=cmd,
        rep=repetitions
    )
    if setup is not None:
        time_cmd = "{}; {}".format(setup, time_cmd)

    realtimes = []
    for i in range(runs):
        process = subprocess.run(
            time_cmd,
            capture_output=True,
            text=True,
            shell=True,
            check=True
        )
        output_lines = process.stderr.split('\n')
        try:
            t_real, t_user, t_sys = output_lines[-4:-1]
            assert t_real.startswith('real')
            t_str = t_real.split('\t')[1]
            min_str, sec_str = t_str.split('m')
            sec = 60 * int(min_str) + float(sec_str[:-1])
            sec_per_rep = sec / repetitions
        except:
            raise RuntimeError(
                'Failed to parse `time` stderr output: {}'.format(process.stderr)
            )
        realtimes.append(sec_per_rep)

    return realtimes


def get_reference_shell_cmd(dirpath, algorithm):
    if algorithm == 'md5':
        pass
    elif algorithm.startswith('sha'):
        version = int(algorithm[3:])
        algorithm = 'shasum -a {}'.format(version)
    else:
        raise ValueError('only md5 and sha supported')

    return 'find {dir} -type f -print0 | sort -z | xargs -0 {alg} | {alg}'.format(
        dir=dirpath,
        alg=algorithm
    )


def get_dirhash_shell_cmd(dirpath, algorithm, workers=1):
    return 'dirhash {} -a {} -j {}'.format(dirpath, algorithm, workers)


def benchmark(dirpath, algorithm, **kwargs):
    test_case = os.path.basename(dirpath)
    result = []

    cmd = get_reference_shell_cmd(dirpath, algorithm)
    realtimes = time_shell(cmd=cmd, **kwargs)
    res = {
        'test_case': test_case,
        'implementation': 'shell reference',
        'algorithm': algorithm,
        'workers': 1,
        't_best': min(realtimes),
        't_median': median(realtimes),
    }
    print(res)
    print(realtimes)
    result.append(res)

    for workers in [1, 2, 4, 8]:
        cmd = get_dirhash_shell_cmd(dirpath, algorithm, workers)
        realtimes = time_shell(cmd=cmd, **kwargs)
        res = {
            'test_case': test_case,
            'implementation': 'dirhash',
            'algorithm': algorithm,
            'workers': workers,
            't_best': min(realtimes),
            't_median': median(realtimes),
        }
        print(res)
        print(realtimes)
        result.append(res)

    return result


if __name__ == '__main__':
    test_cases = require_test_cases()
    results = []
    for alg in ['md5', 'sha1']:
        for test_case in test_cases:
            result = benchmark(test_case, algorithm=alg, runs=5, repetitions=1)
            results.extend(result)

    result_fname = 'results_v{}'.format(__version__)

    with open(os.path.join(BENCHMARK_ROOT, result_fname + '.json'), 'w') as f:
        json.dump(results, f, indent=4)

    try:
        import pandas as pd
        df = pd.DataFrame(results)
        df = df[['test_case', 'implementation', 'algorithm', 'workers',
                 't_best', 't_median']]
        for (tc, alg), subdf in df.groupby(['test_case', 'algorithm']):
            t_ref = subdf[
                subdf['implementation'] == 'shell reference'
            ]['t_median'].values[0]
            speed_up = t_ref / subdf['t_median']
            df.loc[speed_up.index, 'speed-up (median)'] = speed_up
        print(df)
        df_hd = df[df['implementation'] == 'dirhash']
        df_hd_1w = df_hd[df_hd['workers'] == 1]
        df_hd_8w = df_hd[df_hd['workers'] == 8]
        mean_speedup_1w = df_hd_1w.mean()['speed-up (median)']
        mean_speedup_8w = df_hd_8w.mean()['speed-up (median)']
        print('\nAverage speedup (single process): {}'.format(mean_speedup_1w))
        print(df_hd_1w)
        print('\nAverage speedup multiprocess (8 workers): {}'.format(mean_speedup_8w))
        print(df_hd_8w)
        df.to_csv(os.path.join(BENCHMARK_ROOT, result_fname + '.csv'))
    except ImportError:
        pass
