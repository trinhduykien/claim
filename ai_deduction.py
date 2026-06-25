# -*- coding: utf-8 -*-
"""
AI Deduction Analysis Module cho PJICO Claim Bot
- Gọi Ollama Cloud API (kimi-k2.6:cloud) để phân tích ảnh thiệt hại + hợp đồng
- Đọc API key từ: Streamlit secrets -> env var -> file local
- Lưu câu trả lời vào thu muc "trả lời"
"""

import os
import json
import base64
import re
from datetime import datetime
import requests

# ============================================================
# CONFIG
# ============================================================

API_KEY = ""

# Cách 1: Streamlit Cloud Secrets
try:
    import streamlit as st
    _secrets_key = st.secrets.get("ollama_api_key", None)
    if _secrets_key:
        API_KEY = _secrets_key.strip()
except Exception:
    pass

# Cách 2: Environment variable
if not API_KEY:
    API_KEY = os.environ.get("OLLAMA_API_KEY", "")

# Cách 3: File local
if not API_KEY:
    _key_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".kimi_api_key")
    if os.path.exists(_key_file):
        with open(_key_file, "r", encoding="utf-8") as f:
            API_KEY = f.read().strip()

OLLAMA_BASE_URL = "https://ollama.com/v1"
MODEL = "kimi-k2.6:cloud"

REPLY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trả lời")


def has_api_key():
    return bool(API_KEY)


def encode_image_to_base64(image_path):
    with open(image_path, "rb") as f:
        ext = os.path.splitext(image_path)[1].lower().lstrip(".")
        mime = f"image/{ext}" if ext in ("jpg", "jpeg", "png", "gif", "webp") else "image/jpeg"
        data = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{data}"


def extract_pdf_text(pdf_path):
    """Đọc text từ PDF. Trả về None nếu là ảnh scan."""
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

    return None  # PDF là ảnh scan


def pdf_pages_to_images(pdf_path, max_pages=10):
    """Chuyển tối đa max_pages trang PDF thành ảnh base64."""
    try:
        import fitz
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        images = []
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            # 80 DPI để giảm size nhưng vẫn đọc được
            mat = fitz.Matrix(80/72, 80/72)
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("jpeg")  # JPEG nhỏ hơn PNG
            img_b64 = base64.b64encode(img_bytes).decode("utf-8")
            images.append(f"data:image/jpeg;base64,{img_b64}")
        doc.close()
        return images, total_pages
    except ImportError:
        pass
    except Exception:
        pass
    return [], 0


