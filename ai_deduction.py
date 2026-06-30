# -*- coding: utf-8 -*-
"""
AI Deduction Analysis Module cho PJICO Claim Bot
Pipeline 3 tầng (Map-Reduce):
  Tầng 1 (Map): N Kimi đọc ảnh song song — 1 Kimi đọc hóa đơn, N-1 Kimi chia trang hợp đồng
  Tầng 2 (Reduce): N GLM phân tích song song — 1 GLM phân tích hóa đơn, N-1 GLM phân tích trang hợp đồng
  Tầng 3 (Merge): 1 GLM "trưởng phòng" tổng hợp → xuất bảng khấu trừ cuối
- Đọc API key từ: Streamlit secrets -> env var -> file local
- Lưu câu trả lời vào thư mục "trả lời"
"""

import os
import json
import base64
import re
from datetime import datetime
import requests
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

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

VISION_MODEL = "kimi-k2.6:cloud"     # Tầng 1: đọc ảnh, trích xuất text
ANALYSIS_MODEL = "glm-5.2:cloud"     # Tầng 2+3: phân tích + tổng hợp

REPLY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trả lời")

# Số trang hợp đồng mỗi Kimi/GLM xử lý
CONTRACT_CHUNK_SIZE = 10


def has_api_key():
    return bool(API_KEY)


# ============================================================
# UTILITY: IMAGE / PDF
# ============================================================

def encode_image_to_base64(image_path):
    with open(image_path, "rb") as f:
        ext = os.path.splitext(image_path)[1].lower().lstrip(".")
        mime = f"image/{ext}" if ext in ("jpg", "jpeg", "png", "gif", "webp") else "image/jpeg"
        data = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{data}"


def extract_pdf_text(pdf_path):
    """Đọc text từ PDF. Trả về None nếu là ảnh scan hoặc text quá ít."""
    try:
        import fitz
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        text = ""
        pages_with_text = 0
        total_text_chars = 0
        for page_num, page in enumerate(doc, 1):
            page_text = page.get_text().strip()
            if page_text:
                pages_with_text += 1
                total_text_chars += len(page_text)
                text += f"\n--- Trang {page_num} ---\n"
                text += page_text
        doc.close()
        if pages_with_text > 0 and pages_with_text >= total_pages * 0.5 and total_text_chars >= 500:
            return text
        else:
            return None
    except ImportError:
        pass
    except Exception:
        pass

    try:
        import pdfplumber
        text = ""
        pages_with_text = 0
        total_text_chars = 0
        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
            for page_num, page in enumerate(pdf.pages, 1):
                page_text = page.extract_text() or ""
                page_text = page_text.strip()
                if page_text:
                    pages_with_text += 1
                    total_text_chars += len(page_text)
                    text += f"\n--- Trang {page_num} ---\n"
                    text += page_text
        if pages_with_text > 0 and pages_with_text >= total_pages * 0.5 and total_text_chars >= 500:
            return text
        else:
            return None
    except ImportError:
        pass
    except Exception:
        pass

    return None


def pdf_pages_to_images(pdf_path, max_pages=30):
    """Chuyển tối đa max_pages trang PDF thành ảnh base64."""
    try:
        import fitz
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        images = []
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            mat = fitz.Matrix(80/72, 80/72)
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("jpeg")
            img_b64 = base64.b64encode(img_bytes).decode("utf-8")
            images.append(f"data:image/jpeg;base64,{img_b64}")
        doc.close()
        return images, total_pages
    except ImportError:
        pass
    except Exception:
        pass
    return [], 0


# ============================================================
# API CALL HELPERS
# ============================================================

