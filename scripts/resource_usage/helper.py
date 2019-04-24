#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import os

from typing import Dict, Union

STEADY_STATE_WINDOW_SIZE = 3


class TransactionFiles:
    """Helper functions for collecting information from transaction files."""

    _round_index = -1
    round_to_obj = {}   # type: Dict[int, Union[int, str, Dict]]

    def __init__(self, profile_dir):
        """Init TransactionFiles with profile_dir."""
        self.profile_dir = profile_dir

    def fill(self, func, init='{}'):
        """Fill class attribute round_to_obj with function 'func'.

        Attributes:
            init: Initialization obj for a round in round_to_obj.

        """
        transactions_file_pattern = re.compile(r'transactions_round\d+\.dat')
        round_index_pattern = re.compile(r'(\d+)\.dat')

        transaction_files = []
        for dirpath, _, filenames in os.walk(self.profile_dir):
            for filename in filenames:
                if transactions_file_pattern.match(filename):
                    transaction_files.append(
                        os.path.join(dirpath, filename))

        transaction_files.sort(
            key=lambda file: int(
                round_index_pattern.search(file).group(1)),
            reverse=True)

        process_rounds = set()
        for file in transaction_files:
            self._round_index = int(round_index_pattern.search(file).group(1))

            process_rounds.add(self._round_index)
            if len(process_rounds) > STEADY_STATE_WINDOW_SIZE:
                break

            if self._round_index not in self.round_to_obj:
                self.round_to_obj[self._round_index] = init

            func(file, self._round_index)

        if len(process_rounds) < STEADY_STATE_WINDOW_SIZE:
            print("Error: do not have enough transaction files for \
{} rounds in steady state!".format(STEADY_STATE_WINDOW_SIZE))
            exit(1)

    def update_obj_at_cur_round(self, obj):
        """Set obj in attribute round_to_obj for the current round."""
        self.round_to_obj[self._round_index] = obj
