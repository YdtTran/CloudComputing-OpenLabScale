# Kịch bản seminar eBPF (45 phút)

| Người trình bày (MSSV) | Phần phụ trách | Trang PDF | Thời lượng mục tiêu |
| --- | --- | --- | ---: |
| **Trần Đình Ý** (`2414100`) | Mở đầu, Chương 1 & Chương 2 (Giới thiệu & Kiến trúc) | 1–15 | 13 phút |
| **Nguyễn Phúc Vĩnh** (`2414001`) | Chương 3 (Phát triển, BTF/CO-RE, Công cụ & `openat()`) | 16–26 | 13 phút |
| **Trần Văn Minh Triết** (`2413603`) | Chương 4 (Hệ thống thật, Cilium/Tetragon, Demo overhead & Kết luận) | 27–40 | 13 phút |
| **Cả nhóm** | Hỏi – Đáp (Q&A) | — | 6 phút |
| **Tổng cộng** | | **40 trang** | **45 phút** |

> **Nhịp nói gợi ý:** Khoảng 130–140 từ tiếng Việt/phút, chừa 3–5 giây dừng sau mỗi sơ đồ hoặc bảng số liệu để người nghe kịp nhìn trước khi chuyển slide.

---

## Phần 1 — Trần Đình Ý (`2414100`): Mở đầu, Giới thiệu & Kiến trúc eBPF (Trang 1–15 | 13 phút)

### Slide 1 — Trang bìa (~15 giây)

**Lời thuyết trình:**
Kính chào thầy và các bạn. Hôm nay nhóm VYT gồm mình là Trần Đình Ý, bạn Nguyễn Phúc Vĩnh và bạn Trần Văn Minh Triết xin trình bày seminar về chủ đề **eBPF – Extended Berkeley Packet Filter: Quan sát và xử lý sự kiện trong Linux kernel**.

**Chuyển tiếp:**
Trước khi đi vào chi tiết kỹ thuật, mình xin giới thiệu nhanh bố cục bài trình bày và phân công của ba thành viên.

---

### Slide 2 — Nội dung trình bày và thành viên (~30 giây)

**Lời thuyết trình:**
Bài seminar hôm nay gồm bốn phần lớn, tương ứng khoảng 39 phút trình bày kèm demo thực nghiệm trực tiếp và 6 phút thảo luận hỏi đáp. Mình phụ trách Chương 1 và Chương 2, đặt nền tảng vì sao cần eBPF và kiến trúc bên trong Linux kernel. Tiếp theo, bạn Vĩnh sẽ trình bày Chương 3 về quy trình phát triển, BTF và CO-RE, bộ công cụ `bpftool`/`bpftrace`/`libbpf` cùng ví dụ `openat()`. Cuối cùng, bạn Triết sẽ trình bày Chương 4 về ứng dụng eBPF trong Cilium, Hubble, Tetragon, chạy demo đo overhead bốn làn song song và tổng kết các giới hạn vận hành.

**Chuyển tiếp:**
Mình xin bắt đầu với Chương 1: Giới thiệu eBPF.

---

### Slide 3 — Chương 1: Giới thiệu eBPF (~15 giây)

**Lời thuyết trình:**
Ở Chương 1, câu hỏi đầu tiên chúng ta đặt ra là: từ bài toán quan sát hoạt động thực tế trên Linux, vì sao các công cụ truyền thống chưa đủ và điều gì đã dẫn đến sự ra đời của eBPF?

---

### Slide 4 — Container này có đang được sử dụng? (~60 giây)

**Lời thuyết trình:**
Hãy xét một tình huống rất quen thuộc trong hệ thống tính toán dùng chung, nơi mỗi phiên làm việc chạy bên trong một container riêng. Khi nhìn vào bảng giám sát tài nguyên, quản trị viên thấy mức sử dụng CPU của một container xuống rất thấp, gần như bằng không. Câu hỏi đặt ra là: chỉ nhìn vào CPU thấp thì có đủ để kết luận container đó đang rảnh và thu hồi tài nguyên hay không?

Câu trả lời là chưa chắc. Trên slide là một ví dụ điển hình: người dùng đang tải một bộ dữ liệu lớn. Trong lúc tiến trình chờ nhận các gói dữ liệu qua mạng rồi ghi tuần tự xuống đĩa, CPU gần như rảnh, nhưng container thực chất vẫn đang làm việc tích cực. Ngoài ra, có thể tiến trình đang đọc/ghi file, mở kết nối socket hoặc chờ thao tác nhập liệu từ người dùng. Tất cả những hoạt động vào và ra đó được gọi chung là I/O. Vậy trước khi quyết định thu hồi tài nguyên, làm sao chúng ta quan sát được từng container còn đang đọc, ghi hay truyền dữ liệu qua mạng ở mức hệ điều hành?

**Chuyển tiếp:**
Để trả lời câu hỏi đó, hãy điểm qua bốn cách tiếp cận truyền thống trên Linux và đánh đổi của từng cách.

---

### Slide 5 — Các phương pháp truyền thống (~75 giây)

**Lời thuyết trình:**
Cách đầu tiên là **Application Logging**, tức ứng dụng tự chủ động ghi sự kiện ra log. Cách này dễ triển khai và rất giàu ngữ cảnh nghiệp vụ, nhưng log chỉ ghi những gì lập trình viên đã viết sẵn. Nó không cho thấy toàn cảnh hành vi bên trong kernel, và nếu cần thêm loại sự kiện mới, ta buộc phải sửa mã nguồn, biên dịch và triển khai lại từng ứng dụng.

Nhóm thứ hai là **Tracing và Profiling** ở mức hệ thống, tiêu biểu là `strace` và `perf`. `strace` dùng cơ chế `ptrace` để chặn và theo dõi từng system call mà tiến trình gọi xuống kernel, rất hữu ích khi debug nhưng buộc tiến trình phải tạm dừng hai lần mỗi syscall, gây chi phí cực lớn trên tải cao. `perf` linh hoạt hơn với khả năng đếm sự kiện và lấy mẫu, nhưng khi cần thu thập chi tiết từng sự kiện hoặc lọc theo điều kiện phức tạp, chi phí đưa dữ liệu ra user space vẫn tăng nhanh.

Cách cuối cùng là viết **Kernel Module** để mở rộng trực tiếp kernel. Phương pháp này cực kỳ mạnh về hiệu năng và quyền truy cập, nhưng chỉ một lỗi nhỏ về con trỏ hoặc bộ nhớ ở đặc quyền kernel cũng có thể làm sập toàn bộ máy chủ.

**Chuyển tiếp:**
Như vậy, mỗi phương pháp đều đánh đổi giữa chi phí, khả năng tùy biến và tính an toàn. eBPF xuất hiện để dung hòa cả ba yếu tố này.

---

### Slide 6 — eBPF mở rộng khả năng của Linux kernel (~60 giây)

**Lời thuyết trình:**
Bảng so sánh trên slide cho thấy khác biệt cốt lõi giữa việc sửa mã nguồn kernel hoặc viết kernel module truyền thống với eBPF. Nếu sửa kernel, ta phải biên dịch lại nhân và khởi động lại máy; còn kernel module chạy với toàn quyền truy cập bộ nhớ nên rủi ro cao cho độ ổn định hệ thống.

