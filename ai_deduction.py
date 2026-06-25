# -*- coding: utf-8 -*-
"""
AI Deduction Analysis Module cho PJICO Claim Bot
- Gọi Ollama Cloud API (model: kimi-k2.7-code) để phân tích ảnh thiệt hại + hợp đồng
- Đọc API key từ: Streamlit secrets → env var → file local
- Lưu câu trả lời vào thư mục "trả lời"
"""

import os
import json
import base64
import re
from datetime import datetime
import requests

# ============================================================
# CONFIG — đọc API key từ nhiều nguồn, KHÔNG hardcode
# ============================================================

API_KEY = ""

# Cách 1: Streamlit Cloud Secrets (ưu tiên cao nhất cho online)
try:
    import streamlit as st
    _secrets_key = st.secrets.get("ollama_api_key", None)
    if _secrets_key:
        API_KEY = _secrets_key
except Exception:
    pass

# Cách 2: Environment variable (cho local)
if not API_KEY:
    API_KEY = os.environ.get("OLLAMA_API_KEY", "")

# Cách 3: File local .kimi_api_key (cho local, không commit lên git)
if not API_KEY:
    _key_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".kimi_api_key")
    if os.path.exists(_key_file):
        with open(_key_file, "r", encoding="utf-8") as f:
            API_KEY = f.read().strip()

# Ollama Cloud endpoint (OpenAI-compatible)
OLLAMA_BASE_URL = "https://ollama.com/v1"
MODEL = "kimi-k2.6:cloud"  # Ollama Cloud, hỗ trợ vision (đọc ảnh)

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


def extract_pdf_text(pdf_path):
    """Đọc text từ PDF. Thử PyMuPDF trước, sau đó pdfplumber. Trả về None nếu là ảnh scan."""
    # Thử PyMuPDF
    try:
        import fitz
        doc = fitz.open(pdf_path)
        text = ""
        has_text = False
        for page_num, page in enumerate(doc, 1):
            page_text = page.get_text().strip()
            if page_text:
                has_text = True
                text += f"\n--- Trang {page_num} ---\n"
                text += page_text
        doc.close()
        if has_text:
            return text
    except ImportError:
        pass
    except Exception:
        pass
    
    # Thử pdfplumber
    try:
        import pdfplumber
        text = ""
        has_text = False
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                page_text = page.extract_text() or ""
                if page_text.strip():
                    has_text = True
                    text += f"\n--- Trang {page_num} ---\n"
                    text += page_text
        if has_text:
            return text
    except ImportError:
        pass
    except Exception:
        pass
    
    # PDF là ảnh scan hoặc không đọc được
    return None


def pdf_pages_to_images(pdf_path, max_pages=3):
    """Chuyển các trang PDF thành ảnh base64 để gửi cho AI (khi PDF là ảnh scan)."""
    try:
        import fitz
        doc = fitz.open(pdf_path)
        images = []
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            mat = fitz.Matrix(100/72, 100/72)
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("png")
            img_b64 = base64.b64encode(img_bytes).decode("utf-8")
            images.append(f"data:image/png;base64,{img_b64}")
        doc.close()
        return images
    except ImportError:
        # PyMuPDF not available, try pdf2image
        try:
            from pdf2image import convert_from_path
            pages = convert_from_path(pdf_path, dpi=100, first_page=1, last_page=max_pages)
            images = []
            for page in pages:
                import io
                buf = io.BytesIO()
                page.save(buf, format="PNG")
                img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                images.append(f"data:image/png;base64,{img_b64}")
            return images
        except ImportError:
            return []
    except Exception as e:
        return []


def build_analysis_prompt(claim_data, photo_paths, contract_path, contract_text="(Không có hợp đồng đính kèm)"):
    """Xây prompt gửi AI phân tích khấu trừ."""
    product_name = claim_data.get("product", {}).get("name", "Không rõ")
    answers = claim_data.get("answers", {})
    
    answers_text = ""
    for qid, ans in answers.items():
        answers_text += f"- {qid}: {ans}\n"

    prompt = f"""Bạn là chuyên gia bồi thường bảo hiểm của PJICO. Phân tích khấu trừ bồi thường.

THÔNG TIN HỒ SƠ:
- Sản phẩm: {product_name}
- Khách hàng: {claim_data.get('customer_name', 'Không rõ')}

CÂU TRẢ LỜI ĐÁNH GIÁ:
{answers_text}

NỘI DUNG HỢP ĐỒNG BẢO HIỂM:
{contract_text}

YÊU CẦU:
1. Đọc ảnh hóa đơn/viện phí → liệt kê từng khoản chi phí + số tiền.
2. Đọc nội dung hợp đồng bảo hiểm ở trên → tìm các điều khoản loại trừ/không chi trả.
3. So sánh → xác định khoản nào trong hóa đơn bị khấu trừ.

TRẢ LỜI ĐÚNG ĐỊNH DẠNG SAU (tiếng Việt, ngắn gọn):

**Tổng chi phí theo hóa đơn:** [số tiền] VNĐ

| STT | Mục khấu trừ | Số tiền (VNĐ) | Lý do khấu trừ | Tham chiếu hợp đồng |
|-----|-------------|--------------|----------------|-------------------|
| 1   | [tên khoản] | [số tiền]    | [lý do]        | Trang [X], mục [Y] |

**Tổng khấu trừ:** [số tiền] VNĐ
**Tiền bồi thường thực nhận:** [Tổng - Khấu trừ] = [số tiền] VNĐ

Nếu không có khấu trừ, ghi: "Không có khoản khấu trừ, khách hàng nhận toàn bộ [số tiền] VNĐ."
"""
    return prompt


