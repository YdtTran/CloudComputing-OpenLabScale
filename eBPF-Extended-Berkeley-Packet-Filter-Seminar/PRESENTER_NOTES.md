# Kịch bản Part 1 - Introduction: Why eBPF?

Phạm vi: slide 4, 5 và 6 (sau trang chia Chương 1). Thời lượng dự kiến khoảng **4 phút 30 giây**, gồm các khoảng dừng ngắn để chỉ sơ đồ. Chỉ đọc phần **Lời thuyết trình** và **Chuyển tiếp** khi trình bày. Phần thuật ngữ và nguồn dành cho người thuyết trình chuẩn bị trước.

## Slide 4 - Quan sát hoạt động bên trong Linux

**Thời lượng:** khoảng 1 phút 15 giây.

### Mục tiêu

Giúp người nghe thấy nhu cầu quan sát hoạt động của nhiều tiến trình trên máy chủ Linux mà không phải sửa mã nguồn các ứng dụng đang chạy.

### Lời thuyết trình

Hãy hình dung một máy chủ Linux đang phục vụ website. Trên cùng máy đó có Web Server nhận yêu cầu từ người dùng, Database lưu dữ liệu và các chương trình chạy nền thực hiện công việc định kỳ. Những tiến trình này cùng sử dụng các dịch vụ mà kernel cung cấp.

Nhìn vào sơ đồ, cả ba tiến trình đều tương tác với Linux kernel. Một tiến trình có thể mở, đọc hoặc ghi file, gửi và nhận dữ liệu mạng, đồng thời sử dụng CPU và bộ nhớ. Trong kernel, File System xử lý các thao tác liên quan đến file, Network Stack xử lý giao tiếp mạng, còn Scheduler phân phối thời gian CPU. Các khối này minh họa những chức năng dùng chung, không phải mỗi tiến trình chỉ dùng một chức năng riêng.

Giả sử website phản hồi chậm. Người quản trị cần biết tiến trình nào đang truy cập file nhiều, những system call nào đang diễn ra hoặc tài nguyên đang tập trung ở đâu. Chỉ nhìn kết quả mà ứng dụng trả về thường chưa đủ để trả lời. Ta cần theo dõi những hoạt động đó ngay khi hệ thống đang chạy, kể cả khi không thuận tiện sửa mã nguồn ứng dụng để bổ sung thông tin.

### Thuật ngữ

- **Tiến trình:** một chương trình đang thực thi. Web Server phục vụ yêu cầu web, Database quản lý dữ liệu, còn Background Process thực hiện công việc nền.
- **Linux kernel:** phần lõi của hệ điều hành, quản lý tài nguyên và cung cấp các dịch vụ cho ứng dụng.
- **System call:** giao diện để tiến trình yêu cầu dịch vụ của kernel, chẳng hạn đọc file hoặc gửi dữ liệu. Không phải mọi lần tiến trình dùng CPU hay truy cập bộ nhớ đều cần một system call riêng.
- **File System, Network Stack, Scheduler:** lần lượt là các thành phần xử lý hệ thống file, giao tiếp mạng và lập lịch CPU. Sơ đồ thể hiện quan hệ giữa tiến trình với kernel, không mô tả trình tự đầy đủ của một lần thực thi.

### Chuyển tiếp

Để quan sát những hoạt động này, trước hết ta xem các phương pháp đã có và những điều cần cân nhắc khi sử dụng.

### Nguồn

