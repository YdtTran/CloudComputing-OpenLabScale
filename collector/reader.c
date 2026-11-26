#include <bpf/libbpf.h>
#include <bpf/bpf.h>
#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#define MAX_TRACKED 1024
#define TASK_COMM_LEN 16

struct event {
    uint64_t timestamp_ns;
    uint64_t cgroup_id;
    uint32_t pid;
    uint32_t tgid;
    char comm[TASK_COMM_LEN];
};

struct cgroup_stats {
    uint64_t exec_count;
    uint64_t fork_count;
    uint64_t exit_count;
    uint64_t io_read_bytes;
    uint64_t io_write_bytes;
    uint64_t io_events;
    uint64_t sock_rx_bytes;
    uint64_t sock_tx_bytes;
    uint64_t sock_events;
    uint64_t last_exec_ns;
    uint64_t last_io_ns;
    uint64_t last_sock_ns;
};

static volatile sig_atomic_t stop;
static void interrupted(int sig) { (void)sig; stop = 1; }

static uint64_t now_ns(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (uint64_t)t.tv_sec * 1000000000ULL + (uint64_t)t.tv_nsec;
}

static void sanitize_comm(const char *src, char *dst, size_t dst_len) {
    size_t i = 0;
    for (; i + 1 < dst_len && src[i] != '\0'; i++) {
        unsigned char c = (unsigned char)src[i];
        dst[i] = (c >= 32 && c <= 126 && c != '"' && c != '\\') ? (char)c : '?';
    }
    dst[i] = '\0';
}

static int received(void *ctx, void *data, size_t size) {
    (void)ctx;
    if (size != sizeof(struct event)) return -EINVAL;
    struct event *e = data;
    char comm[TASK_COMM_LEN];
    sanitize_comm(e->comm, comm, sizeof(comm));
    printf("{\"type\":\"exec\",\"timestamp_ns\":%"PRIu64",\"cgroup_id\":%"PRIu64",\"pid\":%u,\"tgid\":%u,\"comm\":\"%s\",\"received_ns\":%"PRIu64"}\n",
           e->timestamp_ns, e->cgroup_id, e->pid, e->tgid, comm, now_ns());
    return 0;
}

struct tracker {
    int selected_fd;
    int cgroups_fd;
    int ncpus;
    struct cgroup_stats *scratch;
    struct cgroup_stats *zeros;
    uint64_t ids[MAX_TRACKED];
    size_t count;
};

static int tracker_add(struct tracker *tr, uint64_t id) {
    if (!id) return -EINVAL;
    for (size_t i = 0; i < tr->count; i++) {
        if (tr->ids[i] == id) return 0;
    }
    if (tr->count >= MAX_TRACKED) return -ENOSPC;
    if (bpf_map_update_elem(tr->cgroups_fd, &id, tr->zeros, BPF_ANY)) return -errno;
    uint8_t val = 1;
    if (bpf_map_update_elem(tr->selected_fd, &id, &val, BPF_ANY)) {
        int saved = errno;
        bpf_map_delete_elem(tr->cgroups_fd, &id);
        return -saved;
    }
    tr->ids[tr->count++] = id;
    return 0;
}

static int tracker_remove(struct tracker *tr, uint64_t id) {
    if (!id) return -EINVAL;
    bpf_map_delete_elem(tr->selected_fd, &id);
    bpf_map_delete_elem(tr->cgroups_fd, &id);
    for (size_t i = 0; i < tr->count; i++) {
        if (tr->ids[i] == id) {
            tr->ids[i] = tr->ids[--tr->count];
            break;
        }
    }
    return 0;
}