def analyze_deduction(claim_data, photo_paths, contract_path):
    """Gọi Ollama Cloud API để phân tích khấu trừ."""
    if not has_api_key():
        return {
            "success": False,
            "response": "",
            "error": "Chưa cấu hình API key. Vui lòng thêm key vào Streamlit Cloud Secrets (key: ollama_api_key) hoặc tạo file .kimi_api_key (local)."
        }

    # Khởi tạo content trước (chứa prompt + ảnh)
    content = []

    # Đọc hợp đồng trước
    contract_text = "(Không có hợp đồng đính kèm)"
    if contract_path and os.path.exists(contract_path):
        ext = os.path.splitext(contract_path)[1].lower().lstrip(".")
        if ext == "pdf":
            pdf_text = extract_pdf_text(contract_path)
            if pdf_text and not pdf_text.startswith("[Lỗi"):
                contract_text = pdf_text[:8000]
            else:
                # PDF là ảnh scan → chuyển trang thành ảnh để gửi AI
                pdf_images = pdf_pages_to_images(contract_path, max_pages=3)
                if pdf_images:
                    contract_text = f"(Hợp đồng PDF gồm {len(pdf_images)} trang ảnh - xem ảnh đính kèm)"
                    for idx, img_b64 in enumerate(pdf_images):
                        content.append({"type": "image_url", "image_url": {"url": img_b64}})
                else:
                    contract_text = "(Hợp đồng PDF là ảnh scan hoặc không thể đọc text. Vui lòng upload hợp đồng dạng ảnh JPG/PNG để AI đọc được nội dung.)"
        elif ext in ("jpg", "jpeg", "png", "gif", "webp"):
            contract_text = "(Hợp đồng đính kèm dạng ảnh - xem ảnh trong cuộc trò chuyện)"
        else:
            contract_text = f"(Hợp đồng đính kèm: {os.path.basename(contract_path)})"

    prompt = build_analysis_prompt(claim_data, photo_paths, contract_path, contract_text)

    # Thêm prompt vào đầu content
    content.insert(0, {"type": "text", "text": prompt})

    # Thêm ảnh thiệt hại
    for photo_path in photo_paths:
        if os.path.exists(photo_path):
            try:
                img_b64 = encode_image_to_base64(photo_path)
                content.append({"type": "image_url", "image_url": {"url": img_b64}})
            except Exception as e:
                content.append({"type": "text", "text": f"[Không thể đọc ảnh: {os.path.basename(photo_path)} - {str(e)}]"})

    # Thêm hợp đồng dạng ảnh (không phải PDF - PDF đã xử lý ở trên)
    if contract_path and os.path.exists(contract_path):
        ext = os.path.splitext(contract_path)[1].lower().lstrip(".")
        if ext in ("jpg", "jpeg", "png", "gif", "webp"):
            try:
                img_b64 = encode_image_to_base64(contract_path)
                content.append({"type": "image_url", "image_url": {"url": img_b64}})
            except Exception as e:
                content.append({"type": "text", "text": f"[Không thể đọc hợp đồng: {str(e)}]"})
        else:
            content.append({"type": "text", "text": f"[Hợp đồng đính kèm: {os.path.basename(contract_path)}]"})

    # System message ép AI trả lời trực tiếp, không reasoning
    system_msg = {
        "role": "system",
        "content": "Bạn là chuyên gia bồi thường bảo hiểm PJICO. Khi được yêu cầu phân tích, hãy trả lời trực tiếp bằng tiếng Việt theo đúng định dạng bảng yêu cầu. KHÔNG giải thích quá dài, KHÔNG suy nghĩ nội bộ. Trả lời ngắn gọn, trực tiếp."
    }
    user_msg = {"role": "user", "content": content}
    messages = [system_msg, user_msg]

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 4000
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
        msg = result["choices"][0]["message"]
        # Model kimi-k2.6 có thể trả content rỗng, nội dung nằm trong "reasoning"
        ai_text = msg.get("content", "") or ""
        reasoning = msg.get("reasoning", "") or ""
        # Nếu content rỗng nhưng có reasoning → dùng reasoning
        if not ai_text.strip() and reasoning.strip():
            ai_text = reasoning
        return {"success": True, "response": ai_text, "error": ""}
    except requests.exceptions.Timeout:
        return {"success": False, "response": "", "error": "AI xử lý quá thời gian (timeout 120s)"}
    except requests.exceptions.HTTPError as e:
        return {"success": False, "response": "", "error": f"HTTP error: {e.response.status_code} - {e.response.text[:200]}"}
    except Exception as e:
        return {"success": False, "response": "", "error": str(e)}


def save_reply(claim_data, ai_response, photo_names, contract_name):
    """Lưu câu trả lời AI vào thư mục trả lời."""
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