#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys

from helper import TransactionFiles


def __calc_avg_device_throughput(profile_dir):
    transaction_files = TransactionFiles(profile_dir)

    def __do_update(file, round_index):
        runtime = __extract_runtime_in_seconds(file)
        device_stats_before_file = os.path.join(
            os.path.dirname(file),
            "device_stats_round" + str(round_index) + "_b.log")
        comps_before = __read_device_stats_file(device_stats_before_file)

        device_stats_after_file = os.path.join(
            os.path.dirname(file),
            "device_stats_round" + str(round_index) + "_a.log")
        comps_after = __read_device_stats_file(device_stats_after_file)

        # data_size = sectors written + sectors read
        # see https://www.kernel.org/doc/Documentation/ABI/testing/procfs-diskstats
        data_size = (comps_after[9] - comps_before[9]) + \
            (comps_after[5] - comps_before[5])

        # throughput in MB/s
        throughput = data_size / 2 / 1024 / runtime

        transaction_files.update_obj_at_cur_round(
            throughput + transaction_files.round_to_obj[round_index])

    transaction_files.fill(__do_update, 0)

    device_throughputs = transaction_files.round_to_obj.values()
    avg_throughput = sum(device_throughputs) / len(device_throughputs)
    print("\nAverage Device Throughput is {:.2f} MB/s\n".format(
        avg_throughput))


def __read_device_stats_file(file):
    with open(file, 'r') as filedesc:
        comps = filedesc.read().split()
    return [int(v) if v.isdigit() else v for v in comps]


def __extract_runtime_in_seconds(file):
    with open(file, 'r') as filedesc:
        for line in filedesc:
            if 'RunTime(ms)' in line:
                return int(line.split()[2]) / 1000

    raise EOFError("Can not found runtime value from {}".format(file))


def __print_usage():
    print("""\
Usage: {} PROFILE_DIR

PROFILE_DIR
    Absolute dir that contains all transaction files from a single test
""".format(sys.argv[0]))
    exit(1)


if len(sys.argv) != 2:
    __print_usage()

PROFILE_DIR = sys.argv[1]

if not os.path.isdir(PROFILE_DIR):
    print("\nError: directory {} does not exist!".format(PROFILE_DIR))
    exit(1)

__calc_avg_device_throughput(PROFILE_DIR)