def call_vision_model(messages, max_tokens=8000, timeout=180):
    """Gọi vision model (Kimi K2.6) qua Ollama Cloud API."""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": VISION_MODEL,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": max_tokens,
        "think": False
    }
    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=timeout
        )
        response.raise_for_status()
        result = response.json()
        msg = result["choices"][0]["message"]

        content_text = msg.get("content", "") or ""
        reasoning = msg.get("reasoning", "") or ""

        # Ưu tiên content
        if content_text.strip():
            return {"success": True, "text": content_text.strip(), "error": ""}

        # Fallback: reasoning — lọc thinking tiếng Anh, giữ text tiếng Việt
        if reasoning.strip():
            lines = reasoning.split("\n")
            start_idx = 0
            for i, line in enumerate(lines):
                stripped = line.strip()
                if not stripped or len(stripped) < 10:
                    continue
                viet_chars = sum(1 for c in stripped if 0x00C0 <= ord(c) <= 0x024F or 0x1E00 <= ord(c) <= 0x1EFF)
                if viet_chars >= 3:
                    start_idx = i
                    break
            result_text = "\n".join(lines[start_idx:]).strip()
            if not result_text or len(result_text) < 50:
                result_text = reasoning.strip()
            if len(result_text) > 15000:
                result_text = result_text[:15000]
            return {"success": True, "text": result_text, "error": ""}

        return {"success": False, "text": "", "error": "AI không trả về nội dung."}

    except requests.exceptions.Timeout:
        return {"success": False, "text": "", "error": f"Vision model timeout ({timeout}s)"}
    except requests.exceptions.HTTPError as e:
        return {"success": False, "text": "", "error": f"HTTP error: {e.response.status_code} - {e.response.text[:200]}"}
    except Exception as e:
        return {"success": False, "text": "", "error": str(e)}


def call_analysis_model(messages, max_tokens=6000, timeout=180):
    """Gọi analysis model (GLM-5.2) qua Ollama Cloud API."""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": ANALYSIS_MODEL,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "think": False
    }
    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=timeout
        )
        response.raise_for_status()
        result = response.json()
        msg = result["choices"][0]["message"]

        content_text = msg.get("content", "") or ""
        reasoning = msg.get("reasoning", "") or ""

        if content_text.strip():
            return {"success": True, "text": content_text.strip(), "error": ""}

        # Fallback: reasoning
        if reasoning.strip():
            lines = reasoning.split("\n")
            start_idx = 0
            for i, line in enumerate(lines):
                stripped = line.strip()
                if not stripped or len(stripped) < 10:
                    continue
                viet_chars = sum(1 for c in stripped if 0x00C0 <= ord(c) <= 0x024F or 0x1E00 <= ord(c) <= 0x1EFF)
                if viet_chars >= 3:
                    start_idx = i
                    break
            result_text = "\n".join(lines[start_idx:]).strip()
            if not result_text or len(result_text) < 50:
                result_text = reasoning.strip()
            if len(result_text) > 8000:
                result_text = result_text[:8000]
            return {"success": True, "text": result_text, "error": ""}

        return {"success": False, "text": "", "error": "AI không trả về nội dung."}

    except requests.exceptions.Timeout:
        return {"success": False, "text": "", "error": f"Analysis model timeout ({timeout}s)"}
    except requests.exceptions.HTTPError as e:
        return {"success": False, "text": "", "error": f"HTTP error: {e.response.status_code} - {e.response.text[:200]}"}
    except Exception as e:
        return {"success": False, "text": "", "error": str(e)}


# ============================================================
# TẦNG 1: KIMI ĐỌC ẢNH (MAP)
# ============================================================

