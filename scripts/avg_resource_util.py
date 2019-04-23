#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import re
import os
import sys

from dateutil.parser import parse


STEADY_STATE_WINDOW_SIZE = 3

START_TIME = "start_time"
END_TIME = "end_time"
ROUND = "round"


def calc_avg_resource_util(profile_dir):
    transactions_file_pattern = re.compile(r'transactions_round\d+\.dat')
    round_index_pattern = re.compile(r'(\d+)\.dat')

    transactions_files = []
    for dirpath, _, filenames in os.walk(profile_dir):
        for filename in filenames:
            if transactions_file_pattern.match(filename):
                transactions_files.append(
                    os.path.join(dirpath, filename))

    transactions_files.sort(
        key=lambda file: int(
            round_index_pattern.search(file).group(1)),
        reverse=True)

    round_to_times = {}

    process_rounds = set()
    for file in transactions_files:
        round_index = round_index_pattern.search(file).group(1)

        process_rounds.add(round_index)
        if len(process_rounds) > STEADY_STATE_WINDOW_SIZE:
            break

        if round_index not in round_to_times:
            round_to_times[round_index] = {START_TIME: 0,
                                           END_TIME: sys.maxsize}

        raw_times = __extract_timestamps(file)
        round_to_times[round_index][START_TIME] = \
            max(round_to_times[round_index][START_TIME],
                parse(raw_times[0]).timestamp())
        round_to_times[round_index][END_TIME] = \
            min(round_to_times[round_index][END_TIME],
                parse(raw_times[-1]).timestamp())

    if len(process_rounds) < STEADY_STATE_WINDOW_SIZE:
        print("Error: do not have enough transaction files for \
{} rounds in steady state!".format(STEADY_STATE_WINDOW_SIZE))
        exit(1)

    round_to_idle = \
        __avg_resource_util_of_rounds(round_to_times)
    idles_of_rounds = round_to_idle.values()
    print("\nAverage Utilization Percentage: " +
          str(sum(idles_of_rounds) / len(idles_of_rounds)) + "\n")


def __avg_resource_util_of_rounds(round_to_times):
    time_pattern_in_stat_file = re.compile(r'\d{2}:\d{2}:\d{2} [AP]M')

    round_to_idle = {}
    for cur_round, times in round_to_times.items():
        idle_values = []
        amp = ''
        with open(STAT_LOG_FILE, 'r') as filedesc:
            for line in filedesc:
                if 'Linux' in line:
                    year_month_day = re.search(
                        r'\d{4}\-\d{2}\-\d{2}', line).group()

                if 'Average' in line:
                    print("\nError: \
Cannot find the end time from STAT_LOG_FILE")
                    exit(1)

                if LINE_KEY in line:
                    line_raw_time = \
                        time_pattern_in_stat_file.search(line).group()

                    cur_amp = line_raw_time.split()[-1]
                    if cur_amp == 'AM' and amp == 'PM':
                        year_month_day = \
                            (parse(year_month_day) +
                             datetime.timedelta(days=1)).strftime('%Y-%m-%d')
                    amp = cur_amp

                    line_timestamp = parse(
                        year_month_day + ' ' + line_raw_time).timestamp()

                    if times[START_TIME] - line_timestamp > 5:
                        continue

                    if line_timestamp - times[END_TIME] > 5:
                        break

                    idle_values.append(float(line.split()[-1]))

        round_to_idle[cur_round] = sum(idle_values) / len(idle_values)
    return round_to_idle


def __extract_timestamps(filepath):
    time_pattern_in_transaction_file = \
        re.compile(r'\d{4}\-\d{2}\-\d{2} \d{2}:\d{2}:\d{2}')

    match_strs = []
    with open(filepath, 'r') as filedesc:
        for line in filedesc:
            match_obj = time_pattern_in_transaction_file.search(line)
            if match_obj:
                match_strs.append(match_obj.group())
    return match_strs


def __print_usage():
    print("""\
Usage: {} PROFILE_DIR STAT_LOG_FILE [IF_NAME]

PROFILE_DIR
    Absolute dir that contains all transaction files from a single test
STAT_LOG_FILE
    Absolute path of file cpustat.log or netstat.log
IF_NAME:
    This is the name of network interface for which the utilization is
    measured.
    This parameter is required if the STAT_LOG_FILE is a netstat.log

----------------------------------------------------------------------
Result Explanation
----------------------------------------------------------------------
For STAT_LOG_FILE is a cpustat.log, the output is an average of
CPU idle percentage.
For STAT_LOG_FILE is a netstat.log, the output is an average of
network interface utilization (see %ifutil in sar(1)).
""".format(sys.argv[0]))
    exit(1)


if len(sys.argv) < 3:
    __print_usage()

PROFILE_BASE = sys.argv[1]
STAT_LOG_FILE = sys.argv[2]

if not os.path.isdir(PROFILE_BASE):
    print("\nError: directory {} does not exist!".format(PROFILE_BASE))
    exit(1)

if not os.path.isfile(STAT_LOG_FILE):
    print("\nError: STAT_LOG_FILE {} does not exist!".format(STAT_LOG_FILE))
    exit(1)

if STAT_LOG_FILE.endswith("cpustat.log"):
    LINE_KEY = "all"
elif STAT_LOG_FILE.endswith("netstat.log"):
    if len(sys.argv) != 4:
        __print_usage()

    LINE_KEY = sys.argv[3]
else:
    __print_usage()


calc_avg_resource_util(PROFILE_BASE)
