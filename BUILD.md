# Hướng dẫn build PC Monitor Pro thành file chạy (.exe)

Tài liệu này mô tả cách đóng gói project thành **một file Windows** (`PCMonitor.exe`) để mang sang máy khác **không cần cài Python**.

Cách dùng hàng ngày (clone + `.env` + `start-project`) **không cần build**. Chỉ build khi muốn phân phối máy không có Python.

---

## 1. Nên chọn bản Python hay bản .exe?

| | Bản Python (git) | Bản .exe |
|---|---|---|
| Cài trên máy đích | Cần Python 3.10+ | Không cần Python |
| File cấu hình | `.env` trong repo | `.env` **cùng thư mục** với `.exe` |
| `/update` (git pull) | Có | **Không** — phải build exe mới rồi copy đè |
| `/reload` | Restart `pythonw` | Restart chính `PCMonitor.exe` |
| `/autostart` | Ghi Startup gọi pythonw | Ghi Startup gọi `.exe listen` |
| Sửa code | `git pull` | Build lại trên máy dev |

**Khuyến nghị:** máy bạn tự quản lý → giữ bản Python. Máy người khác / không muốn cài Python → dùng `.exe`.

Không chạy **cùng lúc** một bot (cùng `BOT_TOKEN`) bằng cả Python lẫn exe — Telegram `getUpdates` Conflict.

---

## 2. Máy nào build, máy nào chạy

- **Máy build (dev):** Windows 10/11, có Python 3.10+, pip, Git. Build **trên Windows** nếu exe dành cho Windows. Không build exe Windows từ macOS.
- **Máy đích:** Windows 10/11, có mạng ra `api.telegram.org`. Không cần Python. Pritunl / Git chỉ cần nếu dùng `/vpn` hoặc (bản Python) `/update`.

Antivirus đôi khi cảnh báo PyInstaller (false positive). Nên thêm folder chứa exe vào exclusion nếu Windows Defender chặn.

---

## 3. Chuẩn bị máy build

Mở **CMD** hoặc **PowerShell**, vào thư mục repo:

```bat
cd /d C:\duong\dan\pc-monitor-pro
python --version
python -m pip install -r requirements.txt
python -m pip install pyinstaller
```

Python phải là bản 64-bit cùng “loại” với máy đích (thường AMD64).

Kiểm tra chạy source trước khi đóng gói:

```bat
python main.py test
python main.py listen
```

Ctrl+C dừng listen test. Nếu `test` không gửi được Telegram thì đừng build — sửa `.env` trước.

---

## 4. Lệnh build

### Cách nhanh (Windows)

Đã có script:

```bat
scripts\windows\build.bat
```

Ra file: `dist\PCMonitor.exe`.

Tuỳ chọn:

```bat
scripts\windows\build.bat console
scripts\windows\build.bat onedir
```