Ngược lại, eBPF cho phép nạp các chương trình nhỏ vào kernel đang chạy thông qua BPF API mà không cần khởi động lại máy hay sửa mã nguồn ứng dụng. Trước khi cho phép chạy, thành phần **Verifier** của kernel sẽ kiểm tra tĩnh toàn bộ chương trình để bảo đảm an toàn, và phạm vi thực thi bị giới hạn chặt theo từng loại chương trình và điểm gắn (hook). Nhờ vậy, chỉ với một tracepoint tại `openat()`, ta có thể đếm yêu cầu mở tệp của mọi tiến trình ngay từ host.

**Chuyển tiếp:**
Để hiểu rõ eBPF làm điều đó như thế nào bên dưới, chúng ta cùng chuyển sang Chương 2: Kiến trúc eBPF.

---

### Slide 7 — Chương 2: Kiến trúc eBPF (~15 giây)

**Lời thuyết trình:**
Trong Chương 2, mình sẽ giải đáp hai câu hỏi trọng tâm: chương trình eBPF nằm ở đâu trong kiến trúc Linux, và các thành phần bên trong phối hợp với nhau theo luồng nào từ lúc viết mã đến khi thu được dữ liệu?

---

### Slide 8 — eBPF nằm ở đâu trong Linux? (~55 giây)

**Lời thuyết trình:**
Nhìn vào sơ đồ phân tầng từ trên xuống dưới, hệ thống Linux vẫn giữ nguyên hai vùng ranh giới rõ rệt là User Space và Kernel Space nằm trên lớp Hardware. Các ứng dụng thông thường chạy ở User Space và giao tiếp với các phân hệ quản lý hệ thống như Scheduler, File System hay Network Stack thông qua system calls.

Chương trình eBPF không chạy ở User Space mà nằm trực tiếp trong **Kernel Space**, gắn vào các điểm **hook** được kernel hỗ trợ sẵn. Ở phía trên, các công cụ hoặc ứng dụng sử dụng thư viện như `bpftrace` hay `libbpf` sẽ đóng vai trò điều phối từ User Space: gọi BPF API để nạp chương trình xuống kernel và thu thập kết quả trả về. Ở đây cần nhấn mạnh rằng mũi tên nét đứt chỉ thể hiện vai trò quản lý từ User Space, chứ toàn bộ logic xử lý sự kiện thật sự diễn ra ngay bên trong nhân Linux.

**Chuyển tiếp:**
Vậy một đoạn mã eBPF đi từ file mã nguồn ở User Space đến khi được kích hoạt trong Kernel Space như thế nào?

---

### Slide 9 — Từ mã nguồn đến thực thi eBPF (~65 giây)

**Lời thuyết trình:**
Sơ đồ này tách rõ hai giai đoạn cần phân biệt. Ở User Space, lập trình viên viết mã nguồn bằng C hoặc Rust rồi biên dịch thành tệp object chứa eBPF bytecode. Sau đó, trình nạp (Loader) ở User Space gọi BPF API để yêu cầu kernel nạp đoạn bytecode đó.

Ngay trong bước nạp ở Kernel Space, **Verifier** đứng ra kiểm tra toàn bộ ràng buộc an toàn. Nếu vi phạm, kernel từ chối nạp ngay lập tức. Nếu hợp lệ và kernel có bật trình biên dịch **JIT**, bytecode sẽ được dịch thành mã máy gốc để chạy với tốc độ phần cứng. Tuy nhiên, chương trình được nạp xong vẫn chưa chạy ngay: bước **Attach** là một bước tách biệt, gắn chương trình vào một hook tương thích. Chỉ khi có sự kiện thật đi qua hook đó, chương trình eBPF mới được kích hoạt thực thi.

**Chuyển tiếp:**
Verifier là chốt chặn bảo vệ kernel khỏi sập nguồn. Hãy xem cụ thể Verifier kiểm tra các nhánh lệnh như thế nào.

---

### Slide 10 — Verifier phân tích nhánh và an toàn bộ nhớ (~75 giây)

**Lời thuyết trình:**
Đây là một ví dụ rất điển hình cho thấy cách Verifier suy luận tĩnh trên từng nhánh điều khiển. Khi chương trình gọi hàm `bpf_map_lookup_elem()` để tìm bộ đếm trong map, kiểu con trỏ trả về không phải con trỏ thông thường mà là kiểu `map_value_or_null` — nghĩa là có thể mang giá trị `NULL` nếu khóa chưa tồn tại.

Ở khung màu đỏ bên trái, đoạn mã truyền thẳng con trỏ `c` vào `__sync_fetch_and_add` mà không kiểm tra. Verifier phát hiện đường thực thi có khả năng giải tham chiếu con trỏ `NULL` nên từ chối nạp ngay với thông báo `invalid mem access 'map_value_or_null'`. Khi ta bổ sung nhánh `if (c)` như bên phải, Verifier thu hẹp kiểu con trỏ trong nhánh đúng thành `map_value` hợp lệ và chấp nhận chương trình. Bên cạnh kiểm tra con trỏ và phạm vi truy cập bộ nhớ, Verifier còn kiểm tra để bảo đảm không có vòng lặp vô hạn, không tràn stack 512 byte và chỉ gọi các helper hợp lệ. Tuy nhiên, điều cần nhớ là Verifier chứng minh chương trình an toàn cho kernel, chứ không chứng minh logic đếm đúng theo nghiệp vụ của chúng ta.

**Chuyển tiếp:**
Sau khi vượt qua Verifier, đoạn bytecode đó thực thi trên mô hình máy ảo như thế nào và giao tiếp với kernel ra sao?

---

### Slide 11 — Máy ảo eBPF, biên dịch JIT và cơ chế Helper (~65 giây)

**Lời thuyết trình:**
Bên dưới lớp Verifier là mô hình máy ảo eBPF VM theo kiến trúc tập lệnh RISC 64-bit. Máy ảo này cung cấp 11 thanh ghi 64-bit từ `R0` đến `R10`, trong đó `R1` đến `R5` dùng để truyền tham số hàm, `R0` chứa giá trị trả về, còn `R10` là con trỏ stack chỉ đọc. Kích thước stack của mỗi chương trình eBPF bị giới hạn cứng ở **512 byte**, buộc lập trình viên phải giữ xử lý gọn nhẹ và đưa các cấu trúc dữ liệu lớn ra BPF map.

Để tránh chi phí thông dịch bytecode mỗi lần có sự kiện, trình biên dịch **JIT (Just-In-Time)** chuyển đổi bytecode đã xác minh sang lệnh gốc của CPU như `x86-64` hoặc `ARM64` ngay lúc nạp. Ngoài ra, chương trình eBPF không được phép gọi tùy ý mọi hàm nội bộ trong nhân Linux; mọi tương tác lấy thời gian, đọc tên tiến trình hay cập nhật map đều phải đi qua tập **BPF Helpers** hoặc **kfuncs** được cấp phép riêng cho từng loại chương trình.

**Chuyển tiếp:**
Vậy chương trình eBPF có thể gắn vào những loại điểm móc (hook) nào trong Linux kernel?

---

### Slide 12 — Các nhóm Hook phổ biến trong Linux kernel (~75 giây)

**Lời thuyết trình:**
Bảng trên slide tóm tắt bốn nhóm hook hay gặp nhất trong thực tế và sự đánh đổi giữa chúng. Đầu tiên là **Tracepoint**, các điểm đánh dấu tĩnh do tác giả kernel đặt sẵn tại những vị trí quan trọng như đầu/cuối system call hoặc bộ lập lịch. Ưu điểm lớn của tracepoint là tính ổn định ABI rất cao qua các phiên bản kernel và chi phí thấp.

