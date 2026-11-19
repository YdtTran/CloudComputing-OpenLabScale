# Kịch bản seminar eBPF

| Phần | Trang PDF | Thời lượng mục tiêu |
| --- | --- | ---: |
| Giới thiệu | 1–9 | 6 phút |
| Kiến trúc eBPF | 10–15 | 9 phút |
| Phát triển và công cụ | 16–20 | 6 phút |
| eBPF trong hệ thống thật | 21–27 | 7 phút |
| Demo và kết luận | 28–29 | 2 phút |
| **Tổng** | | **30 phút** |

## Slide 4 - Container này có đang được sử dụng?

**Thời lượng:** khoảng 1 phút.

### Mục tiêu

Giúp người nghe thấy vì sao cần quan sát I/O của từng container trước khi cân nhắc thu hồi tài nguyên.

### Lời thuyết trình

Trong một hệ thống tính toán dùng chung, mỗi phiên làm việc có thể chạy trong một container. Bảng giám sát cho thấy một container dùng rất ít CPU. Liệu số liệu đó có đủ để cân nhắc thu hồi tài nguyên?

Một ví dụ là người dùng đang tải một bộ dữ liệu lớn. Container có thể dùng ít CPU trong lúc vẫn nhận dữ liệu qua mạng và ghi xuống đĩa. Cả hai hoạt động đều là dấu hiệu container vẫn đang xử lý công việc.

Trước khi quyết định, ta muốn biết container đó có đang đọc hoặc ghi dữ liệu, gửi hoặc nhận dữ liệu qua mạng hay không. Đó là những hoạt động vào và ra, gọi tắt là I/O. Câu hỏi đặt ra là làm sao quan sát được các hoạt động này trên từng container?

### Thuật ngữ

- **Container:** môi trường riêng để chạy các chương trình trong một phiên tính toán.
- **I/O:** hoạt động vào và ra, chẳng hạn đọc, ghi dữ liệu hoặc gửi, nhận dữ liệu qua mạng. Xem I/O cùng với CPU khi đánh giá hoạt động của container.

### Chuyển tiếp

Khi thấy có hoạt động đọc, ghi hoặc truyền dữ liệu, câu hỏi tiếp theo là chương trình nào tạo ra hoạt động đó. Linux có nhiều công cụ quan sát cho câu hỏi này.

### Nguồn

[Phạm vi đo của dự án](../measured/README.md).

## Slide 5 - Các phương pháp truyền thống

**Thời lượng:** khoảng 1 phút.

### Mục tiêu

Phân biệt vai trò và giới hạn của Application Logging, Tracing & Profiling và Kernel Modules, từ đó đặt eBPF vào đúng bối cảnh.

### Lời thuyết trình

Phương pháp đầu tiên là Application Logging. Ứng dụng chủ động ghi lại những sự kiện mà lập trình viên đã chọn, chẳng hạn khi tiếp nhận một yêu cầu hoặc gặp lỗi. Với những sự kiện đã hỗ trợ ghi log, đây là cách dễ sử dụng để tìm hiểu hoạt động của ứng dụng. Tuy nhiên, log không tự ghi nhận mọi hoạt động bên trong kernel. Nếu thiếu thông tin cần thiết, ta có thể phải sửa ứng dụng để bổ sung log.

Nhóm thứ hai là các công cụ Tracing và Profiling. strace theo dõi system call của tiến trình, nên hữu ích khi kiểm tra ứng dụng đang yêu cầu kernel thực hiện những thao tác nào. perf hỗ trợ phân tích hoạt động và hiệu năng, với nhiều cơ chế như đếm sự kiện hoặc lấy mẫu. Ta chọn công cụ và cấu hình theo câu hỏi cần trả lời. Khả năng tùy biến và chi phí thu thập phụ thuộc vào công cụ, cơ chế theo dõi và lượng dữ liệu cần lấy, nên không thể gán cùng một mức chi phí cho tất cả trường hợp.

