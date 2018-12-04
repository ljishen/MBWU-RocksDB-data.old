#!/usr/bin/env bash

set -eu -o pipefail

if [ "$#" -ne 1 ]; then
    cat <<-ENDOFMESSAGE
Usage: $0 DEVICE_FULLNAME

This script converts the device name of a partition to the device ID of its
parent held by the type dev_t, which can be then used to filter the device in
the block:* events in ftrace.

DEVICE_FULLNAME:
    Note that this is the full name of a device partition.

For example:
    $0 /dev/sda1

See
https://linux.die.net/man/3/minor
ENDOFMESSAGE
    exit
fi

device_fullname="$1"

pdevice_name="$(lsblk --noheadings --output pkname "$device_fullname" | tail -1)"
majmin="$(cat /sys/class/block/"$pdevice_name"/dev)"
major="${majmin%:*}"
minor="${majmin#*:}"

echo /dev/"$pdevice_name"

# See how to convert the major and minor numbers to the device ID:
#   https://github.com/brendangregg/perf-tools/blob/master/iolatency
echo "$(( (major << 20) + minor ))"