Ngược lại, **kprobe** và **kretprobe** cho phép gắn động vào đầu hoặc cuối gần như mọi hàm nội bộ kernel, rất linh hoạt khi cần điều tra sâu, nhưng dễ bị vỡ khi chữ ký hàm thay đổi giữa các phiên bản kernel và có chi phí ngắt cao hơn. Để khắc phục chi phí đó, từ Linux 5.5 có thêm **fentry** và **fexit** dựa trên BTF trampoline: chúng gắn trực tiếp gần như không tốn chi phí bẫy, và riêng `fexit` cho phép đọc cả tham số đầu vào lẫn giá trị trả về trong cùng một hàm. Cuối cùng là **XDP**, **TC** cho đường đi gói tin tốc độ cao và **BPF LSM** cho kiểm soát bảo mật đồng bộ. Nguyên tắc chung là luôn ưu tiên `tracepoint` hoặc `fentry/fexit` nếu có sẵn.

**Chuyển tiếp:**
Khi một sự kiện kích hoạt tại hook, dữ liệu đầu vào mà chương trình eBPF nhận được là gì?

---

### Slide 13 — Khi sự kiện xảy ra, eBPF nhận dữ liệu gì? (~55 giây)

**Lời thuyết trình:**
Mỗi loại hook sẽ truyền vào chương trình eBPF một con trỏ ngữ cảnh (`ctx`) khác nhau, và **Program Type** sẽ quy định cấu trúc của `ctx` đó cũng như tập helper được dùng. Bảng so sánh hai trường hợp tiêu biểu. Với tracepoint `sys_enter_openat`, sự kiện xảy ra khi tiến trình yêu cầu mở tệp; ngữ cảnh chứa các trường tham số của syscall, và chương trình có thể dùng helper như `bpf_get_current_comm()` để lấy tên tiến trình rồi cập nhật map.

Trong khi đó, với **XDP** ở tầng mạng, sự kiện là gói tin vừa đi vào driver card mạng. Ngữ cảnh nhận được là `struct xdp_md` trỏ tới vùng bộ nhớ gói tin, cho phép chương trình kiểm tra header và trả về quyết định xử lý ngay lập tức như `XDP_PASS` để đi tiếp hoặc `XDP_DROP` để hủy gói tin.

**Chuyển tiếp:**
Mỗi lần hàm eBPF chạy đều kết thúc rất nhanh và không giữ lại biến cục bộ trên stack. Vậy trạng thái tích lũy giữa các lần gọi được lưu ở đâu?

---

### Slide 14 — BPF map lưu số đếm giữa các lời gọi (~55 giây)

**Lời thuyết trình:**
Câu trả lời chính là **BPF Map** — các vùng cấu trúc dữ liệu nằm trong Kernel Space, tồn tại độc lập với từng lần gọi chương trình và cho phép chia sẻ trạng thái cả giữa các lần kích hoạt eBPF lẫn giữa Kernel Space với User Space.

Trong luồng minh họa ở đây, mỗi khi tiến trình gọi `openat()`, tracepoint kích hoạt chương trình eBPF; chương trình lấy tên tác vụ `comm` và cộng dồn vào một BPF Hash Map ngay trong nhân. Ở phía User Space, tiến trình Loader không cần nhận từng sự kiện riêng lẻ mà chỉ cần đọc map định kỳ mỗi 5 giây để lấy bảng tổng hợp số lượt gọi theo tên tác vụ như minh họa ở góc dưới.

**Chuyển tiếp:**
Tuy nhiên, không phải mọi bài toán đều dùng chung một loại Hash Map. Hãy xem sự khác biệt giữa các họ BPF Map khi hệ thống chịu tải cao.

---

### Slide 15 — Các họ BPF Map và đánh đổi đồng thời (~65 giây)

**Lời thuyết trình:**
Khi đưa eBPF vào hệ thống có hàng trăm nghìn đến hàng triệu sự kiện mỗi giây trên nhiều nhân CPU, lựa chọn đúng họ BPF Map quyết định trực tiếp đến hiệu năng. Với **HASH** hoặc **ARRAY** tiêu chuẩn, dữ liệu được dùng chung cho mọi CPU; khi nhiều nhân cùng tăng một bộ đếm, ta phải dùng phép cộng nguyên tử hoặc khóa spinlock, dẫn đến tranh chấp cache line giữa các nhân.

Để loại bỏ tranh chấp đó, **PERCPU_HASH** và **PERCPU_ARRAY** cấp phát riêng một bản sao dữ liệu cho từng nhân CPU. Chương trình eBPF ghi trực tiếp không cần khóa trên nhân đang chạy, rồi khi User Space đọc map mới cộng gộp giá trị từ các nhân lại. Cuối cùng, **RINGBUF** là hàng đợi vòng dùng chung từ Linux 5.8, thích hợp khi ứng dụng cần nhận chi tiết từng bản ghi sự kiện; nhưng ở tốc độ quá cao, nếu User Space đọc không kịp, bộ đệm sẽ đầy và đánh rơi sự kiện. Vì vậy, khi chỉ cần thống kê như đếm lượt gọi hay tổng byte, tổng hợp trong kernel bằng `PERCPU` map luôn vượt trội hơn việc đẩy từng sự kiện qua `RINGBUF`.

**Chuyển tiếp:**
Đó là toàn bộ nền tảng kiến trúc của eBPF. Tiếp theo, mình xin nhường phần trình bày cho bạn Nguyễn Phúc Vĩnh để đi sâu vào Chương 3: Quy trình phát triển, công cụ và phân tích chi tiết mã nguồn ví dụ `openat()`.

---

## Phần 2 — Nguyễn Phúc Vĩnh (`2414001`): Chương 3 — Phát triển, Công cụ & Ví dụ `openat()` (Trang 16–26 | 13 phút)

### Slide 16 — Chương 3: Phát triển và công cụ (~15 giây)

**Lời thuyết trình:**
Cảm ơn bạn Ý. Sau khi đã nắm rõ kiến trúc và các thành phần bên trong kernel, ở Chương 3 mình sẽ đi từ góc độ của người phát triển: làm thế nào để viết, biên dịch, kiểm tra và chạy một chương trình eBPF thực tế từ mã nguồn đến lúc quan sát được sự kiện.

---

### Slide 17 — Quy trình xây dựng ứng dụng eBPF với C và `libbpf` (~70 giây)

**Lời thuyết trình:**
Khi phát triển một ứng dụng eBPF hoàn chỉnh bằng C với thư viện `libbpf`, mã nguồn thường được tách làm hai phần: phần kernel viết trong file `.bpf.c` và phần điều khiển ở user space. Sáu bước trên sơ đồ gắn liền với các tạo tác kỹ thuật cụ thể mà lập trình viên thao tác.

