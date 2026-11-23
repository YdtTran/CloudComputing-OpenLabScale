#!/bin/sh
set -eu

script_dir=$(cd "$(dirname "$0")" && pwd)
build_dir="$script_dir/build"
image=ebpf-seminar-bpftrace:local

if ! docker image inspect "$image" >/dev/null 2>&1; then
    printf 'Missing image %s. Build it first:\n  docker build -t %s %s\n' \
        "$image" "$image" "$script_dir" >&2
    exit 1
fi

mkdir -p "$build_dir"
arch_inc="/usr/include/$(gcc -dumpmachine)"

if [ ! -x "$build_dir/read_workload" ] || [ "$script_dir/read_workload.c" -nt "$build_dir/read_workload" ]; then
    gcc -O2 -Wall -Wextra "$script_dir/read_workload.c" -o "$build_dir/read_workload"
fi
if [ ! -x "$build_dir/userspace_calc" ] || [ "$script_dir/userspace_calc.c" -nt "$build_dir/userspace_calc" ]; then
    gcc -O2 -Wall -Wextra "$script_dir/userspace_calc.c" -o "$build_dir/userspace_calc"
fi
if [ ! -f "$build_dir/inkernel_calc.bpf.o" ] || [ "$script_dir/inkernel_calc.c" -nt "$build_dir/inkernel_calc.bpf.o" ]; then
    clang -O2 -g -target bpf -D__BPF__ -I"$arch_inc" -c "$script_dir/inkernel_calc.c" -o "$build_dir/inkernel_calc.bpf.o"
fi
if [ ! -x "$build_dir/inkernel_calc" ] || [ "$script_dir/inkernel_calc.c" -nt "$build_dir/inkernel_calc" ]; then
    gcc -O2 -Wall -Wextra "$script_dir/inkernel_calc.c" -o "$build_dir/inkernel_calc" -lbpf -lelf -lz
fi

ncpus=$(getconf _NPROCESSORS_ONLN 2>/dev/null || nproc)
if [ "$ncpus" -ge 11 ]; then
    cpu_w1=0; cpu_w2=2; cpu_w3=4; cpu_w4=6
    cpu_o2=8; cpu_o3=9; cpu_o4=10
else
    cpu_w1=$((0 % ncpus)); cpu_w2=$((1 % ncpus)); cpu_w3=$((2 % ncpus)); cpu_w4=$((3 % ncpus))
    cpu_o2=$((4 % ncpus)); cpu_o3=$((5 % ncpus)); cpu_o4=$((6 % ncpus))
fi

duration_ms=${1:-5000}

lab=$(mktemp -d)
chmod 0755 "$lab"
mkdir -p "$lab/sync" \
    "$lab/out/w1" "$lab/out/w2" "$lab/out/w3" "$lab/out/w4" \
    "$lab/out/o2" "$lab/out/o3" "$lab/out/o4"
chmod 0755 "$lab/sync"
chmod 0777 "$lab/out/w1" "$lab/out/w2" "$lab/out/w3" "$lab/out/w4" \
    "$lab/out/o2" "$lab/out/o3" "$lab/out/o4"

w1=""; w2=""; w3=""; w4=""
o2=""; o3=""; o4=""

