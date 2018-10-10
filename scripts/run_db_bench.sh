#!/bin/bash

set -eu -o pipefail

# size constants
K=1024
# shellcheck disable=SC2034
M=$(( 1024 * K ))
# shellcheck disable=SC2034
G=$(( 1024 * M ))

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"

rocksdb_dir="${ROCKSDB_DIR:-/home/ljishen/rocksdb-5.14.3}"
rocksdb_options_file="${ROCKSDB_OPTIONS_FILE:-$(realpath "$SCRIPT_DIR"/../data/workloadc/workloadc_21/OPTIONS)}"
db_on_device_name="${DB_ON_DEVICE_NAME:-sda1}"
db_on_device_fullname="/dev/$db_on_device_name"
data_dir="${DATA_DIR:-/mnt/sda1/rocksdb_data}"

num_threads="${NUM_THREADS:-1}"

# e.g. 70 means 70% out of all read and merge operations are merges
merge_read_ratio="${MERGE_READ_RATIO:-50}"

num_keys="${NUM_KEYS:-$(( 1 * M ))}"
key_size="${KEY_SIZE:-16}"
value_size="${VALUE_SIZE:-$(( 8 * K ))}"

OUTPUT_BASE="$(realpath "$SCRIPT_DIR/../data/db_bench")"

DB_BENCH_LOG="$OUTPUT_BASE"/db_bench.log
IOSTAT_LOG="$OUTPUT_BASE"/iostat.log
MPSTAT_LOG="$OUTPUT_BASE"/mpstat.log
BLKSTAT_LOG="$OUTPUT_BASE"/blkstat.dat

IOSTAT_PIDFILE=iostat.pid
MPSTAT_PIDFILE=mpstat.pid
BLKSTAT_PIDFILE=blkstat.pid

DISKSTATS_LOG_B="$OUTPUT_BASE"/diskstats_b.log     # log the before stats
DISKSTATS_LOG_A="$OUTPUT_BASE"/diskstats_a.log     # log the after stats

device_info="$("$SCRIPT_DIR"/../../playbooks/roles/run/files/devname2id.sh "$db_on_device_fullname")"
pdevice_name="$(echo "$device_info" | head -1)"
pdevice_id="$(echo "$device_info" | tail -1)"

if [ "$#" -lt 1 ]; then
    cat <<-ENDOFMESSAGE
Usage: $0 [--trace_blk_rq] [--backup] BENCHMARK

This script must be run as root.

BENCHMARK:
    Currently available benchmarks: fillseq, readrandom, readrandommergerandom.
    It could also be any of these meta operations on the existing db:
        stats, levelstats, sstables, count_only.

    fillseq:
        Fill num_keys with 1 thread.

    readrandom:
        Read about 75% of num_keys from the existing db.
        This workload is similar to the YCSB workloadc.

    readrandommergerandom:
        Read or merge all keys from the existing db under merge_read_ratio
        (default 50/50).
        This workload is similar to the YCSB workloada. The only difference is
        that the atomic guarantee of the read-modify-write is handled by the
        RocksDB merge operator instead of YCSB as the client.

--trace_blk_rq:
    Trace the ftrace event block_rq_[issue|complete] during benchmarking.

--backup:
    Backup the output files to a time stamped folder under
    $OUTPUT_BASE

IMPORTANT NOTICE:
    Please make sure that the current git repository does NOT reside in any
    partition of $pdevice_name
ENDOFMESSAGE
    exit
fi

if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root."
    exit 1
fi

db_bench_exe="$rocksdb_dir"/db_bench
if [ ! -f "$db_bench_exe" ]; then
    echo "Please check if the ROCKSDB_DIR ($rocksdb_dir) is correct and \
make sure the source is proper compiled to generate the 'db_bench' program."
    exit 1
fi

do_trace_blk_rq=false
if [[ $* == *"--trace_blk_rq "* ]]; then
    do_trace_blk_rq=true
fi

