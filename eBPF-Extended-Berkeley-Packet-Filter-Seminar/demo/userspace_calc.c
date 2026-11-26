#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

enum mode { MODE_STRACE, MODE_PERF };

static void mark_ready(const char *ready_file, int *ready_sent)
{
    if (*ready_sent)
        return;
    int fd = open(ready_file, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd >= 0)
        close(fd);
    *ready_sent = 1;
}

int main(int argc, char **argv)
{
    if (argc != 4) {
        fprintf(stderr, "Usage: %s <strace|perf> <go_file> <ready_file>\n", argv[0]);
        return 2;
    }

    enum mode m;
    if (strcmp(argv[1], "strace") == 0)
        m = MODE_STRACE;
    else if (strcmp(argv[1], "perf") == 0)
        m = MODE_PERF;
    else
        return 2;

    const char *go_file = argv[2];
    const char *ready_file = argv[3];

    uint64_t records = 0;
    uint64_t raw_bytes = 0;
    uint64_t counted_reads = 0;
    uint64_t counted_slow = 0;
    uint64_t counted_bytes = 0;
    uint64_t lost_events = 0;
    int started = 0;
    int ready_sent = 0;

    char line[4096];
    while (fgets(line, sizeof(line), stdin) != NULL) {
        if (!started && access(go_file, F_OK) == 0)
            started = 1;
        if (started)
            raw_bytes += (uint64_t)strlen(line);

        long fd = -1;
        long long ret = 0;
        double dur_us = 0.0;

        if (m == MODE_STRACE) {
            char *p = strstr(line, "read(");
            if (!p)
                continue;
            char *end = NULL;
            fd = strtol(p + 5, &end, 10);
            if (end == p + 5 || (*end != ',' && *end != '<'))
                continue;
            if (fd == 98) {
                mark_ready(ready_file, &ready_sent);
                continue;
            }
            if (fd < 99)
                continue;

            char *eq = strrchr(p, '=');
            char *lt = eq ? strchr(eq, '<') : NULL;
            if (!eq || !lt)
                continue;
            ret = strtoll(eq + 1, NULL, 10);
            dur_us = strtod(lt + 1, NULL) * 1e6;
        } else {
            if (strncmp(line, "LOST ", 5) == 0) {
                if (started)
                    lost_events += strtoull(line + 5, NULL, 10);
                continue;
            }
            char *p = strstr(line, "read(fd: ");
            if (!p)
                continue;
            fd = strtol(p + 9, NULL, 10);
            if (fd == 98) {
                mark_ready(ready_file, &ready_sent);
                continue;
            }
            if (fd < 99)
                continue;

            char *lp = strchr(line, '(');
            char *eq = strrchr(p, '=');
            if (!lp || lp > p || !eq)
                continue;
            dur_us = strtod(lp + 1, NULL) * 1000.0;
            ret = strtoll(eq + 1, NULL, 10);
        }

        if (ret <= 0)
            continue;

        /* Core aggregation in user space: every syscall must leave the kernel */
        records += 1;
        counted_reads += 1;
        counted_bytes += (uint64_t)ret;
        if (dur_us > 500.0)
            counted_slow += 1;
    }

    printf("OBS records=%llu raw_bytes=%llu counted_reads=%llu counted_slow=%llu counted_bytes=%llu lost_events=%llu\n",
           (unsigned long long)records,
           (unsigned long long)raw_bytes,
           (unsigned long long)counted_reads,
           (unsigned long long)counted_slow,
           (unsigned long long)counted_bytes,
           (unsigned long long)lost_events);
    fflush(stdout);
    return 0;
}