Bước 1, trong file `.bpf.c`, ta khai báo map bằng section `SEC(".maps")` và hàm xử lý với `SEC(...)` chỉ rõ loại hook. Bước 2, trình biên dịch `clang -target bpf` biên dịch mã nguồn thành file object ELF `.bpf.o` chứa cả bytecode lẫn metadata kiểu dữ liệu BTF. Bước 3, loader ở user space dùng `libbpf` mở file object đó và nạp xuống kernel, kích hoạt Verifier và JIT. Bước 4, `libbpf` gắn chương trình vào hook và trả về một `bpf_link` để quản lý vòng đời gắn kết. Bước 5, khi sự kiện xảy ra, chương trình thực thi và cập nhật map. Và bước 6, ứng dụng user space đọc dữ liệu tổng hợp qua `map_fd` hoặc tiêu thụ sự kiện từ `ringbuf`.

**Chuyển tiếp:**
Một câu hỏi rất tự nhiên ở Bước 2 và Bước 3 là: file nhị phân `.bpf.o` biên dịch trên máy phát triển liệu có chạy được trên máy chủ dùng phiên bản Linux kernel khác hay không?

---

### Slide 18 — Tính khả chuyển giữa các kernel: BTF và CO-RE (~80 giây)

**Lời thuyết trình:**
Đây từng là điểm yếu lớn của eBPF thế hệ đầu. Các cấu trúc dữ liệu nội bộ như `task_struct` hay `inode` có thể thay đổi vị trí trường dữ liệu qua từng phiên bản Linux kernel. Trước đây, cách tiếp cận của **BCC** truyền thống là nhúng nguyên mã nguồn C vào ứng dụng và mang theo cả bộ biên dịch Clang/LLVM cùng gói `linux-headers` lên từng máy đích để biên dịch lại lúc khởi động, gây tốn RAM, CPU và phụ thuộc nặng nề vào môi trường đích.

Ngày nay, hệ sinh thái eBPF giải quyết triệt để vấn đề này bằng **BTF (BPF Type Format)** và **CO-RE (Compile Once – Run Everywhere)**. Kernel hiện đại tích hợp sẵn mô tả cấu trúc kiểu của chính nó tại `/sys/kernel/btf/vmlinux`. Lập trình viên xuất mô tả này ra một file `vmlinux.h` duy nhất, sử dụng các macro như `BPF_CORE_READ()` khi truy cập trường của struct kernel, và chỉ cần biên dịch một lần bằng `clang -target bpf`. Khi chạy trên máy đích khác phiên bản kernel, thư viện `libbpf` sẽ đọc BTF của máy đích đó và tự động dịch chuyển lại offset các trường trước khi đưa vào Verifier. Nhờ đó, ứng dụng eBPF gọn nhẹ và mang tính khả chuyển cao.

**Chuyển tiếp:**
Bên cạnh `libbpf`, hệ sinh thái eBPF còn có những công cụ nào hỗ trợ phát triển và chẩn đoán hệ thống?

---

### Slide 19 — Công cụ phát triển và sử dụng eBPF (~60 giây)

**Lời thuyết trình:**
Trên thực tế, người dùng và lập trình viên eBPF thường làm việc với bốn công cụ chính bổ trợ cho nhau. Thứ nhất là **bpftool**, công cụ dòng lệnh chính thức đi cùng mã nguồn Linux, giúp kiểm tra khả năng hỗ trợ của kernel và quan sát mọi program, map, link đang hoạt động. Thứ hai là **bpftrace**, ngôn ngữ bậc cao với cú pháp ngắn gọn tương tự `awk`, cực kỳ hữu ích khi cần viết nhanh một phép đo trực tiếp trên terminal.

Thứ ba là **BCC**, tập hợp sẵn hàng chục tiện ích tracing nổi tiếng như `opensnoop`, `execsnoop` hoặc `biolatency` để chẩn đoán hiệu năng nhanh. Và thứ tư là **libbpf**, thư viện C chuẩn hiện đại hỗ trợ CO-RE, phù hợp nhất khi xây dựng agent hoặc hệ thống giám sát chạy dài hạn trong production. Trong các slide tiếp theo, mình sẽ minh họa cách dùng cụ thể của `bpftool`, `bpftrace` và `libbpf`.

**Chuyển tiếp:**
Đầu tiên hãy xem `bpftool` giúp ta kiểm tra môi trường và kiểm chứng chương trình đang chạy ra sao.

---

### Slide 20 — Kiểm tra kernel và đối tượng đang chạy với `bpftool` (~75 giây)

**Lời thuyết trình:**
Trước khi triển khai một chương trình eBPF trên máy chủ mới, câu lệnh đầu tiên nên chạy là `bpftool feature probe` cùng `bpftool btf list`. Chúng cho ta biết chính xác kernel hiện tại có bật BTF, có bật JIT, và hỗ trợ những loại map hay hook nào — giúp phát hiện lỗi thiếu tương thích ngay từ đầu.

Khi một chương trình eBPF đã được nạp vào nhân, lệnh `bpftool prog show` liệt kê toàn bộ các chương trình đang hoạt động cùng ID, loại hook, kích thước mã `xlated` sau verifier, kích thước mã máy `jited`, và danh sách `map_ids` mà chương trình đang tham chiếu. Đặc biệt, trong lúc debug, ta có thể chạy trực tiếp `bpftool map dump name opens` để đọc ngay nội dung bảng băm bên trong kernel ra màn hình shell dưới dạng JSON hoặc hex mà không cần viết thêm công cụ phụ trợ nào.

**Chuyển tiếp:**
Còn khi cần điều tra nhanh một hiện tượng bất thường trên hệ thống mà chưa muốn viết chương trình C, ta dùng `bpftrace`.

---

### Slide 21 — Khảo sát sự kiện nhanh bằng `bpftrace` (~75 giây)

**Lời thuyết trình:**
Slide này trình bày hai câu lệnh một dòng rất gọn của `bpftrace`. Ví dụ đầu tiên gắn vào tracepoint `sys_enter_openat` và gom đếm theo tên tiến trình `comm` bằng cú pháp `@[comm] = count();` — toàn bộ việc sinh bytecode, tạo map, nạp, gắn hook và in kết quả khi nhấn Ctrl+C đều do `bpftrace` tự động hóa.

Ví dụ thứ hai cho thấy sức mạnh tổng hợp ngay trong kernel của `bpftrace`: gắn vào `sys_exit_read` với bộ lọc `args->ret > 0`, rồi gọi `hist(args->ret)` để vẽ trực tiếp biểu đồ phân bố kích thước byte đọc theo lũy thừa của 2. Vậy câu hỏi đặt ra là khi nào dùng `bpftrace` và khi nào dùng `libbpf`? Câu trả lời là `bpftrace` tuyệt vời cho khảo sát, kiểm chứng giả thuyết trong vài giây; còn khi cần tích hợp vào dịch vụ chạy nền ổn định, kiểm soát chặt bộ nhớ và không phụ thuộc runtime LLVM trên máy đích, ta chọn C với `libbpf`.

**Chuyển tiếp:**
Hãy chuyển sang phân tích chi tiết một chương trình C + `libbpf` hoàn chỉnh qua ví dụ xuyên suốt: theo dõi lời gọi `openat()`.

---

### Slide 22 — Ví dụ: Theo dõi lời gọi `openat()` (~55 giây)

**Lời thuyết trình:**
Mục tiêu của ví dụ trong `demo/openat_demo.c` là đếm số lần các tiến trình gọi system call `openat()` để yêu cầu mở tệp hoặc thư mục, rồi thống kê theo tên tác vụ `comm`. Luồng dữ liệu đi qua năm khối: ứng dụng gọi `openat()` đi qua tracepoint `syscalls:sys_enter_openat`; chương trình eBPF đọc `comm` và cập nhật bộ đếm vào eBPF Map; cuối cùng Loader ở user space đọc map định kỳ để hiển thị số đếm tích lũy.

