#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import re
import os
import sys

from dateutil.parser import parse

LATEST_START_TIME = "latest_start_time"
EARLIEST_END_TIME = "earliest_end_time"

CPUSTAT_LOG_FILENAME = "cpustat.log"
NUM_DRIVES_DIRNAME_PATTERN = "_drives"


def calc_avg_cpu_util(base):
    _, base_dirnames, base_filenames = next(os.walk(base))

    if __list_transactions_files(base_filenames):
        # we are directly in the drive profiles folder (e.g., sdX)
        raw_times = __times_info_of_single_drive(base, base_filenames)
        round_to_times = \
            __calc_time_scope_of_rounds([raw_times])
        cpustat_log_file = os.path.join(base, CPUSTAT_LOG_FILENAME)
        print(base)
        __print_idle_percentage(round_to_times, cpustat_log_file)
    elif any(NUM_DRIVES_DIRNAME_PATTERN in dirname
             for dirname in base_dirnames):
        __calc_avg_cpu_util_multi_drives(base, base_dirnames)
    else:
        print("Error: folder \"{}\" does not either contains transactionsi \
files or X_drives directory.\n".format(base))
        exit(1)


def __calc_avg_cpu_util_multi_drives(base, dirnames):
    for dirname in dirnames:
        if NUM_DRIVES_DIRNAME_PATTERN not in dirname:
            continue

        path_to_raw_times = {}

        num_drives_path = os.path.join(base, dirname)
        for dirpath, _, filenames in os.walk(num_drives_path):
            if dirpath.endswith(dirname):
                continue

            # dirpath: one of sdX folders
            random_drive_path = dirpath

            path_to_raw_times[dirpath] = \
                __times_info_of_single_drive(dirpath, filenames)

        round_to_times = \
            __calc_time_scope_of_rounds(path_to_raw_times.values())

        # For Debug
        # from datetime import datetime
        # round_to_times_readable = {}
        # for key, value in round_to_times.items():
        #     latest_start_time = datetime.utcfromtimestamp(
        #         value[LATEST_START_TIME]).strftime('%Y-%m-%d %H:%M:%S')
        #     earliest_end_time = datetime.utcfromtimestamp(
        #         value[EARLIEST_END_TIME]).strftime('%Y-%m-%d %H:%M:%S')

        #     round_to_times_readable[key] = \
        #         {LATEST_START_TIME: latest_start_time,
        #          EARLIEST_END_TIME: earliest_end_time}

        cpustat_log_file = os.path.join(
            random_drive_path, CPUSTAT_LOG_FILENAME)
        print(dirname)
        __print_idle_percentage(round_to_times, cpustat_log_file)


def __print_idle_percentage(round_to_times, cpustat_log_file):
    round_to_idle = __avg_cpu_util_of_rounds(
        round_to_times, cpustat_log_file)
    idles_of_rounds = round_to_idle.values()
    print("idle percentage: " +
          str(sum(idles_of_rounds) / len(idles_of_rounds)) + "\n")


STEADY_STATE_WINDOW_SIZE = 3

START_TIMES = "start_times"
END_TIMES = "end_times"
STEADY_STATE_ROUND = "steady_state_round"


def __calc_time_scope_of_rounds(raw_times_of_drives):
    round_to_times = {}
    for index in range(STEADY_STATE_WINDOW_SIZE):
        for value in raw_times_of_drives:
            cur_round = value[STEADY_STATE_ROUND] + index
            if cur_round not in round_to_times:
                round_to_times[cur_round] = \
                    {LATEST_START_TIME: 0,
                     EARLIEST_END_TIME: sys.maxsize}

            round_to_times[cur_round][LATEST_START_TIME] = \
                max(round_to_times[cur_round][LATEST_START_TIME],
                    parse(value[START_TIMES][index]).timestamp())
            round_to_times[cur_round][EARLIEST_END_TIME] = \
                min(round_to_times[cur_round][EARLIEST_END_TIME],
                    parse(value[END_TIMES][index]).timestamp())

    return round_to_times


