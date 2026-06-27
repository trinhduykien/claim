# -*- coding: utf-8 -*-
"""
AI Deduction Analysis Module cho PJICO Claim Bot
Pipeline 2 bước:
  Bước 1: Kimi K2.6 (vision) -> đọc ảnh hóa đơn + ảnh hợp đồng -> trích xuất text có cấu trúc
  Bước 2: GLM-5.2 (text) -> nhận text đã trích xuất -> phân tích khấu trừ -> xuất bảng
- Đọc API key từ: Streamlit secrets -> env var -> file local
- Lưu câu trả lời vào thư mục "trả lời"
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

# Model cho từng pipeline
VISION_MODEL = "kimi-k2.6:cloud"     # Bước 1: đọc ảnh, trích xuất text
ANALYSIS_MODEL = "glm-5.2:cloud"     # Bước 2: phân tích khấu trừ, xuất bảng

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


def pdf_pages_to_images(pdf_path, max_pages=20):
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
# BƯỚC 1: KIMI K2.6 — ĐỌC ẢNH, TRÍCH XUẤT TEXT
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

ĐỊNH DẠNG XUẤT (bắt buộc theo mẫu):

=== HÓA ĐƠN ===
Tổng tiền: [số tổng cộng trên hóa đơn]

DANH SÁCH MỤC:
1. [Tên mục] | [Mô tả] | [Số lượng] | [Đơn giá] | [Thành tiền]
2. [Tên mục] | [Mô tả] | [Số lượng] | [Đơn giá] | [Thành tiền]
...
N. [Tên mục] | [Mô tả] | [Số lượng] | [Đơn giá] | [Thành tiền]

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

        # Fallback: reasoning có nội dung
        if reasoning.strip():
            # Tìm phần có cấu trúc (=== HÓA ĐƠN === hoặc === HỢP ĐỒNG ===)
            markers = ["=== HÓA ĐƠN ===", "=== HỢP ĐỒNG ===", "DANH SÁCH MỤC", "--- Trang 1 ---", "Tổng tiền:"]
            for marker in markers:
                idx = reasoning.find(marker)
                if idx >= 0:
                    return {"success": True, "text": reasoning[idx:].strip()[:10000], "error": ""}
            # Last resort: lấy 3000 ký tự cuối
            return {"success": True, "text": reasoning[-3000:].strip(), "error": ""}

        return {"success": False, "text": "", "error": "AI không trả về nội dung."}

    except requests.exceptions.Timeout:
        return {"success": False, "text": "", "error": f"Vision model timeout ({timeout}s)"}
    except requests.exceptions.HTTPError as e:
        return {"success": False, "text": "", "error": f"HTTP error: {e.response.status_code} - {e.response.text[:200]}"}
    except Exception as e:
        return {"success": False, "text": "", "error": str(e)}


def extract_invoice_text(photo_paths):
    """Bước 1a: Dùng Kimi K2.6 đọc ảnh hóa đơn -> trích xuất text."""
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


def extract_contract_text_from_images(contract_images, num_pages):
    """Bước 1b: Dùng Kimi K2.6 đọc ảnh hợp đồng -> trích xuất text."""
    prompt = build_extraction_prompt_contract(num_pages)

    content = [{"type": "text", "text": prompt}]
    for img_b64 in contract_images:
        content.append({"type": "image_url", "image_url": {"url": img_b64}})

    messages = [
        {"role": "system", "content": "Bạn là chuyên gia trích xuất dữ liệu từ ảnh hợp đồng bảo hiểm. Đọc chính xác từng trang. Trả lời bằng tiếng Việt. Chỉ xuất kết quả theo định dạng yêu cầu. KHÔNG bỏ sót trang nào."},
        {"role": "user", "content": content}
    ]

    return call_vision_model(messages, max_tokens=12000, timeout=300)


# ============================================================
# BƯỚC 2: GLM-5.2 — PHÂN TÍCH KHẤU TRỪ, XUẤT BẢNG
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
VD: 'Thiết bị y tế hỗ trợ điều trị bao gồm: Sanlein, thuốc nhỏ mắt, băng y tế...'
-> Mỗi khái niệm trong DANH SÁCH A (loại trừ) PHẢI được tra trong DANH SÁCH B để tìm các hạng mục con cụ thể.

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

2.3. VÍ DỤ MINH HỌA (để hiểu cách suy luận, KHÔNG được dùng ví dụ này làm khuôn cố định):

  - Hóa đơn có: 'Thuốc Sanlein - 500.000 VNĐ'
  - DANH SÁCH A: 'Không bồi thường chi phí thiết bị y tế hỗ trợ điều trị' (trang 4)
  - DANH SÁCH B: 'Thiết bị y tế hỗ trợ điều trị bao gồm: Sanlein, thuốc nhỏ mắt...' (trang 7)
  -> Bước 2(A): 'Sanlein' không trùng trực tiếp với 'thiết bị y tế hỗ trợ điều trị' -> Không trùng trực tiếp.
  -> Bước 2(B): Duyệt DANH SÁCH B -> khái niệm 'thiết bị y tế hỗ trợ điều trị' có chứa 'Sanlein'? CÓ. Khái niệm này có bị loại trừ trong DANH SÁCH A? CÓ.
  -> KẾT LUẬN: Sanlein bị KHẤU TRỪ gián tiếp. Lí do: Sanlein thuộc 'thiết bị y tế hỗ trợ điều trị' - hạng mục này bị loại trừ theo điều khoản ở trang 4.

  [!] Đây chỉ là 1 ví dụ về cách suy luận. Hợp đồng thực tế có thể có các khái niệm và điều khoản khác. Bạn PHẢI áp dụng quy trình này cho TỪNG MỤC trong hóa đơn, với TỪNG KHÁI NIỆM trong hợp đồng - không được bỏ qua.

2.4. NGUYÊN TẮC SUY LUẬN

- KHÔNG BỎ SÓT: Đọc hết mọi điều khoản, tìm hết mọi khoản khấu trừ.
- TRUY CHUỖI ĐẾN TẬN CẤP LÁ: A bị khấu trừ chứa B, C -> kiểm tra B, C. B chứa B1, B2 -> tiếp tục. Đi đến tận cùng.
- THAM CHIẾU CHÉO: Điều X dẫn đến Điều Y -> phải đọc cả Y.
- KHÔNG SUY ĐOÁN: Chỉ khấu trừ khi có cơ sở rõ ràng. Nếu không chắc, đánh dấu '[!] Cần xác nhận'.
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
3. Trích dẫn nguồn - mọi kết luận phải có điều khoản hợp đồng làm căn cứ.
4. Chính xác tuyệt đối về con số - không làm tròn, không ước lượng, không 'khoảng'.
5. Chỉ xuất bảng - kết quả cuối cùng là một bảng duy nhất, không kèm lời giải thích bên ngoài.
'''
    return prompt


def call_analysis_model(messages, max_tokens=8000, timeout=300):
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
# PIPELINE CHÍNH: 2 BƯỚC
# ============================================================

def analyze_deduction(claim_data, photo_paths, contract_path):
    """Pipeline 2 bước: Kimi đọc ảnh -> GLM phân tích khấu trừ."""

    if not has_api_key():
        return {
            "success": False,
            "response": "",
            "error": "Chưa cấu hình API key. Vui lòng thêm key vào Streamlit Cloud Secrets (key: ollama_api_key) hoặc tạo file .kimi_api_key (local)."
        }

    # ============================================================
    # BƯỚC 1A: KIMI ĐỌC ẢNH HÓA ĐƠN
    # ============================================================
    invoice_text = "(Không có hóa đơn)"

    if photo_paths:
        any_photo = [p for p in photo_paths if os.path.exists(p)]
        if any_photo:
            invoice_result = extract_invoice_text(any_photo)
            if invoice_result["success"]:
                invoice_text = invoice_result["text"]
            else:
                return {
                    "success": False,
                    "response": "",
                    "error": f"Bước 1 (đọc hóa đơn) thất bại: {invoice_result['error']}"
                }

    # ============================================================
    # BƯỚC 1B: KIMI ĐỌC ẢNH HỢP ĐỒNG
    # ============================================================
    contract_text = "(Không có hợp đồng đính kèm)"
    contract_images = []

    if contract_path and os.path.exists(contract_path):
        ext = os.path.splitext(contract_path)[1].lower().lstrip(".")
        if ext == "pdf":
            # Thử đọc text trước
            pdf_text = extract_pdf_text(contract_path)
            if pdf_text:
                contract_text = pdf_text[:50000]
            else:
                # PDF scan -> chuyển thành ảnh
                contract_images, total_pages = pdf_pages_to_images(contract_path, max_pages=20)
                if contract_images:
                    # Dùng Kimi đọc ảnh hợp đồng
                    contract_result = extract_contract_text_from_images(contract_images, len(contract_images))
                    if contract_result["success"]:
                        contract_text = contract_result["text"]
                    else:
                        # Nếu Kimi đọc fail, vẫn gửi thông tin cho GLM
                        contract_text = f"(Hợp đồng PDF gồm {total_pages} trang ảnh, trích xuất thất bại: {contract_result['error']})"
        elif ext in ("jpg", "jpeg", "png", "gif", "webp"):
            contract_images.append(encode_image_to_base64(contract_path))
            contract_result = extract_contract_text_from_images(contract_images, 1)
            if contract_result["success"]:
                contract_text = contract_result["text"]
            else:
                contract_text = f"(Hợp đồng dạng 1 ảnh, trích xuất thất bại: {contract_result['error']})"

    # ============================================================
    # BƯỚC 2: GLM-5.2 PHÂN TÍCH KHẤU TRỪ
    # ============================================================
    prompt = build_analysis_prompt(claim_data, invoice_text, contract_text)

    system_msg = {
        "role": "system",
        "content": "Bạn là chuyên gia kiểm toán hợp đồng bảo hiểm PJICO cao cấp. LUÔN trả lời bằng tiếng Việt. Nhiệm vụ: ĐỌC TOÀN BỘ text hóa đơn (ghi nhớ từng dòng, từng con số) -> ĐỌC TOÀN BỘ text hợp đồng (mọi điều khoản, phụ lục, đính chính) -> XÂY DỰNG 3 DANH SÁCH TRONG ĐẦU: (A) Điều khoản loại trừ, (B) Khái niệm/định nghĩa/danh mục, (C) Hạn mức chi trả -> MAP TỪNG MỤC trong hóa đơn vào 3 danh sách theo quy trình 2(A) -> 2(B) -> 2(C). ĐẶC BIỆT: khoản trong hóa đơn có thể KHÔNG TRÙNG TÊN trực tiếp với điều khoản loại trừ, nhưng có THUỘC một khái niệm/định nghĩa bị loại trừ (khấu trừ gián tiếp). Phải KẾT NỐI thông tin giữa các trang: loại trừ ở trang 4 nói 'thiết bị y tế' + định nghĩa ở trang 7 nói 'Sanlein thuộc thiết bị y tế' -> Sanlein bị khấu trừ. Mọi kết luận phải có điều khoản hợp đồng làm căn cứ. CHÍNH XÁC TUYỆT ĐỐI về con số - không làm tròn, không ước lượng. Output cuối cùng là MỘT BẢNG DUY NHẤT theo mẫu, không kèm lời giải thích bên ngoài. KHÔNG trả lời 'không có khấu trừ' nếu chưa kiểm tra kỹ tất cả điều khoản hợp đồng."
    }
    user_msg = {"role": "user", "content": prompt}
    messages = [system_msg, user_msg]

    analysis_result = call_analysis_model(messages, max_tokens=8000, timeout=300)

    if analysis_result["success"]:
        return {"success": True, "response": analysis_result["text"], "error": ""}
    else:
        return {"success": False, "response": "", "error": f"Bước 2 (phân tích) thất bại: {analysis_result['error']}"}


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