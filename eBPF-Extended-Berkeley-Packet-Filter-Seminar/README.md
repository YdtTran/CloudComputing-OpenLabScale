# Seminar eBPF trên template LaTeX Beamer HCMUT

Bộ slide tiếng Việt về **eBPF – Extended Berkeley Packet Filter**, kết hợp
Theory + Practice. Giữ các layout bìa, mục lục và thành viên, trang chia chương,
block, bảng và trang kết thúc của template. Theme Madrid, tỉ lệ 16:9, màu,
font, header/footer, logo và hai file nền trong `images/` giữ nguyên.

## Cấu trúc nội dung

Entry point: `main.tex`. Bốn chương lấy nội dung từ `chaptersnew/` và được
trình bày bằng các layout, sơ đồ TikZ trong `chapters/`.
Tổng cộng **21 trang PDF**, gồm bìa, mục lục, bốn trang chia chương, nội dung
và trang kết thúc. Bốn slide thực hành vẫn là placeholder.
Chapter 5 không được nạp vào bản trình chiếu. Các file nguồn trong `chaptersnew/`
được giữ nguyên để đối chiếu.

| Phần | File | Nội dung | Trang PDF |
| --- | --- | --- | --- |
| Mở đầu | `main.tex` | Bìa, mục lục và thành viên | 1–2 |
| Giới thiệu | `chapters/chapter01.tex` | Chia chương, nhu cầu quan sát Linux, các phương pháp, khái niệm eBPF | 3–6 |
| Kiến trúc eBPF | `chapters/chapter02.tex` | Chia chương, User/kernel/hardware, chuẩn bị và thực thi, bốn thành phần, luồng sự kiện | 7–11 |
| Phát triển và công cụ | `chapters/chapter03.tex` | Chia chương, quy trình C/Clang/LLVM/libbpf, công cụ và ví dụ openat | 12–15 |
| Thực hành | `chapters/chapter04.tex` | Chia chương, bốn placeholder: tổng quan, môi trường, execve, đếm openat theo comm | 16–20 |
| Kết thúc | `main.tex` | Cảm ơn và Q&A | 21 |

Sơ đồ được vẽ trực tiếp bằng TikZ, có thể chỉnh sửa trong source. Không thêm
ảnh ngoài hoặc đường dẫn ảnh tuyệt đối. `images/` tiếp tục chứa các PDF nền.

## TODO cho phần thực hành

Chỉ có tiêu đề, mục tiêu, các nội dung thực hành dự kiến, vùng trống và dòng
`TODO: Demo content will be added later`. Không có script, lệnh demo hay output giả.

- **Hands-on Practice:** bổ sung kịch bản và sơ đồ/ảnh tổng quan khi đã chuẩn bị demo.
- **Demo 1:** bổ sung thông tin môi trường thật và screenshot kiểm tra capability.
- **Demo 2:** bổ sung nội dung theo dõi `execve()`, PID và chương trình được yêu cầu thực thi.
- **Demo 3:** bổ sung nội dung đếm `openat()` theo tên chương trình (`comm`) bằng map và kết quả chạy thật. Các tiến trình có thể trùng tên; đây không phải phép đếm theo PID.

Các placeholder dùng macro `\DemoPlaceholder` trong `chapters/chapter04.tex`.
Đối số cuối là chiều cao vùng trống, ví dụ `{3.15cm}`.
Khi cần chèn terminal hoặc ảnh, thay riêng lời gọi tương ứng bằng frame thông thường.
Ảnh bổ sung đặt trong `images/` và dùng đường dẫn tương đối.

Thông tin tác giả/nhóm, giảng viên, MSSV, ngày trình bày và đơn vị vẫn là `[...]`
để người trình bày điền, vì chưa có dữ liệu cá nhân trong yêu cầu.

## Cài đặt và build

- Cài MiKTeX hoặc TeX Live, có `latexmk`, Beamer, `babel` tiếng Việt,
  VNTeX, TikZ và `listings`. Trên Windows, `latexmk` cần Perl
  (có thể dùng Strawberry Perl). Đảm bảo các lệnh nằm trong `PATH`.
- Cài extension **LaTeX Workshop** (`James-Yu.latex-workshop`) trong VS Code
  và mở **cả thư mục project**.
- Compiler đang dùng: **pdfLaTeX qua latexmk**. Cấu hình `.vscode/settings.json`
  tự build khi lưu file `.tex` (`onSave`). File chính là `main.tex`,
  kể cả khi sửa file trong `chapters/`.
- Build thủ công: **Ctrl+Alt+B**. Xem PDF: **Ctrl+Alt+V** hoặc Command Palette
  → **LaTeX Workshop: View LaTeX PDF file**.

Build bằng terminal từ thư mục project:

```powershell
latexmk -pdf -synctex=1 -interaction=nonstopmode -file-line-error -halt-on-error main.tex
```

Kết quả là `main.pdf`. PDF đầu ra và file build phụ được bỏ qua bởi Git;
PDF nền trong `images/` và cấu hình `.vscode/` vẫn được giữ.