Có hai điểm cần ghi nhớ trước khi xem code: thứ nhất, map nhóm theo `comm` nên các tiến trình khác PID nhưng cùng tên lệnh sẽ được cộng chung; thứ hai, tracepoint tại điểm *entry* chỉ ghi nhận yêu cầu mở tệp chứ chưa xác nhận lời gọi đó thành công hay thất bại.

**Chuyển tiếp:**
Bây giờ mình sẽ đi sâu vào nửa mã nguồn chạy trong kernel của file `openat_demo.c`.

---

### Slide 23 — Phía Kernel: Khai báo Map và hàm đếm `openat()` (~85 giây)

**Lời thuyết trình:**
Trên slide là hai đoạn code trích trực tiếp từ phần `#ifdef __BPF__` trong `demo/openat_demo.c`. Ở cột bên trái, ta định nghĩa khóa `struct process_key` chứa mảng `char comm[16]`, và khai báo bảng băm `opens` theo chuẩn BTF-defined map đặt trong section `SEC(".maps")`, với kiểu `BPF_MAP_TYPE_HASH`, tối đa `1024` mục và giá trị đếm 64-bit `__u64`.

Ở cột bên phải là hàm xử lý `count_openat`, được gắn nhãn `SEC("tracepoint/syscalls/sys_enter_openat")`. Khi sự kiện kích hoạt, hàm gọi helper `bpf_get_current_comm` để chép tên tiến trình hiện tại vào `key.comm`, sau đó tra cứu con trỏ trong map bằng `bpf_map_lookup_elem`. Như bạn Ý đã nhắc ở phần Verifier, ta bắt buộc phải rẽ nhánh `if (counter)`: nếu đã tồn tại, dùng `__sync_fetch_and_add` để cộng nguyên tử thêm 1; nếu chưa tồn tại, gọi `bpf_map_update_elem` với cờ `BPF_NOEXIST` để khởi tạo bằng 1.

**Chuyển tiếp:**
Sau khi biên dịch đoạn mã này thành `openat_demo.bpf.o`, phần User Space ở nửa dưới file làm gì để điều khiển và đọc dữ liệu?

---

### Slide 24 — Phía User Space: Nạp, gắn và đọc Map với `libbpf` (~90 giây)

**Lời thuyết trình:**
Cột bên trái minh họa đúng bốn bước vòng đời chuẩn của `libbpf` trong hàm `main()`. Đầu tiên, `bpf_object__open_file` đọc tệp `openat_demo.bpf.o`; kế đó `bpf_object__load` nạp chương trình qua Verifier và khởi tạo map trong kernel. Tiếp theo, ta tìm chương trình `count_openat` và gọi `bpf_program__attach_tracepoint` để gắn vào nhóm `syscalls`, sự kiện `sys_enter_openat`, nhận về một con trỏ `bpf_link`. Sau cùng là lấy file descriptor của map `opens` bằng `bpf_object__find_map_fd_by_name`. Khi chương trình thoát, ta hủy `link` và đóng object để gỡ hook sạch sẽ.

Ở cột bên phải là vòng lặp đọc map mỗi 5 giây trong `print_counts`. Chương trình dùng `bpf_map_get_next_key` bắt đầu từ `NULL` để duyệt tuần tự từng khóa trong bảng băm, kết hợp `bpf_map_lookup_elem` lấy giá trị đếm và in ra màn hình. Lưu ý thêm rằng trong dự án thực tế, người ta thường chạy `bpftool gen skeleton` để sinh sẵn header `.skel.h` — giúp gọi hàm typed an toàn ngay lúc biên dịch thay vì truyền tên chuỗi dễ gõ nhầm.

**Chuyển tiếp:**
Khi chạy chương trình này trên Linux thật, kết quả thu được trông như thế nào và cần lưu ý những cạm bẫy kỹ thuật nào?

---

### Slide 25 — Kết quả chạy và các lưu ý kỹ thuật của `openat()` (~90 giây)

**Lời thuyết trình:**
Khung bên trái cho thấy đầu ra đặc trưng của `openat_demo` sau mỗi chu kỳ 5 giây: ta thấy rõ các tiến trình hệ thống như `systemd-journal`, `dockerd`, `python3` hay `cat` cùng số lượt gọi `openat()` tích lũy.

Tuy nhiên, nhìn ở góc độ kỹ thuật, một bộ đếm đơn giản như vậy ẩn chứa ba cạm bẫy quan trọng ở cột bên phải. Thứ nhất, `sys_enter_openat` ghi nhận tại thời điểm *bắt đầu* syscall nên đếm cả những lượt mở tệp trả về lỗi như không tìm thấy tệp hoặc thiếu quyền; nếu chỉ cần lượt thành công, ta phải theo dõi thêm `sys_exit_openat` để kiểm tra `ret >= 0`. Thứ hai, Hash Map có giới hạn cứng `1024` mục; khi đầy bảng, các tiến trình mới sẽ không được ghi nhận, đồng thời khi hai CPU cùng gặp một `comm` mới lần đầu tiên và cùng dùng `BPF_NOEXIST`, một luồng có thể trả lỗi `EEXIST` làm hụt đúng 1 lượt khởi tạo đầu. Thứ ba, trường `comm` chỉ chứa tối đa 16 byte theo hằng số `TASK_COMM_LEN` và tiến trình có thể tự đổi tên lúc chạy.

**Chuyển tiếp:**
Ngoài ba giới hạn đó, còn một vấn đề lớn hơn khi mang cách đếm theo `comm` này áp dụng vào môi trường container ở Chương 4.

---

### Slide 26 — Từ tên tác vụ (`comm`) đến định danh Container (`cgroup_id`) (~85 giây)

**Lời thuyết trình:**
Slide này đóng vai trò cầu nối trực tiếp sang phần trình bày của Chương 4. Giả sử trên cùng một máy chủ có Container A và Container B đều chạy ứng dụng Python. Bên trong mỗi container, tiến trình chính đều có `PID = 1` do cơ chế cách ly PID namespace, và ở góc nhìn kernel chung trên host, cả hai tiến trình đều mang cùng tên `comm = "python3"`. Nếu bộ đếm eBPF chỉ dùng `comm` làm khóa như ví dụ vừa rồi, toàn bộ hoạt động mở tệp của Container A và Container B sẽ bị gộp lẫn vào một dòng duy nhất, không thể tách bạch để giám sát.

Giải pháp chuẩn của eBPF ở tầng host là kết hợp `bpf_get_current_pid_tgid()` để lấy PID/TGID thật trên host, và quan trọng hơn là gọi helper `bpf_get_current_cgroup_id()` để lấy định danh cgroup v2 duy nhất của container phát sinh syscall. Nhờ khóa `cgroup_id`, mọi sự kiện mức kernel đều được quy chiếu chính xác về đúng workload container tương ứng.

**Chuyển tiếp:**
Mình xin nhường phần tiếp theo cho bạn Trần Văn Minh Triết để trình bày Chương 4: eBPF trong hệ thống thật, các nền tảng thực tế như Cilium và Tetragon, cùng demo đo lường overhead trực tiếp.

---

## Phần 3 — Trần Văn Minh Triết (`2413603`): Chương 4 — eBPF trong hệ thống thật & Demo Overhead (Trang 27–40 | 13 phút)