def build_invoice_prompt():
    return """Bạn là chuyên gia trích xuất dữ liệu từ ảnh hóa đơn/viện phí. Nhiệm vụ: ĐỌC ẢNH HÓA ĐƠN và trích xuất TOÀN BỘ nội dung thành text có cấu trúc.

YÊU CẦU:
1. Đọc từng dòng trên hóa đơn, không bỏ sót bất kỳ dòng nào.
2. Với mỗi hạng mục, ghi rõ: tên mục, mô tả, đơn vị tính, số lượng, đơn giá, thành tiền.
3. Ghi rõ các khoản thuế, phí khác nếu có.
4. Ghi rõ TỔNG CỘNG (tổng số tiền).
5. Giữ nguyên số liệu chính xác - không làm tròn, không ước lượng.

YÊU CẦU ĐẶC BIỆT VỀ TÊN THUỐC / HÀNG MỤC Y TẾ:
- Tên thuốc phải được đọc CHÍNH XÁC từng chữ cái. Đặc biệt chú ý các ký tự dễ nhầm: b/d, n/h, m/n, l/i, o/a.
- Nếu không chắc về một chữ trong tên thuốc, ghi [?] sau chữ đó.
- Không được tự ý "sửa" tên thuốc theo ý hiểu - phải ghi đúng những gì in trên hóa đơn.
- Phân loại rõ mỗi mục: thuốc, vật tư y tế, dịch vụ y tế, hay loại khác.

ĐỊNH DẠNG XUẤT:

=== HÓA ĐƠN ===
Tổng tiền: [số tổng cộng trên hóa đơn]

DANH SÁCH MỤC:
1. [Tên mục] | [Loại: thuốc/vật tư y tế/dịch vụ/khác] | [Mô tả] | [Số lượng] | [Đơn giá] | [Thành tiền]
2. [Tên mục] | [Loại] | [Mô tả] | [Số lượng] | [Đơn giá] | [Thành tiền]
...

Thuế VAT: [số tiền] (nếu có)
Tổng sau thuế: [số tiền] (nếu có)
=== HẾT HÓA ĐƠN ===

Chỉ xuất kết quả theo định dạng trên. Không thêm lời giải thích."""


def build_contract_chunk_prompt(page_start, page_end, num_pages):
    return f"""Bạn là chuyên gia trích xuất dữ liệu từ ảnh hợp đồng bảo hiểm. Nhiệm vụ: ĐỌC {page_end - page_start + 1} TRANG ẢNH (trang {page_start} đến trang {page_end}) và trích xuất TOÀN BỘ nội dung.

YÊU CẦU:
1. Đọc từng trang, không bỏ sót.
2. Giữ nguyên số điều khoản, định nghĩa, danh mục.
3. Không tóm tắt - ghi nguyên văn nội dung.

ĐỊNH DẠNG XUẤT:
--- Trang {page_start} ---
[nội dung nguyên văn]
--- Trang {page_start + 1} ---
[nội dung nguyên văn]
...
--- Trang {page_end} ---
[nội dung nguyên văn]

Chỉ xuất kết quả. Không thêm giải thích."""


def kimi_read_invoice(photo_paths):
    """Kimi đọc ảnh hóa đơn."""
    if not photo_paths:
        return {"success": False, "text": "", "error": "Không có ảnh hóa đơn"}
    any_photo = [p for p in photo_paths if os.path.exists(p)]
    if not any_photo:
        return {"success": False, "text": "", "error": "Không tìm thấy file ảnh"}

    prompt = build_invoice_prompt()
    content = [{"type": "text", "text": prompt}]
    for photo_path in any_photo:
        try:
            content.append({"type": "image_url", "image_url": {"url": encode_image_to_base64(photo_path)}})
        except Exception as e:
            content.append({"type": "text", "text": f"[Không thể đọc ảnh: {str(e)}]"})

    messages = [
        {"role": "system", "content": "Bạn là chuyên gia trích xuất dữ liệu từ ảnh. Đọc chính xác từng dòng. Trả lời bằng tiếng Việt. Chỉ xuất kết quả theo định dạng yêu cầu."},
        {"role": "user", "content": content}
    ]
    return call_vision_model(messages, max_tokens=8000, timeout=180)


def kimi_read_contract_chunk(chunk_images, page_start, page_end):
    """Kimi đọc 1 chunk trang hợp đồng."""
    prompt = build_contract_chunk_prompt(page_start, page_end, page_end)
    content = [{"type": "text", "text": prompt}]
    for img_b64 in chunk_images:
        content.append({"type": "image_url", "image_url": {"url": img_b64}})

    messages = [
        {"role": "system", "content": "Bạn là chuyên gia trích xuất dữ liệu từ ảnh hợp đồng bảo hiểm. Đọc chính xác từng trang. Trả lời bằng tiếng Việt. Chỉ xuất kết quả theo định dạng. KHÔNG bỏ sót trang nào."},
        {"role": "user", "content": content}
    ]
    return call_vision_model(messages, max_tokens=8000, timeout=180)


