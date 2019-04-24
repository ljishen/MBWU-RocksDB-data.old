#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import re
import os
import sys

from enum import Enum
from dateutil.parser import parse
from helper import TransactionFiles

START_TIME = "start_time"
END_TIME = "end_time"


def __calc_avg_resource_util(profile_dir):
    transaction_files = TransactionFiles(profile_dir)

    def __do_update(file, round_index):
        obj_at_cur_round = transaction_files.round_to_obj[round_index]
        raw_times = __extract_timestamps(file)
        start_time = max(obj_at_cur_round[START_TIME],
                         parse(raw_times[0]).timestamp())
        end_time = min(obj_at_cur_round[END_TIME],
                       parse(raw_times[-1]).timestamp())

        transaction_files.update_obj_at_cur_round(
            {START_TIME: start_time,
             END_TIME: end_time})

    transaction_files.fill(__do_update, {START_TIME: 0,
                                         END_TIME: sys.maxsize})

    round_to_util = \
        __avg_resource_util_of_rounds(transaction_files.round_to_obj)
    utils_of_rounds = round_to_util.values()
    print("\nAverage Resource Utilization: {}\n".format(
        sum(utils_of_rounds) / len(utils_of_rounds)))


def __collect_cpu_net_values(times, filedesc, time_pattern):
    res_values = []
    amp = ''
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
                time_pattern.search(line).group()

            cur_amp = line_raw_time.split()[-1]
            if cur_amp == 'AM' and amp == 'PM':
                year_month_day = \
                    (parse(year_month_day) +
                     datetime.timedelta(days=1)).strftime('%Y-%m-%d')
            amp = cur_amp

            line_timestamp = parse(
                year_month_day + ' ' + line_raw_time).timestamp()

            if times[START_TIME] > line_timestamp:
                continue

            if line_timestamp > times[END_TIME]:
                break

            res_values.append(float(line.split()[-1]))

    return res_values


def __collect_mem_values(times, filedesc, time_pattern):
    res_values = []
    is_break = False
    for line in filedesc:
        match_obj = time_pattern.search(line)
        if match_obj:
            line_timestamp = parse(match_obj.group()).timestamp()

            if times[START_TIME] - line_timestamp > 5:
                continue

            if line_timestamp - times[END_TIME] > 5:
                is_break = True
                break

            comps = line.split()
            # system available memory is free + buff + cache
            res_values.append(int(comps[3]) + int(comps[4]) + int(comps[5]))

    if not is_break:
        print("\nError: \
Cannot find the end time from STAT_LOG_FILE")
        exit(1)

    return res_values


def __avg_resource_util_of_rounds(round_to_times):
    round_to_util = {}
    for cur_round, times in round_to_times.items():
        with open(STAT_LOG_FILE, 'r') as filedesc:
            if LOG_TYPE == _LogType.MEMORY:
                res_values = __collect_mem_values(
                    times, filedesc,
                    re.compile(r'\d{4}\-\d{2}\-\d{2} \d{2}:\d{2}:\d{2}'))
            else:
                res_values = __collect_cpu_net_values(
                    times, filedesc,
                    re.compile(r'\d{2}:\d{2}:\d{2} [AP]M'))

        round_to_util[cur_round] = sum(res_values) / len(res_values)
    return round_to_util


def __extract_timestamps(file):
    time_pattern_in_transaction_file = \
        re.compile(r'\d{4}\-\d{2}\-\d{2} \d{2}:\d{2}:\d{2}')

    match_strs = []
    with open(file, 'r') as filedesc:
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
    Absolute path of file cpustat.log, memstat.log, or netstat.log
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
For STAT_LOG_FILE is a memstat.log, the output is available system
memory in KB.
""".format(sys.argv[0]))
    exit(1)


if len(sys.argv) < 3:
    __print_usage()

PROFILE_DIR = sys.argv[1]
STAT_LOG_FILE = sys.argv[2]

if not os.path.isdir(PROFILE_DIR):
    print("\nError: directory {} does not exist!".format(PROFILE_DIR))
    exit(1)

if not os.path.isfile(STAT_LOG_FILE):
    print("\nError: STAT_LOG_FILE {} does not exist!".format(STAT_LOG_FILE))
    exit(1)


class _LogType(Enum):
    CPU = 1
    NETWORK = 2
    MEMORY = 3


if STAT_LOG_FILE.endswith("cpustat.log"):
    LOG_TYPE = _LogType.CPU
    LINE_KEY = "all"
elif STAT_LOG_FILE.endswith("memstat.log"):
    LOG_TYPE = _LogType.MEMORY
elif STAT_LOG_FILE.endswith("netstat.log"):
    if len(sys.argv) != 4:
        __print_usage()

    LOG_TYPE = _LogType.NETWORK
    LINE_KEY = sys.argv[3]
else:
    __print_usage()

__calc_avg_resource_util(PROFILE_DIR)
