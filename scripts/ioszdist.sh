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

echo "Generating events file $events_file"
trace-cmd report -t -i "$input_file" -F "$event" > "$events_file"

echo "Extracting sectors from events file to $sectors_file"
sed -nr 's/^.+,[[:digit:]]+ ([[:upper:]]+).+\+ ([[:digit:]]+).+$/\1 \2/ p' "$events_file" > "$sectors_file"

echo "Parsing results..."

declare -A buckets_read=()
declare -A buckets_write=()

total=0
read_sectors=0
write_sectors=0

while IFS='' read -r line || [[ -n "$line" ]]; do
    rwbs="${line%% *}"
    sectors="${line#* }"
    if [[ $rwbs == *R* ]]; then
        buckets_read[$sectors]="$(( ${buckets_read[$sectors]:-0} + 1 ))"
        read_sectors="$(( read_sectors + sectors ))"
    else
        buckets_write[$sectors]="$(( ${buckets_write[$sectors]:-0} + 1 ))"
        write_sectors="$(( write_sectors + sectors ))"
    fi

    (( total += 1 ))
done < "$sectors_file"

function printSeparator() {
    for _ in $(seq 45); do
        printf '-'
    done
    echo
}

printf '\n%-11s   %-2s   %-12s%s\n' SECTOR_SIZE RW COUNT RATIO
printSeparator

function printTable() {
    eval "declare -A buckets=${1#*=}"
    rw="$2"

    # shellcheck disable=SC2154
    for sectors in "${!buckets[@]}"; do
        printf '%-11d   %-2s   %-12d%.3f%%\n' "$sectors" "$rw" "${buckets[$sectors]}" "$(echo "${buckets[$sectors]}" / "$total * 100" | bc -l)"
    done
}

# Pass associative array as an argument to a function
#   https://stackoverflow.com/a/8879444
(printTable "$(declare -p buckets_read)" R ; printTable "$(declare -p buckets_write)" W) | sort -rn -k3

printf '\n\n'

echo "SUMMARY (512-byte sectors)"
printSeparator

total_sectors="$(( read_sectors + write_sectors ))"
printf 'Total read sectors:  %-11d(%-7.3fMB, %.3f%%)' "$read_sectors" "$(echo "$read_sectors" / 2 / 1024 | bc -l)" "$(echo "$read_sectors" / "$total_sectors * 100" | bc -l)"
echo
printf 'Total write sectors: %-11d(%-7.3fMB, %.3f%%)' "$write_sectors" "$(echo "$write_sectors" / 2 / 1024 | bc -l)" "$(echo "$write_sectors" / "$total_sectors * 100" | bc -l)"
echo