# ============================================================
# TẦNG 2: GLM PHÂN TÍCH (REDUCE)
# ============================================================

def build_invoice_analysis_prompt(invoice_text, claim_data):
    """GLM phân tích hóa đơn — liệt kê mục, phân loại, ghi rõ số tiền."""
    product_name = claim_data.get("product", {}).get("name", "Không rõ")
    return f'''Bạn là chuyên gia phân tích hóa đơn y tế. Đọc hóa đơn dưới đây và xuất danh sách cấu trúc.

Sản phẩm bảo hiểm: {product_name}
Khách hàng: {claim_data.get("customer_name", "Không rõ")}

NỘI DUNG HÓA ĐƠN:
{invoice_text}

NHIỆM VỤ: Với TỪNG mục trong hóa đơn, xác định:
1. Tên chính xác
2. Loại đối tượng: THUỐC (có hoạt chất điều trị) / VẬT TƯ Y TẾ (dụng cụ vật lý) / DỊCH VỤ Y TẾ / KHÁC
3. Số tiền
4. Ghi chú nếu tên có khả năng bị OCR sai (ghi [?])

NGUYÊN TẮC PHÂN LOẠI:
- THUỐC: có hoạt chất y tế, dạng bào chế (viên, nhỏ mắt, mỡ, tiêm...). VD: Ofloxacin 0.3% nhỏ mắt, Paracetamol 500mg
- VẬT TƯ Y TẾ: dụng cụ vật lý không có hoạt chất. VD: băng gạc, ống tiêm, catheter, găng tay
- DỊCH VỤ Y TẾ: quy trình do nhân viên y tế thực hiện. VD: khám bệnh, xét nghiệm, phẫu thuật
- Đường dùng KHÔNG xác định loại: thuốc nhỏ mắt vẫn là THUỐC, không phải vật tư

XUẤT ĐỊNH DẠNG:
=== PHÂN TÍCH HÓA ĐƠN ===
Tổng tiền: [số]
Số mục: [số]

1. Tên: [tên] | Loại: [THUỐC/VẬT TƯ/DỊCH VỤ/KHÁC] | Số tiền: [số] | Ghi chú: [nếu có]
2. Tên: [tên] | Loại: [loại] | Số tiền: [số] | Ghi chú: [nếu có]
...
=== HẾT PHÂN TÍCH ===

Chỉ xuất kết quả theo định dạng trên.'''


def build_contract_analysis_prompt(contract_chunk_text, page_start, page_end):
    """GLM phân tích 1 chunk hợp đồng — tìm loại trừ, định nghĩa, hạn mức."""
    return f'''Bạn là chuyên gia pháp lý bảo hiểm. Đọc đoạn hợp đồng dưới đây (trang {page_start}-{page_end}) và trích xuất 3 loại thông tin:

NỘI DUNG HỢP ĐỒNG (trang {page_start}-{page_end}):
{contract_chunk_text}

NHIỆM VỤ: Tìm và liệt kê:

A. ĐIỀU KHOẢN LOẠI TRỪ (không bồi thường / không chi trả):
- Trích dẫn nguyên văn điều khoản
- Ghi rõ số điều khoản + trang

B. KHÁI NIỆM / ĐỊNH NGHĨA / DANH MỤC:
- Mọi định nghĩa thuật ngữ, liệt kê danh mục, giải thích khái niệm
- Trích dẫn nguyên văn + trang
- Đặc biệt chú ý: định nghĩa nào liệt kê hạng mục cụ thể (VD: "thiết bị y tế bao gồm: ...")

C. HẠN MỨC CHI TRẢ:
- Mọi giới hạn: tối đa X VNĐ/năm, Y VNĐ/lần, Z%...
- Ghi rõ điều khoản + trang

XUẤT ĐỊNH DẠNG:
=== PHÂN TÍCH HỢP ĐỒNG (trang {page_start}-{page_end}) ===

[A] ĐIỀU KHOẢN LOẠI TRỪ:
1. [trích dẫn nguyên văn] — Điều khoản: [số], Trang: [số]
2. ...

[B] KHÁI NIỆM / ĐỊNH NGHĨA:
1. [khái niệm]: [trích dẫn nguyên văn] — Trang: [số]
2. ...

[C] HẠN MỨC CHI TRẢ:
1. [hạn mức] — Điều khoản: [số], Trang: [số]
2. ...

(không có mục nào thì ghi "không có")
=== HẾT PHÂN TÍCH ===

Chỉ xuất kết quả theo định dạng trên.'''