if [ "$do_trace_blk_rq" = true ] && ! command -v trace-cmd &> /dev/null; then
    echo "Program 'trace-cmd' is not available in this bash environment."
    exit 1
fi

mkdir --parents "$OUTPUT_BASE"

bench_comm_command="$db_bench_exe \
    --options_file=$rocksdb_options_file \
    --db=$data_dir \
    --wal_dir=$data_dir \
    --key_size=$key_size \
    --value_size=$value_size \
    --disable_wal=0 \
    --stats_per_interval=1 \
    --stats_interval_seconds=60 \
    --histogram=1"

suffix_params="2>&1 | tee -a $DB_BENCH_LOG"

fillseq_command="$bench_comm_command \
    --use_existing_db=0 \
    --benchmarks=fillseq \
    --num=$num_keys \
    --threads=1 \
    --seed=$( date +%s ) \
    $suffix_params"

readrandom_command="$bench_comm_command \
    --use_existing_db=1 \
    --benchmarks=readrandom \
    --readonly=1 \
    --threads=$num_threads \
    --num=$num_keys \
    --reads=$(( num_keys * 75 / 100 / num_threads )) \
    --seed=$( date +%s ) \
    $suffix_params"

readrandommergerandom_command="$bench_comm_command \
    --use_existing_db=1 \
    --benchmarks=readrandommergerandom \
    --merge_operator='put' \
    --merge_keys=$(( num_keys / num_threads )) \
    --mergereadpercent=$merge_read_ratio \
    --threads=$num_threads \
    --num=$num_keys \
    --seed=$( date +%s ) \
    $suffix_params"

# Get the last argument passed to this shell script
#   https://stackoverflow.com/questions/1853946/getting-the-last-argument-passed-to-a-shell-script
for run_benchmark; do true; done

if [[ $run_benchmark == -* ]]; then
    echo "Which benchmark do you want to run?"
    exit 1
fi

# Check if an item is in a bash array
#   https://unix.stackexchange.com/a/177589
declare -a non_benchmarks=(
    stats levelstats sstables count_only
)
declare -A non_benchmarks_map
for key in "${!non_benchmarks[@]}"; do
    non_benchmarks_map[${non_benchmarks[$key]}]="$key"
done

if [[ -n "${non_benchmarks_map[$run_benchmark]+"check"}" ]]; then
    if [ "$run_benchmark" = "count_only" ]; then
        eval "$rocksdb_dir/ldb --db=$data_dir dump --count_only"
    else
        eval "$db_bench_exe --db=$data_dir --use_existing_db=1 --benchmarks=$run_benchmark"
    fi
    exit 0
fi

if [ "$run_benchmark" = "fillseq" ]; then
    rm -rf "$data_dir" && mkdir --parents "$data_dir"
    db_bench_command="$fillseq_command"
elif [ "$run_benchmark" = "readrandom" ]; then
    db_bench_command="$readrandom_command"
elif [ "$run_benchmark" = "readrandommergerandom" ]; then
    db_bench_command="$readrandommergerandom_command"
else
    echo "Benchmark '$run_benchmark' not found!"
    exit 1
fi

function newline_print() {
    echo; echo "$1"
}

newline_print "Start $run_benchmark at $(date)" | tee "$DB_BENCH_LOG"
echo "===============================================================================" | tee -a "$DB_BENCH_LOG"

newline_print "$db_bench_command" | tee -a "$DB_BENCH_LOG"

newline_print "Starting iostat deamon"
pkill -SIGTERM --pidfile "$IOSTAT_PIDFILE" &> /dev/null || true
rm --force "$IOSTAT_PIDFILE"
nohup stdbuf -oL -eL iostat -dktxyzH -g "$db_on_device_fullname" 3 < /dev/null > "$IOSTAT_LOG" 2>&1 &
echo $! > "$IOSTAT_PIDFILE"

