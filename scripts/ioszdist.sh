#!/usr/bin/env bash

set -eu -o pipefail

if [ "$#" -ne 1 ]; then
    cat <<-ENDOFMESSAGE
Usage: ./ioszdist.sh TRACE_FILE

TRACE_FILE:
    The trace file is the output from 'trace-cmd report' command.


Note that the "sectors" in result are the standard UNIX 512-byte sectors,
not any device- or filesystem-specific block size. See
https://www.kernel.org/doc/Documentation/block/stat.txt
ENDOFMESSAGE
    exit
fi

declare -A buckets

event="block_rq_issue"

while IFS='' read -r line || [[ -n "$line" ]]; do
    # Prevent grep from exiting in case of nomatch
    #   https://unix.stackexchange.com/questions/330660/prevent-grep-from-exiting-in-case-of-nomatch
    sectors="$(grep -oP "$event.+\\+ \\K\\d+" <<< "$line" || :)"

    if [ -n "$sectors" ]; then
        buckets[$sectors]="$(( ${buckets[$sectors]:-0} + 1 ))"
    fi
done < "$1"


total=0
for sec in "${!buckets[@]}"; do
    (( total += ${buckets[$sec]} ))
done

printf '\n%-13s%-11s%s\n' SECTORS COUNT RATIO
for _ in $(seq 45); do
    printf '-'
done
echo

for sec in "${!buckets[@]}"; do
    printf '%-5d   ->   %-11d%.3f%%\n' "$sec" "${buckets[$sec]}" "$(echo "${buckets[$sec]}" / "$total * 100" | bc -l)"
done |
sort -rn -k3