### Slide 27 — Chương 4: eBPF trong hệ thống thật (~15 giây)

**Lời thuyết trình:**
Cảm ơn bạn Vĩnh. Ở Chương 4 cuối cùng này, mình sẽ kết nối các mảnh ghép kiến thức vừa học vào các hệ thống cloud-native thực tế: cách eBPF giám sát đa container từ host, vai trò trong Cilium, Hubble và Tetragon, sau đó chạy trực tiếp demo đo chi phí xử lý bốn làn song song, và khép lại bằng các giới hạn vận hành cần biết.

---

### Slide 28 — Các container trên cùng host dùng chung Linux kernel (~55 giây)

**Lời thuyết trình:**
Tiếp nối ý `cgroup_id` mà bạn Vĩnh vừa nêu, sơ đồ này tóm tắt kiến trúc quan sát container ở tầng host. Dù Container A, B, C được cách ly về góc nhìn tài nguyên và không gian tên qua namespaces và cgroups, tất cả các lời gọi hệ thống của chúng đều đi qua chung một Linux kernel duy nhất trên máy chủ vật lý.

Nhờ vậy, ta chỉ cần đặt hook eBPF ở tầng host — hoàn toàn không cần cài agent vào từng container image hay sửa mã nguồn ứng dụng — rồi cho collector đối chiếu `cgroup_id` với metadata container để tách riêng luồng tín hiệu theo từng workload. Ví dụ, số lượt `openat()` theo `cgroup` giúp phát hiện container đang đọc ghi đĩa ngay cả khi CPU thấp, dù vẫn cần kết hợp thêm tín hiệu khác để phân biệt tác vụ nền với tương tác người dùng.

**Chuyển tiếp:**
Từ cơ chế nền tảng đó, bức tranh tổng thể các dự án eBPF trong công nghiệp hiện nay đang phân bố ra sao?

---

### Slide 29 — Từ Linux kernel đến ứng dụng eBPF (~45 giây)

**Lời thuyết trình:**
Sơ đồ kiến trúc từ trang chủ eBPF.io khái quát toàn bộ hệ sinh thái thành ba lớp rõ ràng. Ở đáy là Kernel Runtime gồm Verifier, JIT, BPF Maps và Helper API. Ở giữa là lớp User Space gồm các bộ SDK đa ngôn ngữ như C `libbpf`, Go (`cilium/ebpf`), Rust (`Aya`) giúp nạp chương trình và đọc dữ liệu từ map. Và ở tầng trên cùng là các dự án mã nguồn mở phục vụ ba trụ cột ứng dụng chính: **Networking** (xử lý mạng), **Security** (bảo mật), và **Observability & Tracing** (giám sát).

**Chuyển tiếp:**
Hãy điểm mặt ba dự án tiêu biểu đại diện cho đúng ba trụ cột đó.

---

### Slide 30 — eBPF được ứng dụng ở đâu? (~45 giây)

**Lời thuyết trình:**
Đại diện cho trụ cột **Observability** là bộ công cụ **BCC** cùng hàng loạt tiện ích theo dõi system call, độ trễ đĩa và mạng để chẩn đoán hiệu năng ứng dụng. Đại diện cho **Networking** là **Cilium**, cung cấp hạ tầng kết nối Pod và cân bằng tải Service hiệu năng cao trong Kubernetes. Và đại diện cho **Security** là **Tetragon**, dự án chuyên giám sát hành vi tiến trình, truy cập tệp và thực thi chính sách bảo mật ngay tại thời điểm workload đang chạy. Trong các slide tiếp theo, mình sẽ đi sâu vào cách hoạt động của Cilium và Tetragon.

**Chuyển tiếp:**
Trước hết, hãy xem Cilium hoạt động như thế nào trong môi trường Kubernetes.

---

### Slide 31 — Cilium là gì? (~45 giây)

**Lời thuyết trình:**
Cilium là dự án tốt nghiệp của CNCF cung cấp plugin mạng CNI chuẩn cho Kubernetes. Khi Kubernetes tạo mới hoặc xóa một Pod, nó gọi plugin CNI của Cilium. Thay vì chỉ dựng các chuỗi luật NAT truyền thống, Cilium Agent sinh và nạp các chương trình eBPF trực tiếp xuống Linux kernel để xử lý gói tin, thiết lập định tuyến giữa các container và áp dụng chính sách mạng ở tốc độ kernel.

**Chuyển tiếp:**
Vậy bên trong một node Kubernetes, Cilium điều phối gói tin, chính sách và khả năng quan sát như thế nào?

---

### Slide 32 — Cilium hoạt động như thế nào? (~55 giây)

**Lời thuyết trình:**
Cilium kết hợp ba nhiệm vụ trên cùng một datapath eBPF. Thứ nhất về **xử lý gói tin**, Cilium Agent trên mỗi node cấu hình chương trình eBPF để chuyển tiếp và cân bằng tải giữa các Pod. Thứ hai về **áp dụng chính sách**, thay vì viết luật tường lửa dựa trên địa chỉ IP dễ thay đổi của Pod, Cilium gán danh tính logic cho từng workload — ví dụ chỉ cho phép Pod có nhãn `frontend` truy cập vào cổng API của dịch vụ đích. Thứ ba về **quan sát luồng mạng**, thành phần **Hubble** gắn liền với Cilium thu thập trực tiếp sự kiện luồng kết nối và hiển thị bản đồ dịch vụ trực quan như ảnh minh họa của Hubble UI bên phải.

**Chuyển tiếp:**
Một câu hỏi kỹ thuật rất hay gặp là: vì sao các cụm Kubernetes lớn lại chọn Cilium để thay thế hoàn toàn `kube-proxy` dựa trên `iptables`?

---

### Slide 33 — Vì sao Cilium thay thế `kube-proxy` (`iptables`)? (~65 giây)

**Lời thuyết trình:**
Bảng so sánh trên slide giải thích lý do hiệu năng phía sau sự chuyển dịch này. Với `kube-proxy` dùng `iptables`, mỗi khi thêm một Service mới, danh sách chuỗi luật Netfilter lại dài thêm, khiến quá trình tra cứu từng gói tin có độ phức tạp tuyến tính $O(N)$. Tệ hơn, mỗi lần một Pod khởi tạo hay bị xóa, toàn bộ bảng luật thường phải được cập nhật lại đồng loạt qua `iptables-restore`.

Ngược lại, Cilium lưu ánh xạ Service và danh sách backend trong **BPF Hash Map**, đưa độ phức tạp tra cứu về hằng số $O(1)$ bất kể cụm có vài chục hay hàng nghìn Service. Khi Pod thay đổi, Agent chỉ cập nhật đúng mục đó một cách nguyên tử vào map. Đặc biệt, Cilium còn hỗ trợ cân bằng tải ngay ở tầng **socket** (`cgroup/connect4`): địa chỉ ClusterIP được dịch sang IP của Pod backend ngay lúc ứng dụng gọi `connect()`, giúp toàn bộ các gói tin sau đó trong kết nối không phải lặp lại bước NAT trên đường đi.

**Chuyển tiếp:**
Sơ đồ ở slide tiếp theo minh họa trực quan cơ chế tra cứu BPF map này của Cilium.

---

### Slide 34 — Cilium cân bằng tải cho Kubernetes Service (~50 giây)