def glm_analyze_invoice(invoice_text, claim_data):
    """GLM phân tích hóa đơn."""
    prompt = build_invoice_analysis_prompt(invoice_text, claim_data)
    messages = [
        {"role": "system", "content": "Bạn là chuyên gia phân tích hóa đơn y tế bảo hiểm. Trả lời bằng tiếng Việt. Chỉ xuất kết quả theo định dạng."},
        {"role": "user", "content": prompt}
    ]
    return call_analysis_model(messages, max_tokens=4000, timeout=120)


def glm_analyze_contract_chunk(chunk_text, page_start, page_end):
    """GLM phân tích 1 chunk hợp đồng."""
    prompt = build_contract_analysis_prompt(chunk_text, page_start, page_end)
    messages = [
        {"role": "system", "content": "Bạn là chuyên gia pháp lý bảo hiểm PJICO. Trả lời bằng tiếng Việt. Chỉ xuất kết quả theo định dạng. Trích dẫn nguyên văn điều khoản."},
        {"role": "user", "content": prompt}
    ]
    return call_analysis_model(messages, max_tokens=4000, timeout=120)


# ============================================================
# TẦNG 3: GLM TRƯỞNG PHÒNG TỔNG HỢP (MERGE)
# ============================================================

def build_merge_prompt(claim_data, invoice_analysis, contract_analyses):
    """GLM trưởng phòng nhận tất cả báo cáo → xuất bảng khấu trừ cuối."""
    product_name = claim_data.get("product", {}).get("name", "Không rõ")
    answers = claim_data.get("answers", {})

    # Ghép các báo cáo hợp đồng
    contract_reports = "\n\n".join(contract_analyses)

    return f'''BẠN LÀ TRƯỞNG PHÒNG KIỂM TOÁN BẢO HIỂM PJICO. Bạn nhận báo cáo từ các nhân viên phân tích và phải xuất bảng khấu trừ bồi thường cuối cùng.

THÔNG TIN HỒ SƠ:
- Sản phẩm bảo hiểm: {product_name}
- Khách hàng: {claim_data.get("customer_name", "Không rõ")}
- Loại sự cố: {answers.get("incident_type", "Không rõ")}

===============================================
BÁO CÁO 1: PHÂN TÍCH HÓA ĐƠN
===============================================
{invoice_analysis}

===============================================
BÁO CÁO 2: PHÂN TÍCH HỢP ĐỒNG (từ các nhân viên)
===============================================
{contract_reports}

===============================================
NHIỆM VỤ CỦA BẠN (TRƯỞNG PHÒNG)
===============================================

Bạn có 2 báo cáo: hóa đơn đã phân loại + hợp đồng đã trích xuất điều khoản. Nhiệm vụ: đối chiếu từng mục hóa đơn với hợp đồng, tìm khoản khấu trừ, xuất bảng cuối.

QUY TRÌNH SUY LUẬN BẮT BUỘC:

Với TỪNG MỤC trong hóa đơn:

BƯỚC A - TRA ĐIỀU KHOẢN LOẠI TRỪ TRỰC TIẾP:
- Mục có trùng tên trực tiếp với điều khoản loại trừ không?
-> Có → KHẤU TRỪ. Ghi: tên + số tiền + điều khoản + trang.
-> Không → sang BƯỚC B.

BƯỚC B - TRA KHÁI NIỆM/ĐỊNH NGHĨA (KHẤU TRỪ GIÁN TIẾP):
- Mục có thuộc khái niệm/định nghĩa nào trong hợp đồng không?
- Khái niệm đó có bị loại trừ không?
-> CẢ HAI → KHẤU TRỪ gián tiếp. Ghi: tên + số tiền + khái niệm trung gian + điều khoản + trang.
-> Không → sang BƯỚC C.

BƯỚC C - TRA HẠN MỨC CHI TRẢ:
- Mục có hạn mức không? Vượt hạn mức không?
-> Vượt → phần vượt bị KHẤU TRỪ.
-> Không → không khấu trừ.

NGUYÊN TẮC PHÂN LOẠI ĐỐI TƯỢNG — QUAN TRỌNG:
- THUỐC (có hoạt chất điều trị) ≠ VẬT TƯ Y TẾ (dụng cụ vật lý) ≠ THIẾT BỊ Y TẾ ≠ DỊCH VỤ
- Đường dùng KHÔNG xác định loại: thuốc nhỏ mắt vẫn là THUỐC
- KHÔNG TỰ Ý MỞ RỘNG khái niệm: hợp đồng loại trừ "thiết bị y tế" → KHÔNG khấu trừ THUỐC theo điều khoản đó
- Chỉ khấu trừ khi hợp đồng THỰC SỰ áp dụng cho loại đối tượng đó
- KẾT NỐI thông tin giữa các trang: loại trừ ở trang 4 + định nghĩa ở trang 7 → suy luận

XUẤT BẢNG THEO MẪU:

**Tổng chi phí theo hóa đơn:** [số tiền] VNĐ

| # | Tổng tiền ban đầu | Mục bị khấu trừ | Số tiền bị khấu trừ (VNĐ) | Lí do bị khấu trừ | Nguồn điều khoản | Tiền còn lại |
|---|---|---|---|---|---|---|
| 0 | [TỔNG] | - | - | - | - | [TỔNG] |
| 1 | | [tên] | [số] | [lí do: điều khoản + giải thích] | [Điều khoản/trang] | [Tổng - KH1] |
| 2 | | [tên] | [số] | [lí do] | [Điều khoản/trang] | [Tổng-KH1-KH2] |
| **KQ** | | **TỔNG KHẤU TRỪ** | **[tổng]** | | | **[còn lại]** |

**Tổng khấu trừ:** [số] VNĐ
**Tiền bồi thường thực nhận:** [Tổng - Khấu trừ] = [số] VNĐ

QUY TẮC:
- Dòng 0 = tổng tiền. Cột 'Tiền còn lại' = TỔNG.
- Cột 'Tiền còn lại' chạy tích lũy.
- Số tiền có dấu phẩy (VD: 1.500.000). Đơn vị VNĐ.
- Không có khấu trừ → dòng 0 + KQ với '0', ghi 'Không có khoản khấu trừ, khách hàng nhận toàn bộ [số] VNĐ.'
- Không chắc → ghi '[!] Cần xác nhận' ở Lí do.
- Chỉ xuất bảng, không kèm lời giải thích bên ngoài.'''


