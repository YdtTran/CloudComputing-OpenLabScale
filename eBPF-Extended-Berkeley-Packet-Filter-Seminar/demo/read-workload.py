import os
import sys
import threading
import time

read_fd, write_fd = os.pipe()
os.dup2(read_fd, 99)
os.close(read_fd)

while not os.path.exists("/tmp/start"):
    time.sleep(0.02)

slow = 0
for index in range(20):
    if index < int(sys.argv[1]):
        writer = threading.Timer(0.32, os.write, (write_fd, b"x"))
        writer.start()
    else:
        writer = None
        os.write(write_fd, b"x")

    start = time.monotonic_ns()
    assert os.read(99, 1) == b"x"
    slow += time.monotonic_ns() - start > 200_000_000
    if writer:
        writer.join()

print(f"reads=20 slow={slow}", flush=True)
deadline = time.monotonic() + 30
while not os.path.exists("/tmp/after"):
    if time.monotonic() >= deadline:
        sys.exit("No post-detach signal")
    time.sleep(0.02)
os.write(write_fd, b"x")
assert os.read(99, 1) == b"x"
print("after-detach=ok", flush=True)
time.sleep(10)
