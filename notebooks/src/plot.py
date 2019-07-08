import glob
import json
import re
import sys

import os
from os.path import basename

import numpy as np

from dateutil.parser import parse
from IPython.display import display, Math

import matplotlib.pyplot as plt
from matplotlib.ticker import AutoMinorLocator
from matplotlib.ticker import MaxNLocator

_SUFFIX = 'suf'
_VALUES = 'vals'

_BEFORE = 'before'
_AFTER = 'after'

SECTOR_SIZE_KB = 0.5


def __get_stats_diffs(file_prefix):
    stat2vals = {
        _BEFORE: {_SUFFIX: '_b.log', _VALUES: []},
        _AFTER:  {_SUFFIX: '_a.log', _VALUES: []}
    }

    for key, kv in stat2vals.items():
        with open(file_prefix + kv[_SUFFIX], 'r') as fh:
            content = fh.readlines()[-1]
            comps = content.split()
            for i in range(3, len(comps)):
                stat2vals[key][_VALUES].append(int(comps[i]))

    diffs = []
    for i in range(len(stat2vals[_BEFORE][_VALUES])):
        diffs.append(
            stat2vals[_AFTER][_VALUES][i] - stat2vals[_BEFORE][_VALUES][i])
    return diffs


def __get_runtime_sec_and_throughput(trans_file):
    with open(trans_file, 'r') as fh:
        runtime = 0
        throughput = 0
        for line in fh:
            if 'RunTime' in line:
                # the `Runtime` value is in ms
                runtime = int(re.split(', *', line)[2]) / 1000
            elif 'Throughput(ops/sec)' in line:
                throughput = float(re.split(', *', line)[2])
                break

    return runtime, throughput


def __get_stats(dir, round):
    device_stats_file_prefix = dir + '/device_stats_round' + str(round)
    transactions_file = dir + '/transactions_round' + str(round) + '.dat'

    runtime, ycsb_tps = __get_runtime_sec_and_throughput(transactions_file)
    diffs = __get_stats_diffs(device_stats_file_prefix)

    # device IOPS, device MB/s, YCSB ops/sec
    return (diffs[0] + diffs[4]) / runtime, \
        (diffs[2] + diffs[6]) * SECTOR_SIZE_KB / 1024 / runtime, \
        ycsb_tps


MEASUREMENT_WINDOW_SIZE = 3


def __get_rounds_in_ss_window(dir):
    profiles = glob.glob(dir + '/transactions_round[0-9]*.dat')

    if len(profiles) < MEASUREMENT_WINDOW_SIZE:
        raise RuntimeError(
            'Not enough transaction profiles in ' + dir)

    rounds = []
    for profile in profiles:
        rounds.append(int(re.search(r'round(\d+)', profile).group(1)))

    return sorted(rounds)[-MEASUREMENT_WINDOW_SIZE:]


def __get_threadcount(dir):
    return int(basename(dir).split('_')[0])


_DEVICE_IOPS = 'device_iops'
_DEVICE_THROUGHPUT = 'device_throughput'
_YCSB_TPS = 'ycsb_ops_per_sec'
_ROCKSDB_THROUGHPUT = 'rocksdb_throughput'

_MEAN = 'mean'
_STD = 'std'

_KEY_SIZE_BYTES = 16
_VALUE_SIZE_BYTES = 4 * 1024

_OUTPUT_FIGURES_BASE = 'figures/'


def __get_avg_throughputs(dir):
    rounds = __get_rounds_in_ss_window(dir)

    device_iopses = []
    device_throughputs = []
    ycsb_tpses = []
    rocksdb_throughputs = []

    for r in rounds:
        device_iops, device_throughput, ycsb_tps = __get_stats(dir, r)
        device_iopses.append(device_iops)
        device_throughputs.append(device_throughput)
        ycsb_tpses.append(ycsb_tps)
        rocksdb_throughputs.append(
            ycsb_tps * (_KEY_SIZE_BYTES + _VALUE_SIZE_BYTES) / 1024 / 1024)

    return {
                _DEVICE_IOPS: {
                    _MEAN: np.mean(device_iopses),
                    _STD:  np.std(device_iopses, ddof=1)
                },
                _DEVICE_THROUGHPUT: {
                    _MEAN: np.mean(device_throughputs),
                    _STD:  np.std(device_throughputs, ddof=1)
                },
                _YCSB_TPS: {
                    _MEAN: np.mean(ycsb_tpses),
                    _STD:  np.std(ycsb_tpses, ddof=1)
                },
                _ROCKSDB_THROUGHPUT: {
                    _MEAN: np.mean(rocksdb_throughputs),
                    _STD:  np.std(rocksdb_throughputs, ddof=1)
                }
    }


