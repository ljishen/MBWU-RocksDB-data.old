#!/usr/bin/env bash

set -eu -o pipefail

if [ "$#" -ne 1 ]; then
    cat <<-ENDOFMESSAGE
Usage: ./ioszdist.sh TRACE_FILE

TRACE_FILE:
    The trace file is the output from the 'trace-cmd report' command.
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

printf '\n%-21s%s\n' 'SECTORS' 'COUNT'
for _ in $(seq 40); do
    printf '-'
done
echo

for sec in "${!buckets[@]}"; do
	printf '%-5s sectors   ->   %s\n' "$sec" "${buckets[$sec]}"
done |
sort -rn -k3