TRANSACTIONS_FILE_PATTERN = re.compile(r'transactions_round\d+\.dat')


def __list_transactions_files(filenames):
    return [f for f in filenames if
            TRANSACTIONS_FILE_PATTERN.search(f)]


def __times_info_of_single_drive(dirpath, filenames):
    transactions_files = __list_transactions_files(filenames)

    transactions_files.sort(
        key=lambda path: re.findall(r'(\d+)\.dat', path)[-1])
    transactions_files_in_steady_state = \
        transactions_files[-1 * STEADY_STATE_WINDOW_SIZE:]

    total_rounds = len(transactions_files)
    if total_rounds < STEADY_STATE_WINDOW_SIZE:
        print("folder {} does not contain {} transactions files!"
              .format(dirpath, STEADY_STATE_WINDOW_SIZE))
        exit(1)

    steady_state_round = \
        total_rounds - STEADY_STATE_WINDOW_SIZE + 1

    start_times = []
    end_times = []

    for filename in transactions_files_in_steady_state:
        filepath = os.path.join(dirpath, filename)
        match_strs = __extract_timestamps(filepath)

        start_times.append(match_strs[0])
        end_times.append(match_strs[-1])

    return {START_TIMES: start_times,
            END_TIMES: end_times,
            STEADY_STATE_ROUND: steady_state_round}


TIME_PATTERN_IN_CPUSTAT = re.compile(r'\d{2}:\d{2}:\d{2} [AP]M')


def __avg_cpu_util_of_rounds(round_to_times, cpustat_log_file):
    round_to_idle = {}
    for key, value in round_to_times.items():
        idle_values = []
        amp = ''
        with open(cpustat_log_file, 'r') as filedesc:
            for line in filedesc:
                if 'Linux' in line:
                    year_month_day = re.search(
                        r'\d{4}\-\d{2}\-\d{2}', line).group()
                if 'all' in line:
                    line_raw_time = \
                        TIME_PATTERN_IN_CPUSTAT.search(line).group()

                    cur_amp = line_raw_time.split()[-1]
                    if cur_amp == 'AM' and amp == 'PM':
                        year_month_day = \
                            (parse(year_month_day) +
                             datetime.timedelta(days=1)).strftime('%Y-%m-%d')
                    amp = cur_amp

                    line_timestamp = parse(
                        year_month_day + ' ' + line_raw_time).timestamp()

                    if value[LATEST_START_TIME] - line_timestamp > 5:
                        continue

                    if line_timestamp - value[EARLIEST_END_TIME] > 5:
                        break

                    idle_values.append(float(line.split()[-1]))

        round_to_idle[key] = sum(idle_values) / len(idle_values)
    return round_to_idle


TIME_PATTERN = re.compile(r'\d{4}\-\d{2}\-\d{2} \d{2}:\d{2}:\d{2}')


def __extract_timestamps(filepath):
    match_strs = []
    with open(filepath, 'r') as filedesc:
        for line in filedesc:
            match_obj = TIME_PATTERN.search(line)
            if match_obj:
                match_strs.append(match_obj.group())
    return match_strs


def __print_usage():
    print("""\
Usage: {} BASEDIR

BASEDIR     path that contains profiles from drives under test.
            There could be two type of dirs:
            1) dir that contains a list of X_drives,
            e.g., /home/ljishen/ycsb-rocksdb/analysis/data/ycsb/workloada/hp/general_mbwus/75%seqfill/32_threads
            2) dir that directly contains transactions profiles,
            e.g., /home/ljishen/ycsb-rocksdb/analysis/data/ycsb/workloada/hp/general_mbwus/75%seqfill/32_threads/2_drives/sda

""".format(sys.argv[0]))


if len(sys.argv) != 2:
    __print_usage()
    exit(1)

# This is the path that contains folders 1_drives, 2_drives, etc.
PROFILE_BASE = sys.argv[1]

if not os.path.isdir(PROFILE_BASE):
    print("{} is not an existing directory!".format(PROFILE_BASE))
    exit(1)

calc_avg_cpu_util(PROFILE_BASE)