Nhóm cuối là Kernel Modules. Đây là cách bổ sung chức năng chạy ở mức kernel, nhưng đòi hỏi hiểu biết chuyên sâu. Mã lỗi chạy với đặc quyền kernel có thể làm hệ thống mất ổn định, thậm chí bị sập.

Những phương pháp này đáp ứng các nhu cầu khác nhau và vẫn có giá trị sử dụng. eBPF bổ sung một cách lập trình logic xử lý sự kiện tại các điểm mà kernel hỗ trợ. Việc lựa chọn vẫn bắt đầu từ nhu cầu quan sát cụ thể của mình.

### Thuật ngữ

- **Application Logging:** cơ chế ứng dụng chủ động ghi lại sự kiện. Thông tin có sẵn phụ thuộc vào mã ứng dụng và cấu hình log.
- **Tracing:** theo dõi các sự kiện trong quá trình thực thi. **strace** là công cụ theo dõi system call và tín hiệu của tiến trình trên Linux.
- **Profiling:** thu thập và phân tích dữ liệu để hiểu cách chương trình hoặc hệ thống sử dụng tài nguyên. **perf** hỗ trợ cả đếm, lấy mẫu và nhiều khả năng tracing, không chỉ có một cơ chế duy nhất.
- **Kernel Module:** mã có thể nạp vào kernel để bổ sung chức năng. Việc phát triển và kiểm thử cần chú ý đến môi trường kernel và ảnh hưởng của lỗi.
- **Chi phí thu thập:** phần CPU, bộ nhớ và công việc xử lý tăng thêm khi đo hoặc theo dõi hệ thống. Slide không đưa ra so sánh hiệu năng tuyệt đối giữa các công cụ.

### Chuyển tiếp

Các công cụ này cung cấp dữ liệu quan sát. Với eBPF, logic tổng hợp còn có thể chạy trong kernel.

### Nguồn