**Lời thuyết trình:**
Trên sơ đồ, một Client Pod gửi yêu cầu tới địa chỉ ảo ClusterIP của Service. Ở phía trên, Cilium Agent luôn theo dõi trạng thái cụm từ API Server và cập nhật bảng ánh xạ các Backend Pod khả dụng vào BPF Map. Khi lưu lượng đi vào Cilium eBPF datapath, chương trình tra cứu trực tiếp map đó với độ phức tạp $O(1)$ để chọn và chuyển tiếp tới một backend phù hợp — ví dụ Backend Pod B như mũi tên nét liền trên hình — mà không cần đi vòng qua chuỗi luật `kube-proxy` ở user space hay `iptables`.

**Chuyển tiếp:**
Đó là góc nhìn mạng với Cilium và Hubble. Còn với trụ cột thứ ba — Bảo mật — eBPF mang lại lợi thế gì qua dự án Tetragon và BPF LSM?

---

### Slide 35 — Bảo mật Runtime trong Kernel với Tetragon và BPF LSM (~65 giây)

**Lời thuyết trình:**
Nếu các hệ thống giám sát bảo mật truyền thống như `auditd` hay thu thập log phải đẩy sự kiện ra user space để phân tích bất đồng bộ, chúng luôn tồn tại một khoảng trễ thời gian (TOCTOU): khi phát hiện một lệnh độc hại chạy hoặc đọc tệp nhạy cảm, tiến trình có thể đã thực thi xong hành động đó rồi mới bị xử lý.

**Tetragon** giải quyết vấn đề này bằng cách đặt logic kiểm tra chính sách trực tiếp trong kernel, gắn với ngữ cảnh Pod và `cgroup` của container. Kết hợp giữa tracepoint/`kprobe` và đặc biệt là **BPF LSM (Linux Security Modules)**, khi một workload gọi `execve` hoặc mở tệp vi phạm chính sách, hook LSM cho phép từ chối đồng bộ bằng mã lỗi `-EPERM` hoặc chấm dứt tiến trình bằng `SIGKILL` ngay trước khi thao tác trong kernel được thực thi xong.

**Chuyển tiếp:**
Bây giờ, để kiểm chứng thực tế lời khẳng định rằng xử lý và tổng hợp dữ liệu ngay trong kernel giúp giảm mạnh chi phí quan sát, mình sẽ trình bày thiết kế bài đo overhead và chạy demo trực tiếp.

---

### Slide 36 — Demo: Thiết kế phép đo overhead bốn làn song song (~55 giây)

**Lời thuyết trình:**
Đây là thí nghiệm đối chứng bốn làn chạy song song trong cùng cửa sổ **5 giây** trên 4 nhân P-core độc lập (`0, 2, 4, 6`). Cả bốn container tải đều chạy cùng một chương trình C gọi liên tục `read()`, trong đó xen kẽ có chủ đích các lượt đọc chậm trên `500 µs`. Bài toán đặt ra cho các công cụ giám sát là: đếm tổng số lượt đọc, tổng số byte và riêng số lượt đọc chậm vượt ngưỡng `500 µs`.

Làn 1 là **Baseline** không gắn công cụ để lấy tốc độ trần. Làn 2 dùng **`strace`** chặn tiến trình qua `ptrace`. Làn 3 dùng **`perf trace`** đẩy từng bản ghi ra user space qua ring buffer. Và làn 4 dùng **eBPF Map** lọc đúng `cgroup_id` và tính ngay trong kernel. Ba tiến trình giám sát được ghim sang 3 nhân E-core riêng (`8, 9, 10`) để bảo đảm không tranh chấp CPU với tải chính.

**Chuyển tiếp:**
Điểm mấu chốt tạo nên khác biệt giữa Làn 2–3 và Làn 4 nằm ở vị trí đặt phép tính trên hai đoạn mã ở slide kế tiếp.

---

### Slide 37 — Demo: Tính ngoài kernel và tính trong kernel (~55 giây)

**Lời thuyết trình:**
Nhìn vào hai khối mã thật từ thư mục `demo/`, bên trái là `userspace_calc.c` dùng cho `strace` và `perf trace`: mọi syscall `read()` đều phải xuất khỏi nhân Linux dưới dạng bản ghi văn bản, đi qua `fgets` để bóc tách chuỗi rồi mới chạy phép so sánh `if (dur_us > 500.0)` và cộng dồn ngoài user space.

Ngược lại, bên phải là `inkernel_calc.c`: phép tính `delta_ns = bpf_ktime_get_ns() - *st` và điều kiện `if (delta_ns > 500000ULL)` chạy ngay trong hook `sys_exit_read`, cộng không khóa vào `PERCPU_ARRAY`. Tiến trình ở user space chỉ việc ngủ yên đủ 5 giây và đọc bảng tổng hợp đúng 1 lần duy nhất lúc kết thúc.

**Chuyển tiếp:**
Bây giờ mình xin chạy trực tiếp lệnh `sh demo/compare-overhead.sh` trên terminal để thầy và các bạn quan sát kết quả thực tế.

---

### Slide 38 — Demo: Kết quả thực nghiệm trong cửa sổ 5 giây (~125 giây, gồm chạy live ~15–20 giây)

*(Thao tác live: chạy `sh demo/compare-overhead.sh` trên terminal khoảng 10–15s rồi đối chiếu bảng 5 cột trên slide.)*

**Lời thuyết trình:**
Như mọi người thấy trên màn hình terminal và bảng đối chiếu từ kết quả đo thực tế trên Debian 13, Linux 6.12 (Intel Core i5-12450HX): đọc từ trái sang phải, ở trạng thái **Baseline** không giám sát, workload đạt gần **1,89 triệu lượt `read()` mỗi giây** với chỉ hơn 1.000 lần chuyển ngữ cảnh.

Khi gắn **`strace`**, do `ptrace` ép dừng tiến trình 2 lần ở mỗi syscall, số lần context switch bùng nổ lên hơn **304 nghìn lần**, kéo throughput rơi thẳng xuống chỉ còn **2%** (~30 nghìn lượt/giây) — chậm hơn eBPF hơn **53 lần**. Với **`perf trace`**, ứng dụng không bị chặn nên throughput giữ được **63%**, nhưng việc đẩy hàng triệu bản ghi qua biên giới kernel–user khiến quá trình đọc và parse chuỗi ngốn trọn một nhân CPU (`5.061 ms` trong cửa sổ 5 giây), truyền `29,7 MB` dữ liệu và vẫn bị đánh rơi hơn **11,5 triệu sự kiện** — kết quả chỉ bắt được **1,9%** số lượt đọc chậm (`214/600`).

Cuối cùng với **eBPF tổng hợp trong kernel map**: vì `0` sự kiện thô phải thoát ra ngoài trong suốt 5 giây, lượng dữ liệu Kernel-to-User chỉ là **288 byte** đọc đúng 1 lần cuối kỳ, CPU giám sát tốn vỏn vẹn **11,3 ms**, throughput giữ được **86%** so với không giám sát và ghi nhận đủ **100%** lượt đọc chậm (`812/812`).

**Chuyển tiếp:**
Tuy hiệu quả vượt trội như vậy, eBPF không phải giải pháp vạn năng không có giới hạn. Slide kế tiếp tóm lược những rào cản kỹ thuật cần cân nhắc khi triển khai thực tế.

---

