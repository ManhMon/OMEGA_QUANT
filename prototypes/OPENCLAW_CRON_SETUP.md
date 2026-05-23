# OPENCLAW_CRON_SETUP.md
# OpenClaw Wakeup Cron - Installation & Usage Guide

## 📋 Tổng Quan

Hệ thống cron này tự động đánh thức OpenClaw gateway mỗi 60 giây để xử lý pending tasks mà không cần chờ event.

**Vấn đề cũ**: OpenClaw chỉ xử lý task khi có event → chậm, không real-time
**Giải pháp mới**: Cron job gọi gateway callback hook định kỳ → nhanh, tự động

---

## 🚀 Cài Đặt (Windows Task Scheduler)

### Bước 1: Mở PowerShell as Administrator
```powershell
# Right-click PowerShell → "Run as Administrator"
```

### Bước 2: Chạy script cài đặt
```powershell
cd C:\Users\GHC\.openclaw\workspace\scripts
powershell -ExecutionPolicy Bypass -File install_openclaw_cron.ps1
```

**Output mong đợi:**
```
✅ OpenClaw wakeup cron installed successfully!
   Task Name: OpenClawWakeup
   Interval: Every 1 minutes
   Script: C:\Users\GHC\.openclaw\workspace\scripts\wakeup_openclaw_cron.ps1
```

---

## ✅ Kiểm Tra Cài Đặt

### Xem task đã cài
```powershell
Get-ScheduledTask -TaskName OpenClawWakeup | Format-List *
```

### Xem log wakeup
```powershell
Get-Content C:\Users\GHC\.openclaw\workspace\.ly_state\logs\cron_wakeup.log -Tail 20
```

### Chạy thủ công để test
```powershell
& "C:\Users\GHC\.openclaw\workspace\scripts\wakeup_openclaw_cron.ps1" -IntervalSeconds 5
```

---

## 🔧 Tuỳ Chỉnh Interval

### Mặc định: 60 giây (1 phút)
Để thay đổi, edit `wakeup_openclaw_cron.ps1`:
```powershell
[int]$IntervalSeconds = 60  # Thay đổi số này (tính bằng giây)
```

Hoặc chạy với parameter:
```powershell
powershell -ExecutionPolicy Bypass -File wakeup_openclaw_cron.ps1 -IntervalSeconds 120
```

---

## 🗑️ Gỡ Cài Đặt

```powershell
powershell -ExecutionPolicy Bypass -File uninstall_openclaw_cron.ps1
```

---

## 📊 Cách Hoạt Động

```
┌─────────────────────────────────────────────────────────┐
│ Windows Task Scheduler (mỗi 30s)                        │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│ wakeup_openclaw_cron.ps1                                │
│ - Gọi gateway callback endpoint                         │
│ - Log kết quả vào .ly_state/logs/cron_wakeup.log       │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│ gateway_callback_hook_v2.py                             │
│ - Đọc active_tasks.json                                │
│ - Trigger pending tasks                                │
│ - Log events vào gateway_callback.log                  │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│ OpenClaw Gateway                                        │
│ - Xử lý pending tasks ngay lập tức                     │
│ - Không cần chờ event                                  │
└─────────────────────────────────────────────────────────┘
```

---

## 📝 Log Files

| File | Mục đích |
|:-----|:---------|
| `.ly_state/logs/cron_wakeup.log` | PowerShell script logs (wakeup attempts) |
| `.ly_state/logs/gateway_callback.log` | Python callback logs (task triggers) |

---

## 🎯 Lợi Ích

✅ **Tự động**: Không cần chờ event, cron tự gọi định kỳ
✅ **Nhanh**: 30 giây/lần (tuỳ chỉnh được)
✅ **Transparent**: Log đầy đủ để debug
✅ **Dễ gỡ**: Một lệnh để uninstall
✅ **Windows Native**: Dùng Task Scheduler, không cần thêm tool

---

## 🐛 Troubleshooting

### Task không chạy
```powershell
# Kiểm tra status
Get-ScheduledTask -TaskName OpenClawWakeup | Select-Object State
# Output: Running hoặc Ready

# Chạy thủ công
Start-ScheduledTask -TaskName OpenClawWakeup
```

### Permission denied
```powershell
# Chạy PowerShell as Administrator
# Hoặc thay đổi execution policy
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Gateway không respond
```powershell
# Kiểm tra gateway đang chạy
netstat -ano | findstr :8080

# Hoặc test endpoint
Invoke-WebRequest -Uri "http://localhost:8080/callback/wakeup" -Method POST
```

---

**Version**: 1.0
**Last Updated**: 2026-05-17
**Status**: Ready for Production
