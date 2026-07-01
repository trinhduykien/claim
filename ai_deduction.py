# -*- coding: utf-8 -*-
"""
AI Deduction Analysis Module cho PJICO Claim Bot
Pipeline 3 tầng (Map-Reduce-Merge):
  TIER 1 (MAP):    Kimi K2.6 đọc ảnh hóa đơn + chunks hợp đồng song song (threading)
  TIER 2 (REDUCE): GLM-5.2 phân tích từng chunk song song (threading)
  TIER 3 (MERGE):  GLM-5.2 tổng hợp kết quả -> xuất bảng khấu trừ cuối cùng
- Đọc API key từ: Streamlit secrets -> env var -> file local
- Lưu câu trả lời vào thư mục "trả lời"
"""

import os
import json
import base64
import re
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

# ============================================================
# CONFIG
# ============================================================

API_KEY = ""

# Streamlit availability — dùng cho st.status (perceived wait). Fallback im lặng nếu không có.
_ST = None
try:
    import streamlit as _st_module
    _ST = _st_module
except Exception:
    _ST = None

# Cách 1: Streamlit Cloud Secrets
try:
    if _ST is not None:
        _secrets_key = _ST.secrets.get("ollama_api_key", None)
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

# Model cho từng pipeline
VISION_MODEL = "kimi-k2.6:cloud"     # Tier 1: đọc ảnh, trích xuất text
ANALYSIS_MODEL = "glm-5.2:cloud"     # Tier 2, 3: phân tích khấu trừ, xuất bảng

REPLY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trả lời")


def _log(msg):
    """Log timing/progress ra console — không ảnh hưởng kết quả."""
    print(f"[ai_deduction] {msg}", flush=True)


class _NoopStatus:
    """Fallback context manager khi không có Streamlit (chạy headless/CLI)."""
    def __enter__(self):
        return self
    def __exit__(self, *exc):
        return False
    def update(self, *a, **k):
        pass


def _status(label):
    """Trả về context manager hiển thị tiến trình pha (st.status) nếu có Streamlit."""
    if _ST is None:
        return _NoopStatus()
    try:
        return _ST.status(label)
    except Exception:
        return _NoopStatus()


def has_api_key():
    return bool(API_KEY)


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


def _is_real_text(text):
    """Kiểm tra text có phải nội dung thật không phải placeholder/rác."""
    if not text or len(text) < 50:
        return False
    # Phát hiện placeholder tiếng Anh (Word template)
    placeholder_markers = [
        "grab your reader",
        "quote from the document",
        "drag it",
        "place this text box",
        "emphasize a key point",
        "lorem ipsum",
        "click here",
        "type here",
        "placeholder",
    ]
    text_lower = text.lower()
    for marker in placeholder_markers:
        if marker in text_lower:
            return False
    # Nếu text quá ngắn (< 100 chars) và chỉ có 1-2 từ tiếng Việt → có thể là text rác
    # Phải có ít nhất 100 chars HOẶC chứa dấu câu tiếng Việt (>5 ký tự có dấu)
    if len(text) < 100:
        import unicodedata
        viet_chars = sum(1 for c in text if 0x00C0 <= ord(c) <= 0x024F or 0x1E00 <= ord(c) <= 0x1EFF)
        if viet_chars < 5:
            return False
    return True


def extract_pdf_text_and_image_pages(pdf_path, max_pages=100):
    """Tách PDF thành 2 nhóm: trang có text thật (dùng luôn) và trang ảnh/placeholder (gửi Kimi).
    
    Returns:
        (text_pages: dict {page_num: text}, image_page_indices: list [0-based indices])
    """
    text_pages = {}
    image_page_indices = []
    
    try:
        import fitz
        doc = fitz.open(pdf_path)
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            page_text = page.get_text().strip()
            if _is_real_text(page_text):
                text_pages[i + 1] = page_text  # 1-based page number
            else:
                image_page_indices.append(i)  # 0-based index for image conversion
        doc.close()
    except Exception:
        pass
    
    return text_pages, image_page_indices


def pdf_pages_to_images_by_indices(pdf_path, page_indices):
    """Chỉ chuyển các trang được chỉ định (0-based index) thành ảnh base64."""
    try:
        import fitz
        doc = fitz.open(pdf_path)
        images = []
        for idx in page_indices:
            if idx >= len(doc):
                break
            page = doc[idx]
            mat = fitz.Matrix(80/72, 80/72)
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("jpeg")
            img_b64 = base64.b64encode(img_bytes).decode("utf-8")
            images.append(f"data:image/jpeg;base64,{img_b64}")
        total_pages = len(doc)
        doc.close()
        return images, total_pages
    except Exception:
        pass
    return [], 0


def pdf_pages_to_images(pdf_path, max_pages=100):
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
# TIER 1: KIMI K2.6 — ĐỌC ẢNH, TRÍCH XUẤT TEXT
# ============================================================

def build_extraction_prompt_invoice():
    """Prompt cho Kimi đọc ảnh hóa đơn và trích xuất text có cấu trúc."""
    return """Bạn là chuyên gia trích xuất dữ liệu từ ảnh hóa đơn/viện phí. Nhiệm vụ: ĐỌC ẢNH HÓA ĐƠN và trích xuất TOÀN BỘ nội dung thành text có cấu trúc.

YÊU CẦU:
1. Đọc từng dòng trên hóa đơn, không bỏ sót bất kỳ dòng nào.
2. Với mỗi hạng mục, ghi rõ: tên mục, mô tả (nếu có), đơn vị tính, số lượng, đơn giá, thành tiền.
3. Ghi rõ các khoản thuế, phí khác nếu có.
4. Ghi rõ TỔNG CỘNG (tổng số tiền).
5. Giữ nguyên số liệu chính xác - không làm tròn, không ước lượng.

YÊU CẦU ĐẶC BIỆT VỀ TÊN THUỐC / HÀNG MỤC Y TẾ:
- Tên thuốc phải được đọc CHÍNH XÁC từng chữ cái. Đặc biệt chú ý các ký tự dễ nhầm: b/d, n/h, m/n, l/i, o/a.
- Nếu tên thuốc in trên hóa đơn có dấu hoặc không dấu, ghi nguyên văn như in.
- Nếu không chắc về một chữ trong tên thuốc, ghi [?] sau chữ đó để đánh dấu cần kiểm tra.
- Không được tự ý "sửa" tên thuốc theo ý hiểu - phải ghi đúng những gì in trên hóa đơn.
- Phân loại rõ mỗi mục: thuốc, vật tư y tế, dịch vụ y tế, hay loại khác.

ĐỊNH DẠNG XUẤT (bắt buộc theo mẫu):

=== HÓA ĐƠN ===
Tổng tiền: [số tổng cộng trên hóa đơn]

DANH SÁCH MỤC:
1. [Tên mục] | [Loại: thuốc/vật tư y tế/dịch vụ/khác] | [Mô tả] | [Số lượng] | [Đơn giá] | [Thành tiền]
2. [Tên mục] | [Loại: thuốc/vật tư y tế/dịch vụ/khác] | [Mô tả] | [Số lượng] | [Đơn giá] | [Thành tiền]
...
N. [Tên mục] | [Loại: thuốc/vật tư y tế/dịch vụ/khác] | [Mô tả] | [Số lượng] | [Đơn giá] | [Thành tiền]

(thuế/phí nếu có)
Thuế VAT: [số tiền]
Tổng sau thuế: [số tiền]
=== HẾT HÓA ĐƠN ===

Chỉ xuất kết quả theo định dạng trên. Không thêm lời giải thích."""


