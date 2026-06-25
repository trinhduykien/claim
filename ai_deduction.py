# -*- coding: utf-8 -*-
"""
AI Deduction Analysis Module cho PJICO Claim Bot
- Gọi Ollama Cloud API (model: kimi-k2.7-code) để phân tích ảnh thiệt hại + hợp đồng
- Xác định các khoản khấu trừ trong tiền bồi thường
- Trả về câu trả lời cho khách hàng
- Lưu câu trả lời vào thư mục "trả lời"
"""

import os
import json
import base64
import re
from datetime import datetime
import requests

# ============================================================
# CONFIG — đọc API key từ env hoặc file local, KHÔNG hardcode
# ============================================================

# Cách 1: Environment variable
# set OLLAMA_API_KEY=your_key_here  (PowerShell)
# $env:OLLAMA_API_KEY="your_key"    (PowerShell session)
API_KEY = os.environ.get("OLLAMA_API_KEY", "")

# Cách 2: File local (không commit lên git) — dùng lại .kimi_api_key
_key_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".kimi_api_key")
if not API_KEY and os.path.exists(_key_file):
    with open(_key_file, "r", encoding="utf-8") as f:
        API_KEY = f.read().strip()

# Ollama Cloud endpoint
OLLAMA_BASE_URL = "https://api.ollama.ai/v1"  # OpenAI-compatible endpoint
MODEL = "kimi-k2.7-code"

# Thư mục lưu câu trả lời
REPLY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trả lời")


def has_api_key():
    """Kiểm tra đã có API key chưa."""
    return bool(API_KEY)


def encode_image_to_base64(image_path):
    """Encode ảnh sang base64 để gửi API."""
    with open(image_path, "rb") as f:
        ext = os.path.splitext(image_path)[1].lower().lstrip(".")
        mime = f"image/{ext}" if ext in ("jpg", "jpeg", "png", "gif", "webp") else "image/jpeg"
        data = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{data}"


def build_analysis_prompt(claim_data, photo_paths, contract_path):
    """
    Xây prompt gửi AI: gồm thông tin claim, danh sách ảnh, hợp đồng.
    Yêu cầu AI phân tích khấu trừ và trả lời khách hàng.
    """
    product_name = claim_data.get("product", {}).get("name", "Không rõ")
    answers = claim_data.get("answers", {})
    
    # Tóm tắt câu trả lời đánh giá
    answers_text = ""
    for qid, ans in answers.items():
        answers_text += f"- {qid}: {ans}\n"

    prompt = f"""Bạn là chuyên gia bồi thường bảo hiểm của PJICO (Tổng Công ty Cổ phần Bảo hiểm Petrolimex).

Nhiệm vụ: Phân tích hồ sơ bồi thường và xác định các khoản khấu trừ trong tiền bồi thường phải trả cho khách hàng.

THÔNG TIN HỒ SƠ:
- Sản phẩm bảo hiểm: {product_name}
- Khách hàng: {claim_data.get('customer_name', 'Không rõ')}
- Thời gian đánh giá: {claim_data.get('timestamp', 'Không rõ')}

CÂU TRẢ LỜI ĐÁNH GIÁ ĐIỀU KIỆN:
{answers_text}

HƯỚNG DẪN PHÂN TÍCH:
1. Xem xét các ảnh thiệt hại được đính kèm (nếu có).
2. Xem xét hợp đồng bảo hiểm được đính kèm (nếu có).
3. Dựa trên thông tin hồ sơ + ảnh + hợp đồng, xác định:
   - Các khoản khấu trừ hợp lệ (franchise, deductible, khấu trừ theo tỷ lệ thiếu phí, khấu trừ do vi phạm điều kiện...)
   - Các khoản không được bồi thường (thiệt hại ngoài phạm vi, tài sản không thuộc bảo hiểm...)
   - Tiền bồi thường dự kiến sau khấu trừ
4. Giải thích rõ ràng lý do từng khoản khấu trừ cho khách hàng.

YÊU CẦU ĐỊNH DẠNG TRẢ LỜI:
- Viết bằng tiếng Việt, lịch sự, chuyên nghiệp.
- Trình bày rõ: Tổng bồi thường → Khấu trừ → Bồi thường thực nhận.
- Nếu không có khấu trừ, nói rõ "Không có khoản khấu trừ, khách hàng nhận toàn bộ tiền bồi thường."
- Nếu có ảnh/hợp đồng đính kèm, đề cập đến chi tiết quan trọng trong đó.

Lưu ý: Chỉ đưa ra phân tích dựa trên thông tin có sẵn. Nếu thông tin không đủ, ghi rõ cần bổ sung gì.
"""

    return prompt