def build_analysis_prompt(claim_data, contract_text, num_contract_pages):
    """Xây prompt phân tích khấu trừ — chain-of-thought có hướng dẫn."""
    product_name = claim_data.get("product", {}).get("name", "Không rõ")
    answers = claim_data.get("answers", {})

    answers_text = ""
    for qid, ans in answers.items():
        answers_text += f"- {qid}: {ans}\n"

    if num_contract_pages > 0:
        contract_info = f"""Hợp đồng bảo hiểm có {num_contract_pages} trang ảnh đính kèm.
BẠN PHẢI ĐỌC KỸ TỪNG TRANG ẢNH HỢP ĐỒNG. Mỗi trang có thể chứa:
- Trang bìa: thông tin hợp đồng, bên tham gia, thời hạn
- Trang giữa: phạm vi bảo hiểm, quyền lợi, hạn mức chi trả
- Trang điều khoản loại trừ: các khoản KHÔNG được bồi thường
- Trang khái niệm/định nghĩa: giải thích thuật ngữ y tế, thiết bị y tế, vật liệu...
- Trang phụ lục: danh mục chi tiết các hạng mục được/không được chi trả

QUAN TRỌNG: Điều khoản loại trừ ở một trang có thể tham chiếu đến khái niệm ở trang khác.
Ví dụ: Trang 4 ghi "không bồi thường chi phí thiết bị y tế hỗ trợ điều trị" + Trang 5-7 định nghĩa "Sanlein thuộc thiết bị y tế hỗ trợ điều trị" → Sanlein bị khấu trừ."""
    elif contract_text and contract_text != "(Không có hợp đồng đính kèm)":
        contract_info = f"Nội dung hợp đồng bảo hiểm:\n{contract_text}"
    else:
        contract_info = "(Không có hợp đồng đính kèm)"

    prompt = f"""BẠN LÀ CHUYÊN VIÊN BỒI THƯỜNG BẢO HIỂM PJICO. NHIỆM VỤ: PHÂN TÍCH KHẤU TRỪ BỒI THƯỜNG.

THÔNG TIN HỒ SƠ:
- Sản phẩm bảo hiểm: {product_name}
- Khách hàng: {claim_data.get('customer_name', 'Không rõ')}
- Loại sự cố: {answers.get('incident_type', 'Không rõ')}

{contract_info}

HƯỚNG DẪN PHÂN TÍCH (LÀM THEO TỪNG BƯỚC):

BƯỚC 1 — ĐỌC HÓA ĐƠN:
- Đọc ảnh hóa đơn/viện phí đính kèm.
- Liệt kê TỪNG khoản chi phí: tên thuốc/dịch vụ + số lượng + đơn giá + thành tiền.
- Tính tổng chi phí.

BƯỚC 2 — ĐỌC HỢP ĐỒNG (TẤT CẢ TRANG):
- Đọc từng trang hợp đồng từ đầu đến cuối.
- Tìm các điều khoản LOẠI TRỪ: các khoản KHÔNG được bồi thường.
- Tìm các KHÁI NIỆM/ĐỊNH NGHĨA: giải thích thuật ngữ (thiết bị y tế, vật liệu, thuốc men...).
- Tìm các HẠN MỨC: giới hạn chi trả theo hạng mục.
- ĐÁNH DẤU: điều khoản loại trừ ở trang nào, khái niệm ở trang nào.

BƯỚC 3 — CROSS-REFERENCE (SO SÁNH CHÉO):
- Với TỪNG khoản trong hóa đơn, tra cứu trong hợp đồng:
  + Khoản này có nằm trong điều khoản loại trừ không?
  + Khoản này có thuộc khái niệm/định nghĩa nào bị loại trừ không?
  + Khoản này có vượt hạn mức chi trả không?
  + PHẢI KIỂM TRA CẢ ĐỊNH NGHĨA Ở TRANG KHÁC (vd: loại trừ ở trang 4 nói "thiết bị y tế" → phải xem trang 5-7 định nghĩa gì là "thiết bị y tế").
- Nếu khoản trong hóa đơn KHỚP với điều khoản loại trừ → bị KHẤU TRỪ.
- Nếu không khớp bất kỳ điều khoản loại trừ nào → KHÔNG bị khấu trừ.

BƯỚC 4 — TRẢ LỜI:
- Trả lời BẰNG TIẾNG VIỆT.
- Trả lời theo đúng định dạng bên dưới.
- Mỗi khoản khấu trừ phải ghi rõ: số tiền + lý do + trang nào trong hợp đồng.

ĐỊNH DẠNG TRẢ LỜI (BẮT BUỘC):

**Tổng chi phí theo hóa đơn:** [số tiền] VNĐ

| STT | Mục khấu trừ | Số tiền (VNĐ) | Lý do khấu trừ | Tham chiếu hợp đồng |
|-----|-------------|--------------|----------------|-------------------|
| 1   | [tên khoản] | [số tiền]    | [lý do: khoản này thuộc điều khoản loại trừ nào] | Trang [X], mục [Y] |

**Tổng khấu trừ:** [số tiền] VNĐ
**Tiền bồi thường thực nhận:** [Tổng - Khấu trừ] = [số tiền] VNĐ

Nếu sau khi kiểm tra tất cả điều khoản loại trừ mà không có khoản nào bị khấu trừ, ghi:
Không có khoản khấu trừ, khách hàng nhận toàn bộ [số tiền] VNĐ.
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

    # Xử lý hợp đồng
    contract_text = "(Không có hợp đồng đính kèm)"
    num_contract_pages = 0
    contract_images = []

    if contract_path and os.path.exists(contract_path):
        ext = os.path.splitext(contract_path)[1].lower().lstrip(".")
        if ext == "pdf":
            # Thử đọc text trước
            pdf_text = extract_pdf_text(contract_path)
            if pdf_text:
                contract_text = pdf_text[:10000]
            else:
                # PDF scan → chuyển thành ảnh
                contract_images, total_pages = pdf_pages_to_images(contract_path, max_pages=10)
                if contract_images:
                    num_contract_pages = len(contract_images)
                    contract_text = f"(Hợp đồng PDF gồm {total_pages} trang, gửi {num_contract_pages} trang ảnh)"
        elif ext in ("jpg", "jpeg", "png", "gif", "webp"):
            contract_images.append(encode_image_to_base64(contract_path))
            num_contract_pages = 1
            contract_text = "(Hợp đồng dạng 1 ảnh)"

    prompt = build_analysis_prompt(claim_data, contract_text, num_contract_pages)

    # Build content: prompt text + ảnh hóa đơn + ảnh hợp đồng
    content = [{"type": "text", "text": prompt}]

    # Ảnh hóa đơn/thiệt hại
    for photo_path in photo_paths:
        if os.path.exists(photo_path):
            try:
                content.append({"type": "image_url", "image_url": {"url": encode_image_to_base64(photo_path)}})
            except Exception as e:
                content.append({"type": "text", "text": f"[Không thể đọc ảnh: {str(e)}]"})

    # Ảnh hợp đồng
    for img_b64 in contract_images:
        content.append({"type": "image_url", "image_url": {"url": img_b64}})

    # System message
    system_msg = {
        "role": "system",
        "content": "Bạn là chuyên viên bồi thường bảo hiểm PJICO. LUÔN trả lời bằng tiếng Việt. Phải ĐỌC KỸ và SO SÁNH CHÉO giữa hóa đơn và hợp đồng: khoản nào trong hóa đơn có bị loại trừ trong hợp đồng (kể cả qua định nghĩa ở trang khác) thì KHẤU TRỪ. Trả lời theo đúng định dạng bảng. KHÔNG trả lời 'không có khấu trừ' nếu chưa kiểm tra kỹ tất cả trang hợp đồng."
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
        "temperature": 0.2,
        "max_tokens": 4000,
        "think": False
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

        ai_text = msg.get("content", "") or ""
        reasoning = msg.get("reasoning", "") or ""

        if ai_text.strip():
            return {"success": True, "response": ai_text.strip(), "error": ""}

        if not reasoning.strip():
            return {"success": True, "response": "AI không trả về nội dung. Vui lòng thử lại.", "error": ""}

        # Content rỗng, reasoning có nội dung → tìm phần bảng/đáp án
        markers = ["**Tổng chi phí", "| STT |", "**Tổng khấu trừ", "Không có khoản khấu trừ", "Tổng chi phí theo"]
        for marker in markers:
            idx = reasoning.find(marker)
            if idx >= 0:
                return {"success": True, "response": reasoning[idx:][:3000].strip(), "error": ""}

        # Fallback: tìm phần cuối có dấu hiệu trả lời
        lines = reasoning.split("\n")
        answer_lines = []
        in_answer = False
        for line in lines:
            if any(m in line for m in ["**Tổng", "| STT", "| 1 ", "| 1  ", "Không có khoản", "Tiền bồi thường"]):
                in_answer = True
            if in_answer:
                answer_lines.append(line)

        if answer_lines:
            return {"success": True, "response": "\n".join(answer_lines)[:3000], "error": ""}

        # Last resort: lấy 1000 ký tự cuối
        return {"success": True, "response": reasoning[-1000:].strip(), "error": ""}

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