def build_extraction_prompt_contract(num_pages):
    """Prompt cho Kimi đọc ảnh hợp đồng và trích xuất text có cấu trúc."""
    return f"""Bạn là chuyên gia trích xuất dữ liệu từ ảnh hợp đồng bảo hiểm. Nhiệm vụ: ĐỌC TẤT CẢ {num_pages} TRANG ẢNH HỢP ĐỒNG và trích xuất TOÀN BỘ nội dung thành text có cấu trúc.

YÊU CẦU:
1. Đọc từng trang từ trang 1 đến trang {num_pages}, không bỏ sót trang nào.
2. Với mỗi trang, trích xuất toàn bộ text trên trang đó.
3. Giữ nguyên số điều khoản, số trang, định nghĩa, danh mục.
4. Không tóm tắt, không rút gọn - ghi nguyên văn nội dung.

ĐỊNH DẠNG XUẤT (bắt buộc theo mẫu):

=== HỢP ĐỒNG ===

--- Trang 1 ---
[nội dung nguyên văn trang 1]

--- Trang 2 ---
[nội dung nguyên văn trang 2]

...

--- Trang {num_pages} ---
[nội dung nguyên văn trang {num_pages}]

=== HẾT HỢP ĐỒNG ===

Chỉ xuất kết quả theo định dạng trên. Không thêm lời giải thích."""


def call_vision_model(messages, max_tokens=8000, timeout=300):
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

        # Fallback: reasoning có nội dung — lọc thinking tiếng Anh, giữ text tiếng Việt
        if reasoning.strip():
            lines = reasoning.split("\n")
            # Kimi thường: thinking tiếng Anh ở đầu, text tiếng Việt ở sau
            # Heuristic: tìm dòng đầu tiên có >= 3 ký tự tiếng Việt (có dấu)
            # Ký tự tiếng Việt: 0x00C0-0x024F (Latin Extended), 0x1E00-0x1EFF
            start_idx = 0
            for i, line in enumerate(lines):
                stripped = line.strip()
                if not stripped or len(stripped) < 10:
                    continue
                # Đếm ký tự tiếng Việt (có dấu)
                viet_chars = sum(1 for c in stripped if 0x00C0 <= ord(c) <= 0x024F or 0x1E00 <= ord(c) <= 0x1EFF)
                # Dòng có >= 3 ký tự tiếng Việt -> likely là nội dung trích xuất
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


def extract_invoice_text(photo_paths):
    """Tier 1a: Dùng Kimi K2.6 đọc ảnh hóa đơn -> trích xuất text."""
    prompt = build_extraction_prompt_invoice()

    content = [{"type": "text", "text": prompt}]
    for photo_path in photo_paths:
        if os.path.exists(photo_path):
            try:
                content.append({"type": "image_url", "image_url": {"url": encode_image_to_base64(photo_path)}})
            except Exception as e:
                content.append({"type": "text", "text": f"[Không thể đọc ảnh: {str(e)}]"})

    messages = [
        {"role": "system", "content": "Bạn là chuyên gia trích xuất dữ liệu từ ảnh. Đọc chính xác từng dòng. Trả lời bằng tiếng Việt. Chỉ xuất kết quả theo định dạng yêu cầu."},
        {"role": "user", "content": content}
    ]

    return call_vision_model(messages, max_tokens=8000, timeout=180)


def extract_contract_text_from_images(contract_images, num_pages, batch_size=4):
    """Tier 1b: Dùng Kimi K2.6 đọc ảnh hợp đồng -> trích xuất text.
    Chia thành batch để tránh bị cắt nội dung."""
    all_extracted_text = []
    total_images = len(contract_images)

    # Nếu ít trang, gửi 1 lần
    if total_images <= batch_size:
        prompt = build_extraction_prompt_contract(num_pages)
        content = [{"type": "text", "text": prompt}]
        for img_b64 in contract_images:
            content.append({"type": "image_url", "image_url": {"url": img_b64}})

        messages = [
            {"role": "system", "content": "Bạn là chuyên gia trích xuất dữ liệu từ ảnh hợp đồng bảo hiểm. Đọc chính xác từng trang. Trả lời bằng tiếng Việt. Chỉ xuất kết quả theo định dạng yêu cầu. KHÔNG bỏ sót trang nào."},
            {"role": "user", "content": content}
        ]

        return call_vision_model(messages, max_tokens=10000, timeout=180)

    # Nếu nhiều trang, chia thành batch
    num_batches = (total_images + batch_size - 1) // batch_size

    for batch_idx in range(num_batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, total_images)
        batch_images = contract_images[start:end]
        batch_num_pages = end - start
        page_start = start + 1
        page_end = end

        prompt = f"""Bạn là chuyên gia trích xuất dữ liệu từ ảnh hợp đồng bảo hiểm. Nhiệm vụ: ĐỌC {batch_num_pages} TRANG ẢNH (từ trang {page_start} đến trang {page_end}) và trích xuất TOÀN BỘ nội dung.

YÊU CẦU:
1. Đọc từng trang, không bỏ sót.
2. Giữ nguyên số điều khoản, định nghĩa, danh mục.
3. Không tóm tắt - ghi nguyên văn.

ĐỊNH DẠNG XUẤT:
--- Trang {page_start} ---
[nội dung]
--- Trang {page_start + 1} ---
[nội dung]
...
--- Trang {page_end} ---
[nội dung]

Chỉ xuất kết quả. Không thêm giải thích."""

        content = [{"type": "text", "text": prompt}]
        for img_b64 in batch_images:
            content.append({"type": "image_url", "image_url": {"url": img_b64}})

        messages = [
            {"role": "system", "content": "Bạn là chuyên gia trích xuất dữ liệu từ ảnh hợp đồng bảo hiểm. Đọc chính xác từng trang. Trả lời bằng tiếng Việt. Chỉ xuất kết quả theo định dạng. KHÔNG bỏ sót trang nào."},
            {"role": "user", "content": content}
        ]

        result = call_vision_model(messages, max_tokens=8000, timeout=180)

        if result["success"]:
            all_extracted_text.append(result["text"])
        else:
            # Nếu batch fail, ghi lỗi nhưng tiếp tục batch khác
            all_extracted_text.append(f"[Batch {batch_idx + 1} (trang {page_start}-{page_end}) trích xuất thất bại: {result['error']}]")

    # Ghép tất cả batch lại
    combined_text = "\n\n".join(all_extracted_text)
    return {"success": True, "text": combined_text, "error": ""}