PROFILES_BASE = '../data/ycsb'


def __list_subfolders(folder, pattern):
    path = os.path.join(PROFILES_BASE, folder)
    files = []
    for file in os.listdir(path):
        if re.match(pattern, file):
            files.append(os.path.join(path, file))
    return files


def __do_plot(ax, throughput_type, text_pos, color, fmt, tcs, ths):
    means = [v[throughput_type][_MEAN] for v in ths]
    bar = ax.errorbar(tcs, means,
                      yerr=[v[throughput_type][_STD] for v in ths],
                      fmt=fmt, color=color)
    for idx, tc in enumerate(tcs):
        ax.text(tc, means[idx] * (1 + text_pos * 0.07), '%.1f' % means[idx],
                ha='center', size=6, color=color)
    return bar


def plot_throughputs(folder):
    plt.rc('xtick', labelsize=10)
    plt.rc('ytick', labelsize=10)

    fig, ax = plt.subplots()
    ax.grid(which='major', alpha=0.5)
    fig.set_dpi(150)

    tc2th = {}
    subfolders = __list_subfolders(folder, r'^\d+_threads$')
    for subf in subfolders:
        throughputs = __get_avg_throughputs(subf)
        threadcount = __get_threadcount(subf)
        tc2th[threadcount] = throughputs

    tcs = sorted(tc2th.keys())
    ths = []
    for tc in tcs:
        ths.append(tc2th[tc])

    max_key = max(tc2th.keys(), key=(lambda tc: tc2th[tc][_YCSB_TPS][_MEAN]))
    print('Info of the max YCSB throughput: ' +
          str(max_key) + ' threads -> ' +
          str(tc2th[max_key]))

    bars = []

    color = 'b'
    ax.set_ylabel('ops/sec', color=color)
    ax.tick_params('y', colors=color)

    bars.append(__do_plot(ax, _YCSB_TPS, -1, color, '-.x', tcs, ths))

    ax.set_ylim(0)

    ax_t = ax.twinx()

    color = 'r'
    ax_t.set_ylabel('MB/s', color=color)
    ax_t.tick_params('y', colors=color)

    bars.append(
        __do_plot(ax_t, _DEVICE_THROUGHPUT, 1, color, '-x', tcs, ths))

    bars.append(
        __do_plot(ax_t, _ROCKSDB_THROUGHPUT, 1, color, '--|', tcs, ths))

    ax_t.set_ylim(0)

    ax.set_xlabel('number of threads')

    plt.xticks(tcs)
    plt.title('Summary of Throughputs\n(%s)' % folder, y=1.12)

    plt.legend(
        bars, ['YCSB ops/sec', 'device throughput', 'RocksDB throughput'],
        loc=8,
        bbox_to_anchor=(0.5, 1.02),
        ncol=3,
        frameon=False,
        prop={'size': 8})

    plt.savefig(
        _OUTPUT_FIGURES_BASE + folder.replace('/', '_'), bbox_inches='tight')


def compare_general_mbwus_of_threads(folder, nr_drives):
    subfolders = __list_subfolders(folder, r'^\d+_threads$')
    subfolders.sort(key=lambda path: re.findall(r'/(\d+)_', path)[-1])

    total_ops_of_threads = {}

    # nr_threads_folder: x_threads
    for nr_threads_folder in subfolders:
        nr_drives_folder = os.path.join(
            nr_threads_folder, str(nr_drives) + '_drives')
        folder_of_drive = next(os.walk(nr_drives_folder))[1]

        total_ops_of_cur_thread = 0

        # drive: sdx
        for drive in folder_of_drive:
            realpath = os.path.join(nr_drives_folder, drive)
            rounds = __get_rounds_in_ss_window(realpath)

            total_ops_of_cur_drive = 0
            for r in rounds:
                device_iops, device_throughput, ycsb_tps = \
                    __get_stats(realpath, r)
                total_ops_of_cur_drive = ycsb_tps + total_ops_of_cur_drive

            total_ops_of_cur_thread = \
                total_ops_of_cur_thread + total_ops_of_cur_drive / len(rounds)

        nr_threads = int(re.findall(r'/(\d+)_', nr_threads_folder)[-1])
        total_ops_of_threads[nr_threads] = total_ops_of_cur_thread

    fig, ax = plt.subplots()
    fig.set_dpi(150)
    ax.yaxis.grid(which='major', alpha=0.5)
    ax.yaxis.grid(which='minor', alpha=0.2)

    width = 0.2
    ax.bar(total_ops_of_threads.keys(),
           total_ops_of_threads.values(),
           width, color='m')
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))

    # plot value on top of bar
    for nr_threads, total_ops in total_ops_of_threads.items():
        ax.text(nr_threads, total_ops * 1.02,
                '%.1f' % total_ops,
                ha='center', size=9, color='m')

    ax.set_ylim(0)

    ax.set_ylabel('ops/sec')
    ax.set_xlabel('number of threads')
    ax.set_title('Compare throughputs using {:d} drives'.format(nr_drives),
                 y=1.05)

    ax.yaxis.set_minor_locator(AutoMinorLocator(5))

    plt.show()