static void emit_snapshot(struct tracker *tr, int loss_fd, int live_mode) {
    uint64_t ts = now_ns();
    uint32_t key = 0;
    uint64_t loss_count = 0;
    int loss_ok = (bpf_map_lookup_elem(loss_fd, &key, &loss_count) == 0);

    if (!live_mode) {
        if (loss_ok)
            printf("{\"type\":\"loss\",\"count\":%"PRIu64",\"received_ns\":%"PRIu64"}\n", loss_count, ts);
        else
            printf("{\"type\":\"loss\",\"count\":null,\"received_ns\":%"PRIu64"}\n", ts);
    }

    printf("{\"type\":\"snapshot\",\"monotonic_ns\":%"PRIu64",\"loss_count\":", ts);
    if (loss_ok) printf("%"PRIu64, loss_count);
    else printf("null");
    printf(",\"cgroups\":{");
    int first = 1;
    for (size_t i = 0; i < tr->count; i++) {
        uint64_t id = tr->ids[i];
        if (bpf_map_lookup_elem(tr->cgroups_fd, &id, tr->scratch)) continue;
        struct cgroup_stats sum = {0};
        for (int c = 0; c < tr->ncpus; c++) {
            struct cgroup_stats *p = &tr->scratch[c];
            sum.exec_count += p->exec_count;
            sum.fork_count += p->fork_count;
            sum.exit_count += p->exit_count;
            sum.io_read_bytes += p->io_read_bytes;
            sum.io_write_bytes += p->io_write_bytes;
            sum.io_events += p->io_events;
            sum.sock_rx_bytes += p->sock_rx_bytes;
            sum.sock_tx_bytes += p->sock_tx_bytes;
            sum.sock_events += p->sock_events;
            if (p->last_exec_ns > sum.last_exec_ns) sum.last_exec_ns = p->last_exec_ns;
            if (p->last_io_ns > sum.last_io_ns) sum.last_io_ns = p->last_io_ns;
            if (p->last_sock_ns > sum.last_sock_ns) sum.last_sock_ns = p->last_sock_ns;
        }
        if (!first) putchar(',');
        first = 0;
        printf("\"%"PRIu64"\":{\"exec\":%"PRIu64",\"fork\":%"PRIu64",\"exit\":%"PRIu64
               ",\"io_read_bytes\":%"PRIu64",\"io_write_bytes\":%"PRIu64",\"io_events\":%"PRIu64
               ",\"sock_rx_bytes\":%"PRIu64",\"sock_tx_bytes\":%"PRIu64",\"socket_events\":%"PRIu64
               ",\"last_exec_ns\":%"PRIu64",\"last_io_ns\":%"PRIu64",\"last_sock_ns\":%"PRIu64"}",
               id, sum.exec_count, sum.fork_count, sum.exit_count,
               sum.io_read_bytes, sum.io_write_bytes, sum.io_events,
               sum.sock_rx_bytes, sum.sock_tx_bytes, sum.sock_events,
               sum.last_exec_ns, sum.last_io_ns, sum.last_sock_ns);
    }
    printf("}}\n");
}

static void handle_control_line(struct tracker *tr, const char *line) {
    while (*line == ' ' || *line == '\t') line++;
    if (*line == '\0') return;
    if (strcmp(line, "quit") == 0) {
        stop = 1;
        return;
    }
    if ((line[0] == '+' || line[0] == '-') && (line[1] == ' ' || line[1] == '\t' || isdigit((unsigned char)line[1]))) {
        const char *p = line + 1;
        while (*p == ' ' || *p == '\t') p++;
        char *end = NULL;
        uint64_t id = strtoull(p, &end, 10);
        if (!id || !end || (*end != '\0' && !isspace((unsigned char)*end))) {
            printf("{\"type\":\"control_error\",\"line\":\"invalid_cgroup_id\"}\n");
            return;
        }
        int err = (line[0] == '+') ? tracker_add(tr, id) : tracker_remove(tr, id);
        if (err)
            printf("{\"type\":\"control_error\",\"op\":\"%c\",\"cgroup_id\":%"PRIu64",\"errno\":%d}\n", line[0], id, -err);
        else
            printf("{\"type\":\"ack\",\"op\":\"%c\",\"cgroup_id\":%"PRIu64"}\n", line[0], id);
    }
}