[Python Logging HOWTO](https://docs.python.org/3/howto/logging.html), [strace](https://strace.io/), [Linux perf wiki](https://perfwiki.github.io/main/), [Linux kernel: External Modules](https://docs.kernel.org/kbuild/modules.html).

## Slide 6 — eBPF mở rộng khả năng của Linux kernel

**Thời lượng:** khoảng 1 phút.

Sửa mã nguồn kernel và viết kernel module là hai cách bổ sung chức năng ở mức kernel. Với một phép đo tại hook có sẵn, eBPF cung cấp cách nạp logic vào kernel đang chạy. Kernel kiểm tra chương trình trước khi chấp nhận. Ví dụ, bộ đếm yêu cầu mở tệp có thể chạy mà không cần sửa ứng dụng hoặc khởi động lại máy chủ.

Phép thử đọc chậm sau đây cho thấy dữ liệu đầu ra thay đổi thế nào khi logic tổng hợp chạy ngay trong kernel.

## Slide 7 — Phép thử đếm lượt đọc chậm theo container

**Thời lượng:** khoảng 30 giây.

### Lời thuyết trình

Giả sử đội vận hành muốn biết container nào thường xuyên phải chờ dữ liệu. Ta dùng hai container chạy cùng một chương trình. Mỗi bên đọc 20 lần từ một ống dữ liệu. Ở container A, dữ liệu có sẵn trước khi đọc. Ở container B, bên cấp dữ liệu chờ khoảng 320 ms ở bốn lượt. Hai công cụ quan sát chạy đồng thời và cùng dùng ngưỡng 200 ms.

Với `perf trace`, script bên ngoài kernel nhận các bản ghi lượt đọc rồi đếm theo container. Với eBPF, probe kiểm tra thời lượng và tăng bộ đếm ngay trong kernel. Ta đọc bộ đếm của mỗi container ở mốc 5 giây.

### Chuyển tiếp

Terminal cho thấy số lượt đọc chậm và lượng bản ghi mỗi cách dùng để tính kết quả.

## Slide 8 — Kết quả đo lượt đọc chậm theo container

**Thời lượng:** khoảng 1 phút.

### Lời thuyết trình

Cả hai cách cho cùng kết quả trong lần chạy thật. Container A có 0 lượt chậm, container B có 4. Script phía `perf trace` dùng 40 bản ghi đọc mẫu. Phía eBPF đọc hai giá trị tổng, mỗi container một giá trị. Sau khi dừng bộ giám sát, script kích hoạt thêm một lượt đọc thành công ở cả hai container và kiểm tra PID của chương trình vẫn như ban đầu.

40 là số bản ghi của các lượt đọc mẫu được script tổng hợp. 2 là số giá trị của bộ đếm eBPF ở lần đọc đầu tiên. Phép thử này đo dữ liệu mà chương trình giám sát cần xử lý. Thời gian của `read()` trong demo bao gồm chờ dữ liệu trên ống, không phải độ trễ đĩa.

### Chạy lại demo

Từ thư mục seminar trên Linux có Docker, cgroup v2, BTF và hai tracepoint `syscalls:sys_enter_read` và `syscalls:sys_exit_read`:

```sh
docker build -t ebpf-seminar-bpftrace:local demo
sh demo/compare-slow-reads.sh
```

- [compare-slow-reads.sh](demo/compare-slow-reads.sh) tạo hai container, gắn các công cụ, đối chiếu kết quả với chương trình đọc và kiểm tra hai chương trình đọc tiếp sau khi gỡ.
- [read-workload.py](demo/read-workload.py) tạo hai tải có cùng số lượt đọc và thời gian cấp dữ liệu khác nhau.
- [slow-reads.bt](demo/slow-reads.bt) đo thời gian theo luồng và đếm lượt vượt ngưỡng theo cgroup trong kernel.
- [Đầu ra terminal](demo/slow-reads-run.txt) và [ảnh chụp](images/demo-slow-reads-terminal.png) từ cùng lần chạy.

Container chạy tác vụ không có quyền đặc biệt. Container giám sát dùng `SYS_ADMIN` và các mount kernel chỉ đọc.

### Chuyển tiếp

Hai công cụ cho cùng số lượt chậm dù quy tắc tính chỉ số chạy ở những nơi khác nhau.

## Slide 9 — Phép đo eBPF trên kernel đang chạy

**Thời lượng:** khoảng 1 phút.

### Lời thuyết trình

Ở bên trái, `perf trace` lấy sự kiện theo cgroup. Script đọc thời lượng trong từng dòng và đếm các lượt vượt 200 ms. Ở bên phải, đoạn mã bpftrace làm phép kiểm tra và cộng dồn trong kernel, khi lời gọi `read()` kết thúc. Map giữ bộ đếm của từng container. Đoạn mã còn lại trong probe lưu mốc bắt đầu và in các bộ đếm sau 5 giây.

Đây là điểm có ích khi cloud đang phục vụ người dùng. Ta có thể nạp một quy tắc đo tùy chỉnh vào hệ thống đang chạy và gỡ nó khi đã thu đủ dữ liệu. Kernel kiểm tra probe khi nạp. Việc triển khai vẫn cần các hook được hỗ trợ và quyền phù hợp.

### Thuật ngữ

- **Hook:** điểm gắn chương trình. Demo dùng một hook khi `read()` bắt đầu và một hook khi nó kết thúc.
- **Probe:** đoạn mã eBPF thực thi tại hook.
- **eBPF Map:** cấu trúc lưu dữ liệu của probe. Demo dùng map để lưu thời điểm bắt đầu và các bộ đếm theo container.
- **User Space:** nơi script tổng hợp của `perf trace` và công cụ đọc bộ đếm eBPF chạy.

### Chuyển tiếp

Vậy kernel kiểm tra probe như thế nào, và công cụ giám sát đọc bộ đếm từ đâu?

### Nguồn

[eBPF Foundation: What is eBPF?](https://ebpf.io/what-is-ebpf/), [Linux kernel: BPF maps](https://docs.kernel.org/bpf/maps.html), [Linux kernel: eBPF verifier](https://docs.kernel.org/bpf/verifier.html).

## Kiến trúc eBPF

- **Trang 12, khoảng 90 giây.** Compiler tạo object chứa bytecode. Loader dùng BPF API để yêu cầu kernel nạp, verifier kiểm tra trong bước này. Khi kernel hỗ trợ và bật JIT, bytecode có thể chuyển thành mã máy. Attach liên kết chương trình đã nạp với hook để sự kiện kích hoạt chương trình.
- **Trang 13, khoảng 1 phút.** Lookup trả về con trỏ đến bộ đếm hoặc NULL. Verifier theo dõi đường thực thi và kiểu con trỏ. Nhánh có bộ đếm hợp lệ tăng giá trị, nhánh kia thử tạo bộ đếm. Tính đúng của kết quả còn phụ thuộc logic đếm.
- **Trang 14, khoảng 90 giây.** Tracepoint mở tệp và XDP nhận dữ liệu context khác nhau. Demo nhận tham số ctx nhưng lấy tên tác vụ bằng helper. XDP nhận thông tin về vùng dữ liệu gói tin và có thể quyết định cách xử lý gói.
- **Trang 15, khoảng 80 giây.** Một lần gọi chương trình kết thúc nhanh. Map giữ số đếm tích lũy giữa các lần gọi. Loader đọc mỗi 5 giây. Bảng trình bày giá trị minh họa. Ring buffer phù hợp khi phân tích từng bản ghi sự kiện.

## eBPF trong hệ thống thật

- **Trang 22, khoảng 75 giây.** Các container trên cùng host dùng chung một Linux kernel và vẫn có ranh giới cách ly. Hook tại host quan sát sự kiện, còn dữ liệu cgroup hoặc metadata cho biết sự kiện thuộc workload nào. Hệ thống giám sát có thể kết hợp các sự kiện đó với số liệu tài nguyên theo container. Một lời gọi mở tệp đơn lẻ chưa đủ để suy ra người dùng đang tương tác.
- **Trang 27, khoảng 90 giây.** Service cung cấp một địa chỉ logic ổn định. Cilium Agent đồng bộ trạng thái Service và backend vào BPF maps. Datapath chọn backend dựa trên thông tin này. Vị trí xử lý phụ thuộc chế độ. Hubble quan sát các kết nối mạng.

## Demo openat() và kết luận

Hai phút cuối dành cho kết quả bộ đếm (trang 28) và thông điệp kết luận (trang 29). Phần biên dịch có thể hoàn tất trước seminar. Mỗi lượt chạy cat có thể phát sinh nhiều lời gọi mở tệp, kể cả của trình nạp thư viện. Giá trị quan sát là số đếm tích lũy của các tác vụ cùng tên. Mô hình hook và map cũng xuất hiện trong giám sát và xử lý mạng, với dữ liệu và logic riêng của từng hệ thống.

### Chuẩn bị demo openat()

Từ thư mục `demo/` trên máy Linux có tracepoint, Clang và libbpf:

~~~sh
clang -O2 -g -target bpf -D__BPF__ \
  -I/usr/include/$(gcc -dumpmachine) \
  -c openat_demo.c -o openat_demo.bpf.o
gcc -O2 openat_demo.c -o openat_demo -lbpf -lelf -lz
~~~

Phiên terminal của loader:

~~~sh
sudo ./openat_demo
~~~

Tải minh họa ở terminal thứ hai:

~~~sh
for i in $(seq 1 20); do
  cat /etc/hostname > /dev/null
done
~~~

Loader in cột `OPENAT CALLS` mỗi 5 giây và kết thúc khi nhận Ctrl+C.