newline_print "Starting mpstat deamon"
pkill -SIGTERM --pidfile "$MPSTAT_PIDFILE" &> /dev/null || true
rm --force "$MPSTAT_PIDFILE"
nohup stdbuf -oL -eL mpstat -P ALL 3 < /dev/null > "$MPSTAT_LOG" 2>&1 &
echo $! > "$MPSTAT_PIDFILE"

newline_print "Freeing the slab objects and pagecache"
sync; echo 3 > /proc/sys/vm/drop_caches

if [ "$do_trace_blk_rq" = true ]; then
    newline_print "Starting to trace the block events for device $pdevice_name"
    trace-cmd reset
    blk_trace_command="nohup trace-cmd record \
        -o $BLKSTAT_LOG \
        --date \
        -e block:block_rq_issue \
        -f 'dev == $pdevice_id' \
        -e block:block_rq_complete \
        -f 'dev == $pdevice_id' \
        < /dev/null > nohup.out 2>&1 &"
    newline_print "$blk_trace_command" | tee -a "$DB_BENCH_LOG"

    eval "$blk_trace_command"
    echo $! > "$BLKSTAT_PIDFILE"

    newline_print "Pause 7 seconds to wait for the tracer to start..."
    sleep 7
fi

newline_print "Saving disk stats (before)"
grep "$db_on_device_name" /proc/diskstats > "$DISKSTATS_LOG_B"

echo | tee -a "$DB_BENCH_LOG"
eval "$db_bench_command"

newline_print "Saving disk stats (after)"
sync; grep "$db_on_device_name" /proc/diskstats > "$DISKSTATS_LOG_A"

newline_print "Stopping iostat deamon"
pkill -SIGTERM --pidfile "$IOSTAT_PIDFILE" || true
rm --force "$IOSTAT_PIDFILE"

newline_print "Stopping mpstat deamon"
pkill -SIGINT --pidfile "$MPSTAT_PIDFILE" || true
rm --force "$MPSTAT_PIDFILE"

if [ "$do_trace_blk_rq" = true ]; then
    newline_print "Stopping blkstat deamon"
    pkill -SIGINT --pidfile "$BLKSTAT_PIDFILE" &> /dev/null || true

    newline_print "Pause 20 seconds to wait for the tracer to finish..."
    sleep 20

    rm --force "$BLKSTAT_PIDFILE"

    if command -v gzip &> /dev/null; then
        BLKSTAT_LOG_GZ="${BLKSTAT_LOG}".gz
        newline_print "Compressing the output from block event tracer to ${BLKSTAT_LOG_GZ}"
        gzip --force --keep --name "${BLKSTAT_LOG}"
    else
        newline_print "Did not compress the output from block event tracer \
            because program 'gzip' is not found."
    fi

    IOSZDIST_LOG="$OUTPUT_BASE"/ioszdist.log
    newline_print "Generating I/O size distribution to $IOSZDIST_LOG"
    "$SCRIPT_DIR"/ioszdist.sh "$BLKSTAT_LOG" | tee "$IOSZDIST_LOG"
    rm "$OUTPUT_BASE"/events.dat "$OUTPUT_BASE"/sectors.dat
fi

if [[ $* == *"--backup "* ]]; then
    backup_dir="$OUTPUT_BASE/$(date +%F_%T)"
    newline_print "Backuping files to dir $backup_dir"
    mkdir "$backup_dir"
    mv "$DB_BENCH_LOG" \
        "$IOSTAT_LOG" \
        "$MPSTAT_LOG" \
        "$DISKSTATS_LOG_B" \
        "$DISKSTATS_LOG_A" \
        "$backup_dir"

    if [ "$do_trace_blk_rq" = true ]; then
        mv "$BLKSTAT_LOG" "$IOSZDIST_LOG" "$backup_dir"

        if [[ -n "${BLKSTAT_LOG_GZ+"check"}" ]]; then
            mv "$BLKSTAT_LOG_GZ" "$backup_dir"
        fi
    fi
fi
