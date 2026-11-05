#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>

struct event { __u64 timestamp_ns, cgroup_id; __u32 pid, tgid; };
struct { __uint(type, BPF_MAP_TYPE_RINGBUF); __uint(max_entries, 1 << 20); } events SEC(".maps");
struct { __uint(type, BPF_MAP_TYPE_ARRAY); __uint(max_entries, 1); __type(key, __u32); __type(value, __u64); } loss SEC(".maps");
struct { __uint(type, BPF_MAP_TYPE_HASH); __uint(max_entries, 2); __type(key, __u64); __type(value, __u8); } selected SEC(".maps");

SEC("tracepoint/sched/sched_process_exec")
int on_exec(void *ctx)
{
    (void)ctx;
    __u64 cgroup = bpf_get_current_cgroup_id();
    if (!bpf_map_lookup_elem(&selected, &cgroup)) return 0;
    struct event *e = bpf_ringbuf_reserve(&events, sizeof(*e), 0);
    if (!e) {
        __u32 key = 0;
        __u64 *count = bpf_map_lookup_elem(&loss, &key);
        if (count) __sync_fetch_and_add(count, 1);
        return 0;
    }
    __u64 id = bpf_get_current_pid_tgid();
    e->timestamp_ns = bpf_ktime_get_ns();
    e->cgroup_id = cgroup;
    e->pid = (__u32)id;
    e->tgid = id >> 32;
    bpf_ringbuf_submit(e, 0);
    return 0;
}
char LICENSE[] SEC("license") = "GPL";