# ============================================================
# TIER 2: GLM-5.2 — PHÂN TÍCH TỪNG CHUNK (REDUCE)
# ============================================================

def build_invoice_analysis_prompt(invoice_text):
    """Prompt đơn giản cho GLM phân tích hóa đơn — phân loại từng mục."""
    return f"""Bạn là chuyên gia phân tích hóa đơn y tế. Đọc nội dung hóa đơn dưới đây và phân loại từng hạng mục.

NỘI DUNG HÓA ĐƠN:
{invoice_text}

YÊU CẦU:
1. Đọc toàn bộ hóa đơn.
2. Với MỖI mục, xác định loại thuộc một trong: THUOC (thuốc - có hoạt chất điều trị), VAT TU Y TE (vật tư y tế - băng gạc, ống tiêm, dụng cụ vật lý), DICH VU Y TE (dịch vụ y tế - khám, xét nghiệm, phẫu thuật), KHAC (loại khác - thực phẩm chức năng, mỹ phẩm...).
3. Liệt kê từng mục với: tên mục, số tiền thành tiền, loại đã phân loại.
4. Ghi rõ tổng tiền hóa đơn.

ĐỊNH DẠNG XUẤT:
=== PHÂN TÍCH HÓA ĐƠN ===
Tổng tiền: [số tổng]

1. [Tên mục] | [Thành tiền] | [Loại: THUOC/VAT TU Y TE/DICH VU Y TE/KHAC]
2. [Tên mục] | [Thành tiền] | [Loại: THUOC/VAT TU Y TE/DICH VU Y TE/KHAC]
...

=== HẾT PHÂN TÍCH ===

Chỉ xuất kết quả theo định dạng trên. Không thêm lời giải thích."""


def build_contract_analysis_prompt(contract_chunk_text, chunk_idx):
    """Prompt đơn giản cho GLM phân tích 1 chunk hợp đồng — trích xuất A, B, C."""
    return f"""Bạn là chuyên gia phân tích hợp đồng bảo hiểm y tế. Đọc đoạn hợp đồng dưới đây và trích xuất 3 loại thông tin.

ĐOẠN HỢP ĐỒNG (Phần {chunk_idx + 1}):
{contract_chunk_text}

YÊU CẦU: Trích xuất 3 danh sách sau từ đoạn hợp đồng này:

DANH SÁCH A - ĐIỀU KHOẢN LOẠI TRỪ:
Mọi điều khoản nói về việc KHÔNG bồi thường / loại trừ / không chi trả.
Ghi rõ: nội dung điều khoản, số điều khoản, số trang.

DANH SÁCH B - KHÁI NIỆM / ĐỊNH NGHĨA / DANH MỤC:
Mọi định nghĩa thuật ngữ, liệt kê danh mục, giải thích khái niệm.
VD: 'Thiết bị y tế hỗ trợ điều trị bao gồm: ...'
Ghi rõ: khái niệm được định nghĩa, nội dung định nghĩa, số trang.

DANH SÁCH C - HẠN MỨC CHI TRẢ:
Mọi giới hạn chi trả: tối đa X VNĐ/năm, tối đa Y VNĐ/lần, tối đa Z%...
Ghi rõ: nội dung hạn mức, số điều khoản, số trang.

ĐỊNH DẠNG XUẤT:
=== PHÂN TÍCH HỢP ĐỒNG (Phần {chunk_idx + 1}) ===

DANH SÁCH A - ĐIỀU KHOẢN LOẠI TRỪ:
- [Nội dung] | Điều khoản: [số] | Trang: [số]
- [Nội dung] | Điều khoản: [số] | Trang: [số]
(nếu không có, ghi: Không phát hiện)

DANH SÁCH B - KHÁI NIỆM / ĐỊNH NGHĨA:
- [Khái niệm]: [Nội dung định nghĩa] | Trang: [số]
- [Khái niệm]: [Nội dung định nghĩa] | Trang: [số]
(nếu không có, ghi: Không phát hiện)

DANH SÁCH C - HẠN MỨC CHI TRẢ:
- [Nội dung hạn mức] | Điều khoản: [số] | Trang: [số]
- [Nội dung hạn mức] | Điều khoản: [số] | Trang: [số]
(nếu không có, ghi: Không phát hiện)

=== HẾT PHÂN TÍCH ===

Chỉ xuất kết quả theo định dạng trên. Không thêm lời giải thích."""