__timestamp_pattern_in_transactions_log = \
    re.compile(r'\d{4}\-\d{2}-\d{2} \d{2}:\d{2}:\d{2}')


def plot_general_mbwus(folder):
    # subfolders: [x_drives]
    subfolders = __list_subfolders(folder, r'^\d+_drives$')

    subfolders.sort(key=lambda path: re.findall(r'/(\d+)_', path)[-1])

    nr_drives = []
    agg_ops_sec = []
    agg_mb_s = []

    transactions_start_times = {}
    transactions_end_times = {}

    # nr_drives_folder: x_drives
    for nr_drives_folder in subfolders:
        res_folder_of_drive = glob.glob(
            nr_drives_folder + '/**/sd[a-z]*' + os.sep, recursive=True)
        res_folder_of_drive = [res_folder for res_folder in res_folder_of_drive
                               if not res_folder.startswith(
                                   nr_drives_folder + '/storage-')]

        ops_sec = {}
        mb_s = {}

        cur_nr_drives = len(res_folder_of_drive)

        # realpath: folder that end with 'sdx'
        for realpath in res_folder_of_drive:
            rounds = __get_rounds_in_ss_window(realpath)
            for r in rounds:
                device_iops, device_throughput, ycsb_tps = \
                    __get_stats(realpath, r)
                ops_sec[r] = ycsb_tps + ops_sec.get(r, 0)
                mb_s[r] = device_throughput + mb_s.get(r, 0)

                transactions_log_file = os.path.join(
                    realpath, 'transactions_round' + str(r) + '.dat')

                with open(transactions_log_file, 'r') as fobj:
                    file_str = fobj.read()
                    ts_strs = re.findall(
                        __timestamp_pattern_in_transactions_log, file_str)

                    if cur_nr_drives not in transactions_start_times:
                        transactions_start_times[cur_nr_drives] = {}
                    transactions_start_times[cur_nr_drives][r] = \
                        max(transactions_start_times[cur_nr_drives].get(r, 0),
                            parse(ts_strs[0]).timestamp())

                    if cur_nr_drives not in transactions_end_times:
                        transactions_end_times[cur_nr_drives] = {}
                    transactions_end_times[cur_nr_drives][r] = \
                        min(transactions_end_times[cur_nr_drives].get(
                            r, sys.maxsize),
                            parse(ts_strs[-1]).timestamp())

        nr_drives.append(cur_nr_drives)
        agg_ops_sec.append(list(ops_sec.values()))
        agg_mb_s.append(list(mb_s.values()))

        phase_load_file = __get_phase_load_file(nr_drives_folder)
        if os.path.isfile(phase_load_file):
            median_idx = int(np.ceil(
                np.median(
                    sorted(transactions_start_times[cur_nr_drives].keys()))))
            __plot_power_consumption_time_series(
                phase_load_file,
                transactions_start_times[cur_nr_drives][median_idx],
                transactions_end_times[cur_nr_drives][median_idx],
                cur_nr_drives,
                median_idx,
                folder)

    __plot_power_consumption(
        subfolders,
        transactions_start_times,
        transactions_end_times,
        folder)

    figure_name_prefix = folder.replace('/', '_')

    __plot_general_throughputs(nr_drives,
                               agg_ops_sec,
                               'b',
                               'ops/sec',
                               'Aggregated YCSB Throughput\n(%s)' % folder,
                               figure_name_prefix + '_ycsb_throughput')

    __plot_general_throughputs(nr_drives,
                               agg_mb_s,
                               'r',
                               'MB/s',
                               'Aggregated Device Throughput\n(%s)' % folder,
                               figure_name_prefix + '_device_throughput')


