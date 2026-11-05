# 04 — Hướng dẫn Thực nghiệm & Chỉ số Đánh giá

Tài liệu này cung cấp hướng dẫn vận hành chi tiết (*Runbook*) cho cả hai chế độ: **Mô phỏng ngoại tuyến (Offline Simulation)** và **Đo lường container thực tế trên máy chủ Linux (Live Host Measured Runs)**, cùng phương pháp tính toán các chỉ số nghiệm thu.

---

## 1. Môi trường Yêu cầu & Điều kiện Tiên quyết

* **Python 3.9+**: Hoàn toàn sử dụng thư viện chuẩn (`stdlib`), không cài thêm thư viện bên ngoài (`pip`).
* **Máy chủ Linux (cho chế độ Live Measured)**:
  * Hệ điều hành Linux (khuyến nghị Debian 12 hoặc Ubuntu 22.04+).
  * Kích hoạt cgroup v2 đồng nhất (kiểm tra `grep cgroup2 /proc/filesystems`).
  * Nhân hỗ trợ BPF Type Format (BTF) tại `/sys/kernel/btf/vmlinux`.
  * Docker Engine và Docker Compose v2.

---

## 2. Hướng dẫn Vận hành Ngoại tuyến (`simulation/`)

Chế độ mô phỏng cho phép sinh dữ liệu tất định và kiểm chứng chính sách mà không cần Docker hay quyền root.

### Bước 1: Sinh bộ dữ liệu giả lập (Synthetic Bundle)
```bash
# Sinh 10 phiên giả lập với seed 42
python3 -m simulation generate /tmp/sim-dev42 --seed 42

# Tùy biến quy mô 30 phiên với độ trễ bắt đầu 10s
python3 -m simulation generate /tmp/sim-scale30 \
  --seed 42 \
  --count 30 \
  --start-offset-ms 10000 \
  --cpu-limit-cores 0.5 \
  --memory-limit-mb 256 \
  --overwrite
```

### Bước 2: Kiểm tra tính hợp lệ & Tính toàn vẹn hợp đồng
```bash
# Kiểm tra định dạng schema, thứ tự thời gian và mã băm SHA-256
python3 -m simulation validate /tmp/sim-dev42
```

### Bước 3: Đánh giá & Chấm điểm chính sách
```bash
# Chạy dự đoán chính sách và tính điểm trực tiếp
python3 -m simulation evaluate /tmp/sim-dev42 /tmp/sim-dev42/evaluation

# Hoặc tách biệt rõ ràng pha dự đoán và pha chấm điểm:
python3 -m simulation predict /tmp/sim-dev42 /tmp/sim-dev42/separate-eval
python3 -m simulation score /tmp/sim-dev42 /tmp/sim-dev42/separate-eval
```
Kết quả chấm điểm được xuất tự động thành tệp `metrics.json` và báo cáo phân tích Markdown `report.md`.

---

## 3. Hướng dẫn Đo lường Thực tế trên Máy chủ (`measured/`)

Chế độ đo lường thực thi các container thực tế, đọc telemetry từ cgroup v2 và tracepoint kernel `sched:sched_process_exec` qua eBPF.

### Bước 1: Chạy kiểm tra tiền điều kiện (Preflight Check)
Kiểm tra cấu hình Compose, biên dịch collector container, xác nhận probe đính kèm vào kernel và dọn dẹp sạch sẽ:
```bash
export MEASURED_PROJECT=measured-build-check
docker compose -f compose.measured.yaml config --quiet
python3 -m measured preflight
```

### Bước 2: Chạy thực nghiệm đo lường hoàn chỉnh
```bash
# Thực thi thực nghiệm từ kế hoạch nguồn (source bundle) ra thư mục lưu trữ mới
python3 -m measured run data/measured-v1/source-42 /tmp/measured-run-01
```

Quá trình thực nghiệm diễn ra qua các bước tự động:
1. Xác thực kế hoạch phiên nguồn (`source.py`).
2. Khởi tạo dự án Docker Compose riêng biệt mang tên định danh độc nhất (`MEASURED_PROJECT=measured-<uuid>`).
3. Khởi chạy collector eBPF và đợi tín hiệu sẵn sàng từ kernel tracepoint.
4. Điều phối các container tính toán (`cpu`, `idle`) theo đúng lịch trình.
5. Bộ lấy mẫu `telemetry.py` đọc `/sys/fs/cgroup` và đồng bộ luồng eBPF JSONL vào các cửa sổ 5000ms.
6. Xây dựng nhãn mặt đất (`truth.py`) dựa trên xác nhận phản hồi tác tử.
7. Đóng gói thư mục thành chuẩn `v1` bundle và chạy validation kiểm tra tính hợp lệ.
8. Chạy dự đoán chính sách (`predict`) và đối chiếu ground truth (`score`).
9. Dọn dẹp an toàn các container thuộc sở hữu của phiên chạy.

### Bước 3: Kiểm chứng gói dữ liệu đã đo
```bash
python3 -m tests.live_measured verify data/measured-v1/debian-first-run
```

---

## 4. Các Chỉ số Đánh giá Hiệu năng & Nghiệm thu

Kết quả đánh giá so sánh hiệu quả giữa 5 chính sách dựa trên các tiêu chí toán học chuẩn xác:

* **Tỷ lệ Thu hồi Nhầm (False-Reclaim Rate - $FRR$)**:
  $$FRR = \frac{\text{Số lần đề xuất thu hồi khi container đang ACTIVE}}{\text{Tổng số lần container ở trạng thái ACTIVE}}$$
  *Mục tiêu an toàn*: $FRR$ của các chính sách nâng cao phải bằng 0% hoặc tiệm cận 0%.
* **Tỷ lệ Bắt trúng Nhàn rỗi (Idle Capture Rate - $ICR$)**:
  $$ICR = \frac{\text{Số lần phát hiện IDLE chính xác}}{\text{Tổng thời lượng container thực sự IDLE}}$$
* **Độ trễ Thu hồi (Reclaim Latency)**: Thời gian trung bình từ thời điểm container bắt đầu nhàn rỗi cho đến khi chính sách phát ra khuyến nghị `IDLE_CANDIDATE`.
* **Tỷ lệ Từ chối (Abstention Rate)**: Tỷ lệ các cửa sổ quan sát được gán nhãn `UNKNOWN` khi telemetry bị suy giảm, chứng minh cơ chế Fail-Safe hoạt động đúng thiết kế.
* **Chi phí Vận hành (System Overhead)**: Đo lường mức chiếm dụng CPU (%) và RAM (MiB) của container collector eBPF ở tầng host, chứng minh tính gọn nhẹ của kiến trúc giám sát phi xâm lấn.
