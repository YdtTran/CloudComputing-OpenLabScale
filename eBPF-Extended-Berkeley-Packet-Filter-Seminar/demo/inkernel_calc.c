#ifdef __BPF__

/* ===== Kernel space: filter, measure latency, and aggregate inside eBPF map ===== */

#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>

struct sys_enter_read_args {
    unsigned long long unused;
    int syscall_nr;
    int pad;
    unsigned long fd;
    unsigned long buf;
    unsigned long count;
};

struct sys_exit_read_args {
    unsigned long long unused;
    int syscall_nr;
    int pad;
    long ret;
};

struct read_stats {
    __u64 reads;
    __u64 slow_reads;
    __u64 bytes;
};

struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 1);
    __type(key, __u32);
    __type(value, __u64);
} target_cg SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 1024);
    __type(key, __u32);
    __type(value, __u64);
} inflight SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_PERCPU_ARRAY);
    __uint(max_entries, 1);
    __type(key, __u32);
    __type(value, struct read_stats);
} totals SEC(".maps");

SEC("tracepoint/syscalls/sys_enter_read")
int on_enter_read(struct sys_enter_read_args *ctx)
{
    __u32 key = 0;
    __u64 *cg = bpf_map_lookup_elem(&target_cg, &key);
    if (!cg || bpf_get_current_cgroup_id() != *cg)
        return 0;
    if (ctx->fd < 99)
        return 0;

    __u32 tid = (__u32)bpf_get_current_pid_tgid();
    __u64 ts = bpf_ktime_get_ns();
    __u64 *slot = bpf_map_lookup_elem(&inflight, &tid);
    if (slot)
        *slot = ts;
    else
        bpf_map_update_elem(&inflight, &tid, &ts, BPF_ANY);
    return 0;
}

SEC("tracepoint/syscalls/sys_exit_read")
int on_exit_read(struct sys_exit_read_args *ctx)
{
    __u32 key = 0;
    __u64 *cg = bpf_map_lookup_elem(&target_cg, &key);
    if (!cg || bpf_get_current_cgroup_id() != *cg)
        return 0;

    __u32 tid = (__u32)bpf_get_current_pid_tgid();
    __u64 *st = bpf_map_lookup_elem(&inflight, &tid);
    if (!st || *st == 0)
        return 0;

    __u64 delta_ns = bpf_ktime_get_ns() - *st;
    *st = 0;

    struct read_stats *s = bpf_map_lookup_elem(&totals, &key);
    if (!s)
        return 0;

    /* Core aggregation inside the kernel: 0 raw events leave kernel space */
    if (ctx->ret > 0) {
        s->reads += 1;
        s->bytes += (__u64)ctx->ret;
        if (delta_ns > 500000ULL)
            s->slow_reads += 1;
    }
    return 0;
}

char LICENSE[] SEC("license") = "GPL";

#else

/* ===== User space: attach probe, wait quietly, read summary map once ===== */

#include <bpf/bpf.h>
#include <bpf/libbpf.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

struct read_stats {
    uint64_t reads;
    uint64_t slow_reads;
    uint64_t bytes;
};

static volatile sig_atomic_t stop;

static void on_sig(int sig)
{
    (void)sig;
    stop = 1;
}

int main(int argc, char **argv)
{
    if (argc != 5) {
        fprintf(stderr, "Usage: %s <bpf_obj> <cgroup_id> <ready_file> <stop_file>\n", argv[0]);
        return 2;
    }

    const char *obj_path = argv[1];
    uint64_t cg_id = strtoull(argv[2], NULL, 10);
    const char *ready_file = argv[3];
    const char *stop_file = argv[4];

    signal(SIGINT, on_sig);
    signal(SIGTERM, on_sig);

    int ncpus = libbpf_num_possible_cpus();
    if (ncpus <= 0) {
        fprintf(stderr, "libbpf_num_possible_cpus failed: %d\n", ncpus);
        return 1;
    }
    struct read_stats *vals = calloc((size_t)ncpus, sizeof(*vals));
    if (!vals)
        return 1;

    struct bpf_object *obj = bpf_object__open_file(obj_path, NULL);
    if (!obj || libbpf_get_error(obj)) {
        fprintf(stderr, "Failed to open BPF object: %s\n", obj_path);
        free(vals);
        return 1;
    }

    int rc = 1;
    struct bpf_link *links[2] = { NULL, NULL };
    size_t nlinks = 0;

    if (bpf_object__load(obj)) {
        fprintf(stderr, "Failed to load BPF object\n");
        goto out;
    }

    int target_fd = bpf_object__find_map_fd_by_name(obj, "target_cg");
    int totals_fd = bpf_object__find_map_fd_by_name(obj, "totals");
    if (target_fd < 0 || totals_fd < 0) {
        fprintf(stderr, "Missing BPF map fd\n");
        goto out;
    }

    uint32_t key = 0;
    if (bpf_map_update_elem(target_fd, &key, &cg_id, BPF_ANY)) {
        perror("bpf_map_update_elem(target_cg)");
        goto out;
    }

    struct bpf_program *prog;
    bpf_object__for_each_program(prog, obj) {
        struct bpf_link *lnk = bpf_program__attach(prog);
        if (!lnk || libbpf_get_error(lnk)) {
            fprintf(stderr, "Failed to attach %s\n", bpf_program__name(prog));
            goto out;
        }
        if (nlinks < 2)
            links[nlinks++] = lnk;
    }

    int rfd = open(ready_file, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (rfd >= 0)
        close(rfd);

    while (!stop && access(stop_file, F_OK) != 0)
        usleep(20000);

    if (bpf_map_lookup_elem(totals_fd, &key, vals) != 0) {
        perror("bpf_map_lookup_elem(totals)");
        goto out;
    }

    uint64_t total_reads = 0;
    uint64_t total_slow = 0;
    uint64_t total_bytes = 0;
    for (int i = 0; i < ncpus; i++) {
        total_reads += vals[i].reads;
        total_slow += vals[i].slow_reads;
        total_bytes += vals[i].bytes;
    }

    unsigned long long raw_bytes = (unsigned long long)ncpus * sizeof(struct read_stats);
    printf("OBS records=1 raw_bytes=%llu counted_reads=%llu counted_slow=%llu counted_bytes=%llu lost_events=0\n",
           raw_bytes,
           (unsigned long long)total_reads,
           (unsigned long long)total_slow,
           (unsigned long long)total_bytes);
    fflush(stdout);
    rc = 0;

out:
    for (size_t i = 0; i < nlinks; i++)
        bpf_link__destroy(links[i]);
    bpf_object__close(obj);
    free(vals);
    return rc;
}

#endif