def call_analysis_model(messages, max_tokens=12000, timeout=600):
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

        # Ưu tiên content
        if content_text.strip():
            return {"success": True, "text": content_text.strip(), "error": ""}

        # Fallback: reasoning có nội dung -> tìm bảng cuối cùng
        if reasoning.strip():
            markers = ["**Tổng chi phí", "| # |", "| STT |", "**Tổng khấu trừ", "Không có khoản khấu trừ", "Tổng chi phí theo", "Tiền bồi thường thực nhận"]
            last_match_idx = -1
            for marker in markers:
                idx = reasoning.rfind(marker)
                if idx > last_match_idx:
                    last_match_idx = idx
            if last_match_idx >= 0:
                return {"success": True, "text": reasoning[last_match_idx:][:5000].strip(), "error": ""}

            # Fallback: tìm phần cuối có dấu hiệu trả lời (bảng)
            lines = reasoning.split("\n")
            answer_lines = []
            in_answer = False
            for line in lines:
                if any(m in line for m in ["**Tổng", "| # |", "| STT", "| 1 ", "| 1  ", "Không có khoản", "Tiền bồi thường", "Tiền còn lại"]):
                    in_answer = True
                if in_answer:
                    answer_lines.append(line)

            if answer_lines:
                return {"success": True, "text": "\n".join(answer_lines)[:5000], "error": ""}

            return {"success": True, "text": reasoning[-2000:].strip(), "error": ""}

        return {"success": False, "text": "", "error": "AI không trả về nội dung."}

    except requests.exceptions.Timeout:
        return {"success": False, "text": "", "error": f"Analysis model timeout ({timeout}s)"}
    except requests.exceptions.HTTPError as e:
        return {"success": False, "text": "", "error": f"HTTP error: {e.response.status_code} - {e.response.text[:200]}"}
    except Exception as e:
        return {"success": False, "text": "", "error": str(e)}


# ============================================================
# TIER 3: GLM-5.2 — MERGE & XUẤT BẢNG CUỐI CÙNG
# ============================================================

