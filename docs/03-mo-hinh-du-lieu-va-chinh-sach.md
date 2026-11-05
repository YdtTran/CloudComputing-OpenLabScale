# 03 — Mô hình Dữ liệu, Bất biến Thiết kế & Chính sách Thu hồi

Cốt lõi tính tái lập và tính trung thực của **OpenLab-Scale** nằm ở hợp đồng dữ liệu chuẩn hóa (`v1` Bundle Contract), nguyên lý nhân quả hai đồng hồ và hệ thống 4 bất biến an toàn.

---

## 1. Chuẩn Gói Dữ liệu `v1` Bundle Contract

Mỗi tập thực nghiệm (dù là mô phỏng ngoại tuyến hay chạy trên máy chủ thực tế) đều được lưu trữ thành một gói thư mục tự chứa (*self-contained bundle*) tuân thủ schema `1.0`.

### Cấu trúc 5 Bảng CSV và Tệp Manifest

1. **`sessions.csv`**: Danh mục các phiên container với định danh `session_id`, thời điểm bắt đầu `start_ms`, thời điểm kết thúc `end_ms`, kịch bản `scenario`, giới hạn CPU `cpu_limit_cores` và RAM `memory_limit_mb`.
2. **`events.csv`**: Dòng sự kiện rời rạc mức hạt nhân và tương tác (`CLIENT_ATTACH`, `INTERACTION_INPUT`, `PROCESS_EXEC`, `CLIENT_DETACH`,...).
3. **`phases.csv`**: Lịch trình các pha hoạt động nội tại (`interactive`, `cpu_burst`, `io_burst`, `sleep_idle`, `mixed_fault`). Chỉ tồn tại trong mô phỏng; tách biệt hoàn toàn khỏi chính sách.
4. **`observations.csv`**: Các cửa sổ quan sát định lượng 5000ms tổng hợp CPU (`cpu_pct`), RAM (`memory_rss_bytes`), sự kiện kernel (`event_count`), trạng thái tín hiệu (`OK` hoặc `DEGRADED`), cờ nguồn gốc (`source`), và độ trễ công bố (`available_at_ms`).
5. **`truth.csv`**: Nhãn trạng thái mặt đất chuẩn (`ACTIVE`, `IDLE`, `TERMINATED`) được xác lập độc lập từ tín hiệu vòng đời và xác nhận phản hồi tác tử, tuyệt đối không được đọc trong pha dự đoán chính sách.
6. **`manifest.json`**: Tệp kiểm tra toàn vẹn lưu trữ mã băm SHA-256 của từng tệp dữ liệu, siêu dữ liệu môi trường và phiên bản schema.

---

## 2. Nguyên lý Nhân quả Hai Đồng hồ (Two-Clock Causal Gate)

Nhằm đảm bảo các chính sách thu hồi trong thực tế có thể vận hành được và không mắc lỗi nhìn trước tương lai (*lookahead bias*), hệ thống áp đặt hàm chiếu nhân quả `causal_projection(observations, events, decision_ms)` tuân thủ nghiêm ngặt hai mốc thời gian:

$$\text{Tồn tại sự kiện: } at\_ms \le decision\_ms$$
$$\text{Đã truyền tới chính sách: } available\_at\_ms \le decision\_ms$$
$$\text{Đối với cửa sổ quan sát: } window\_end\_ms \le decision\_ms$$

Mọi dữ liệu phát sinh sau `decision_ms` hoặc có độ trễ truyền thông vượt quá `decision_ms` đều bị che giấu hoàn toàn khỏi bộ đánh giá chính sách.

---

## 3. Hệ thống 5 Chính sách Thu hồi Tài nguyên

Hệ thống cung cấp và đánh giá 5 chính sách thu hồi tài nguyên độc lập:

| Chính sách | Mô tả Cơ chế Quyết định | Hành vi khi Tín hiệu Suy giảm (`DEGRADED`) |
| :--- | :--- | :--- |
| **`no-reclaim`** | Baseline thụ động: không bao giờ đề xuất thu hồi container, giữ tài nguyên cho đến khi phiên kết thúc tự nhiên. | Giữ nguyên container (`RETAIN`). |
| **`interaction-timeout`** | Đếm thời gian kể từ sự kiện tương tác (`INTERACTION_INPUT`) hoặc gắn kết client (`CLIENT_ATTACH`) gần nhất. Nếu vượt quá `interaction_timeout_ms` (mặc định 60s), đề xuất `IDLE_CANDIDATE`. | Bỏ qua telemetry phần cứng; chỉ phụ thuộc vào sự kiện kết nối. |
| **`cpu-only`** | Chỉ xem xét mức tiêu thụ CPU từ cgroup v2. Nếu CPU duy trì dưới `cpu_threshold_pct` liên tục trong `quiet_ms` + `hysteresis_ms`, đề xuất `IDLE_CANDIDATE`. Dễ mắc lỗi ngộ nhận nhàn rỗi (*False-Idle*) khi tải I/O. | Vẫn xét ngưỡng CPU nếu trường CPU có giá trị hợp lệ. |
| **`resource-multi`** | Tổng hợp đa chiều: CPU, RAM, I/O đĩa và thông lượng mạng. Chỉ đề xuất nhàn rỗi khi toàn bộ các chỉ số đều dưới ngưỡng yên lặng. | **Từ chối quyết định (`UNKNOWN`)**: nếu bất kỳ kênh đo lường nào thiếu hụt, chính sách từ chối phân loại để đảm bảo an toàn. |
| **`interaction-aware`** | Kết hợp mức tài nguyên đa chiều với trạng thái tương tác client. Nếu client đã ngắt kết nối và toàn bộ tài nguyên rơi vào trạng thái yên lặng, đề xuất thu hồi nhanh chóng. | **Từ chối quyết định (`UNKNOWN`)** khi thiếu kênh đo lường hoặc khi chưa có xác nhận tương tác tin cậy. |

---

## 4. Bốn Bất biến An toàn Tuyệt đối (System Invariants)

Mọi dòng mã trong kho lưu trữ đều phải tuân thủ 4 quy tắc bất biến sau:

1. **Bất biến 1 — Tách biệt nguồn gốc (Provenance Separation)**:  
   Sự kiện eBPF và chỉ số cgroup v2 luôn mang trường `source` phân biệt rõ ràng (`ebpf_collector` vs `cgroup_v2`). Dữ liệu trạng thái phản hồi từ Docker Engine tuyệt đối không được sử dụng làm đặc trưng phân loại nhàn rỗi.
2. **Bất biến 2 — Cách ly nhãn chuẩn (Ground-Truth Isolation)**:  
   Tệp `truth.csv` và `phases.csv` chỉ được đọc bởi bộ chấm điểm (`simulation/scoring.py`), tuyệt đối không được nhập vào `simulation/policies.py` hay bộ điều khiển thực nghiệm.
3. **Bất biến 3 — Chống định danh cũ (Anti-Stale Attribution)**:  
   Bảng ánh xạ `(PID, cgroup_id) -> Container ID` phải bị hủy và làm mới ngay khi container khởi động lại hoặc khi PID kết thúc, ngăn chặn triệt để hiện tượng ghi nhận nhầm sự kiện do Linux tái sử dụng PID.
4. **Bất biến 4 — Không thu hồi mù / tự động (No Unapproved or Degraded Reclaim)**:  
   Đề xuất `IDLE_CANDIDATE` không phải là lệnh tiêu diệt tự động. Mọi hành vi thu hồi bắt buộc thỏa mãn 3 điều kiện: (1) Telemetry tươi mới và hợp lệ, (2) Quản trị viên phê duyệt tường minh, và (3) Khớp đúng Container ID trước khi phát lệnh dừng.