### Slide 39 — Giới hạn kỹ thuật và đánh đổi khi vận hành eBPF (~65 giây)

**Lời thuyết trình:**
Có bốn đánh đổi quan trọng mà kỹ sư hệ thống phải tính đến. Thứ nhất là **đặc quyền**: trên các bản Linux thương mại, quyền chạy eBPF cho người dùng thường bị tắt; collector vẫn cần các capability nhạy cảm ở host như `CAP_BPF`, `CAP_PERFMON` hay `CAP_NET_ADMIN`. Thứ hai là **phụ thuộc phiên bản kernel và BTF**: các tính năng mới như `RINGBUF`, `fentry/fexit` hay `BPF LSM` đòi hỏi nhân Linux đủ mới và bật sẵn `CONFIG_DEBUG_INFO_BTF`.

Thứ ba là **giới hạn của Verifier và máy ảo**: stack 512 byte và ràng buộc độ phức tạp khiến eBPF không thể thay thế các hệ thống con phức tạp hoặc driver phần cứng, nơi vẫn cần mã nhân truyền thống. Và thứ tư là **chi phí trên đường nóng**: ngay cả trong demo vừa rồi, trên syscall gọi gần 2 triệu lần/giây, eBPF vẫn giảm throughput từ `100%` xuống `86%`. Do đó ở tải cực cao, ta luôn phải lọc sớm theo `cgroup_id` và cộng dồn qua `PERCPU` map thay vì xuất từng sự kiện thô.

**Chuyển tiếp:**
Mình xin đi vào slide kết luận để tổng hợp lại nội dung toàn bài.

---

### Slide 40 — Kết luận (~45 giây)

**Lời thuyết trình:**
Tóm lại qua bốn chương của buổi seminar hôm nay, eBPF đã thay đổi cách chúng ta mở rộng Linux kernel một cách an toàn và linh hoạt mà không cần sửa mã nhân hay khởi động lại hệ thống. Với ba trụ cột gồm **Observability** (thu thập và tổng hợp sự kiện chi phí thấp), **Networking** (xử lý lưu lượng mạng như Cilium) và **Security** (thực thi chính sách đồng bộ như Tetragon/BPF LSM), eBPF giúp các hệ thống giám sát hiện đại kết hợp chính xác bộ đếm sự kiện mức hạt nhân với số liệu CPU và I/O để đánh giá đúng trạng thái từng container.

Phần trình bày của nhóm VYT xin kết thúc tại đây. Rất mong nhận được câu hỏi và góp ý từ thầy và các bạn.

---

## Runbook Demo & Ngân hàng Q&A

### Chuẩn bị & chạy lại demo so sánh overhead (Slides 36–38)

Từ thư mục `eBPF-Extended-Berkeley-Packet-Filter-Seminar/` trên máy Linux có Docker, cgroup v2, BTF, `gcc`, `clang`, `libbpf-dev` và image `ebpf-seminar-bpftrace:local`:

```sh
docker build -t ebpf-seminar-bpftrace:local demo
sh demo/compare-overhead.sh
```

*(Nếu đã build image `ebpf-seminar-bpftrace:local` trước đó, chỉ cần chạy trực tiếp `sh demo/compare-overhead.sh`; script tự biên dịch các file C vào `demo/build/` khi cần và tự dọn toàn bộ container khi xong.)*

### Các câu hỏi thường gặp (Q&A Bank — ~6 phút)

1. **Vì sao ở `strace`, tỷ lệ bắt tổng số lượt đọc đạt `100.0%` nhưng cột lượt chậm chỉ ghi `202/470` (Slide 38)?**
   Vì `read_workload.c` đo độ trễ quanh lời gọi `read()` từ user space (bao gồm cả thời gian tiến trình bị `ptrace` chặn lại trước và sau khi vào kernel), trong khi `strace -T` chỉ đo thời gian thực thi bên trong nhân Linux nên nhiều lượt bị chậm ở góc nhìn ứng dụng nhưng trong kernel vẫn dưới `500 µs`.
2. **Không dùng eBPF có đạt được hiệu năng tương đương không?**
   Có thể đạt tốc độ tương đương bằng cách viết **Kernel Module (LKM)**, dùng bộ đếm cố định sẵn có của kernel (`cgroup`, `perf stat`, `ftrace hist`), hoặc chèn thư viện trực tiếp trong ứng dụng (`LD_PRELOAD`). Tuy nhiên eBPF là cơ chế duy nhất gom đủ cả ba yếu tố cùng lúc: chạy ngay tại kernel, tùy biến logic linh hoạt không sửa ứng dụng, và được Verifier kiểm chứng an toàn trước khi nạp.
3. **BTF + CO-RE giải quyết bài toán khác phiên bản kernel như thế nào mà không cần cài `clang` trên máy đích?**
   Kernel Linux cung cấp mô tả cấu trúc dữ liệu nội bộ tại `/sys/kernel/btf/vmlinux`. Khi biên dịch file `.bpf.c` bằng `clang -target bpf -g`, trình biên dịch ghi lại bảng relocation cho từng trường struct cần đọc qua `BPF_CORE_READ`. Lúc nạp file `.bpf.o` trên máy đích, `libbpf` đối chiếu relocation đó với `/sys/kernel/btf/vmlinux` của máy đích để tự động sửa lại offset cho khớp nhân đang chạy.
4. **Vì sao trong bài đo overhead lại dùng `BPF_MAP_TYPE_PERCPU_ARRAY` thay vì `BPF_MAP_TYPE_HASH` dùng chung?**
   Với `HASH` hay `ARRAY` dùng chung, mỗi lần nhiều CPU cùng cập nhật một bộ đếm phải thực hiện phép toán nguyên tử hoặc spinlock, gây xung đột cache line. `PERCPU_ARRAY` cấp một bản sao riêng cho từng nhân CPU để hàm `sys_exit_read` ghi không cần khóa, sau đó tiến trình user space chỉ cộng gộp các nhân đúng 1 lần khi đọc map.
5. **Khi nào nên dùng `fentry`/`fexit` thay cho cặp tracepoint `sys_enter_read` + `sys_exit_read`?**
   Với tracepoint syscall, muốn đo thời gian thực thi ta phải lưu timestamp lúc `enter` vào map theo TID rồi tra cứu lại lúc `exit`. Nếu hook vào hàm kernel nội bộ bằng trampoline `fexit`, một hàm eBPF duy nhất đọc được cả tham số đầu vào lẫn giá trị trả về, giảm một nửa số lần tra cứu map; tuy nhiên `sys_enter_*`/`sys_exit_*` lại có ưu điểm là giao diện syscall ổn định hơn qua các phiên bản kernel.
6. **Nếu Verifier đã chứng minh an toàn thì tại sao vẫn cần quyền `CAP_BPF` / `CAP_PERFMON` để nạp chương trình eBPF?**
   Verifier bảo đảm chương trình không làm treo hoặc hỏng bộ nhớ kernel, nhưng khả năng gắn hook đọc tham số hệ thống hay chặn gói tin mạng vẫn liên quan đến tính bảo mật dữ liệu và từ chối dịch vụ (ví dụ đọc dữ liệu nhạy cảm giữa các tiến trình hoặc làm chậm đường syscall nóng). Vì vậy quyền nạp phải được kiểm soát qua `CAP_BPF` kết hợp `CAP_PERFMON` (tracing) hoặc `CAP_NET_ADMIN` (mạng).
