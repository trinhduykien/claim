# AI Claim Chatbot - Streamlit App

## Cài đặt & chạy

```bash
cd D:\WORK\idea
pip install streamlit openai
python -m streamlit run app.py
```

## Yêu cầu

### Cách 1: Dùng Ollama local (miễn phí)

```bash
# Cài Ollama: https://ollama.com
ollama serve
ollama pull qwen2.5:7b   # hoặc llama3.1:8b, glm4:9b...
```

Mặc định app sẽ kết nối `http://localhost:11434/v1`, model `qwen2.5:7b`.

### Cách 2: Dùng OpenAI API

Set environment variable:
```bash
set OPENAI_API_KEY=sk-xxxxx
set CLAIM_MODEL=gpt-4o-mini
```

Hoặc chỉnh trực tiếp trong sidebar của app.

## Cách hoạt động

1. Khách hàng mở web → chatbot AI chào hỏi
2. Khách mô tả sự cố (vd: "nhà tôi bị cháy, tôi có mua bảo hiểm nhà ở combo 360")
3. AI tự nhận diện sản phẩm bảo hiểm phù hợp
4. AI hỏi linh hoạt như đánh giá viên thật — mỗi lần 1-2 câu, đợi trả lời rồi hỏi tiếp
5. Khi đủ thông tin → AI đánh giá và kết luận:
   - ✅ **ĐỦ ĐIỀU KIỆN TIẾP NHẬN BỒI THƯỜNG**
   - ❌ **KHÔNG ĐỦ ĐIỀU KIỆN TIẾP NHẬN BỒI THƯỜNG** + lý do
6. Hồ sơ tự động lưu vào `claim_logs/` dạng JSON

## Sản phẩm bảo hiểm đã nhập liệu

11 sản phẩm từ https://www..com.vn/san-pham:

1. Combo 360° Nhà – Gia đình – Ô tô (599k/năm)
2. Combo 360° Nhà – Gia đình – Xe máy (199k/năm)
3. Cháy nổ toàn diện nhà ở Phú Gia
4. Sức khỏe gia đình Family Care (2-11.2 triệu/năm)
5. TNDS chủ xe mô tô/xe gắn máy
6. Gián đoạn kinh doanh
7. Kết hợp con người (Bảo hiểm thân thể)
8. Bệnh ung thư
9. Bệnh hiểm nghèo
10. Tai nạn con người 24/24
11. Tai nạn con người mức trách nhiệm cao

## Cấu trúc file

```
D:\WORK\idea\
├── app.py                  # App Streamlit AI chatbot
├── insurance_products.py   # Dữ liệu sản phẩm + điều kiện tiếp nhận bồi thường
├── requirements.txt
├── README.md
└── claim_logs/             # Thư mục lưu hồ sơ (tự tạo)
    └── claim_*.json
```

## Tùy chỉnh

- Đổi model: chỉnh trong sidebar hoặc set env `CLAIM_MODEL`
- Đổi API endpoint: chỉnh trong sidebar hoặc set env `OLLAMA_BASE_URL`
- Thêm sản phẩm: thêm vào `PRODUCTS` trong `insurance_products.py`

python -m streamlit run D:\WORK\idea\app.py

cd D:\WORK\idea
rd /s /q __pycache__
python -m streamlit run app.py