[Linux system calls](https://man7.org/linux/man-pages/man2/syscalls.2.html).

## Slide 5 - Các phương pháp truyền thống

**Thời lượng:** khoảng 1 phút 35 giây.

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

Vậy eBPF cung cấp khả năng xử lý sự kiện đó như thế nào ở mức khái niệm?

### Nguồn

[Python Logging HOWTO](https://docs.python.org/3/howto/logging.html), [strace](https://strace.io/), [Linux perf wiki](https://perfwiki.github.io/main/), [Linux kernel: External Modules](https://docs.kernel.org/kbuild/modules.html).

## Slide 6 - eBPF là gì?

**Thời lượng:** khoảng 1 phút 40 giây.

### Mục tiêu

Giới thiệu eBPF qua thực thi theo sự kiện, xử lý trong kernel và chia sẻ dữ liệu với User Space, đồng thời nêu ngắn gọn phạm vi ứng dụng.

### Lời thuyết trình

eBPF cho phép chạy các chương trình đã qua kiểm tra trong Linux kernel để theo dõi hoặc xử lý sự kiện tại những hook được hỗ trợ. Hook có thể hiểu là một điểm mà kernel cho phép gắn logic phù hợp. Ở đây, ta chỉ cần nắm ba ý chính.

Thứ nhất là Event-driven Execution. Khi sự kiện phù hợp xảy ra tại hook tương ứng, kernel có thể thực thi chương trình eBPF đã gắn ở đó. Ví dụ, ta có thể theo dõi một sự kiện liên quan đến system call mà tiến trình thực hiện.

Thứ hai là In-kernel Processing. Chương trình có thể lọc dữ liệu hoặc tổng hợp kết quả ngay trong kernel. Chẳng hạn, nếu chỉ cần số lần một sự kiện xảy ra, ta có thể cập nhật bộ đếm thay vì chuyển nguyên vẹn từng sự kiện về ứng dụng. Như vậy, lượng dữ liệu cần chuyển về User Space có thể giảm tùy cách thiết kế.

Thứ ba là Data Collection & Sharing. Chương trình eBPF có thể lưu kết quả trong cấu trúc như eBPF Map. Ứng dụng ở User Space đọc dữ liệu qua API phù hợp rồi hiển thị hoặc phân tích tiếp. Với ví dụ bộ đếm, ứng dụng đọc giá trị đã tổng hợp để người quản trị xem.

eBPF còn có phạm vi rộng hơn packet filtering. Công nghệ này được dùng trong Observability để quan sát hoạt động, Networking để xử lý mạng và Security để hỗ trợ bảo mật. Ở phần giới thiệu, ta chỉ cần nhận diện các lĩnh vực này. Khả năng cụ thể vẫn phụ thuộc vào hook, loại chương trình và kernel hỗ trợ.

### Thuật ngữ

- **eBPF Program:** chương trình được kernel kiểm tra trước khi chấp nhận nạp, thực hiện logic trong phạm vi mà loại chương trình và hook cho phép. Việc kiểm tra không bảo đảm mọi logic của ứng dụng đều đúng.
- **Hook:** điểm gắn chương trình được hỗ trợ. Sự kiện và ngữ cảnh thực thi phải phù hợp với chương trình gắn tại đó.
- **Event-driven Execution:** thực thi khi sự kiện tương ứng xảy ra. **In-kernel Processing:** thực hiện phần xử lý dữ liệu ngay trong kernel.
- **eBPF Map:** cấu trúc lưu dữ liệu mà chương trình eBPF và ứng dụng có thể truy cập qua cơ chế phù hợp. Bộ đếm là một ví dụ đơn giản về dữ liệu có thể lưu.
- **User Space:** môi trường chạy ứng dụng thông thường ngoài kernel. **API:** giao diện lập trình để ứng dụng yêu cầu thao tác, ví dụ đọc dữ liệu trong map. **Data Collection & Sharing:** thu thập, lưu và chia sẻ dữ liệu giữa các thành phần.
- **Packet filtering:** lọc gói tin mạng theo điều kiện. **Observability:** quan sát và phân tích hoạt động hệ thống từ dữ liệu thu thập. **Networking:** các chức năng mạng. **Security:** các chức năng phục vụ bảo mật. Slide chỉ giới thiệu phạm vi, chưa phân tích ứng dụng cụ thể.

### Chuyển tiếp

Từ ba ý này, phần tiếp theo sẽ làm rõ các thành phần eBPF nằm ở đâu và phối hợp với nhau ra sao.

### Nguồn

[eBPF Foundation: What is eBPF?](https://ebpf.io/what-is-ebpf/), [Linux kernel: BPF maps](https://docs.kernel.org/bpf/maps.html), [Linux kernel: BPF design Q&A](https://docs.kernel.org/bpf/bpf_design_QA.html).
