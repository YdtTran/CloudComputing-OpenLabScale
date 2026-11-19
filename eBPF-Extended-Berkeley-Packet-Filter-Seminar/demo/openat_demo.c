
#ifdef __BPF__

// ===== eBPF program: runs inside the kernel =====

#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>

struct process_key {
    char comm[16];
};

// Map: process name -> openat() call count
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 1024);
    __type(key, struct process_key);
    __type(value, __u64);
} opens SEC(".maps");

SEC("tracepoint/syscalls/sys_enter_openat")
int count_openat(void *ctx)
{
    struct process_key key = {};
    __u64 initial = 1;
    __u64 *counter;

    bpf_get_current_comm(key.comm, sizeof(key.comm));

    counter = bpf_map_lookup_elem(&opens, &key);

    if (counter) {
        __sync_fetch_and_add(counter, 1);
    } else {
        bpf_map_update_elem(&opens, &key,
                            &initial, BPF_NOEXIST);
    }

    return 0;
}

char LICENSE[] SEC("license") = "GPL";

#else

// ===== Userspace application: loads and reads eBPF =====

#include <stdio.h>
#include <signal.h>
#include <unistd.h>
#include <errno.h>
#include <string.h>
#include <bpf/bpf.h>
#include <bpf/libbpf.h>

struct process_key {
    char comm[16];
};

static volatile sig_atomic_t running = 1;

static void stop(int signo)
{
    (void)signo;
    running = 0;
}

static void print_counts(int map_fd)
{
    struct process_key key, next;
    __u64 count;
    int err;

    printf("\n%-16s %s\n", "PROCESS", "OPENAT CALLS");
    printf("-----------------------------\n");

    err = bpf_map_get_next_key(map_fd, NULL, &next);

    while (err == 0) {
        key = next;

        if (bpf_map_lookup_elem(map_fd, &key, &count) == 0)
            printf("%-16.16s %llu\n",
                   key.comm, (unsigned long long)count);

        err = bpf_map_get_next_key(map_fd, &key, &next);
    }

    if (errno != ENOENT)
        perror("Map iteration");
}

int main(void)
{
    struct bpf_object *obj;
    struct bpf_program *prog;
    struct bpf_link *link;
    int map_fd;
    int err;

    signal(SIGINT, stop);
    signal(SIGTERM, stop);

    obj = bpf_object__open_file("openat_demo.bpf.o", NULL);
    if (!obj || libbpf_get_error(obj)) {
        fprintf(stderr, "Cannot open BPF object\n");
        return 1;
    }

    err = bpf_object__load(obj);
    if (err) {
        fprintf(stderr, "BPF load failed: %d\n", err);
        bpf_object__close(obj);
        return 1;
    }

    prog = bpf_object__find_program_by_name(
        obj, "count_openat");

    if (!prog) {
        fprintf(stderr, "Program not found\n");
        bpf_object__close(obj);
        return 1;
    }

    link = bpf_program__attach_tracepoint(
        prog, "syscalls", "sys_enter_openat");

    if (!link || libbpf_get_error(link)) {
        fprintf(stderr, "Tracepoint attach failed\n");
        bpf_object__close(obj);
        return 1;
    }

    map_fd = bpf_object__find_map_fd_by_name(obj, "opens");

    if (map_fd < 0) {
        fprintf(stderr, "Map not found\n");
        bpf_link__destroy(link);
        bpf_object__close(obj);
        return 1;
    }

    printf("Monitoring openat()... Ctrl+C to stop\n");

    while (running) {
        sleep(5);
        print_counts(map_fd);
    }

    bpf_link__destroy(link);
    bpf_object__close(obj);

    return 0;
}

#endif