def __get_phase_load_file(base):
    return os.path.join(base, 'phase_load.log')


def __plot_general_throughputs(nr_drives,
                               values,
                               color,
                               ytitle,
                               title,
                               output_figure_name):
    fig, ax = plt.subplots()
    fig.set_dpi(150)
    ax.yaxis.grid(which='major', alpha=0.5)
    ax.yaxis.grid(which='minor', alpha=0.2)

    means = [np.mean(vl) for vl in values]
    stds = [np.std(vl, ddof=1) for vl in values]

    width = 0.2
    ax.bar(nr_drives, means, width, yerr=stds, color=color, label='raw value')

    # plot value on top of bar
    text_pos_incr = min(means) * 0.2
    for idx, nd in enumerate(nr_drives):
        ax.text(nd, means[idx] + text_pos_incr,
                '%.1f' % means[idx],
                ha='center', size=9, color='r')

    # calculate polynomial
    poly_degree = 2
    coeffs = np.polyfit(nr_drives, means, poly_degree)

    display(Math(r'throughput(n) = {:.3f}n^2 {} {:.3f}n {} {:.3f}'.format(
        coeffs[0],
        '+' if coeffs[1] > 0 else '', coeffs[1],
        '+' if coeffs[2] > 0 else '', coeffs[2])))
    print('where throughput(n) is in the unit of {}, \
and n is the number of drives\n'.format(ytitle))

    poly = np.poly1d(coeffs)

    poly_x = np.linspace(nr_drives[0], nr_drives[-1], 200 * len(nr_drives))
    poly_y = poly(poly_x)

    # plot the polynomial fit
    ax.plot(poly_x,
            poly_y,
            color='lightgreen',
            label='least squares fit (deg = {:d})'.format(poly_degree))
    ax.plot(nr_drives, poly(nr_drives), 'o', color='lightgreen')

    ax.set_ylim(0)

    ax.set_ylabel(ytitle)
    ax.set_xlabel('number of drives')
    ax.set_title(title, y=1.12)

    ax.yaxis.set_minor_locator(AutoMinorLocator(5))

    plt.legend(loc=8,
               bbox_to_anchor=(0.5, 1.02),
               ncol=2,
               frameon=False,
               prop={'size': 9})

    plt.savefig(_OUTPUT_FIGURES_BASE + output_figure_name, bbox_inches='tight')


__load_line_pattern = \
    re.compile(r'\[(\d{4}\-\d{2}-\d{2}\w+\d{2}:\d{2}:\d{2}).+\] (.+)')


def __extract_time_and_load_from(line):
    m = __load_line_pattern.match(line)
    if not m:
        return None

    load_str = m.group(2)
    if load_str.startswith('{'):
        load = float(
            json.loads(load_str)['emeter']['get_realtime']['power']) / 120
    else:
        load = float(load_str)

    # time in seconds, load in amperes
    return parse(m.group(1)).timestamp(), load


def __extract_loads_of_transactions(load_file,
                                    transactions_start_in_secs,
                                    transactions_end_in_secs):
    times = []
    loads = []

    with open(load_file, 'r') as fh:
        for line in fh:
            res = __extract_time_and_load_from(line)
            if res:
                time, load = res[0], res[1]
                if time > transactions_end_in_secs:
                    break
                if time > transactions_start_in_secs:
                    times.append(time)
                    loads.append(load)

    # normalize the time in seconds so that the first time in the array is 0
    time_base = times[0]
    for idx in range(len(times)):
        times[idx] -= time_base

    return times, loads


def __plot_power_consumption_time_series(load_file,
                                         transactions_start_in_secs,
                                         transactions_end_in_secs,
                                         nr_drives,
                                         round_idx,
                                         title_note):
    times, loads = __extract_loads_of_transactions(load_file,
                                                   transactions_start_in_secs,
                                                   transactions_end_in_secs)

    __do_plot_power_consumption_time_series(times,
                                            loads,
                                            nr_drives,
                                            round_idx,
                                            title_note)


def __do_plot_power_consumption_time_series(times,
                                            loads,
                                            nr_drives,
                                            round_idx,
                                            title_note):
    # we finally can start to plot the load now!
    fig, ax = plt.subplots()
    fig.set_dpi(150)

    line = ax.plot(times, loads, color='g')
    plt.setp(line, linewidth=0.5)

    ax.set_ylim(0)
    ax.set_ylabel('current (amperes)')
    ax.set_xlabel('seconds')
    ax.set_title(
        'Power Consumption Time Series\n[%d drives, \
round %d, average load: %.2f amperes]\n(%s)' %
        (nr_drives, round_idx, np.mean(loads), title_note))

    plt.show()


