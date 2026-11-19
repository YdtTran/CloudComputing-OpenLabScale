# Seminar eBPF trên template LaTeX Beamer HCMUT

Bộ slide tiếng Việt về **eBPF – Extended Berkeley Packet Filter**, kết hợp
lý thuyết, demo và ứng dụng thực tế. Giữ các layout bìa, mục lục và thành viên,
trang chia chương, block và bảng của template. Theme Madrid, tỉ lệ 16:9, màu,
font, header/footer, logo và hai file nền trong `images/` giữ nguyên.

## Cấu trúc nội dung

Entry point: `main.tex`. Bốn chương lấy nội dung từ `chaptersnew/` và được
trình bày bằng các layout, sơ đồ TikZ trong `chapters/`.
Tổng cộng **29 trang PDF**, gồm bìa, mục lục, bốn phần nội dung và kết luận.
Chapter 5 không được nạp vào bản trình chiếu. Các file nguồn trong `chaptersnew/`
được giữ nguyên để đối chiếu.

| Phần | File | Nội dung | Trang PDF |
| --- | --- | --- | --- |
| Mở đầu | `main.tex` | Bìa, mục lục và thành viên | 1–2 |
| Giới thiệu | `chapters/chapter01.tex` | Chia chương, nhu cầu quan sát Linux, các phương pháp, mở rộng kernel, demo đếm lượt đọc chậm bằng perf trace và eBPF, khái niệm eBPF | 3–9 |
| Kiến trúc eBPF | `chapters/chapter02.tex` | Chia chương, user/kernel space, nạp và gắn chương trình, verifier, context, maps | 10–15 |
| Phát triển và công cụ | `chapters/chapter03.tex` | Chia chương, quy trình C/Clang/LLVM/libbpf, công cụ, ví dụ và demo openat | 16–20 |
| eBPF trong hệ thống thật | `chapters/chapter04.tex` | Mở chương, kernel dùng chung, ứng dụng, Cilium Service load balancing, Hubble, demo `openat()` và kết luận | 21–29 |

Các sơ đồ TikZ có thể chỉnh sửa trong source. Hình từ tài liệu bên ngoài cho
Chương 4 nằm trong `images/chapter04/` và được chèn bằng đường dẫn tương đối.
Mỗi slide có liên kết nguồn hình. Các logo BCC, Cilium và Tetragon được chuyển
từ SVG sang PNG để dùng với pdfLaTeX.

Thông tin tác giả/nhóm, giảng viên, MSSV và ngày trình bày dùng các mục `[...]`
để người trình bày điền.

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

## Sửa bài thuyết trình

- **Thông tin bìa:** sửa `\title` (tên ngắn và tên đầy đủ), `\subtitle`,
  `\author` (tên ngắn ở footer và nội dung đầy đủ), `\date` trong `main.tex`.
  Sửa bảng thành viên và mô tả mục lục tại cùng file.
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
  trong `main.tex` theo thứ tự trình bày. Cập nhật slide mục lục tương ứng.
- **Ảnh:** thêm ảnh vào `images/` và dùng `\includegraphics`.
  Giữ `Background.pdf` và `FrontBackground.pdf` để bảo toàn thiết kế.
- Slide chứa `lstlisting` cần `\begin{frame}[fragile]{...}`.

Giữ pdfLaTeX để dùng ngay với cấu hình hiện tại. Nếu chủ động chuyển sang
XeLaTeX/LuaLaTeX, cần cài Noto Sans và Noto Sans Mono theo cấu hình font.

## Kịch bản thuyết trình và nguồn kỹ thuật

Kịch bản thuyết trình phân bổ 30 phút theo từng phần. Ghi chú có lệnh chuẩn bị và chạy lại hai demo. [Kịch bản seminar](PRESENTER_NOTES.md)

Nguồn hình của Chương 4 hiển thị trực tiếp trên slide. Nguồn kỹ thuật bổ sung
nằm trong kịch bản và các phần `\note{...}` của Beamer.

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
