#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>
#include <bpf/bpf_core_read.h>

#define S_IFMT   0170000
#define S_IFBLK  0060000
#define S_IFREG  0100000
#define S_IFSOCK 0140000
#define TASK_COMM_LEN 16

typedef __u16 umode_t;
typedef __u64 size_t;
typedef __s64 ssize_t;
typedef __s64 loff_t;

struct inode {
    umode_t i_mode;
} __attribute__((preserve_access_index));

struct file {
    struct inode *f_inode;
} __attribute__((preserve_access_index));

struct socket {
    int state;
} __attribute__((preserve_access_index));

struct msghdr {
    unsigned int msg_flags;
} __attribute__((preserve_access_index));

struct event {
    __u64 timestamp_ns;
    __u64 cgroup_id;
    __u32 pid;
    __u32 tgid;
    char comm[TASK_COMM_LEN];
};

struct cgroup_stats {
    __u64 exec_count;
    __u64 fork_count;
    __u64 exit_count;
    __u64 io_read_bytes;
    __u64 io_write_bytes;
    __u64 io_events;
    __u64 sock_rx_bytes;
    __u64 sock_tx_bytes;
    __u64 sock_events;
    __u64 last_exec_ns;
    __u64 last_io_ns;
    __u64 last_sock_ns;
};

struct {
    __uint(type, BPF_MAP_TYPE_RINGBUF);
    __uint(max_entries, 1 << 20);
} events SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 1);
    __type(key, __u32);
    __type(value, __u64);
} loss SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 1024);
    __type(key, __u64);
    __type(value, __u8);
} selected SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_PERCPU_HASH);
    __uint(max_entries, 1024);
    __type(key, __u64);
    __type(value, struct cgroup_stats);
} cgroups SEC(".maps");

static __always_inline struct cgroup_stats *lookup_selected(__u64 *cgroup_out)
{
    __u64 cgroup = bpf_get_current_cgroup_id();
    if (!bpf_map_lookup_elem(&selected, &cgroup))
        return 0;
    *cgroup_out = cgroup;
    return bpf_map_lookup_elem(&cgroups, &cgroup);
}

SEC("tracepoint/sched/sched_process_exec")
int on_exec(void *ctx)
{
    (void)ctx;
    __u64 cgroup = 0;
    struct cgroup_stats *s = lookup_selected(&cgroup);
    if (!s)
        return 0;
    __u64 ts = bpf_ktime_get_ns();
    s->exec_count += 1;
    s->last_exec_ns = ts;

    struct event *e = bpf_ringbuf_reserve(&events, sizeof(*e), 0);
    if (!e) {
        __u32 key = 0;
        __u64 *count = bpf_map_lookup_elem(&loss, &key);
        if (count)
            __sync_fetch_and_add(count, 1);
        return 0;
    }
    __u64 id = bpf_get_current_pid_tgid();
    e->timestamp_ns = ts;
    e->cgroup_id = cgroup;
    e->pid = (__u32)id;
    e->tgid = id >> 32;
    bpf_get_current_comm(e->comm, sizeof(e->comm));
    bpf_ringbuf_submit(e, 0);
    return 0;
}

SEC("tracepoint/sched/sched_process_fork")
int on_fork(void *ctx)
{
    (void)ctx;
    __u64 cgroup = 0;
    struct cgroup_stats *s = lookup_selected(&cgroup);
    if (!s)
        return 0;
    s->fork_count += 1;
    return 0;
}

SEC("tracepoint/sched/sched_process_exit")
int on_exit(void *ctx)
{
    (void)ctx;
    __u64 cgroup = 0;
    struct cgroup_stats *s = lookup_selected(&cgroup);
    if (!s)
        return 0;
    s->exit_count += 1;
    return 0;
}

SEC("fexit/vfs_read")
int BPF_PROG(on_vfs_read, struct file *file, char *buf, size_t count, loff_t *pos, ssize_t ret)
{
    (void)buf;
    (void)count;
    (void)pos;
    if (ret <= 0)
        return 0;
    __u64 cgroup = 0;
    struct cgroup_stats *s = lookup_selected(&cgroup);
    if (!s)
        return 0;
    struct inode *inode = BPF_CORE_READ(file, f_inode);
    if (!inode)
        return 0;
    umode_t kind = BPF_CORE_READ(inode, i_mode) & S_IFMT;
    if (kind != S_IFREG && kind != S_IFBLK)
        return 0;
    s->io_read_bytes += (__u64)ret;
    s->io_events += 1;
    s->last_io_ns = bpf_ktime_get_ns();
    return 0;
}

SEC("fexit/vfs_write")
int BPF_PROG(on_vfs_write, struct file *file, const char *buf, size_t count, loff_t *pos, ssize_t ret)
{
    (void)buf;
    (void)count;
    (void)pos;
    if (ret <= 0)
        return 0;
    __u64 cgroup = 0;
    struct cgroup_stats *s = lookup_selected(&cgroup);
    if (!s)
        return 0;
    struct inode *inode = BPF_CORE_READ(file, f_inode);
    if (!inode)
        return 0;
    umode_t kind = BPF_CORE_READ(inode, i_mode) & S_IFMT;
    if (kind == S_IFREG || kind == S_IFBLK) {
        s->io_write_bytes += (__u64)ret;
        s->io_events += 1;
        s->last_io_ns = bpf_ktime_get_ns();
    } else if (kind == S_IFSOCK) {
        s->sock_tx_bytes += (__u64)ret;
        s->sock_events += 1;
        s->last_sock_ns = bpf_ktime_get_ns();
    }
    return 0;
}

SEC("fexit/sock_sendmsg")
int BPF_PROG(on_sock_sendmsg, struct socket *sock, struct msghdr *msg, int ret)
{
    (void)sock;
    (void)msg;
    if (ret <= 0)
        return 0;
    __u64 cgroup = 0;
    struct cgroup_stats *s = lookup_selected(&cgroup);
    if (!s)
        return 0;
    s->sock_tx_bytes += (__u64)ret;
    s->sock_events += 1;
    s->last_sock_ns = bpf_ktime_get_ns();
    return 0;
}

SEC("fexit/sock_recvmsg")
int BPF_PROG(on_sock_recvmsg, struct socket *sock, struct msghdr *msg, int flags, int ret)
{
    (void)sock;
    (void)msg;
    (void)flags;
    if (ret <= 0)
        return 0;
    __u64 cgroup = 0;
    struct cgroup_stats *s = lookup_selected(&cgroup);
    if (!s)
        return 0;
    s->sock_rx_bytes += (__u64)ret;
    s->sock_events += 1;
    s->last_sock_ns = bpf_ktime_get_ns();
    return 0;
}

char LICENSE[] SEC("license") = "GPL";