def build_analysis_prompt(claim_data, invoice_text, contract_text):
    """Xây prompt phân tích khấu trừ cho GLM-5.2 — chỉ nhận text, không nhận ảnh."""
    product_name = claim_data.get("product", {}).get("name", "Không rõ")
    answers = claim_data.get("answers", {})

    prompt = f'''BẠN LÀ CHUYÊN GIA KIỂM TOÁN HỢP ĐỒNG BẢO HIỂM PJICO CAO CẤP.
NHIỆM VỤ: Phân tích khấu trừ bồi thường bằng cách đối chiếu hóa đơn với hợp đồng, suy luận logic (kể cả khấu trừ gián tiếp/nhúng), rồi xuất ra MỘT BẢNG DUY NHẤT theo mẫu quy định.

Bạn làm việc theo 3 BƯỚC BẮT BUỘC, không bỏ qua bước nào, không rút gọn, không tóm tắt - đọc TOÀN VĂN tài liệu.

THÔNG TIN HỒ SƠ:
- Sản phẩm bảo hiểm: {product_name}
- Khách hàng: {claim_data.get('customer_name', 'Không rõ')}
- Loại sự cố: {answers.get('incident_type', 'Không rõ')}

===============================================
BƯỚC 1 - ĐỌC VÀ GHI NHỚ TOÀN BỘ HÓA ĐƠN
===============================================

Dưới đây là nội dung hóa đơn đã được trích xuất từ ảnh:

{invoice_text}

Đọc TOÀN BỘ hóa đơn. Với MỖI mục, ghi nhớ:
- Tên mục / hạng mục
- Mô tả chi tiết (nếu có)
- Đơn vị tính và số lượng (nếu có)
- Đơn giá (nếu có)
- Thành tiền

Tính và ghi nhớ:
- TỔNG TIỀN TRƯỚC THUẾ (nếu có)
- TIỀN THUẾ (nếu có)
- TỔNG TIỀN SAU THUẾ (= TỔNG CỘNG)

[!] Bạn phải ghi nhớ CHÍNH XÁC TỪNG CON SỐ. Không được tóm tắt, không được gộp mục nếu không chắc chắn.

===============================================
BƯỚC 2 - ĐỌC TOÀN BỘ HỢP ĐỒNG & XÂY BẢNG TRA CỨU
===============================================

Dưới đây là nội dung hợp đồng đã được trích xuất từ ảnh:

{contract_text}

Đọc TOÀN BỘ hợp đồng - mọi điều khoản, phụ lục, đính chính. Không được bỏ qua bất kỳ điều khoản nào.

[!] ĐIỀU QUAN TRỌNG NHẤT: Thông tin loại trừ và thông tin định nghĩa THƯỜNG NẰM Ở CÁC TRANG KHÁC NHAU. Bạn KHÔNG ĐƯỢC chỉ đọc từng trang riêng lẻ. Bạn PHẢI tổng hợp thông tin từ TẤT CẢ các trang, kết nối chúng lại, rồi mới suy luận.

2.1. XÂY DỰNG 3 DANH SÁCH BẮT BUỘC (làm trong đầu, không xuất ra)

DANH SÁCH A - ĐIỀU KHOẢN LOẠI TRỪ:
Mọi điều khoản nói về việc KHÔNG bồi thường / loại trừ / không chi trả.
Hạng mục bị loại trừ có thể là:
  - Tên trực tiếp: 'Không bồi thường thuốc ngoài danh mục'
  - Tên nhóm/khái niệm: 'Không bồi thường thiết bị y tế hỗ trợ điều trị'
  -> Với tên nhóm, bạn PHẢI tra trong DANH SÁCH B để xem nhóm đó bao gồm những hạng mục cụ thể nào.

DANH SÁCH B - KHÁI NIỆM / ĐỊNH NGHĨA / DANH MỤC:
Mọi trang định nghĩa thuật ngữ, liệt kê danh mục, giải thích khái niệm.
VD: 'Thiết bị y tế hỗ trợ điều trị bao gồm: ...'
-> Mỗi khái niệm trong DANH SÁCH A (loại trừ) PHẢI được tra trong DANH SÁCH B để tìm các hạng mục con cụ thể.
-> Lưu ý: định nghĩa trong hợp đồng có thể KHÔNG bao gồm thuốc. Phải đọc kỹ xem định nghĩa ghi gì.

DANH SÁCH C - HẠN MỨC CHI TRẢ:
Mọi giới hạn chi trả: tối đa X VNĐ/năm, tối đa Y VNĐ/lần, tối đa Z% giá trị...

2.2. QUY TRÌNH SUY LUẬN BẮT BUỘC - MAP HÓA ĐƠN VÀO 3 DANH SÁCH

Với TỪNG MỖI MỤC trong hóa đơn, thực hiện:

BƯỚC 2(A) - TRA DANH SÁCH A (điều khoản loại trừ):
  - Mục trong hóa đơn có trùng tên trực tiếp với bất kỳ hạng mục nào trong DANH SÁCH A không?
    -> Có -> KHẤU TRỪ. Ghi rõ: tên mục + số tiền + điều khoản + trang.
    -> Không -> chuyển sang BƯỚC 2(B).

BƯỚC 2(B) - TRA DANH SÁCH B (khái niệm/định nghĩa) - KIỂM TRA KHẤU TRỪ GIÁN TIẾP:
  - Mục trong hóa đơn có thuộc bất kỳ khái niệm/định nghĩa nào trong DANH SÁCH B không?
    -> DUYỆT TỪNG khái niệm trong DANH SÁCH B:
      - Khái niệm này có liệt kê/bao gồm mục trong hóa đơn không?
      - Khái niệm này có bị NHẮC ĐẾN trong DANH SÁCH A (tức là khái niệm đó bị loại trừ) không?
      -> NẾU CẢ HAI ĐỀU CÓ: mục trong hóa đơn thuộc khái niệm bị loại trừ -> KHẤU TRỪ (gián tiếp).
        Ghi rõ: tên mục + số tiền + khái niệm trung gian + điều khoản loại trừ + trang.
      -> Chỉ có 1/2: không đủ cơ sở, chuyển sang khái niệm tiếp theo.
  - Sau khi duyệt hết DANH SÁCH B mà vẫn không tìm thấy -> chuyển sang BƯỚC 2(C).

BƯỚC 2(C) - TRA DANH SÁCH C (hạn mức chi trả):
  - Mục trong hóa đơn có thuộc một hạng mục có hạn mức trong DANH SÁCH C không?
  - Số tiền có vượt hạn mức không?
    -> Vượt -> phần vượt bị KHẤU TRỪ.
    -> Không vượt -> không khấu trừ.

BƯỚC 2(D) - KẾT LUẬN:
  - Nếu mục bị khấu trừ qua bất kỳ bước 2(A)/2(B)/2(C) nào -> đưa vào bảng kết quả.
  - Nếu không bị khấu trừ qua bất kỳ bước nào -> KHÔNG đưa vào bảng.

2.3. NGUYÊN TẮC PHÂN LOẠI ĐỐI TƯỢNG — QUAN TRỌNG NHẤT

Khi đối chiếu mục trong hóa đơn với khái niệm trong hợp đồng, bạn PHẢI xác định ĐÚNG LOẠI của đối tượng:

  a) THUỐC (medicine/pharmaceutical drug):
     - Là chế phẩm có hoạt chất y tế được dùng qua đường uống, nhỏ mắt, nhỏ tai, bôi da, tiêm, truyền...
     - Bao gồm: thuốc nhỏ mắt, thuốc mỡ bôi ngoài da, thuốc uống, thuốc tiêm, gel bôi trơn mắt (nếu có hoạt chất điều trị)...
     - Đặc điểm: thường có tên thương mại + hàm lượng hoạt chất + dạng bào chế (vd: 'Ofloxacin 0.3% nhỏ mắt 5ml', 'Sanlein 0.3% nhỏ mắt 5ml').
     - Nếu hợp đồng nói 'không bồi thường thuốc ngoài danh mục' -> kiểm tra thuốc có trong danh mục không.
     - Nếu hợp đồng nói 'không bồi thường thiết bị y tế' -> THUỐC KHÔNG PHẢI THIẾT BỊ Y TẾ. Không được khấu trừ thuốc theo điều khoản loại trừ thiết bị y tế.

  b) VẬT TƯ Y TẾ (medical device/supplies):
     - Là dụng cụ/hàng lo dùng trong y tế KHÔNG có hoạt chất điều trị: băng gạc, ống tiêm, kim tiêm, catheter, găng tay y tế, máy đo huyết áp, nhiệt kế...
     - Đặc điểm: là vật lý, không phải chế phẩm dược phẩm.
     - Nếu hợp đồng nói 'không bồi thường thiết bị y tế' -> vật tư y tế MỚI bị khấu trừ.

  c) DỊCH VỤ Y TẾ (medical service):
     - Khám bệnh, xét nghiệm, phẫu thuật, vật lý trị liệu, chụp X-quang, siêu âm...
     - Là quy trình/dịch vụ do nhân viên y tế thực hiện.

  d) CÁC LOẠI KHÁC: thực phẩm chức năng, mỹ phẩm, hàng hóa...

NGUYÊN TẮC XÁC ĐỊNH:
- XÉT THEO BẢN CHẤT CỦA ĐỐI TƯỢNG, KHÔNG XÉT THEO ĐƯỜNG DÙNG.
  VD: Thuốc nhỏ mắt là THUỐC (có hoạt chất điều trị), KHÔNG PHẢI vật tư y tế, KHÔNG PHẢI thiết bị y tế.
  VD: Gel bôi trơn mắt (nếu có hoạt chất điều trị) là THUỐC. Nếu KHÔNG có hoạt chất điều trị (chỉ là gel bôi trơn) thì là vật tư y tế.
- KHI HỢP ĐỒNG LIỆT KÊ 'thiết bị y tế hỗ trợ điều trị', bạn PHẢI tra trong DANH SÁCH B để xem định nghĩa cụ thể: hợp đồng ghi rõ 'thiết bị y tế' gồm những gì. Nếu định nghĩa không nhắc đến thuốc -> thuốc KHÔNG bị khấu trừ theo điều khoản đó.
- KHÔNG ĐƯỢC TỰ Ý MỞ RỘNG khái niệm: nếu hợp đồng nói 'thiết bị y tế' mà hóa đơn là 'thuốc' -> KHÔNG KHẤU TRỪ theo điều khoản thiết bị y tế. Phải tìm điều khoản khác áp dụng trực tiếp cho thuốc.
- ĐƯỜNG DÙNG KHÔNG XÁC ĐỊNH LOẠI: thuốc nhỏ mắt vẫn là thuốc, thuốc mỡ bôi da vẫn là thuốc. Không được gọi thuốc là 'thiết bị y tế' chỉ vì cùng đường dùng với vật tư.

2.4. VÍ DỤ MINH HỌA (để hiểu cách suy luận, KHÔNG được dùng ví dụ này làm khuôn cố định):

  Tình huống 1 — Khấu trừ gián tiếp HỢP LỆ:
  - Hóa đơn có: 'Băng gạc y tế - 50.000 VNĐ' (vật tư y tế)
  - DANH SÁCH A: 'Không bồi thường vật tư y tế tiêu hao' (trang 4)
  - DANH SÁCH B: 'Vật tư y tế tiêu hao bao gồm: băng gạc, bông y tế, ống tiêm...' (trang 7)
  -> Bước 2(A): 'Băng gạc' không trùng trực tiếp với 'vật tư y tế tiêu hao' -> Không trùng trực tiếp.
  -> Bước 2(B): Duyệt DANH SÁCH B -> khái niệm 'vật tư y tế tiêu hao' có chứa 'băng gạc'? CÓ. Khái niệm này có bị loại trừ trong DANH SÁCH A? CÓ.
  -> KẾT LUẬN: Băng gạc bị KHẤU TRỪ gián tiếp. Đúng loại đối tượng.

  Tình huống 2 — KHÔNG khấu trừ vì sai loại đối tượng:
  - Hóa đơn có: 'Thuốc Ofloxacin 0.3% nhỏ mắt 5ml - 60.000 VNĐ' (THUỐC)
  - DANH SÁCH A: 'Không bồi thường thiết bị y tế hỗ trợ điều trị' (trang 4)
  - DANH SÁCH B: 'Thiết bị y tế hỗ trợ điều trị bao gồm: băng gạc, ống tiêm, catheter...' (trang 7) — KHÔNG nhắc đến thuốc
  -> Bước 2(A): 'Ofloxacin' không trùng trực tiếp với 'thiết bị y tế' -> Không trùng trực tiếp.
  -> Bước 2(B): Duyệt DANH SÁCH B -> 'thiết bị y tế' có chứa 'Ofloxacin'? KHÔNG. Định nghĩa không nhắc đến thuốc.
  -> Ofloxacin là THUỐC, không phải thiết bị y tế -> KHÔNG KHẤU TRỪ theo điều khoản thiết bị y tế.
  -> Tiếp tục tra các điều khoản khác (có điều khoản nào nói rõ 'không bồi thường thuốc ngoài danh mục' không?).

  [!] Đây chỉ là ví dụ về cách suy luận. Bạn PHẢI áp dụng cho TỪNG MỤC trong hóa đơn, với TỪNG KHÁI NIỆM trong hợp đồng — dựa trên NỘI DUNG THỰC TẾ của hợp đồng, không dựa trên ví dụ.

2.5. NGUYÊN TẮC SUY LUẬN

- KHÔNG BỎ SÓT: Đọc hết mọi điều khoản, tìm hết mọi khoản khấu trừ.
- TRUY CHUỖI ĐẾN TẬN CẤP LÁ: A bị khấu trừ chứa B, C -> kiểm tra B, C. B chứa B1, B2 -> tiếp tục. Đi đến tận cùng.
- THAM CHIẾU CHÉO: Điều X dẫn đến Điều Y -> phải đọc cả Y.
- KHÔNG SUY ĐOÁN: Chỉ khấu trừ khi có cơ sở rõ ràng. Nếu không chắc, đánh dấu '[!] Cần xác nhận'.
- KHÔNG TỰ Ý MỞ RỘNG KHÁI NIỆM: Khấu trừ theo đúng loại đối tượng. Thuốc ≠ thiết bị y tế ≠ vật tư y tế. Chỉ khấu trừ khi hợp đồng THỰC SỰ áp dụng cho loại đối tượng đó.
- GHI NGUỒN: Mỗi kết luận khấu trừ phải kèm số điều khoản + số trang trong hợp đồng.
- KIỂM TRA CHÉO BẮT BUỘC: MỖI MỤC trong hóa đơn PHẢI kiểm tra cả 3 danh sách A, B, C.

===============================================
BƯỚC 3 - XUẤT BẢNG KẾT QUẢ
===============================================

Xuất DUY NHẤT MỘT BẢNG theo đúng mẫu bên dưới. Không viết thêm lời dẫn, không giải thích bên ngoài bảng. Chỉ hiện bảng.

ĐỊNH DẠNG BẢNG (BẮT BUỘC - làm đúng mẫu):

**Tổng chi phí theo hóa đơn:** [số tiền] VNĐ

| # | Tổng tiền ban đầu | Mục bị khấu trừ | Số tiền bị khấu trừ (VNĐ) | Lí do bị khấu trừ | Nguồn điều khoản | Tiền còn lại |
|---|---|---|---|---|---|---|
| 0 | [TỔNG CỘNG từ hóa đơn] | - | - | - | - | [TỔNG CỘNG] |
| 1 | | [tên hạng mục] | [số tiền] | [lí do: trích dẫn điều khoản + giải thích vì sao khoản trong hóa đơn bị khấu trừ] | [Điều khoản/trang] | [Tổng - KH1] |
| 2 | | [tên hạng mục] | [số tiền] | [lí do: trích dẫn điều khoản + giải thích] | [Điều khoản/trang] | [Tổng-KH1 - KH2] |
| ... | | | | | | |
| **KQ** | | **TỔNG KHẤU TRỪ** | **[tổng cộng]** | | | **[tiền cuối cùng còn lại]** |

**Tổng khấu trừ:** [số tiền] VNĐ
**Tiền bồi thường thực nhận:** [Tổng - Khấu trừ] = [số tiền] VNĐ

QUY TẮC XUẤT BẢNG:
- Dòng 0 = tổng tiền ban đầu. Cột 'Tiền còn lại' = TỔNG CỘNG.
- Mỗi dòng khấu trừ = một hạng mục cụ thể trong hóa đơn bị khấu trừ.
- Cột 'Lí do' PHẢI ghi rõ: (a) điều khoản hợp đồng gì, (b) vì sao khoản trong hóa đơn bị khấu trừ theo điều khoản đó.
- Cột 'Nguồn điều khoản' = số điều khoản + số trang (nếu có).
- Cột 'Tiền còn lại' = chạy tích lũy: dòng 1 = Tổng - KH1; dòng 2 = (Tổng-KH1) - KH2; v.v.
- Dòng cuối (KQ) = tổng cộng khấu trừ và số tiền cuối cùng còn lại.
- Số tiền: định dạng có dấu phẩy (VD: 1.500.000.000). Đơn vị VNĐ.
- Nếu KHÔNG có khoản nào bị khấu trừ: chỉ xuất dòng 0 và dòng KQ với '0' cho tổng khấu trừ, ghi 'Không có khoản khấu trừ, khách hàng nhận toàn bộ [số tiền] VNĐ.'
- Nếu CÓ khoản không chắc chắn: vẫn đưa vào bảng nhưng ghi '[!] Cần xác nhận' ở cột Lí do.

NGUYÊN TẮC TỔNG QUÁT:
1. Đọc hết, nhớ hết - không bỏ sót bất kỳ dòng nào trong hóa đơn hay điều khoản nào trong hợp đồng.
2. Suy luận đến tận gốc - khấu trừ gián tiếp, khấu trừ nhúng, khấu trừ theo điều kiện, vượt hạn mức đều phải kiểm tra.
3. KHÔNG TỰ Ý MỞ RỘNG KHÁI NIỆM - khấu trừ đúng loại đối tượng: thuốc là thuốc, thiết bị là thiết bị, vật tư là vật tư. Chỉ khấu trừ khi hợp đồng thực sự áp dụng cho loại đối tượng đó.
4. Trích dẫn nguồn - mọi kết luận phải có điều khoản hợp đồng làm căn cứ.
5. Chính xác tuyệt đối về con số - không làm tròn, không ước lượng, không 'khoảng'.
6. Chỉ xuất bảng - kết quả cuối cùng là một bảng duy nhất, không kèm lời giải thích bên ngoài.
'''
    return prompt