- `console` — có cửa sổ CMD, dễ xem lỗi lần đầu.
- `onedir` — một **thư mục** (`dist\PCMonitor\`), khởi động nhanh hơn onefile, vẫn không cần Python.
- mặc định — **một file** `.exe`, ẩn cửa sổ (giống pythonw).

### Lệnh tay (onefile, ẩn cửa sổ)

Trong thư mục gốc repo:

```bat
python -m PyInstaller --noconfirm --clean --onefile --noconsole --name PCMonitor --hidden-import mss --hidden-import mss.windows --hidden-import PIL --hidden-import PIL.Image --hidden-import psutil --hidden-import dotenv --hidden-import requests --hidden-import urllib3 --collect-all mss main.py
```

| Cờ | Ý nghĩa |
|---|---|
| `--onefile` | Gộp thành 1 `.exe` |
| `--noconsole` | Không hiện CMD (chạy nền) |
| `--console` | Hiện CMD — dùng khi debug |
| `--onedir` | Thư mục thay vì 1 file |
| `--clean` | Xoá cache build cũ |
| `--collect-all mss` | Kèm binary chụp màn hình |

File ra: `dist\PCMonitor.exe`.  
Thư mục `build\` chỉ là rác build, không copy sang máy đích.

---

## 5. Đóng gói mang sang máy đích

Tạo folder, ví dụ `C:\Tools\PCMonitor\`:

```
C:\Tools\PCMonitor\
  PCMonitor.exe          (copy từ dist\)
  .env                   (copy từ máy bạn, HOẶC copy .env.example rồi điền)
```

Nếu build `onedir`:

```
C:\Tools\PCMonitor\
  PCMonitor.exe
  _internal\             (bắt buộc, copy cả thư mục dist\PCMonitor)
  .env
```

**Bắt buộc:** `.env` nằm **cùng thư mục** với `.exe`. Token không được nhét vào exe.

Nội dung `.env` tối thiểu:

```env
BOT_TOKEN=123456789:AA....token_tu_BotFather
ALLOWED_CHAT_IDS=924153689
COMPUTER_NAME=May-Van-Phong
```

Hai tài khoản Telegram remote chung một máy:

```env
ALLOWED_CHAT_IDS=924153689,111222333
```

**Không** commit `.env` lên git. Mỗi máy một file `.env`.

---

## 6. Chạy trên máy đích

Mở CMD trong folder chứa exe:

```bat
PCMonitor.exe test
```

Phải nhận tin Telegram. Rồi:

```bat
PCMonitor.exe listen
```

Bản `--noconsole` không hiện cửa sổ. Xem log:

```
C:\Tools\PCMonitor\pc_monitor.log
```

Lệnh CLI giống `main.py`:

| Lệnh | Việc |
|---|---|
| `PCMonitor.exe test` | Thử gửi Telegram |
| `PCMonitor.exe listen` | Listen (nên dùng cái này) |
| `PCMonitor.exe hide` | Spawn listen ẩn rồi thoát |
| `PCMonitor.exe install` | Đăng ký chạy khi đăng nhập Windows |
| `PCMonitor.exe uninstall` | Gỡ autostart |
| `PCMonitor.exe service` | Xem đã đăng ký / listen đang chạy chưa |
| `PCMonitor.exe reload` | Restart listen (không git pull) |

Sau `install`, đăng xuất/đăng nhập lại — exe tự `listen`. Không cần mở CMD mỗi lần.

Từ Telegram: `/autostart` cũng đăng ký Startup (gọi đúng `.exe listen` khi đang chạy bản freeze).

---

## 7. Cập nhật bản exe

`/update` trên exe **báo không hỗ trợ** (không có git source).

Quy trình:

1. Sửa code trên máy dev, `git pull` nếu cần.
2. Build lại `PCMonitor.exe`.
3. Trên máy đích: tắt listen cũ (Task Manager `PCMonitor.exe`, hoặc `/reload` sẽ không kéo code mới).
4. Copy đè `PCMonitor.exe` (giữ nguyên `.env`).
5. Chạy `PCMonitor.exe listen` hoặc đăng nhập lại nếu đã `/autostart`.

`.env` không ghi đè khi copy exe.

---

## 8. Lỗi thường gặp

**`LOI: khong tim thay file .env`**  
`.env` không cùng folder với exe. Copy vào đúng chỗ.

**`test` / listen im, không tin Telegram**  
Sai `BOT_TOKEN` / `ALLOWED_CHAT_IDS`. Thử build `console` rồi chạy `PCMonitor.exe test` để đọc lỗi.

**Windows Defender xoá exe**  
False positive PyInstaller. Khôi phục trong Virus & threat protection → Protection history. Thêm folder `C:\Tools\PCMonitor` vào exclusions.

**Screenshot không gửi**  
Máy đang khoá màn hình, hoặc session dịch vụ không có desktop. Listen phải chạy **sau khi đăng nhập** (Startup VBS), không phải Windows Service Session 0.

**Conflict getUpdates**  
Còn listen Python hoặc exe khác cùng bot. Task Manager tắt hết `pythonw` / `PCMonitor.exe` trùng bot, chỉ để một process.

**`/vpn` không bật**  
Vẫn cần Pritunl Client cài trên máy đích. Exe chỉ gọi local API/CLI, không chứa Pritunl.

**Exe rất chậm lúc mở**  
Bình thường với `--onefile` (giải nén temp). Dùng `build.bat onedir` nếu khó chịu.

**Build trên Mac rồi copy sang Windows**  
Không được. Build trên Windows.

---

## 9. macOS / Linux

PyInstaller cũng build được binary, nhưng:

- macOS: thường ra file trong `dist/`, Gatekeeper chặn app không ký. Cần `open` trong Terminal hoặc ký notarize nếu phân phối rộng.
- Linux: phụ thuộc glibc của máy build. Máy đích quá cũ có thể không chạy.

Lệnh tương tự, bỏ `mss.windows`, thêm `mss.darwin` hoặc `mss.linux`. Autostart (`launchd` / systemd) trên bản freeze chưa được ưu tiên trong script Windows; trên Mac/Linux nên giữ bản Python.

---

## 10. Checklist trước khi đưa máy thật

- [ ] `python main.py test` OK trên máy build
- [ ] `scripts\windows\build.bat console` rồi `dist\PCMonitor.exe test` OK
- [ ] Build lại `--noconsole` (mặc định)
- [ ] Folder máy đích có `PCMonitor.exe` + `.env` (token thật)
- [ ] `PCMonitor.exe test` nhận tin trên điện thoại
- [ ] `PCMonitor.exe listen` → `/status` `/screenshot`
- [ ] (Tuỳ chọn) `PCMonitor.exe install` → reboot/login → vẫn `/ping`
- [ ] Chỉ **một** process listen cho bot đó
- [ ] Không copy `.env` lên GitHub / chat

---

## 11. Gỡ trên máy đích

```bat
PCMonitor.exe uninstall
```

Xoá folder `C:\Tools\PCMonitor`. Tắt process `PCMonitor.exe` nếu còn.
