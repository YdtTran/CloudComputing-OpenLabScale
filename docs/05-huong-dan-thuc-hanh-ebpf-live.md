# 05 — Hướng dẫn Thực hành Nhanh: Quan sát eBPF & Telemetry Trực tiếp (Hands-On Manual Guide)

Tài liệu này ghi lại toàn bộ các thao tác thực chiến đã kiểm chứng trong phiên làm việc thực tế, giúp bạn dễ dàng bắt đầu lại hoặc hướng dẫn thành viên mới hiểu rõ cơ chế vận hành của eBPF và cgroup v2.

---

## 1. Thiết lập Môi trường Ban đầu (Quick Setup)

```bash
# 1. Kích hoạt môi trường ảo Python
source .venv/bin/activate

# 2. Chạy bộ kiểm thử tự động (45 bài test)
python3 -m unittest discover -s tests -v

# 3. Kiểm tra tính sẵn sàng của Kernel, BTF và eBPF
python3 -m measured preflight
```
> **Dấu hiệu thành công**: Lệnh preflight in ra JSON chứa `"status": "attached"`.

---

## 2. Thí nghiệm Tương tác Trực tiếp: Bắt Sự kiện eBPF Bằng Tay

Thí nghiệm này giúp bạn quan sát trực tiếp probe eBPF trong kernel phản ứng tức thì khi một lệnh chạy trong container.

### Bước 1: Khởi chạy một container mục tiêu
```bash
docker run -d --name ebpf-demo --cpus 0.5 -m 256m debian:trixie-slim sleep 3600
```

### Bước 2: Tìm `cgroup_id` (số inode trong nhân Linux)
```bash
CGROUP_PATH=$(docker inspect ebpf-demo --format '{{.Id}}' | xargs -I{} find /sys/fs/cgroup -name "*{}*" | head -n 1)
CGROUP_ID=$(stat -c '%i' "$CGROUP_PATH")
echo "Container cgroup inode: $CGROUP_ID"
```

### Bước 3: Đính kèm Collector eBPF (Terminal 1)
> [!NOTE]
> Lưu ý cờ lệnh CLI của Docker là `--cgroupns host` (khác với cú pháp `cgroup: host` trong tệp docker-compose.yaml).

```bash
docker run --rm -it \
  --cap-drop=ALL --cap-add=SYS_ADMIN \
  --pid=host --cgroupns host --network=none --read-only \
  -v /sys/kernel/tracing:/sys/kernel/tracing:ro \
  -v /sys/kernel/btf:/sys/kernel/btf:ro \
  -v /sys/fs/cgroup:/sys/fs/cgroup:ro \
  measured-collector:local "$CGROUP_ID"
```
Khi thấy dòng:
```json
{"type":"ready","monotonic_ns":...}
```
Nghĩa là eBPF probe đã được nạp vào hạt nhân Linux và đang lắng nghe riêng container này.

### Bước 4: Kích hoạt sự kiện bên trong container (Terminal 2)
Mở một cửa sổ dòng lệnh thứ hai và chạy một lệnh bất kỳ trong container:
```bash
docker exec ebpf-demo ls -la
```

### Bước 5: Quan sát kết quả tại Terminal 1
Ngay lập tức, collector in ra bản ghi:
```json
{"type":"exec","timestamp_ns":16437043653013,"cgroup_id":29799,"pid":425495,"tgid":425495,"received_ns":16437043677812}
```

---

## 3. Cách Đọc và Giải mã Bản ghi JSON eBPF

| Trường dữ liệu | Ý nghĩa Kỹ thuật |
| :--- | :--- |
| `"type": "exec"` | Tracepoint `sched:sched_process_exec` phát hiện lệnh gọi hệ thống `execve()` thành công (tiến trình mới được thực thi). |
| `"cgroup_id": 29799` | Khớp 100% với số inode cgroup của container mục tiêu. BPF Map chỉ lọc đúng container này, loại trừ mọi tiến trình host khác. |
| `"pid": 425495` | Mã định danh luồng (Thread ID / TID) nhìn từ host root PID namespace. |
| `"tgid": 425495` | Mã nhóm luồng (Thread Group ID / PID tiến trình chính). Khi `pid == tgid`, đây là tiến trình độc lập, không phải luồng con. |
| `"timestamp_ns"` | Mốc thời gian nano giây do kernel ghi nhận ngay khi sự kiện phát sinh (`bpf_ktime_get_ns()`). |
| `"received_ns"` | Mốc thời gian nano giây khi tiến trình userspace đọc được từ RingBuffer. |
| **Độ trễ truyền dẫn** | $\text{received\_ns} - \text{timestamp\_ns} \approx 25\,\mu\text{s}$ (siêu thấp, chứng tỏ không bị nghẽn đệm). |

**Ý nghĩa đối với chính sách thu hồi:**
* Container này **đang hoạt động (`ACTIVE`)**, tuyệt đối không nhàn rỗi.
* Bộ đếm `event_count` trong cửa sổ 5000ms tăng thêm ít nhất +1.
* Mọi bộ đếm lùi thời gian nhàn rỗi (30s quiet time) bị thiết lập lại về 0, ngăn chặn việc đề xuất thu hồi nhầm.

---

## 4. Giám sát Lại Container Mà Không Cần Khởi động Lại Container

Do eBPF đính kèm từ tầng kernel bên ngoài, bạn có thể ngắt kết nối (`Ctrl+C`) và gắn lại bất kỳ lúc nào mà container mục tiêu không bị ảnh hưởng.

### Cách 1: Gắn lại nhanh bằng lệnh 1 dòng (Interactive)
```bash
docker run --rm -it \
  --cap-drop=ALL --cap-add=SYS_ADMIN \
  --pid=host --cgroupns host --network=none --read-only \
  -v /sys/kernel/tracing:/sys/kernel/tracing:ro \
  -v /sys/kernel/btf:/sys/kernel/btf:ro \
  -v /sys/fs/cgroup:/sys/fs/cgroup:ro \
  measured-collector:local \
  "$(stat -c '%i' "$(find /sys/fs/cgroup -name "*$(docker inspect ebpf-demo --format '{{.Id}}')*" | head -n 1)")"
```

### Cách 2: Chạy Collector ngầm dưới dạng Daemon
```bash
# Bật collector chạy nền
docker run -d --name ebpf-mon \
  --cap-drop=ALL --cap-add=SYS_ADMIN \
  --pid=host --cgroupns host --network=none --read-only \
  -v /sys/kernel/tracing:/sys/kernel/tracing:ro \
  -v /sys/kernel/btf:/sys/kernel/btf:ro \
  -v /sys/fs/cgroup:/sys/fs/cgroup:ro \
  measured-collector:local \
  "$(stat -c '%i' "$(find /sys/fs/cgroup -name "*$(docker inspect ebpf-demo --format '{{.Id}}')*" | head -n 1)")"

# Xem luồng sự kiện kernel bất cứ lúc nào:
docker logs -f ebpf-mon

# Dừng collector khi xong việc:
docker stop ebpf-mon && docker rm ebpf-mon
```

---

## 5. Dọn dẹp Tài nguyên Thử nghiệm
Khi kết thúc phiên thực hành:
```bash
docker stop ebpf-demo && docker rm ebpf-demo
```