int main(int argc, char **argv) {
    int result = 1;
    int live_mode = 0;
    int interval_ms = 500;
    struct bpf_object *obj = NULL;
    struct ring_buffer *ring = NULL;
    struct bpf_link *links[7] = {0};
    size_t nlinks = 0;
    struct tracker tr = {0};

    setvbuf(stdout, NULL, _IOLBF, 0);
    signal(SIGTERM, interrupted);
    signal(SIGINT, interrupted);
    signal(SIGPIPE, SIG_IGN);

    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--live") == 0) {
            live_mode = 1;
            if (interval_ms == 500) interval_ms = 1000;
        } else if (strcmp(argv[i], "--interval-ms") == 0 && i + 1 < argc) {
            interval_ms = atoi(argv[++i]);
            if (interval_ms < 100 || interval_ms > 10000) return 2;
        }
    }

    const char *required[] = {
        "/sys/fs/cgroup/cgroup.controllers",
        "/sys/kernel/btf/vmlinux",
        "/sys/kernel/tracing/events/sched/sched_process_exec/id",
    };
    for (size_t i = 0; i < sizeof(required) / sizeof(required[0]); i++) {
        if (access(required[i], R_OK)) {
            fprintf(stderr, "Prerequisite unreadable: %s (errno=%d). Verify the read-only host mount and permissions.\n", required[i], errno);
            return 1;
        }
    }

    tr.ncpus = libbpf_num_possible_cpus();
    if (tr.ncpus <= 0) {
        fprintf(stderr, "libbpf_num_possible_cpus failed: %d\n", tr.ncpus);
        return 1;
    }
    tr.scratch = calloc((size_t)tr.ncpus, sizeof(struct cgroup_stats));
    tr.zeros = calloc((size_t)tr.ncpus, sizeof(struct cgroup_stats));
    if (!tr.scratch || !tr.zeros) goto done;

    obj = bpf_object__open_file("/usr/local/lib/exec.bpf.o", NULL);
    if (libbpf_get_error(obj)) { obj = NULL; goto done; }
    if (bpf_object__load(obj)) goto done;

    tr.selected_fd = bpf_object__find_map_fd_by_name(obj, "selected");
    tr.cgroups_fd = bpf_object__find_map_fd_by_name(obj, "cgroups");
    int events_fd = bpf_object__find_map_fd_by_name(obj, "events");
    int loss_fd = bpf_object__find_map_fd_by_name(obj, "loss");
    if (tr.selected_fd < 0 || tr.cgroups_fd < 0 || events_fd < 0 || loss_fd < 0) goto done;

    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--live") == 0) continue;
        if (strcmp(argv[i], "--interval-ms") == 0) { i++; continue; }
        char *end = NULL;
        uint64_t id = strtoull(argv[i], &end, 10);
        if (!id || !end || *end || tracker_add(&tr, id)) goto done;
    }

    struct bpf_program *prog;
    bpf_object__for_each_program(prog, obj) {
        struct bpf_link *lnk = bpf_program__attach(prog);
        if (libbpf_get_error(lnk)) {
            fprintf(stderr, "Failed to attach BPF program %s (errno=%d)\n", bpf_program__name(prog), errno);
            goto done;
        }
        if (nlinks < sizeof(links) / sizeof(links[0])) links[nlinks++] = lnk;
    }

    ring = ring_buffer__new(events_fd, received, NULL, NULL);
    if (!ring) goto done;

    printf("{\"type\":\"ready\",\"monotonic_ns\":%"PRIu64",\"probes\":[\"sched:sched_process_exec\",\"sched:sched_process_fork\",\"sched:sched_process_exit\",\"fexit:vfs_read\",\"fexit:vfs_write\",\"fexit:sock_sendmsg\",\"fexit:sock_recvmsg\"]}\n", now_ns());

    if (live_mode) {
        int flags = fcntl(STDIN_FILENO, F_GETFL, 0);
        if (flags >= 0) fcntl(STDIN_FILENO, F_SETFL, flags | O_NONBLOCK);
    }

    char inbuf[4096];
    size_t inlen = 0;
    uint64_t next_tick = now_ns() + (uint64_t)interval_ms * 1000000ULL;
    int ring_fd = ring_buffer__epoll_fd(ring);

    while (!stop) {
        uint64_t cur = now_ns();
        int timeout_ms = (cur >= next_tick) ? 0 : (int)((next_tick - cur) / 1000000ULL);
        if (timeout_ms > interval_ms) timeout_ms = interval_ms;
        if (timeout_ms < 10 && cur < next_tick) timeout_ms = 10;

        struct pollfd fds[2];
        nfds_t nfds = 0;
        if (ring_fd >= 0) {
            fds[nfds].fd = ring_fd;
            fds[nfds].events = POLLIN;
            nfds++;
        }
        if (live_mode) {
            fds[nfds].fd = STDIN_FILENO;
            fds[nfds].events = POLLIN;
            nfds++;
        }

        int rc = poll(fds, nfds, timeout_ms);
        if (rc < 0) {
            if (errno == EINTR) continue;
            goto done;
        }

        if (ring_fd >= 0 && (fds[0].revents & POLLIN)) {
            int err = ring_buffer__consume(ring);
            if (err < 0 && err != -EINTR) goto done;
        }

        if (live_mode && nfds > 1 && (fds[nfds - 1].revents & (POLLIN | POLLHUP))) {
            while (1) {
                ssize_t n = read(STDIN_FILENO, inbuf + inlen, sizeof(inbuf) - 1 - inlen);
                if (n > 0) {
                    inlen += (size_t)n;
                    inbuf[inlen] = '\0';
                    char *start = inbuf;
                    char *nl;
                    while ((nl = strchr(start, '\n')) != NULL) {
                        *nl = '\0';
                        if (nl > start && nl[-1] == '\r') nl[-1] = '\0';
                        handle_control_line(&tr, start);
                        start = nl + 1;
                    }
                    size_t rem = (size_t)(inbuf + inlen - start);
                    if (rem > 0 && start != inbuf) memmove(inbuf, start, rem);
                    inlen = rem;
                    if (inlen >= sizeof(inbuf) - 1) inlen = 0;
                } else if (n == 0) {
                    stop = 1;
                    break;
                } else {
                    if (errno == EAGAIN || errno == EWOULDBLOCK) break;
                    if (errno == EINTR) continue;
                    stop = 1;
                    break;
                }
            }
        }

        cur = now_ns();
        if (cur >= next_tick) {
            emit_snapshot(&tr, loss_fd, live_mode);
            while (next_tick <= cur) next_tick += (uint64_t)interval_ms * 1000000ULL;
        }
    }
    result = 0;

done:
    if (result) fprintf(stderr, "Collector failed: verify cgroup v2, tracefs, kernel BPF/BTF support, required BPF/PERFMON privileges and container confinement (errno=%d). No synthetic fallback.\n", errno);
    ring_buffer__free(ring);
    for (size_t i = 0; i < nlinks; i++) bpf_link__destroy(links[i]);
    bpf_object__close(obj);
    free(tr.scratch);
    free(tr.zeros);
    return result;
}
