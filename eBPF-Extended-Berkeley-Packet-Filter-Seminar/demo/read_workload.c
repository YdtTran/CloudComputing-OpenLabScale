#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/timerfd.h>
#include <time.h>
#include <unistd.h>

#ifndef PR_SET_PTRACER
#define PR_SET_PTRACER 0x59616d61
#endif
#ifndef PR_SET_PTRACER_ANY
#define PR_SET_PTRACER_ANY ((unsigned long)-1)
#endif

#define FAST_FD 99
#define SLOW_FD 100
#define READY_FD 98
#define SLOW_THRESHOLD_NS 500000ULL
#define SLOW_DELAY_NS 1200000L
#define SLOW_EVERY 10000ULL

static inline uint64_t monotonic_ns(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}

static int write_result_atomic(const char *path, const char *tmp_path, const char *line)
{
    FILE *fp = fopen(tmp_path, "w");
    if (!fp)
        return -1;
    if (fputs(line, fp) == EOF || fflush(fp) != 0) {
        fclose(fp);
        return -1;
    }
    fclose(fp);
    return rename(tmp_path, path);
}

int main(int argc, char **argv)
{
    uint64_t duration_ms = 5000;
    if (argc > 1) {
        unsigned long parsed = strtoul(argv[1], NULL, 10);
        if (parsed >= 500 && parsed <= 60000)
            duration_ms = (uint64_t)parsed;
    }

    (void)prctl(PR_SET_PTRACER, PR_SET_PTRACER_ANY, 0, 0, 0);

    int zfd = open("/dev/zero", O_RDONLY);
    if (zfd < 0) {
        perror("open /dev/zero");
        return 1;
    }
    if (dup2(zfd, READY_FD) < 0 || dup2(zfd, FAST_FD) < 0) {
        perror("dup2 /dev/zero");
        return 1;
    }
    if (zfd != READY_FD && zfd != FAST_FD)
        close(zfd);

    int tfd = timerfd_create(CLOCK_MONOTONIC, 0);
    if (tfd < 0) {
        perror("timerfd_create");
        return 1;
    }
    if (dup2(tfd, SLOW_FD) < 0) {
        perror("dup2 timerfd");
        return 1;
    }
    if (tfd != SLOW_FD)
        close(tfd);

    char buf[64];
    struct timespec pause_ts = { .tv_sec = 0, .tv_nsec = 20000000L };

    /* Warmup / Sync phase: emit fd=98 probes so attached tracers flush stdio buffers */
    while (access("/sync/go", F_OK) != 0) {
        for (int i = 0; i < 80; i++) {
            ssize_t r = read(READY_FD, buf, 1);
            (void)r;
        }
        nanosleep(&pause_ts, NULL);
    }

    struct rusage ru0, ru1;
    getrusage(RUSAGE_SELF, &ru0);
    uint64_t t0 = monotonic_ns();
    uint64_t deadline = t0 + duration_ms * 1000000ULL;

    uint64_t actual_reads = 0;
    uint64_t actual_slow = 0;
    uint64_t actual_bytes = 0;
    uint64_t iter = 0;
    uint64_t now = t0;

    while (now < deadline) {
        ssize_t ret;
        uint64_t r0, r1;

        if ((iter % SLOW_EVERY) == 0) {
            struct itimerspec its = {
                .it_interval = {0, 0},
                .it_value = { .tv_sec = 0, .tv_nsec = SLOW_DELAY_NS }
            };
            uint64_t exp = 0;
            timerfd_settime(SLOW_FD, 0, &its, NULL);
            r0 = monotonic_ns();
            ret = read(SLOW_FD, &exp, sizeof(exp));
            r1 = monotonic_ns();
        } else {
            r0 = monotonic_ns();
            ret = read(FAST_FD, buf, sizeof(buf));
            r1 = monotonic_ns();
        }

        if (ret > 0) {
            actual_reads += 1;
            actual_bytes += (uint64_t)ret;
            if ((r1 - r0) > SLOW_THRESHOLD_NS)
                actual_slow += 1;
        }
        iter += 1;
        now = r1;
    }

    uint64_t t1 = monotonic_ns();
    getrusage(RUSAGE_SELF, &ru1);

    long ctx_sw = (ru1.ru_nvcsw - ru0.ru_nvcsw) + (ru1.ru_nivcsw - ru0.ru_nivcsw);
    double wall_ms = (double)(t1 - t0) / 1e6;

    char line[256];
    snprintf(line, sizeof(line),
             "DONE reads=%llu slow=%llu bytes=%llu wall_ms=%.2f ctx_sw=%ld\n",
             (unsigned long long)actual_reads,
             (unsigned long long)actual_slow,
             (unsigned long long)actual_bytes,
             wall_ms,
             ctx_sw);

    if (write_result_atomic("/out/workload.txt", "/out/workload.txt.tmp", line) != 0) {
        perror("write /out/workload.txt");
        return 1;
    }
    fputs(line, stdout);
    fflush(stdout);

    struct timespec hold_ts = { .tv_sec = 60, .tv_nsec = 0 };
    nanosleep(&hold_ts, NULL);
    return 0;
}
