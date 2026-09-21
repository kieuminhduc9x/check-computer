# PC Monitor Pro

Theo doi va dieu khien may tinh tu xa qua Telegram Bot: biet may dang bat
hay tat, xem CPU/RAM/o dia, chup man hinh, khoa may, tat/khoi dong lai —
tat ca tu dien thoai. Chay duoc tren **Windows, macOS va Linux**, cau hinh
qua file `.env` de dung cho **nhieu may tinh va nhieu bot Telegram khac nhau**.

## Muc luc

1. [Cau truc project](#cau-truc-project)
2. [Tong quan tinh nang](#tong-quan-tinh-nang)
3. [Chuan bi: tao bot Telegram va lay chat_id](#chuan-bi-tao-bot-telegram-va-lay-chat_id)
4. [Cai dat chung (moi OS)](#cai-dat-chung-moi-os)
5. [Cai dat rieng tren Windows](#cai-dat-rieng-tren-windows)
6. [Cai dat rieng tren macOS](#cai-dat-rieng-tren-macos)
7. [Cai dat rieng tren Linux](#cai-dat-rieng-tren-linux)
8. [Giai thich tung bien trong .env](#giai-thich-tung-bien-trong-env)
9. [Danh sach toan bo lenh Telegram](#danh-sach-toan-bo-lenh-telegram)
10. [Dung cho nhieu may / nhieu bot](#dung-cho-nhieu-may--nhieu-bot)
11. [File log](#file-log)
12. [Troubleshooting](#troubleshooting)
13. [Gioi han & luu y bao mat](#gioi-han--luu-y-bao-mat)

---

## Cau truc project

```
pc-monitor-pro/
├── main.py                    # startup/shutdown/heartbeat/test/listen/install
├── requirements.txt           # danh sach thu vien python can cai
├── .env.example                # file cau hinh mau (copy thanh .env)
├── pc_monitor/                 # ma nguon chinh
│   ├── config.py               # doc .env
│   ├── telegram_api.py         # goi Telegram Bot API
│   ├── system_info.py          # CPU/RAM/dia/uptime/ip (cross-platform)
│   ├── actions.py              # screenshot/lock/shutdown/restart (rieng tung OS)
│   ├── autostart.py            # dang ky service khoi dong (Windows/macOS/Linux)
│   ├── commands.py             # noi dung + dieu phoi lenh Telegram
│   └── listener.py             # vong lap long-polling + canh bao CPU/RAM
└── scripts/
    ├── windows/setup_task_scheduler.ps1
    ├── macos/install.sh + uninstall.sh + *.plist.template
    └── linux/install.sh + uninstall.sh + *.service.template
```

## Tong quan tinh nang

| Nhom | Tinh nang |
|---|---|
| Bao trang thai (tu dong) | Bao khi BAT may, khi SAP TAT/khoi dong lai, heartbeat dinh ky |
| Hoi truc tiep | `/status`, `/ping` — hoi la tra loi ngay (CPU/RAM, app dang mo), im lang = may dang tat |
| Giam sat | `/apps`, `/cpu`, `/ram`, `/disk`, `/procs`, `/ip` |
| Dieu khien | `/screenshot`, `/lock`, `/shutdown_now`, `/restart_now` (co xac nhan) |
| Tien ich | `/note` — ghi chu; `/autostart` — dang ky chay khi khoi dong |
| Canh bao chu dong | Tu bao khi CPU/RAM vuot nguong dat trong `.env` |
| Bao mat | Chi tra loi cac `chat_id` nam trong danh sach cho phep |

## Chuan bi: tao bot Telegram va lay chat_id

1. Mo Telegram, tim **@BotFather**, gui `/newbot`, dat ten cho bot (vi du
   `PC Nha Bot`). BotFather tra ve 1 **token** dang
   `123456789:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` — day la `BOT_TOKEN`.
2. Nhan tin bat ky (vi du "hi") cho bot vua tao.
3. Mo trinh duyet, truy cap:
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
   (thay `<TOKEN>` bang token that). Tim so o `"chat":{"id": ...}` — do la
   `ALLOWED_CHAT_IDS` cua ban.

> Muon theo doi nhieu may? Xem muc [Dung cho nhieu may / nhieu bot](#dung-cho-nhieu-may--nhieu-bot).

## Cai dat chung (moi OS)

Cac buoc nay giong nhau tren ca 3 he dieu hanh, lam truoc khi chay script
rieng cua tung OS ben duoi.

### Buoc 1: Cai Python 3

- **Windows**: tai tu https://python.org, khi cai nho tick **"Add python.exe to PATH"**.
- **macOS**: `brew install python3` (can Homebrew: https://brew.sh), hoac tai tu python.org.
- **Linux**: thuong co san; neu chua co: `sudo apt install python3 python3-pip` (Debian/Ubuntu)
  hoac `sudo dnf install python3 python3-pip` (Fedora).

Kiem tra: `python3 --version` (Windows co the dung `python --version`).

### Buoc 2: Copy project vao may

Copy toan bo thu muc `pc-monitor-pro` vao may can theo doi.

### Buoc 3: Cai thu vien Python

Mo terminal/Command Prompt tai thu muc goc project:
```bash
pip install -r requirements.txt
```
(Tren Linux/macOS neu bao loi "externally-managed-environment", dung:
`pip install -r requirements.txt --break-system-packages`)

### Buoc 4: Tao file .env

```bash
cp .env.example .env        # macOS / Linux
copy .env.example .env      # Windows CMD
```
Mo `.env` bang Notepad/VS Code, dien it nhat:
```env
BOT_TOKEN=123456789:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ALLOWED_CHAT_IDS=987654321
COMPUTER_NAME=PC-Nha
```
Xem giai thich day du cac bien o [phan ben duoi](#giai-thich-tung-bien-trong-env).

### Buoc 5: Test ket noi

```bash
python main.py test
```
Neu dung, Telegram se nhan tin "✅ Ket noi Telegram bot thanh cong!" ngay lap tuc.
Neu loi, xem [Troubleshooting](#troubleshooting).

### Buoc 6: Thu chay lang nghe lenh (tuy chon, de kiem tra truoc khi cai dich vu)

```bash
python main.py listen
```
Mo Telegram, gui `/help` cho bot — neu bot tra loi ngay la thanh cong. Nhan
`Ctrl+C` de dung thu, roi dang ky chay khi khoi dong o buoc tiep theo.

### Buoc 7: Dang ky chay khi khoi dong (moi OS)

Lenh nay giong nhau tren Windows, macOS va Linux — moi may chi can chay 1 lan:

```bash
python main.py install
```

Sau do bot tu chay khi **dang nhap / khoi dong may**: bao startup, lang nghe
lenh Telegram, gui heartbeat. Kiem tra:

```bash
python main.py service
```

Go bo:

```bash
python main.py uninstall
```

Cung co the dang ky tu dien thoai: gui `/autostart` cho bot (may phai dang
chay `listen`). `/service` de xem da cai chua, `/autostart_off` de go.

---

## Cai dat rieng tren Windows

Cach khuyen nghi: `python main.py install` (khong can Administrator).
Lenh nay **start listener ngay**, roi moi lan dang nhap Windows se tu chay lai.

Neu Telegram **khong phan hoi** tren Windows:
1. Chay `python main.py test` — phai nhan tin thanh cong.
2. Chay `python main.py listen` (de mo cua so nay), roi gui `/help`.
3. Khong dung Python cai tu Microsoft Store. Cai tu https://python.org
   va tick **"Add python.exe to PATH"**.
4. Xem `pc_monitor.log` va `pc_monitor_task.log` trong thu muc project.
5. Task Scheduler -> `PCMonitorPro_Listener` -> Last Run Result phai la `0x0`.

Hoac chay script:

```powershell
cd scripts\windows
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
.\setup_task_scheduler.ps1
```

Tao 3 task: `PCMonitorPro_Startup`, `PCMonitorPro_Heartbeat`,
`PCMonitorPro_Listener`. Kiem tra trong **Task Scheduler**.

**Go bo:** `python main.py uninstall` hoac `.\setup_task_scheduler.ps1 -Uninstall`

## Cai dat rieng tren macOS

Cach khuyen nghi: `python3 main.py install` (launchd LaunchAgents).

Hoac:

```bash
cd scripts/macos
chmod +x install.sh
./install.sh
```

Tao 3 LaunchAgent: `com.pcmonitor.startup`, `com.pcmonitor.heartbeat`,
`com.pcmonitor.listener`.

Kiem tra: `launchctl list | grep pcmonitor`

**Go bo:** `python3 main.py uninstall` hoac `./uninstall.sh`

> macOS se hoi quyen truy cap **Accessibility** / **Screen Recording** khi
> `python3` lan dau goi lenh khoa man hinh hoac chup man hinh — vao
> System Settings -> Privacy & Security va cap quyen cho Terminal/Python.

## Cai dat rieng tren Linux

Cach khuyen nghi: `python3 main.py install` (systemd --user).

Hoac:

```bash
cd scripts/linux
chmod +x install.sh
./install.sh
```

Tao: `pcmonitor-startup.service`, `pcmonitor-listener.service`,
`pcmonitor-heartbeat.timer` + `pcmonitor-heartbeat.service`.

Kiem tra: `systemctl --user status pcmonitor-listener.service`

Neu muon dich vu chay ca khi ban **chua dang nhap** (vi du server khong co
man hinh), chay them 1 lan:
```bash
sudo loginctl enable-linger $USER
```

**Go bo:** `python3 main.py uninstall` hoac `./uninstall.sh`

> Cac lenh `/lock`, `/screenshot` can co phien dang nhap do hoa (X11/Wayland)
> dang chay — phu hop khi may co man hinh va ban dang dang nhap. Tren server
> khong man hinh, cac lenh nay se bao loi ro rang thay vi crash.

---

## Giai thich tung bien trong .env

| Bien | Bat buoc | Y nghia |
|---|---|---|
| `BOT_TOKEN` | Co | Token bot Telegram tu BotFather |
| `ALLOWED_CHAT_IDS` | Co | 1 hoac nhieu chat_id (cach nhau boi dau phay) duoc phep nhan tin & gui lenh |
| `COMPUTER_NAME` | Khong | Ten hien thi cho may nay trong moi tin nhan |
| `HEARTBEAT_MINUTES` | Khong | Bao nhieu phut gui 1 lan tin "van dang bat" (mac dinh 60) |
| `ALERT_CPU_PERCENT` | Khong | Canh bao neu CPU vuot % nay (0 = tat) |
| `ALERT_RAM_PERCENT` | Khong | Canh bao neu RAM vuot % nay (0 = tat) |
| `ALERT_CONSECUTIVE_CHECKS` | Khong | So lan kiem tra lien tiep vuot nguong truoc khi bao (tranh bao nham) |
| `ALERT_CHECK_INTERVAL_SECONDS` | Khong | Khoang cach giua cac lan kiem tra CPU/RAM |
| `ENABLE_SCREENSHOT` | Khong | Bat/tat lenh `/screenshot` |
| `ENABLE_LOCK` | Khong | Bat/tat lenh `/lock` |
| `ENABLE_SHUTDOWN_RESTART` | Khong | Bat/tat lenh `/shutdown_now`, `/restart_now` |
| `ENABLE_NOTE` | Khong | Bat/tat lenh `/note` |
| `ENABLE_AUTOSTART` | Khong | Bat/tat lenh `/autostart`, `/autostart_off`, `/service` |
| `NOTE_FILE` | Khong | Ten file luu ghi chu (mac dinh `notes.txt`) |

## Danh sach toan bo lenh Telegram

Gui cac lenh nay cho bot cua ban tren Telegram:

| Lenh | Chuc nang |
|---|---|
| `/status` hoac `/ping` | May dang bat: CPU/RAM/o dia, man hinh khoa hay mo, app dang dung, danh sach app dang mo |
| `/cpu` | % su dung CPU, toc do, so nhan/luong |
| `/ram` | % su dung RAM, da dung / tong |
| `/disk` | Dung luong tung o dia |
| `/procs` | Top 5 tien trinh dang ngon CPU nhat |
| `/apps` hoac `/windows` | Danh sach day du ung dung dang mo, cua so, va app dang duoc dung |
| `/ip` | IP noi bo (LAN) va IP cong khai |
| `/screenshot` | Chup va gui anh man hinh hien tai |
| `/lock` | Khoa man hinh may ngay lap tuc |
| `/shutdown_now` | Yeu cau tat may (phai `/confirm_shutdown` trong 30s de xac nhan) |
| `/restart_now` | Yeu cau khoi dong lai (phai `/confirm_restart` trong 30s de xac nhan) |
| `/note noi dung` | Luu 1 dong ghi chu vao file `notes.txt` tren may |
| `/autostart` | Dang ky bot tu chay khi khoi dong / dang nhap |
| `/autostart_off` | Go bo service khoi dong |
| `/service` | Xem service khoi dong da cai chua |
| `/help` hoac `/start` | Xem lai danh sach lenh |

Neu may da tat, moi lenh o tren se **khong co phan hoi gi ca** — do chinh
la dau hieu bao may dang tat.

## Dung cho nhieu may / nhieu bot

Khuyen nghi: **moi may 1 bot rieng** (tao qua BotFather, dat ten de phan
biet nhu `PC_Nha_bot`, `PC_Cong_ty_bot`), nhung ban co the dung **chung 1
`ALLOWED_CHAT_IDS`** (chinh la Telegram cua ban) cho tat ca — vi do la tai
khoan nhan tin, khong phai may tinh.

Cach lam:
1. Copy nguyen thu muc `pc-monitor-pro` sang tung may.
2. Moi may tao 1 bot rieng qua BotFather, dien `BOT_TOKEN` khac nhau vao
   `.env` cua tung may.
3. `ALLOWED_CHAT_IDS` co the giong nhau (chat_id cua ban) o ca 2 may.
4. Dien `COMPUTER_NAME` khac nhau de phan biet khi doc tin nhan.
5. Tren Telegram, moi bot la 1 doan chat rieng — muon hoi may nao thi vao
   dung doan chat voi bot cua may do.

> **Tai sao khong dung chung 1 bot cho nhieu may?** Telegram chi giao 1
> tin nhan cho 1 nguoi nhan `getUpdates` dau tien; neu 2 may cung poll 1
> bot, chung se tranh nhau update va lenh co the bi may khac "an mat",
> may kia khong phan hoi. Dung bot rieng cho moi may tranh hoan toan van
> de nay va con giup ban de phan biet dang noi chuyen voi may nao.

Neu muon nhieu nguoi cung giam sat 1 may, chi can them chat_id cua ho vao
`ALLOWED_CHAT_IDS`, cach nhau dau phay:
```env
ALLOWED_CHAT_IDS=987654321,111222333
```

## File log

- `pc_monitor.log` — log logic ung dung (gui tin nhan, nhan lenh, loi mang...).
- `pc_monitor_launchd.log` (macOS) hoac `pc_monitor_systemd.log` (Linux) —
  log dau ra tho cua tien trinh (stdout/stderr), huu ich khi service khong
  khoi dong duoc.

## Troubleshooting

| Trieu chung | Nguyen nhan thuong gap |
|---|---|
| `LOI: khong tim thay file .env` | Chua `cp .env.example .env` |
| `LOI CAU HINH: BOT_TOKEN chua duoc dien dung` | Con nguyen chu `DAN_...` trong `.env` |
| `python main.py test` bao HTTPError 404 | Token sai, kiem tra lai tu BotFather |
| Bot khong tra loi tren Windows | Listener chua chay, hoac Python Store stub. Chay `python main.py listen`, xem `pc_monitor_task.log`. Cai Python tu python.org (khong dung Microsoft Store) |
| Bot khong tra loi `/status` | Tien trinh `listen` chua chay — `python main.py install` hoac `python main.py listen` |
| `/autostart` bao `Access is denied` tren Windows | Khong du quyen tao Task Scheduler. Chuot phai Command Prompt -> **Run as administrator**, `cd` toi project, chay `python main.py install`. Neu khong co Admin, bot se tu dang ky bang thu muc Startup |
| `ModuleNotFoundError` | Chua `pip install -r requirements.txt` dung moi truong python dang dung de chay |
| `/screenshot` bao loi tren Linux | Can co man hinh do hoa (X11/Wayland) dang chay, khong dung duoc tren server khong man hinh |
| `/lock` khong hoat dong tren Linux | Desktop environment khong ho tro lenh khoa duoc thu (xem `actions.py`), thu cai `xdg-utils` |
| `/apps` chi ra danh sach tien trinh he thong dai, khong phai ung dung | Thieu cong cu / quyen doc danh sach cua so: Linux can cai `wmctrl`; macOS can cap quyen **Accessibility** cho Terminal/Python (System Settings -> Privacy & Security); Windows thuong tu hoat dong |
| `/shutdown_now` bao "thieu quyen" tren Linux | Chay `install.sh` da dung systemd user, mot so distro can them polkit rule cho phep `shutdown` khong can mat khau — tim "polkit allow shutdown without password" |

## Gioi han & luu y bao mat

- Neu may **mat dien dot ngot**, khong co canh bao truoc nao kip chay —
  day la gioi han vat ly, khong phai loi phan mem. Heartbeat bi gian doan
  hoac `/status` khong duoc tra loi la dau hieu duy nhat trong truong hop nay.
- Bot **chi tra loi** tin nhan tu dung `chat_id` trong `ALLOWED_CHAT_IDS`.
  Tin nhan tu nguoi la se bi bo qua va ghi vao log — **giu `BOT_TOKEN` bi
  mat**, ai co token deu doc duoc cac lenh gui den (du khong thuc thi duoc
  vi kiem tra chat_id, nhung van nen giu kin).
- Lenh `/shutdown_now` va `/restart_now` yeu cau xac nhan trong 30 giay de
  tranh bam nham; ban van co the tat han bang `ENABLE_SHUTDOWN_RESTART=false`
  neu day la may quan trong khong muon rui ro.
- File `.env` chua thong tin nhay cam (token bot) — **khong** commit len
  Git cong khai. Neu dung Git, them `.env` vao `.gitignore`.
# check-computer