def analyze_deduction(claim_data, photo_paths, contract_path):
    """
    Gọi Ollama Cloud API (kimi-k2.7-code) để phân tích khấu trừ.
    
    Args:
        claim_data: dict — dữ liệu claim log (product, answers, result, customer_name...)
        photo_paths: list[str] — đường dẫn ảnh thiệt hại
        contract_path: str — đường dẫn file hợp đồng (ảnh hoặc PDF)
    
    Returns:
        dict: {"success": bool, "response": str, "error": str}
    """
    if not has_api_key():
        return {
            "success": False,
            "response": "",
            "error": "Chưa cấu hình API key. Vui lòng set environment variable OLLAMA_API_KEY hoặc tạo file .kimi_api_key"
        }

    prompt = build_analysis_prompt(claim_data, photo_paths, contract_path)

    # Build messages với ảnh — dùng OpenAI-compatible format
    content = [{"type": "text", "text": prompt}]

    # Thêm ảnh thiệt hại
    for photo_path in photo_paths:
        if os.path.exists(photo_path):
            try:
                img_b64 = encode_image_to_base64(photo_path)
                content.append({
                    "type": "image_url",
                    "image_url": {"url": img_b64}
                })
            except Exception as e:
                content.append({"type": "text", "text": f"[Không thể đọc ảnh: {os.path.basename(photo_path)} - {str(e)}]"})

    # Thêm hợp đồng (nếu là ảnh)
    if contract_path and os.path.exists(contract_path):
        ext = os.path.splitext(contract_path)[1].lower().lstrip(".")
        if ext in ("jpg", "jpeg", "png", "gif", "webp"):
            try:
                img_b64 = encode_image_to_base64(contract_path)
                content.append({
                    "type": "image_url",
                    "image_url": {"url": img_b64}
                })
            except Exception as e:
                content.append({"type": "text", "text": f"[Không thể đọc hợp đồng: {str(e)}]"})
        else:
            # PDF hoặc file khác → ghi chú
            content.append({"type": "text", "text": f"[Hợp đồng đính kèm: {os.path.basename(contract_path)}]"})

    messages = [{"role": "user", "content": content}]

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 2000
    }

    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=120
        )
        response.raise_for_status()
        result = response.json()
        ai_text = result["choices"][0]["message"]["content"]
        return {"success": True, "response": ai_text, "error": ""}
    except requests.exceptions.Timeout:
        return {"success": False, "response": "", "error": "AI xử lý quá thời gian (timeout 120s)"}
    except requests.exceptions.HTTPError as e:
        return {"success": False, "response": "", "error": f"HTTP error: {e.response.status_code} - {e.response.text[:200]}"}
    except Exception as e:
        return {"success": False, "response": "", "error": str(e)}


def save_reply(claim_data, ai_response, photo_names, contract_name):
    """
    Lưu câu trả lời AI vào thư mục "trả lời".
    
    Returns:
        str: đường dẫn file đã lưu
    """
    os.makedirs(REPLY_DIR, exist_ok=True)
    
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = re.sub(r'[^\w]', '_', claim_data.get("customer_name", "khach_hang"))
    product_id = claim_data.get("product", {}).get("id", "unknown")
    
    filename = f"reply_{safe_name}_{product_id}_{ts}.md"
    filepath = os.path.join(REPLY_DIR, filename)
    
    content = f"""# Phân tích khoản khấu trừ bồi thường

**Khách hàng:** {claim_data.get('customer_name', 'Không rõ')}
**Sản phẩm:** {claim_data.get('product', {}).get('name', 'Không rõ')}
**Thời gian:** {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}

## Ảnh thiệt hại đính kèm:
"""
    for name in photo_names:
        content += f"- {name}\n"
    
    content += f"""
## Hợp đồng đính kèm:
- {contract_name or 'Không có'}

## Phân tích AI:
{ai_response}
"""
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    
    return filepath