def glm_merge_analysis(claim_data, invoice_analysis, contract_analyses):
    """GLM trưởng phòng tổng hợp tất cả báo cáo → xuất bảng cuối."""
    prompt = build_merge_prompt(claim_data, invoice_analysis, contract_analyses)
    messages = [
        {"role": "system", "content": "Bạn là trưởng phòng kiểm toán bảo hiểm PJICO. Nhận báo cáo từ nhân viên, đối chiếu hóa đơn với hợp đồng, xuất bảng khấu trừ. Trả lời bằng tiếng Việt. PHÂN BIỆT ĐÚNG LOẠI ĐỐI TƯỢNG: thuốc ≠ thiết bị y tế ≠ vật tư. KHÔNG tự ý mở rộng khái niệm. Chỉ xuất bảng kết quả."},
        {"role": "user", "content": prompt}
    ]
    return call_analysis_model(messages, max_tokens=6000, timeout=240)


# ============================================================
# PIPELINE CHÍNH: 3 TẦNG (MAP-REDUCE-MERGE)
# ============================================================

def analyze_deduction(claim_data, photo_paths, contract_path):
    """Pipeline 3 tầng song song."""

    if not has_api_key():
        return {
            "success": False,
            "response": "",
            "error": "Chưa cấu hình API key. Vui lòng thêm key vào Streamlit Cloud Secrets (key: ollama_api_key) hoặc tạo file .kimi_api_key (local)."
        }

    # ============================================================
    # TẦNG 1: KIMI ĐỌC ẢNH (MAP) — song song
    # ============================================================
    # Chuẩn bị dữ liệu
    invoice_images = []
    contract_images = []
    total_contract_pages = 0

    # Hóa đơn
    if photo_paths:
        invoice_images = [p for p in photo_paths if os.path.exists(p)]

    # Hợp đồng
    if contract_path and os.path.exists(contract_path):
        ext = os.path.splitext(contract_path)[1].lower().lstrip(".")
        if ext == "pdf":
            pdf_text = extract_pdf_text(contract_path)
            if pdf_text:
                # PDF có text → không cần Kimi, dùng trực tiếp
                contract_text_raw = pdf_text[:50000]
                contract_images = []  # không cần đọc ảnh
            else:
                contract_images, total_contract_pages = pdf_pages_to_images(contract_path, max_pages=30)
        elif ext in ("jpg", "jpeg", "png", "gif", "webp"):
            contract_images = [encode_image_to_base64(contract_path)]
            total_contract_pages = 1

    # Chia trang hợp đồng thành các chunk (mỗi chunk = CONTRACT_CHUNK_SIZE trang)
    contract_chunks = []
    if contract_images:
        chunk_size = CONTRACT_CHUNK_SIZE
        for i in range(0, len(contract_images), chunk_size):
            chunk_imgs = contract_images[i:i + chunk_size]
            page_start = i + 1
            page_end = min(i + chunk_size, len(contract_images))
            contract_chunks.append({
                "images": chunk_imgs,
                "page_start": page_start,
                "page_end": page_end
            })

    # Nếu PDF có text sẵn → 1 chunk text
    if not contract_chunks and contract_path and os.path.exists(contract_path):
        ext = os.path.splitext(contract_path)[1].lower().lstrip(".")
        if ext == "pdf":
            pdf_text = extract_pdf_text(contract_path)
            if pdf_text:
                # Chia text theo trang
                pages = re.split(r'--- Trang \d+ ---', pdf_text)
                pages = [p.strip() for p in pages if p.strip()]
                chunk_size = CONTRACT_CHUNK_SIZE
                for i in range(0, len(pages), chunk_size):
                    chunk_pages = pages[i:i + chunk_size]
   
# ============================================================
# LUU KET QUA
# ============================================================

def save_reply(claim_data, ai_response, photo_names, contract_name):
    """Luu cau tra loi AI vao thu muc tra loi."""
    os.makedirs(REPLY_DIR, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = re.sub(r'[^\w]', '_', claim_data.get("customer_name", "khach_hang"))
    product_id = claim_data.get("product", {}).get("id", "unknown")

    filename = f"reply_{safe_name}_{product_id}_{ts}.md"
    filepath = os.path.join(REPLY_DIR, filename)

    content = f"""# Phan tich khoan khau tru boi thuong

**Khach hang:** {claim_data.get('customer_name', 'Khong ro')}
**San pham:** {claim_data.get('product', {}).get('name', 'Khong ro')}
**Thoi gian:** {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}

## Anh thiet hai dinh kem:
"""
    for name in photo_names:
        content += f"- {name}\n"

    content += f"""
## Hop dong dinh kem:
- {contract_name or 'Khong co'}

## Phan tich AI:
{ai_response}
"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return filepath
