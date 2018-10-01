#!/usr/bin/env bash

set -eu -o pipefail

if [ "$#" -ne 1 ]; then
    cat <<-ENDOFMESSAGE
Usage: ./ioszdist.sh TRACE_FILE

TRACE_FILE:
    The trace file is the output from 'trace-cmd record' command.


Note that the "sectors" in result are the standard UNIX 512-byte sectors,
not any device- or filesystem-specific block size. See
https://www.kernel.org/doc/Documentation/block/stat.txt
https://github.com/brendangregg/perf-tools/blob/master/disk/bitesize
ENDOFMESSAGE
    exit
fi

input_file="$1"
input_file_dir="$( cd "$( dirname "$input_file" )" >/dev/null && pwd )"
events_file="$input_file_dir"/events.dat
sectors_file="$input_file_dir"/sectors.dat

event="block_rq_issue"

echo "Generating events file with command 'trace-cmd report': $events_file"
trace-cmd report -t -i "$input_file" -F "$event" > "$events_file"

echo "Extracting sectors from events file to file: $sectors_file"
grep -oP "$event.+\\+ \\K\\d+" "$events_file" > "$sectors_file"

declare -A buckets

while IFS='' read -r sectors || [[ -n "$sectors" ]]; do
    buckets[$sectors]="$(( ${buckets[$sectors]:-0} + 1 ))"
done < "$sectors_file"


total=0
for sectors in "${!buckets[@]}"; do
    (( total += ${buckets[$sectors]} ))
done

printf '\n%-13s%-11s%s\n' SECTORS COUNT RATIO
for _ in $(seq 45); do
    printf '-'
done
echo

for sectors in "${!buckets[@]}"; do
    printf '%-5d   ->   %-11d%.3f%%\n' "$sectors" "${buckets[$sectors]}" "$(echo "${buckets[$sectors]}" / "$total * 100" | bc -l)"
done |
sort -rn -k3
