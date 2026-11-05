FROM debian:trixie-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends clang llvm bpftool libbpf-dev libelf-dev zlib1g-dev gcc libc6-dev make && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY collector/ ./
RUN clang -O2 -g -target bpf -I/usr/include/$(gcc -dumpmachine) -c exec.bpf.c -o exec.bpf.o && gcc -O2 -Wall -Wextra -Werror reader.c -o collector -lbpf -lelf -lz

FROM debian:trixie-slim
RUN apt-get update && apt-get install -y --no-install-recommends libbpf1 libelf1 zlib1g && rm -rf /var/lib/apt/lists/*
COPY --from=build /build/collector /usr/local/bin/collector
COPY --from=build /build/exec.bpf.o /usr/local/lib/exec.bpf.o
ENTRYPOINT ["collector"]