Bản hiện tại đã build bằng lệnh trên thành PDF 21 trang và được render để
kiểm tra trực quan. Không có cảnh báo overfull/underfull hoặc ký tự thiếu;
toàn bộ font được nhúng. MiKTeX hiện còn cảnh báo chưa nạp mẫu ngắt từ tiếng Việt
và dùng mẫu dự phòng. Không thay đổi cấu hình hệ thống để xử lý cảnh báo này.

## Sửa bài thuyết trình

- **Thông tin bìa:** sửa `\title` (tên ngắn và tên đầy đủ), `\subtitle`,
  `\author` (tên ngắn ở footer và nội dung đầy đủ), `\date` trong `main.tex`.
  Sửa bảng thành viên và mô tả mục lục tại cùng file. Dòng đơn vị ở trang kết thúc
  nằm trong `main.tex`.
- **Nội dung:** sửa `chapters/chapter01.tex` đến `chapter04.tex`.
  Mỗi chương có một trang chia chương. Bản trình chiếu chỉ nạp `chapter01.tex`–`chapter04.tex`.
- **Thêm slide:** chèn vào file chương:

```latex
\begin{frame}{[Tiêu đề slide]}
  [Nội dung slide.]
\end{frame}
```

- **Thêm chương:** sao chép một file chương thành `chapters/chapter07.tex`,
  sửa `\section` và `\ChapterDivider`, thêm `\input{chapters/chapter07}`
  trong `main.tex` trước trang kết thúc. Cập nhật slide mục lục tương ứng.
- **Ảnh:** thêm ảnh vào `images/` và dùng `\includegraphics`.
  Giữ `Background.pdf` và `FrontBackground.pdf` để bảo toàn thiết kế.
- Slide chứa `lstlisting` cần `\begin{frame}[fragile]{...}`.

Giữ pdfLaTeX để dùng ngay với cấu hình hiện tại. Nếu chủ động chuyển sang
XeLaTeX/LuaLaTeX, cần cài Noto Sans và Noto Sans Mono theo cấu hình font.

## Kịch bản thuyết trình và nguồn kỹ thuật

`PRESENTER_NOTES.md` hiện chỉ chứa lời thuyết trình Part 1, tương ứng slide 4–6,
thời lượng khoảng 4 phút 30 giây. Mỗi slide có mục tiêu, lời nói, thuật ngữ,
câu chuyển tiếp và nguồn. Slide 17–20 là placeholder thực hành, chờ bổ sung
từ môi trường demo thật.

Nguồn theo từng slide nằm trong kịch bản và `\note{...}` của Beamer, không hiển thị
ở bản trình chiếu mặc định. Có thể bật chế độ notes khi cần đọc cùng source.

- [eBPF Foundation: What is eBPF?](https://ebpf.io/what-is-ebpf/)
- [Linux BPF documentation](https://docs.kernel.org/bpf/)
- [eBPF Docs (tài liệu cộng đồng)](https://docs.ebpf.io/)
- [libbpf: kho mã nguồn chính thức](https://github.com/libbpf/libbpf)
- [Linux: ví dụ đếm syscall tracepoint](https://github.com/torvalds/linux/blob/master/samples/bpf/syscall_tp_kern.c)
- [Linux: libbpf overview và vòng đời chương trình](https://docs.kernel.org/bpf/libbpf/libbpf_overview.html)
- [Linux: eBPF verifier](https://docs.kernel.org/bpf/verifier.html)
- [Linux: BPF maps](https://docs.kernel.org/bpf/maps.html)
- [Application Logging: Python logging](https://docs.python.org/3/library/logging.html)
- [Linux: ftrace](https://docs.kernel.org/trace/ftrace.html)
- [Linux: xây dựng external kernel modules](https://docs.kernel.org/kbuild/modules.html)
- [Linux: BPF design Q&A](https://docs.kernel.org/bpf/bpf_design_QA.html)
- [Linux: BPF LSM](https://docs.kernel.org/bpf/prog_lsm.html)
- [bpftrace](https://bpftrace.org/about)
- [bpftool manual](https://github.com/libbpf/bpftool/blob/main/docs/bpftool.rst)
- [BCC](https://github.com/iovisor/bcc)
- [Cilium](https://docs.cilium.io/en/stable/overview/intro/)
- [Tetragon](https://tetragon.io/docs/overview/)

Các sơ đồ tách luồng chuẩn bị chương trình và luồng xử lý sự kiện. Verifier kiểm tra
trong yêu cầu nạp; gắn vào hook là bước riêng. JIT dịch bytecode sang mã máy khi
được hỗ trợ và kích hoạt, không phải hook hay điều kiện bắt buộc trong mọi trường hợp.
Hook và API phụ thuộc program type, map type và kernel. Verifier không bảo đảm
chương trình hoàn toàn đúng về logic. Sự kiện bắt đầu `openat()` hoặc `execve()`
chỉ ghi nhận yêu cầu; chưa xác nhận thao tác đã thành công.