cleanup() {
    for owned in "$o4" "$o3" "$o2" "$w4" "$w3" "$w2" "$w1"; do
        if [ -n "$owned" ]; then
            docker rm -f "$owned" >/dev/null 2>&1 || true
        fi
    done
    rm -rf "$lab"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

start_workload() {
    lane=$1
    cpu=$2
    docker run -d --pull=never --cpuset-cpus="$cpu" \
        --network none --read-only --user 65534:65534 \
        --cap-drop ALL --security-opt no-new-privileges \
        --memory 256m --pids-limit 16 \
        -v "$build_dir:/bin_ro:ro" \
        -v "$lab/sync:/sync:ro" \
        -v "$lab/out/$lane:/out:rw" \
        "$image" /bin_ro/read_workload "$duration_ms"
}

host_pid() {
    docker inspect --format '{{.State.Pid}}' "$1"
}

cgroup_path_of() {
    sed -n 's/^0:://p' "/proc/$1/cgroup"
}

cpu_usage_usec() {
    awk '$1 == "usage_usec" { print $2; exit }' "/sys/fs/cgroup$1/cpu.stat"
}

wait_file_has() {
    file=$1
    pattern=$2
    for attempt in $(seq 1 300); do
        if [ -f "$file" ] && grep -q "$pattern" "$file" 2>/dev/null; then
            return 0
        fi
        sleep 0.1
    done
    printf 'Timed out waiting for %s (%s)\n' "$file" "$pattern" >&2
    return 1
}

wait_file_exists() {
    file=$1
    for attempt in $(seq 1 150); do
        if [ -f "$file" ]; then
            return 0
        fi
        sleep 0.1
    done
    printf 'Timed out waiting for %s\n' "$file" >&2
    return 1
}

printf 'Starting 4 isolated workload lanes (P-cores %s,%s,%s,%s | E-cores %s,%s,%s)...\n' \
    "$cpu_w1" "$cpu_w2" "$cpu_w3" "$cpu_w4" "$cpu_o2" "$cpu_o3" "$cpu_o4"

w1=$(start_workload w1 "$cpu_w1")
w2=$(start_workload w2 "$cpu_w2")
w3=$(start_workload w3 "$cpu_w3")
w4=$(start_workload w4 "$cpu_w4")

pid_w3=$(host_pid "$w3")
pid_w4=$(host_pid "$w4")
cg_path_w3=$(cgroup_path_of "$pid_w3")
cg_path_w4=$(cgroup_path_of "$pid_w4")
cg_id_w4=$(stat -c %i "/sys/fs/cgroup$cg_path_w4")

o2=$(docker run -d --pull=never --cpuset-cpus="$cpu_o2" --pid="container:$w2" \
    --user 65534:65534 --cap-drop ALL --security-opt no-new-privileges \
    --network none --read-only --tmpfs /tmp:rw,nosuid,nodev,mode=1777 \
    -v "$build_dir:/bin_ro:ro" \
    -v "$lab/sync:/sync:ro" \
    -v "$lab/out/o2:/out:rw" \
    "$image" sh -c '
        mkfifo /tmp/p
        (trap - INT; exec strace -qq -s 0 -T -e trace=read -e signal=none -p 1) > /tmp/p 2>&1 &
        tp=$!
        /bin_ro/userspace_calc strace /sync/go /out/ready < /tmp/p > /out/obs.txt.tmp &
        cp=$!
        while [ ! -e /sync/stop ]; do sleep 0.05; done
        kill -INT "$tp" 2>/dev/null || true
        wait "$tp" 2>/dev/null || true
        wait "$cp" 2>/dev/null || true
        mv /out/obs.txt.tmp /out/obs.txt
        sleep 60
    ')

o3=$(docker run -d --pull=never --cpuset-cpus="$cpu_o3" \
    --cap-drop ALL --cap-add SYS_ADMIN --security-opt no-new-privileges \
    --network none --read-only --pid=host --cgroupns=host \
    --tmpfs /tmp:rw,nosuid,nodev,mode=1777 \
    -v /sys/kernel/tracing:/sys/kernel/tracing:ro \
    -v /sys/kernel/btf:/sys/kernel/btf:ro \
    -v /sys/fs/cgroup:/sys/fs/cgroup:ro \
    -v "$build_dir:/bin_ro:ro" \
    -v "$lab/sync:/sync:ro" \
    -v "$lab/out/o3:/out:rw" \
    "$image" sh -c '
        mkfifo /tmp/p
        (trap - INT; exec perf trace -a --no-comm -G "$1" -e read) > /tmp/p 2>&1 &
        tp=$!
        /bin_ro/userspace_calc perf /sync/go /out/ready < /tmp/p > /out/obs.txt.tmp &
        cp=$!
        while [ ! -e /sync/stop ]; do sleep 0.05; done
        kill -INT "$tp" 2>/dev/null || true
        wait "$tp" 2>/dev/null || true
        wait "$cp" 2>/dev/null || true
        mv /out/obs.txt.tmp /out/obs.txt
        sleep 60
    ' sh "$cg_path_w3")

o4=$(docker run -d --pull=never --cpuset-cpus="$cpu_o4" \
    --cap-drop ALL --cap-add SYS_ADMIN --security-opt no-new-privileges \
    --network none --read-only --pid=host --cgroupns=host \
    -v /sys/kernel/tracing:/sys/kernel/tracing:ro \
    -v /sys/kernel/btf:/sys/kernel/btf:ro \
    -v /sys/fs/cgroup:/sys/fs/cgroup:ro \
    -v "$build_dir:/bin_ro:ro" \
    -v "$lab/sync:/sync:ro" \
    -v "$lab/out/o4:/out:rw" \
    "$image" sh -c '
        /bin_ro/inkernel_calc /bin_ro/inkernel_calc.bpf.o "$1" /out/ready /sync/stop > /out/obs.txt.tmp
        mv /out/obs.txt.tmp /out/obs.txt
        sleep 60
    ' sh "$cg_id_w4")

wait_file_exists "$lab/out/o2/ready" || { docker logs "$o2" >&2; exit 1; }
wait_file_exists "$lab/out/o3/ready" || { docker logs "$o3" >&2; exit 1; }
wait_file_exists "$lab/out/o4/ready" || { docker logs "$o4" >&2; exit 1; }

cg_o2=$(cgroup_path_of "$(host_pid "$o2")")
cg_o3=$(cgroup_path_of "$(host_pid "$o3")")
cg_o4=$(cgroup_path_of "$(host_pid "$o4")")

u0_o2=$(cpu_usage_usec "$cg_o2")
u0_o3=$(cpu_usage_usec "$cg_o3")
u0_o4=$(cpu_usage_usec "$cg_o4")

printf 'All observers attached. Running %s ms synchronized race...\n' "$duration_ms"
touch "$lab/sync/go"

wait_file_has "$lab/out/w1/workload.txt" '^DONE '
wait_file_has "$lab/out/w2/workload.txt" '^DONE '
wait_file_has "$lab/out/w3/workload.txt" '^DONE '
wait_file_has "$lab/out/w4/workload.txt" '^DONE '

sleep 0.2
touch "$lab/sync/stop"

wait_file_has "$lab/out/o2/obs.txt" '^OBS ' || { docker logs "$o2" >&2; exit 1; }
wait_file_has "$lab/out/o3/obs.txt" '^OBS ' || { docker logs "$o3" >&2; exit 1; }
wait_file_has "$lab/out/o4/obs.txt" '^OBS ' || { docker logs "$o4" >&2; exit 1; }

u1_o2=$(cpu_usage_usec "$cg_o2")
u1_o3=$(cpu_usage_usec "$cg_o3")
u1_o4=$(cpu_usage_usec "$cg_o4")

cpu_ms_o2=$(awk -v a="$u0_o2" -v b="$u1_o2" 'BEGIN { printf "%.1f", (b - a) / 1000.0 }')
cpu_ms_o3=$(awk -v a="$u0_o3" -v b="$u1_o3" 'BEGIN { printf "%.1f", (b - a) / 1000.0 }')
cpu_ms_o4=$(awk -v a="$u0_o4" -v b="$u1_o4" 'BEGIN { printf "%.1f", (b - a) / 1000.0 }')

w1_line=$(cat "$lab/out/w1/workload.txt")
w2_line=$(cat "$lab/out/w2/workload.txt")
w3_line=$(cat "$lab/out/w3/workload.txt")
w4_line=$(cat "$lab/out/w4/workload.txt")

o2_line=$(cat "$lab/out/o2/obs.txt")
o3_line=$(cat "$lab/out/o3/obs.txt")
o4_line=$(cat "$lab/out/o4/obs.txt")

awk -v w1="$w1_line" -v w2="$w2_line" -v w3="$w3_line" -v w4="$w4_line" \
    -v o2="$o2_line" -v o3="$o3_line" -v o4="$o4_line" \
    -v m2="$cpu_ms_o2" -v m3="$cpu_ms_o3" -v m4="$cpu_ms_o4" '
function parse_kv(str, out,    n, i, a, kv) {
    delete out
    n = split(str, a, /[[:space:]]+/)
    for (i = 2; i <= n; i++) {
        if (split(a[i], kv, "=") == 2)
            out[kv[1]] = kv[2]
    }
}
function commas(n,    s, res, len, i) {
    s = sprintf("%.0f", n + 0)
    len = length(s)
    res = ""
    for (i = 1; i <= len; i++) {
        res = res substr(s, i, 1)
        if ((len - i) > 0 && ((len - i) % 3) == 0)
            res = res ","
    }
    return res
}
function fmt_bytes(b,    v) {
    v = b + 0
    if (v >= 1073741824) return sprintf("%.1f GB", v / 1073741824)
    if (v >= 1048576)    return sprintf("%.1f MB", v / 1048576)
    if (v >= 1024)       return sprintf("%.1f KB", v / 1024)
    return sprintf("%d B", v)
}
function short_rec(n,    v) {
    v = n + 0
    if (v >= 1000000) return sprintf("%.2fM", v / 1000000)
    if (v >= 1000)    return sprintf("%.1fK", v / 1000)
    return sprintf("%d", v)
}
function print_row(label, w, o, obs_ms, has_obs, base_rate,    rate, pct, tp_str, ctx_str, data_str, cpu_str, cap_str, cap_pct) {
    rate = w["reads"] / (w["wall_ms"] / 1000.0)
    pct = (base_rate > 0) ? (rate * 100.0 / base_rate) : 100.0
    tp_str = sprintf("%s/s (%3.0f%%)", commas(rate), pct)
    ctx_str = commas(w["ctx_sw"])
    if (!has_obs) {
        data_str = "-"
        cpu_str = "-"
        cap_str = "-"
    } else {
        data_str = sprintf("%s (%s)", fmt_bytes(o["raw_bytes"]), short_rec(o["records"]))
        cpu_str = sprintf("%s ms", obs_ms)
        cap_pct = (w["reads"] > 0) ? (o["counted_reads"] * 100.0 / w["reads"]) : 0.0
        cap_str = sprintf("%.1f%% (%s/%s)", cap_pct, o["counted_slow"], w["slow"])
    }
    printf "%-21s | %-18s | %10s | %-18s | %9s | %-17s\n",
        label, tp_str, ctx_str, data_str, cpu_str, cap_str
}
BEGIN {
    parse_kv(w1, dw1); parse_kv(w2, dw2); parse_kv(w3, dw3); parse_kv(w4, dw4)
    parse_kv(o2, do2); parse_kv(o3, do3); parse_kv(o4, do4)

    base_rate = dw1["reads"] / (dw1["wall_ms"] / 1000.0)
    printf "\n"
    printf "%-21s | %-18s | %10s | %-18s | %9s | %-17s\n",
        "Mode", "App Throughput", "Ctx Switch", "Kernel->User Data", "Obs CPU", "Captured (Slow)"
    printf "%-21s-+-%-18s-+-%10s-+-%-18s-+-%9s-+-%-17s\n",
        "---------------------", "------------------", "----------", "------------------", "---------", "-----------------"
    print_row("Baseline",             dw1, do2, 0,   0, base_rate)
    print_row("strace (ptrace+user)", dw2, do2, m2,  1, base_rate)
    print_row("perf trace (user)",    dw3, do3, m3,  1, base_rate)
    print_row("eBPF (in-kernel map)", dw4, do4, m4,  1, base_rate)

    rate2 = dw2["reads"] / (dw2["wall_ms"] / 1000.0)
    rate4 = dw4["reads"] / (dw4["wall_ms"] / 1000.0)
    printf "\nSummary:\n"
    printf "  - strace vs eBPF throughput : %s/s vs %s/s (%.1fx faster under eBPF)\n",
        commas(rate2), commas(rate4), (rate2 > 0 ? rate4 / rate2 : 0)
    printf "  - perf trace Kernel->User   : %s (%s events, lost=%s) vs eBPF %s (%s map read)\n",
        fmt_bytes(do3["raw_bytes"]), commas(do3["records"]), commas(do3["lost_events"]),
        fmt_bytes(do4["raw_bytes"]), do4["records"]
    printf "  - Observer CPU cost         : strace %s ms | perf trace %s ms | eBPF %s ms\n\n",
        m2, m3, m4
}'
