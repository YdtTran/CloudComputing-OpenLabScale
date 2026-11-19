#!/bin/sh
set -eu

lab=$(mktemp -d)
baseline=
collector=
perf_job=
: > "$lab/perf.log"
cleanup() {
    [ -z "$collector" ] || docker rm -f "$collector" >/dev/null
    [ -z "$perf_job" ] || wait "$perf_job" 2>/dev/null || true
    [ -z "$baseline" ] || docker rm -f "$baseline" >/dev/null
    rm "$lab/demo-data.bin" "$lab/perf.log"
    rmdir "$lab"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

image=ebpf-seminar-bpftrace:local
dd if=/dev/zero of="$lab/demo-data.bin" bs=4096 count=1 status=none
baseline=$(docker run -d --pull=never --network none --read-only --user 65534:65534 \
    --cap-drop ALL --security-opt no-new-privileges --cpus .5 --memory 256m \
    --pids-limit 16 --tmpfs /tmp:rw,nosuid,nodev,mode=1777 \
    -v "$lab/demo-data.bin:/demo-data.bin:ro" "$image" \
    strace -f -qq -s 0 -y -e trace=read -e signal=none -P /demo-data.bin -o /tmp/strace.log \
    sh -eu -c 'while [ ! -e /tmp/start ]; do sleep .1; done
        head -c 1024 /demo-data.bin >/dev/null
        exec sleep 60')
host_pid=$(docker inspect --format '{{.State.Pid}}' "$baseline")
cgroup_path=$(sed -n 's/^0:://p' "/proc/$host_pid/cgroup")
cgroup_id=$(stat -c %i "/sys/fs/cgroup$cgroup_path")

collector=$(docker run -d --pull=never --network none --read-only --cap-drop ALL \
    --cap-add SYS_ADMIN --security-opt no-new-privileges --pid=host --cgroupns=host \
    -v /sys/kernel/tracing:/sys/kernel/tracing:ro \
    -v /sys/kernel/btf:/sys/kernel/btf:ro \
    -v /sys/fs/cgroup:/sys/fs/cgroup:ro "$image" \
    bpftrace -B line -e "
      tracepoint:syscalls:sys_exit_read
      /cgroup == $cgroup_id && comm == \"head\" && args.ret > 0/
      { printf(\"comm=%s pid=%d bytes=%ld\\n\", comm, pid, args.ret); }
      BEGIN { printf(\"READY\\n\"); }")

ready=0
for attempt in $(seq 1 30); do
    if docker logs "$collector" 2>&1 | grep -qx READY; then
        ready=1
        break
    fi
    sleep .2
done
if [ "$ready" -ne 1 ]; then
    docker logs "$collector" >&2
    exit 1
fi

docker exec "$collector" perf trace -a --no-syscalls -e syscalls:sys_exit_read -G "$cgroup_path" \
    >"$lab/perf.log" 2>&1 &
perf_job=$!

# Confirm perf is collecting before releasing the two demo reads.
for attempt in $(seq 1 30); do
    docker exec "$baseline" dd if=/demo-data.bin of=/dev/null bs=512 count=1 status=none
    if grep -Eq 'dd/[0-9]+.*sys_exit_read\(.*ret: (512|0x200)\)' "$lab/perf.log"; then
        break
    fi
    sleep .2
done
if ! grep -Eq 'dd/[0-9]+.*sys_exit_read\(.*ret: (512|0x200)\)' "$lab/perf.log"; then
    cat "$lab/perf.log" >&2
    exit 1
fi

docker exec "$baseline" sh -eu -c 'touch /tmp/start; head -c 4096 /demo-data.bin >/dev/null'
for attempt in $(seq 1 30); do
    events=$(docker logs "$collector" 2>/dev/null | grep '^comm=' || true)
    pid_1024=$(printf '%s\n' "$events" | sed -n 's/^comm=head pid=\([0-9]*\) bytes=1024$/\1/p')
    pid_4096=$(printf '%s\n' "$events" | sed -n 's/^comm=head pid=\([0-9]*\) bytes=4096$/\1/p')
    if [ -n "$pid_1024" ] && [ -n "$pid_4096" ] &&
        grep -Eq "/$pid_1024 syscalls:sys_exit_read\(ret: 1024\)" "$lab/perf.log" &&
        grep -Eq "/$pid_4096 syscalls:sys_exit_read\(ret: 4096\)" "$lab/perf.log"; then
        break
    fi
    sleep .2
done
traditional=$(docker exec "$baseline" cat /tmp/strace.log)
if ! printf '%s\n' "$traditional" | grep -Eq 'read.*= 1024$' ||
    printf '%s\n' "$traditional" | grep -q '= 4096$' ||
    [ -z "$pid_1024" ] || [ -z "$pid_4096" ] ||
    ! grep -Eq "/$pid_1024 syscalls:sys_exit_read\(ret: 1024\)" "$lab/perf.log" ||
    ! grep -Eq "/$pid_4096 syscalls:sys_exit_read\(ret: 4096\)" "$lab/perf.log"; then
    printf 'Unexpected trace output\n%s\n%s\n' "$traditional" "$events" >&2
    cat "$lab/perf.log" >&2
    exit 1
fi

printf 'Baseline container %.12s   |   cgroup %s\n\n' "$baseline" "$cgroup_id"
printf 'strace -f  |  selected process tree\n%s\n\n' "$traditional"
printf 'eBPF      |  same container, comm=head\n%s\n\n' "$events"
printf 'perf trace  |  same container, matched worker PIDs\n'
grep -E "/($pid_1024|$pid_4096) syscalls:sys_exit_read" "$lab/perf.log"
