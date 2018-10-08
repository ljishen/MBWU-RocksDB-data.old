#!/bin/bash

set -eu -o pipefail

# size constants
K=1024
# shellcheck disable=SC2034
M=$(( 1024 * K ))
# shellcheck disable=SC2034
G=$(( 1024 * M ))

rocksdb_dir="${ROCKSDB_DIR:-/home/ljishen/rocksdb-5.14.3}"
rocksdb_options_file="${ROCKSDB_OPTIONS_FILE:-/home/ljishen/ycsb-rocksdb/analysis/data/workloadc/workloadc_21/OPTIONS}"
db_on_device_name="${DB_ON_DEVICE_NAME:-sda1}"
data_dir="${DATA_DIR:-/mnt/sda1/rocksdb_data}"

NUM_KEYS="$(( 1 * K ))"
KEY_SIZE=16
VALUE_SIZE="$(( 8 * K ))"
NUM_THREADS=1

OUTPUT_BASE=../data/db_bench
DB_BENCH_LOG="$OUTPUT_BASE"/db_bench.log
IOSTAT_LOG="$OUTPUT_BASE"/iostat.log
PIDFILE=iostat.pid
DISKSTATS_LOG_B="$OUTPUT_BASE"/diskstats_b.log     # log the before stats
DISKSTATS_LOG_A="$OUTPUT_BASE"/diskstats_a.log     # log the after stats

if [ "$#" -lt 1 ]; then
    cat <<-ENDOFMESSAGE
Usage: $0 [--backup] BENCHMARK

BENCHMARK:
    Currently available benchmarks: fillrandom, randomread.
    It could also be any of these meta operations: stats, levelstats, sstables.

--backup:
    Backup the output files to a time stamped folder.
ENDOFMESSAGE
    exit
fi

mkdir --parents "$OUTPUT_BASE"

benchmark_comm="$rocksdb_dir/db_bench \
    --options_file=$rocksdb_options_file \
    --db=$data_dir \
    --wal_dir=$data_dir \
    --key_size=$KEY_SIZE \
    --value_size=$VALUE_SIZE \
    --disable_wal=0 \
    --stats_per_interval=1 \
    --stats_interval_seconds=60 \
    --histogram=1"

suffix_params="2>&1 | tee -a $DB_BENCH_LOG"

fillrandom_command="rm -rf $data_dir && mkdir $data_dir && $benchmark_comm \
    --use_existing_db=0 \
    --benchmarks=fillrandom \
    --num=$NUM_KEYS \
    --threads=1 \
    --seed=$( date +%s ) \
    $suffix_params"

randomread_command="$benchmark_comm \
    --use_existing_db=1 \
    --benchmarks=readrandom \
    --readonly=1 \
    --threads=$NUM_THREADS \
    --num=$NUM_KEYS \
    --reads=$NUM_KEYS \
    --seed=$( date +%s ) \
    $suffix_params"

# Check if an item is in a bash array
#   https://unix.stackexchange.com/a/177589
declare -a non_benchmarks=(
    stats levelstats sstables
)
declare -A non_benchmarks_map
for key in "${!non_benchmarks[@]}"; do
    non_benchmarks_map[${non_benchmarks[$key]}]="$key"
done

# get the last argument passed to this shell script
#   https://stackoverflow.com/questions/1853946/getting-the-last-argument-passed-to-a-shell-script
for run_benchmark; do true; done

if [[ -n "${non_benchmarks_map[$run_benchmark]+"check"}" ]]; then
    run_command="$rocksdb_dir/db_bench \
        --db=$data_dir \
        --benchmarks=$run_benchmark"
    eval "$run_command"
    exit 0
fi

if [ "$run_benchmark" = "fillrandom" ]; then
    run_command="$fillrandom_command"
elif [ "$run_benchmark" = "randomread" ]; then
    run_command="$randomread_command"
else
    echo "Benchmark '$run_benchmark' not found!"
    exit 1
fi

function newline_print() {
    printf '\n%s\n' "$1"
}

newline_print "Starting iostat deamon"
pkill -SIGTERM --pidfile "$PIDFILE" &> /dev/null || true
rm --force "$PIDFILE"
nohup stdbuf -oL -eL iostat -dktxyzH -g /dev/"$db_on_device_name" 3 < /dev/null > "$IOSTAT_LOG" 2>&1 & echo $! > "$PIDFILE"

newline_print "Freeing the slab objects and pagecache"
sync; sudo sh -c "echo 3 > /proc/sys/vm/drop_caches"

newline_print "Saving disk stats (before)"
grep "$db_on_device_name" /proc/diskstats > "$DISKSTATS_LOG_B"

echo
printf "%s\\n\\n" "$run_command" | tee "$DB_BENCH_LOG"
eval "$run_command"

newline_print "Saving disk stats (after)"
sync; grep "$db_on_device_name" /proc/diskstats > "$DISKSTATS_LOG_A"

newline_print "Stopping iostat deamon"
pkill -SIGTERM --pidfile "$PIDFILE" &> /dev/null
rm --force "$PIDFILE"

if [ "$1" = "--backup" ]; then
    backup_dir="$OUTPUT_BASE/$(date +%F_%T)"
    newline_print "Backuping files to dir $(realpath "$backup_dir")"
    mkdir "$backup_dir"
    mv "$DB_BENCH_LOG" "$IOSTAT_LOG" "$DISKSTATS_LOG_B" "$DISKSTATS_LOG_A" "$backup_dir"
fi
