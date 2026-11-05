# 01 — Tổng quan Bài toán & Phạm vi Dự án (OpenLab-Scale)

> **Mã dự án**: OpenLab-Scale (Monitoring-First Proof of Concept)  
> **Học phần**: Điện toán đám mây (Cloud Computing) — HK Fall 2026, ĐH Bách Khoa ĐHQG-HCM  
> **Giảng viên hướng dẫn**: PGS. Thoại Nam  
> **Nhóm thực hiện (VYT Group)**: Nguyễn Phúc Vĩnh (2414001), Trần Văn Minh Triết (2413603), Trần Đình Ý (2414100)

---

## 1. Bối cảnh & Đặt vấn đề

Trong các hạ tầng điện toán đám mây công cộng và các hệ thống phòng thí nghiệm tính toán ảo hóa chia sẻ (Cloud Dev Workspaces, JupyterHub, Remote Container Labs), việc người dùng khởi chạy môi trường nhưng không giải phóng tài nguyên sau khi rời đi là nguyên nhân chính gây lãng phí CPU và RAM.

Ngược lại, người dùng thường khởi chạy các tác vụ chạy ngầm hợp lệ (như biên dịch mã nguồn, tải dữ liệu lớn, hoặc huấn luyện mô hình) rồi ngắt kết nối SSH/Web client. Các phương pháp thu hồi tài nguyên truyền thống bộc lộ ba hạn chế nghiêm trọng:

1. **Fixed-Timeout (Ngắt cố định theo tương tác)**: Đặt một ngưỡng thời gian không có thao tác bàn phím/chuột (ví dụ 30 phút). Cơ chế này chắc chắn sẽ chấm dứt nhầm các tác vụ tính toán nền đang hoạt động tích cực mà không cần người dùng can thiệp trực tiếp.
2. **Polling cgroup / `/proc` chu kỳ thưa (15s–30s)**: Việc lấy mẫu CPU định kỳ với chu kỳ thưa không chỉ bỏ sót các xung tải ngắn hạn (*bursty blindness*), mà còn mắc lỗi **ngộ nhận nhàn rỗi (False-Idle)**: khi một tiến trình chờ I/O đĩa hoặc chờ dữ liệu qua mạng, mức tiêu thụ CPU tiệm cận 0% dù tiến trình đang xử lý nghiệp vụ quan trọng.
3. **In-Container / Sidecar Agent**: Yêu cầu nhúng phần mềm giám sát vào từng container gây tốn dung lượng bộ nhớ phụ trội, xâm lấn môi trường lập trình của người dùng và làm tăng bề mặt tấn công.

---

## 2. Mục tiêu Nghiên cứu

Dự án **OpenLab-Scale** phát triển một nguyên mẫu kiểm chứng (*Proof of Concept*) theo nguyên lý **Monitoring-First**:
* **Phi xâm lấn (Non-invasive)**: Đặt toàn bộ tác tử giám sát ở tầng máy chủ (Host-level), quan sát trực tiếp các sự kiện hạt nhân Linux thông qua **eBPF tracepoints** kết hợp với bộ đếm tài nguyên định lượng từ **cgroup v2**.
* **Đa tín hiệu & Nhận biết suy giảm**: Phân loại trạng thái container bằng cách tích hợp cả hoạt động CPU, I/O, tiến trình và tương tác; tự động chuyển sang trạng thái an toàn `UNKNOWN` (từ chối thu hồi) khi tín hiệu đo lường bị thiếu hụt hoặc suy giảm (*Degraded Telemetry*).
* **An toàn & Có phê duyệt (Human-in-the-Loop)**: Mọi quyết định thu hồi dừng ở mức đề xuất ứng viên (*Idle Candidate*), bắt buộc có sự kiểm duyệt của quản trị viên và xác thực lại định danh (*fencing check*) trước khi phát lệnh dừng container.

### 4 Câu hỏi Nghiên cứu Cốt lõi (Research Questions)

* **RQ1 (Độ tin cậy Telemetry & Ánh xạ)**: Agent eBPF ở tầng host có thể thu thập sự kiện kernel và ánh xạ chính xác `(PID/TGID, cgroup_id)` sang Docker Container ID (kể cả khi tái sử dụng PID hoặc container khởi động lại) với tỷ lệ mất sự kiện kiểm soát được hay không?
* **RQ2 (Độ chính xác Phân loại)**: Bộ phân loại đa tín hiệu cải thiện Precision, Recall, F1 và giảm tỷ lệ thu hồi nhầm (*False Reclaim Rate*) như thế nào so với các baseline Fixed-Timeout và CPU-only trên các kịch bản tải ngắt quãng / chạy nền?
* **RQ3 (Chi phí Vận hành - Overhead)**: Mức tiêu thụ CPU, RAM phụ trội và độ ổn định của eBPF collector trên máy chủ khi bật giám sát so với khi tắt giám sát là bao nhiêu?
* **RQ4 (Tính an toàn khi Thu hồi)**: Quy trình đề xuất `Idle Candidate` kết hợp trạng thái `UNKNOWN`, phê duyệt của Admin, và kiểm tra lại qua `docker inspect` có ngăn chặn triệt để hành vi dừng nhầm container khi telemetry trễ hoặc suy giảm hay không?

---

## 3. Ranh giới & Phạm vi Dự án (Bounded Scope)

| Phân nhóm | Chi tiết Hạng mục Kỹ thuật |
| :--- | :--- |
| **Bắt buộc (In-Scope / P0 MVP)** | • Triển khai trên máy chủ Linux hỗ trợ cgroup v2 và BTF kernel (`/sys/kernel/btf/vmlinux`).<br>• Quản lý 2–10 workload container đồng nhất hạn mức CPU (0.5 core) và RAM (256 MiB) qua Docker Compose.<br>• Bộ sinh tải thực nghiệm có seed ngẫu nhiên cố định kèm trích xuất nhãn chuẩn (*Ground-Truth*) cách ly độc lập.<br>• Thu thập song song sự kiện eBPF (`sched:sched_process_exec`) và số liệu cgroup v2 (`cpu.stat`, `memory.current`), gom cụm cửa sổ 5000ms có gắn nhãn nguồn gốc (*provenance*).<br>• Bộ phân loại 4 trạng thái (`ACTIVE`, `IDLE`, `MIXED`, `UNKNOWN`) và chính sách nhân quả 2 đồng hồ.<br>• Đánh giá định lượng trên 5 chính sách thu hồi và tính toán ma trận nhầm lẫn, tỷ lệ thu hồi nhầm, tỷ lệ bắt trúng nhàn rỗi. |
| **Ngoài phạm vi / Đã hoãn (Out-of-Scope)** | • Bộ cấp phát 100-seat Floating License và hàng duyệt cấp phép phức tạp.<br>• Điều phối phân tán trên cụm nhiều node (Kubernetes Operator / Nomad).<br>• Tự động tiêu diệt container không có kiểm duyệt của con người (*unattended destruction*).<br>• Can thiệp hoặc phân tích nội dung gói tin mạng / tệp tin riêng tư của người dùng bên trong container. |
| **Mở rộng tùy chọn (Optional)** | • Tích hợp adapter giả lập tương tác chuột/bàn phím từ trình duyệt với cơ chế timeout suy biến an toàn (`INTERACTION_UNKNOWN`). |
