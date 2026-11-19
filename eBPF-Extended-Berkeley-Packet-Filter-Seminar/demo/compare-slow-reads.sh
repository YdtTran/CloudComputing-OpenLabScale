#!/bin/sh
set -eu
cd "$(dirname "$0")"
image=ebpf-seminar-bpftrace:local
lab=$(mktemp -d)
fast=
slow=
collector=
cleanup() {
    for owned in "$collector" "$fast" "$slow"; do
        if [ -n "$owned" ]; then
            docker rm -f "$owned" >/dev/null || true
        fi
    done
    rm "$lab/A" "$lab/B"
    rmdir "$lab"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
: > "$lab/A"
: > "$lab/B"

start_workload() {
    docker run -d --pull=never --network none --read-only --user 65534:65534 \
        --cap-drop ALL --security-opt no-new-privileges --cpus .5 --memory 256m \
        --pids-limit 16 --tmpfs /tmp:rw,nosuid,nodev,mode=1777 \
        -v "$PWD/read-workload.py:/workload.py:ro" "$image" python3 /workload.py "$1"
}

host_pid() {
    docker inspect --format '{{.State.Pid}}' "$1"
}

fast=$(start_workload 0)
slow=$(start_workload 4)
pid_a=$(host_pid "$fast")
pid_b=$(host_pid "$slow")
path_a=$(sed -n 's/^0:://p' "/proc/$pid_a/cgroup")
path_b=$(sed -n 's/^0:://p' "/proc/$pid_b/cgroup")
id_a=$(stat -c %i "/sys/fs/cgroup$path_a")
id_b=$(stat -c %i "/sys/fs/cgroup$path_b")

collector=$(docker run -d --pull=never --network none --read-only --cap-drop ALL \
    --cap-add SYS_ADMIN --security-opt no-new-privileges --pid=host --cgroupns=host \
    --tmpfs /tmp:rw,nosuid,nodev,mode=1777 \
    -v /sys/kernel/tracing:/sys/kernel/tracing:ro \
    -v /sys/kernel/btf:/sys/kernel/btf:ro \
    -v /sys/fs/cgroup:/sys/fs/cgroup:ro \
    -v "$PWD/slow-reads.bt:/slow-reads.bt:ro" "$image" sleep 45)

docker exec "$collector" perf trace -a -G "$path_a" -e read >"$lab/A" 2>&1 &
docker exec "$collector" perf trace -a -G "$path_b" -e read >"$lab/B" 2>&1 &

wait_for() {
    for attempt in $(seq 1 60); do
        if "$@"; then return 0; fi
        sleep .2
    done
    printf 'Timed out: %s\n' "$*" >&2
    cat "$lab/A" "$lab/B" >&2
    return 1
}

perf_ready() {
    docker exec "$fast" cat /proc/self/status >/dev/null
    docker exec "$slow" cat /proc/self/status >/dev/null
    grep -q 'read(' "$lab/A" && grep -q 'read(' "$lab/B"
}

wait_for perf_ready
docker exec "$collector" sh -c 'bpftrace -B line /slow-reads.bt "$@" > /tmp/probe.log 2>&1' \
    demo "$id_a" "$id_b" &
probe_has() {
    docker exec "$collector" grep -Fxq "$1" /tmp/probe.log 2>/dev/null
}
wait_for probe_has READY || { docker exec "$collector" cat /tmp/probe.log >&2; exit 1; }

docker exec "$fast" touch /tmp/start
docker exec "$slow" touch /tmp/start

workload_has() {
    docker logs "$1" | grep -Fxq "$2"
}
wait_for workload_has "$fast" 'reads=20 slow=0'
wait_for workload_has "$slow" 'reads=20 slow=4'
wait_for probe_has "@slow[$id_a]: 0"
wait_for probe_has "@slow[$id_b]: 4"

summarize_perf() {
    awk '/read\(fd: 99([<,[:space:]]|$)/ && /= 1([[:space:]]|$)/ {
        split($0, duration, "[()]");
        records++;
        if (duration[2] + 0 > 200) slow++;
    }
    END {print "records=" records+0, "slow=" slow+0}' "$1"
}

result_a=$(summarize_perf "$lab/A")
result_b=$(summarize_perf "$lab/B")
snapshot=$(docker exec "$collector" cat /tmp/probe.log)
first_counter() {
    printf '%s\n' "$snapshot" | awk -v key="@slow[$1]:" '$1 == key {print $2; exit}'
}
counter_a=$(first_counter "$id_a")
counter_b=$(first_counter "$id_b")
if [ "$result_a" != 'records=20 slow=0' ] || [ "$result_b" != 'records=20 slow=4' ] ||
   [ "$counter_a" != 0 ] || [ "$counter_b" != 4 ]; then
    printf '%s\n%s\n' "$result_a" "$result_b" >&2
    cat "$lab/A" "$lab/B" >&2
    printf '%s\n' "$snapshot" >&2
    exit 1
fi

docker rm -f "$collector" >/dev/null
collector=
docker exec "$fast" touch /tmp/after
docker exec "$slow" touch /tmp/after
wait_for workload_has "$fast" 'after-detach=ok'
wait_for workload_has "$slow" 'after-detach=ok'
test "$(host_pid "$fast")" = "$pid_a"
test "$(host_pid "$slow")" = "$pid_b"

printf 'Two running containers | 20 reads each | slow > 200 ms\n\n'
printf 'perf trace | count in user space\n'
printf '  A: %s\n  B: %s\n\n' "$result_a" "$result_b"
printf 'eBPF | count in kernel, read a 5 s snapshot\n'
printf '  A: summary=1 slow=%s\n  B: summary=1 slow=%s\n\n' \
    "$counter_a" "$counter_b"
printf 'Same slow counts | 40 trace records vs 2 counter values\n'
printf 'After detach     | both read again, same PIDs\n'
