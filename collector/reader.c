#include <bpf/libbpf.h>
#include <bpf/bpf.h>
#include <errno.h>
#include <inttypes.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>

struct event { uint64_t timestamp_ns, cgroup_id; uint32_t pid, tgid; };
static volatile sig_atomic_t stop;
static void interrupted(int sig) { (void)sig; stop = 1; }
static uint64_t now(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (uint64_t)t.tv_sec * 1000000000 + t.tv_nsec;
}
static int received(void *ctx, void *data, size_t size) {
    (void)ctx;
    if (size != sizeof(struct event)) return -EINVAL;
    struct event *e = data;
    printf("{\"type\":\"exec\",\"timestamp_ns\":%"PRIu64",\"cgroup_id\":%"PRIu64",\"pid\":%u,\"tgid\":%u,\"received_ns\":%"PRIu64"}\n",
           e->timestamp_ns, e->cgroup_id, e->pid, e->tgid, now());
    return 0;
}
int main(int argc, char **argv) {
    int result = 1;
    struct bpf_link *link = NULL;
    struct ring_buffer *ring = NULL;
    setvbuf(stdout, NULL, _IOLBF, 0);
    signal(SIGTERM, interrupted);
    signal(SIGINT, interrupted);
    const char *required[] = {"/sys/fs/cgroup/cgroup.controllers", "/sys/kernel/btf/vmlinux",
                             "/sys/kernel/tracing/events/sched/sched_process_exec/id"};
    for (size_t i = 0; i < sizeof(required) / sizeof(required[0]); i++) {
        if (access(required[i], R_OK)) {
            fprintf(stderr, "Prerequisite unreadable: %s (errno=%d). Verify the read-only host mount and permissions.\n", required[i], errno);
            return 1;
        }
    }
    struct bpf_object *obj = bpf_object__open_file("/usr/local/lib/exec.bpf.o", NULL);
    if (libbpf_get_error(obj)) { obj = NULL; goto done; }
    if (bpf_object__load(obj)) goto done;
    int selected = bpf_object__find_map_fd_by_name(obj, "selected");
    for (int i = 1; i < argc; i++) {
        char *end;
        uint64_t id = strtoull(argv[i], &end, 10);
        uint8_t value = 1;
        if (!id || *end || bpf_map_update_elem(selected, &id, &value, BPF_NOEXIST)) goto done;
    }
    link = bpf_program__attach_tracepoint(bpf_object__find_program_by_name(obj, "on_exec"), "sched", "sched_process_exec");
    if (libbpf_get_error(link)) { link = NULL; goto done; }
    ring = ring_buffer__new(bpf_object__find_map_fd_by_name(obj, "events"), received, NULL, NULL);
    if (!ring) goto done;
    printf("{\"type\":\"ready\",\"monotonic_ns\":%"PRIu64"}\n", now());
    uint32_t key = 0;
    int loss = bpf_object__find_map_fd_by_name(obj, "loss");
    while (!stop) {
        int err = ring_buffer__poll(ring, 100);
        if (err < 0 && err != -EINTR) goto done;
        uint64_t count;
        if (bpf_map_lookup_elem(loss, &key, &count))
            printf("{\"type\":\"loss\",\"count\":null,\"received_ns\":%"PRIu64"}\n", now());
        else
            printf("{\"type\":\"loss\",\"count\":%"PRIu64",\"received_ns\":%"PRIu64"}\n", count, now());
    }
    result = 0;
done:
    if (result) fprintf(stderr, "Collector failed: verify cgroup v2, tracefs sched_process_exec, kernel BPF/ring-buffer support, required BPF/perf privileges (verified Debian config: SYS_ADMIN) and container confinement (errno=%d). No synthetic fallback.\n", errno);
    ring_buffer__free(ring);
    bpf_link__destroy(link);
    bpf_object__close(obj);
    return result;
}
