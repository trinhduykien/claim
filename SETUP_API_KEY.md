# Hướng dẫn setup API Key cho AI Deduction Module

## ⚠️ QUAN TRỌNG: Bảo mật API Key

**KHÔNG bao giờ dán API key vào chat, Discord, hay commit lên GitHub.**

## Cách 1: Environment Variable (khuyên dùng)

### PowerShell (tạm thời - mất khi tắt terminal)
```powershell
$env:KIMI_API_KEY = "your-key-here"
streamlit run app.py
```

### PowerShell (vĩnh viễn - cho user hiện tại)
```powershell
[System.Environment]::SetEnvironmentVariable("KIMI_API_KEY", "your-api-key-here", "User")
```
→ Restart terminal để áp dụng.

## Cách 2: File local (không commit lên git)

Tạo file `.kimi_api_key` trong cùng thư mục với `app.py`:
```
your-api-key-here
```

File này đã được thêm vào `.gitignore` → sẽ không bị push lên GitHub.

## Kiểm tra

Sau khi setup, chạy app và thử:
1. Hoàn tất đánh giá claim → kết quả "ĐỦ ĐIỀU KIỆN"
2. Upload ảnh + hợp đồng
3. Bấm "Phân tích khấu trừ" → AI sẽ xử lý

Nếu chưa có API key, app sẽ hiển thị thông báo lỗi hướng dẫn.