# ============================================================
# PIPELINE CHÍNH: 3 TẦNG (MAP-REDUCE-MERGE)
# ============================================================

def analyze_deduction(claim_data, photo_paths, contract_path):
    """Pipeline 3 tầng: Tier 1 (Map) -> Tier 2 (Reduce) -> Tier 3 (Merge)."""

    if not has_api_key():
        return {
            "success": False,
            "response": "",
            "error": "Chưa cấu hình API key. Vui lòng thêm key vào Streamlit Cloud Secrets (key: ollama_api_key) hoặc tạo file .kimi_api_key (local)."
        }

    try:
        import threading
        t_total = time.perf_counter()

        # ============================================================
        # TIER 1 (MAP): KIMI ĐỌC ẢNH HÓA ĐƠN + CHUNKS HỢP ĐỒNG SONG SONG
        # Chunk 5 trang/call + ThreadPoolExecutor(max_workers=6) để cap concurrency.
        # Tổng text trích xuất KHÔNG đổi -> accuracy giữ nguyên.
        # ============================================================

        # Chuẩn bị chunks hợp đồng cho Kimi
        contract_chunks_images = []  # list of (images_batch, num_pages_in_batch)
        # Dùng cho trang có text (không cần Kimi)
        contract_text_pages = {}  # {page_num: text}

        if contract_path and os.path.exists(contract_path):
            ext = os.path.splitext(contract_path)[1].lower().lstrip(".")
            if ext == "pdf":
                # Tách trang có text và trang chỉ có ảnh
                text_pages, image_page_indices = extract_pdf_text_and_image_pages(contract_path, max_pages=100)
                contract_text_pages = text_pages

                if image_page_indices:
                    # Có trang ảnh scan → chuyển sang ảnh cho Kimi đọc
                    contract_images, total_pages = pdf_pages_to_images_by_indices(contract_path, image_page_indices)
                    if contract_images:
                        chunk_size = 5
                        for i in range(0, len(contract_images), chunk_size):
                            batch = contract_images[i:i + chunk_size]
                            contract_chunks_images.append((batch, len(batch)))
            elif ext in ("jpg", "jpeg", "png", "gif", "webp"):
                img_b64 = encode_image_to_base64(contract_path)
                contract_chunks_images.append(([img_b64], 1))

        n_contract_chunks = len(contract_chunks_images)
        has_invoice = bool(photo_paths)

        def _read_invoice():
            if not photo_paths:
                return {"success": False, "text": "", "error": "Không có ảnh"}
            any_photo = [p for p in photo_paths if os.path.exists(p)]
            if not any_photo:
                return {"success": False, "text": "", "error": "Không tìm thấy file ảnh"}
            return extract_invoice_text(any_photo)

        def _read_contract_chunk(images_batch, num_pages_batch):
            return extract_contract_text_from_images(images_batch, num_pages_batch, batch_size=5)

        t_tier1 = time.perf_counter()
        tier1_label = "Đang đọc ảnh hợp đồng & hóa đơn (Tier 1)..."
        if contract_text_pages and not n_contract_chunks:
            tier1_label = "Hợp đồng có sẵn text — đang đọc hóa đơn (Tier 1)..."
        elif contract_text_pages and n_contract_chunks:
            tier1_label = "Đang đọc text + ảnh hợp đồng & hóa đơn (Tier 1)..."
        elif not n_contract_chunks:
            tier1_label = "Đang đọc hóa đơn (Tier 1)..."

        with _status(tier1_label) as status:
            invoice_result = None
            contract_chunk_results = [None] * n_contract_chunks

            ex = ThreadPoolExecutor(max_workers=6)
            fut_invoice = ex.submit(_read_invoice) if has_invoice else None
            fut_contracts = {
                ex.submit(_read_contract_chunk, imgs, np): idx
                for idx, (imgs, np) in enumerate(contract_chunks_images)
            }

            # Chờ invoice (timeout 200s)
            if fut_invoice is not None:
                try:
                    invoice_result = fut_invoice.result(timeout=200)
                except Exception as e:
                    invoice_result = {"success": False, "text": "", "error": f"Tier 1 invoice timeout/error: {e}"}

            # Chờ contract chunks (timeout tổng 600s)
            try:
                for fut in as_completed(fut_contracts, timeout=600):
                    idx = fut_contracts[fut]
                    try:
                        contract_chunk_results[idx] = fut.result()
                    except Exception as e:
                        contract_chunk_results[idx] = {"success": False, "text": "", "error": f"Tier 1 chunk {idx + 1}: {e}"}
            except Exception:
                # timeout tổng -> các chunk chưa xong giữ None -> xử lý như timeout bên dưới
                pass

            # Không chờ thêm các future đang chạy (giữ timeout cap như bản cũ).
            ex.shutdown(wait=False)

            tier1_elapsed = time.perf_counter() - t_tier1
            _log(f"Tier 1 xong sau {tier1_elapsed:.1f}s "
                 f"(invoice={'có' if has_invoice else 'không'}, contract_chunks={n_contract_chunks}, "
                 f"text_pages={len(contract_text_pages)})")
            if status is not None and hasattr(status, "update"):
                try:
                    status.update(label=f"Đã đọc xong Tier 1 ({tier1_elapsed:.1f}s)")
                except Exception:
                    pass

        # Xử lý kết quả invoice
        invoice_text = "(Không có hóa đơn)"
        if invoice_result and invoice_result.get("success") and invoice_result.get("text"):
            invoice_text = invoice_result["text"]
        elif invoice_result and not invoice_result.get("success") and photo_paths:
            return {
                "success": False,
                "response": "",
                "error": f"Tier 1 (đọc hóa đơn) thất bại: {invoice_result.get('error', 'unknown')}"
            }

        # Xử lý kết quả contract — gộp text pages + image chunks
        contract_chunk_texts = []

        # 1. Trang có text sẵn → thêm trực tiếp (không cần Kimi)
        if contract_text_pages:
            for page_num in sorted(contract_text_pages.keys()):
                contract_chunk_texts.append(f"\n--- Trang {page_num} ---\n{contract_text_pages[page_num]}")

        # 2. Trang ảnh scan → kết quả từ Kimi
        if contract_chunks_images:
            for idx, res in enumerate(contract_chunk_results):
                if res and res.get("success") and res.get("text"):
                    contract_chunk_texts.append(res["text"])
                elif res and not res.get("success"):
                    contract_chunk_texts.append(f"[Chunk {idx + 1} trích xuất thất bại: {res.get('error', 'unknown')}]")
                else:
                    contract_chunk_texts.append(f"[Chunk {idx + 1} không có kết quả (timeout)]")
        elif not contract_text_pages and contract_path and os.path.exists(contract_path):
            contract_chunk_texts.append("(Hợp đồng trích xuất thất bại hoặc không thể đọc)")
        else:
            contract_chunk_texts.append("(Không có hợp đồng đính kèm)")

        # ============================================================
        # TIER 2 (BỎ): Truyền thẳng text từ Tier 1 sang Tier 3
        # (Như v0.6 gốc - GLM nhận raw text, đọc trực tiếp -> giữ accuracy)
        # ============================================================

        invoice_analysis = invoice_text
        contract_analyses = contract_chunk_texts

        # ============================================================
        # TIER 3 (MERGE): GLM PHÂN TÍCH KHẤU TRỪ -> XUẤT BẢNG CUỐI CÙNG
        # ============================================================

        contract_analyses_joined = "\n\n".join(contract_analyses)

        # Bỏ giới hạn text — gửi toàn bộ text hợp đồng cho GLM phân tích
        prompt = build_analysis_prompt(claim_data, invoice_analysis, contract_analyses_joined)

        system_msg = {
            "role": "system",
            "content": "Bạn là chuyên gia kiểm toán hợp đồng bảo hiểm PJICO cao cấp. LUÔN trả lời bằng tiếng Việt. Nhiệm vụ: ĐỌC TOÀN BỘ text hóa đơn (ghi nhớ từng dòng, từng con số) -> ĐỌC TOÀN BỘ text hợp đồng (mọi điều khoản, phụ lục, đính chính) -> XÂY DỰNG 3 DANH SÁCH TRONG ĐẦU: (A) Điều khoản loại trừ, (B) Khái niệm/định nghĩa/danh mục, (C) Hạn mức chi trả -> MAP TỪNG MỤC trong hóa đơn vào 3 danh sách theo quy trình 2(A) -> 2(B) -> 2(C). ĐẶC BIỆT: khoản trong hóa đơn có thể KHÔNG TRÙNG TÊN trực tiếp với điều khoản loại trừ, nhưng có THUỘC một khái niệm/định nghĩa bị loại trừ (khấu trừ gián tiếp). Phải KẾT NỐI thông tin giữa các trang. QUAN TRỌNG: PHẢI PHÂN BIỆT ĐÚNG LOẠI ĐỐI TƯỢNG — thuốc là thuốc (có hoạt chất điều trị), thiết bị y tế là thiết bị (dụng cụ vật lý), vật tư y tế là vật tư (băng gạc, ống tiêm...). KHÔNG ĐƯỢC tự ý mở rộng khái niệm: nếu hợp đồng loại trừ 'thiết bị y tế' thì KHÔNG được khấu trừ THUỐC theo điều khoản đó. Chỉ khấu trừ khi hợp đồng THỰC SỰ áp dụng cho loại đối tượng đó. Mọi kết luận phải có điều khoản hợp đồng làm căn cứ. CHÍNH XÁC TUYỆT ĐỐI về con số - không làm tròn, không ước lượng. Output cuối cùng là MỘT BẢNG DUY NHẤT theo mẫu, không kèm lời giải thích bên ngoài. KHÔNG trả lời 'không có khấu trừ' nếu chưa kiểm tra kỹ tất cả điều khoản hợp đồng."
        }
        user_msg = {"role": "user", "content": prompt}
        messages = [system_msg, user_msg]

        merge_result_box = {"result": None}

        def run_merge():
            merge_result_box["result"] = call_analysis_model(messages, max_tokens=16000, timeout=600)

        t_tier3 = time.perf_counter()
        with _status("Đang tổng hợp & xuất bảng khấu trừ (Tier 3)...") as status:
            t_merge = threading.Thread(target=run_merge)
            t_merge.start()
            t_merge.join(timeout=620)

            tier3_elapsed = time.perf_counter() - t_tier3
            _log(f"Tier 3 xong sau {tier3_elapsed:.1f}s")
            if status is not None and hasattr(status, "update"):
                try:
                    status.update(label=f"Đã tổng hợp xong Tier 3 ({tier3_elapsed:.1f}s)")
                except Exception:
                    pass

        analysis_result = merge_result_box["result"]
        _log(f"Tổng thời gian analyze_deduction: {time.perf_counter() - t_total:.1f}s")

        if analysis_result and analysis_result.get("success") and analysis_result.get("text"):
            return {"success": True, "response": analysis_result["text"], "error": ""}
        elif analysis_result and not analysis_result.get("success"):
            return {"success": False, "response": "", "error": f"Tier 3 (merge) thất bại: {analysis_result['error']}"}
        else:
            return {"success": False, "response": "", "error": "Tier 3 (merge) timeout hoặc không có kết quả"}

    except Exception as e:
        return {"success": False, "response": "", "error": str(e)}


# ============================================================
# LƯU KẾT QUẢ
# ============================================================

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