def __plot_power_consumption(subfolders,
                             transactions_start_times,
                             transactions_end_times,
                             title_note):
    nr_drives = []
    loads_of_nr_drives = []

    # subfolders: [x_drives]
    for nr_drives_folder in subfolders:
        phase_load_file = __get_phase_load_file(nr_drives_folder)
        if os.path.isfile(phase_load_file):
            cur_nr_drives = int(re.search("(\\d+)_drives$",
                                          nr_drives_folder).group(1))
            nr_drives.append(cur_nr_drives)

            means_of_loads = []
            for rd in transactions_start_times[cur_nr_drives].keys():
                _, loads = __extract_loads_of_transactions(
                    phase_load_file,
                    transactions_start_times[cur_nr_drives][rd],
                    transactions_end_times[cur_nr_drives][rd])
                means_of_loads.append(np.mean(loads))

            loads_of_nr_drives.append(means_of_loads)

    fig, ax = plt.subplots()
    fig.set_dpi(150)
    ax.yaxis.grid(which='major', alpha=0.5)
    ax.yaxis.grid(which='minor', alpha=0.2)

    means = [np.mean(loads) for loads in loads_of_nr_drives]
    stds = [np.std(loads, ddof=1) for loads in loads_of_nr_drives]

    width = 0.2
    ax.bar(nr_drives, means, width, yerr=stds, color='g', label='average load')

    # plot value on top of bar
    text_pos_incr = max(means) * 0.03
    for idx, nd in enumerate(nr_drives):
        ax.text(nd, means[idx] + text_pos_incr,
                '%.2f' % means[idx],
                ha='center', size=9, color='r')

    # calculate polynomial
    poly_degree = 2
    coeffs = np.polyfit(nr_drives, means, poly_degree)

    display(Math(r'power(n) = {:.3f}n^2 {} {:.3f}n {} {:.3f}'.format(
        coeffs[0],
        '+' if coeffs[1] > 0 else '', coeffs[1],
        '+' if coeffs[2] > 0 else '', coeffs[2])))
    print('where n is the number of drives\n')

    poly = np.poly1d(coeffs)

    poly_x = np.linspace(nr_drives[0], nr_drives[-1], 200 * len(nr_drives))
    poly_y = poly(poly_x)

    # plot the polynomial fit
    ax.plot(poly_x,
            poly_y,
            color='orange',
            label='least squares fit (deg = {:d})'.format(poly_degree))
    ax.plot(nr_drives, poly(nr_drives), 'o', color='orange')

    ax.set_ylim(0)

    ax.set_ylabel('current (amperes)')
    ax.set_xlabel('number of drives')
    ax.set_title('Summary of Power Consumption\n(%s)' % title_note, y=1.12)

    ax.yaxis.set_minor_locator(AutoMinorLocator(5))

    plt.legend(loc=8,
               bbox_to_anchor=(0.5, 1.02),
               ncol=2,
               frameon=False,
               prop={'size': 9})

    output_figure_name = title_note.replace('/', '_') + '_power_consumption'
    plt.savefig(_OUTPUT_FIGURES_BASE + output_figure_name, bbox_inches='tight')


def plot_power_consumption_time_series_rockpro64(folder):
    path_prefix = os.path.join(PROFILES_BASE, folder)
    load_file = os.path.join(path_prefix, 'energy.log')

    rounds = __get_rounds_in_ss_window(path_prefix)
    means_of_loads = []
    for r in rounds:
        transactions_log_file = os.path.join(
            path_prefix, 'transactions_round' + str(r) + '.dat')
        with open(transactions_log_file, 'r') as fh:
            file_str = fh.read()
            ts_strs = re.findall(
                __timestamp_pattern_in_transactions_log, file_str)
        transactions_start_in_secs = parse(ts_strs[0]).timestamp()
        transactions_end_in_secs = parse(ts_strs[-1]).timestamp()

        times, loads = __extract_loads_of_transactions(
            load_file,
            transactions_start_in_secs,
            transactions_end_in_secs)
        means_of_loads.append(np.mean(loads))

        if r == int(np.ceil(np.median(rounds))):
            __do_plot_power_consumption_time_series(times,
                                                    loads,
                                                    1,
                                                    r,
                                                    folder)

    print('Average Load of all ' +
          str(len(rounds)) +
          ' rounds is: ' +
          str(np.mean(means_of_loads)) +
          ' amperes')
