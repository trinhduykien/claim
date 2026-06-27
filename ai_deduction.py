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
    """Đọc text từ PDF. Trả về None nếu là ảnh scan hoặc text quá ít (PDF scan có overlay text)."""
    # Thử PyMuPDF
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
        # Chỉ coi là PDF text nếu:
        # - Tất cả hoặc phần lớn trang có text (>= 50%)
        # - Tổng text đủ dài (>= 500 ký tự - không phải vài dòng lẻ)
        # Nếu không đủ điều kiện -> coi là PDF scan -> trả về None để chuyển thành ảnh
        if pages_with_text > 0 and pages_with_text >= total_pages * 0.5 and total_text_chars >= 500:
            return text
        else:
            return None  # PDF scan hoặc text quá ít -> cần chuyển thành ảnh
    except ImportError:
        pass
    except Exception:
        pass

    # Thử pdfplumber
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

    return None  # PDF là ảnh scan


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
    """Xây prompt phân tích khấu trừ - 3 bước: đọc hóa đơn -> suy luận hợp đồng -> xuất 1 bảng."""
    product_name = claim_data.get("product", {}).get("name", "Không rõ")
    answers = claim_data.get("answers", {})

    answers_text = ""
    for qid, ans in answers.items():
        answers_text += f"- {qid}: {ans}\n"

    if num_contract_pages > 0:
        contract_info = f"""Hợp đồng bảo hiểm có {num_contract_pages} trang ảnh đính kèm.
BẠN PHẢI ĐỌC KỸ TỪNG TRANG ẢNH HỢP ĐỒNG từ trang 1 đến trang cuối cùng. Không được bỏ sót trang nào, không được đọc lướt.

Các trang hợp đồng bảo hiểm thường chứa:
- Trang bìa: thông tin hợp đồng, bên tham gia, thời hạn
- Trang giữa: phạm vi bảo hiểm, quyền lợi, hạn mức chi trả
- Trang điều khoản loại trừ: các khoản KHÔNG được bồi thường
- Trang khái niệm/định nghĩa: giải thích thuật ngữ y tế, thiết bị y tế, vật liệu, thuốc...
- Trang phụ lục: danh mục chi tiết các hạng mục được/không được chi trả
- Trang đính chính/bổ sung: sửa đổi hoặc thêm điều khoản gốc

[!] ĐIỀU KIỆN SỐNG CÒN - KẾT NỐI THÔNG TIN GIỮA CÁC TRANG:
Thông tin loại trừ và thông tin định nghĩa THƯỜNG NẰM Ở CÁC TRANG KHÁC NHAU.
- Một trang ghi điều khoản loại trừ: 'Không bồi thường chi phí thiết bị y tế hỗ trợ điều trị'
- Một trang KHÁC định nghĩa: 'Thiết bị y tế hỗ trợ điều trị bao gồm: Sanlein, thuốc nhỏ mắt, băng y tế...'
- Hóa đơn có: Sanlein
- -> Phải KẾT NỐI: Sanlein thuoc Thiết bị y tế hỗ trợ điều trị -> bị loại trừ -> KHẤU TRỪ

Bạn KHÔNG ĐƯỢC chỉ đọc từng trang riêng lẻ. Bạn PHẢI tổng hợp thông tin từ TẤT CẢ các trang rồi kết nối chúng lại với nhau.
Nếu Điều X tham chiếu Điều Y, bạn PHẢI đọc cả Điều Y để hiểu đầy đủ."""
    elif contract_text and contract_text != '(Không có hợp đồng đính kèm)':
        contract_info = f'Nội dung hợp đồng bảo hiểm:\n{contract_text}'
    else:
        contract_info = '(Không có hợp đồng đính kèm)'

    prompt = f'''BẠN LÀ CHUYÊN GIA KIỂM TOÁN HỢP ĐỒNG BẢO HIỂM PJICO CAO CẤP.
NHIỆM VỤ: Phân tích khấu trừ bồi thường bằng cách đối chiếu hóa đơn với hợp đồng, suy luận logic (kể cả khấu trừ gián tiếp/nhúng), rồi xuất ra MỘT BẢNG DUY NHẤT theo mẫu quy định.

Bạn làm việc theo 3 BƯỚC BẮT BUỘC, không bỏ qua bước nào, không rút gọn, không tóm tắt - đọc TOÀN VĂN tài liệu.

THÔNG TIN HỒ SƠ:
- Sản phẩm bảo hiểm: {product_name}
- Khách hàng: {claim_data.get('customer_name', 'Không rõ')}
- Loại sự cố: {answers.get('incident_type', 'Không rõ')}

{contract_info}

===============================================
BƯỚC 1 - ĐỌC VÀ GHI NHỚ TOÀN BỘ HÓA ĐƠN
===============================================

Đọc TOÀN BỘ ảnh hóa đơn/viện phí đính kèm từ đầu đến cuối. Không được bỏ sót bất kỳ dòng, mục, chú thích hay ghi chú nhỏ nào.

Với MỖI mục trong hóa đơn, bạn phải nắm bắt và lưu trong bộ nhớ:
- Tên mục / hạng mục (ví dụ: 'Thuốc Sanlein', 'Dịch vụ Xét nghiệm', 'Giường bệnh')
- Mô tả chi tiết (nếu có)
- Đơn vị tính & số lượng (nếu có)
- Đơn giá (nếu có)
- Thành tiền

Sau khi đọc xong, tính và ghi nhớ:
- TỔNG TIỀN TRƯỚC THUẾ (nếu có tách riêng)
- TIỀN THUẾ (VAT hoặc các loại, nếu có)
- TỔNG TIỀN SAU THUẾ (= TỔNG CỘNG)

[!] Bạn phải ghi nhớ CHÍNH XÁC TỪNG CON SỐ. Nếu hóa đơn có 200 dòng, bạn nhớ 200 dòng. Không được tóm tắt, không được 'v.v.', không được gộp mục nếu không chắc chắn.

===============================================
BƯỚC 2 - ĐỌC TOÀN BỘ HỢP ĐỒNG & XÂY BẢNG TRA CỨU
===============================================

Đọc TOÀN BỘ hợp đồng từ trang 1 đến trang cuối - mọi trang ảnh, mọi điều khoản, phụ lục, đính chính, văn bản đính kèm. Không được bỏ qua bất kỳ điều khoản nào.

[!] ĐIỀU QUAN TRỌNG NHẤT: Thông tin loại trừ và thông tin định nghĩa THƯỜNG NẮM Ở CÁC TRANG KHÁC NHAU. Bạn KHÔNG ĐƯỢC chỉ đọc từng trang riêng lẻ. Bạn PHẢI tổng hợp thông tin từ TẤT CẢ các trang, kết nối chúng lại, rồi mới suy luận.

2.1. XÂY DỰNG 3 DANH SÁCH BẮT BUỘC (làm trong đầu, không xuất ra)

Trong quá trình đọc hợp đồng, bạn phải xây dựng 3 danh sách sau:

------------------------------------------------
DANH SÁCH A - ĐIỀU KHOẢN LOẠI TRỪ
------------------------------------------------
Mọi điều khoản nói về việc KHÔNG bồi thường / loại trừ / không chi trả cho một hạng mục nào đó.
Ghi chú: hạng mục bị loại trừ có thể là:
  - Tên trực tiếp: 'Không bồi thường thuốc ngoài danh mục'
  - Tên nhóm/khái niệm: 'Không bồi thường thiết bị y tế hỗ trợ điều trị'
  -> Với tên nhóm, bạn PHẢI tra trong DANH SÁCH B để xem nhóm đó bao gồm những hạng mục cụ thể nào.

------------------------------------------------
DANH SÁCH B - KHÁI NIỆM / ĐỊNH NGHĨA / DANH MỤC
------------------------------------------------
Mọi trang định nghĩa thuật ngữ, liệt kê danh mục, giải thích khái niệm.
VD: 'Thiết bị y tế hỗ trợ điều trị bao gồm: Sanlein, thuốc nhỏ mắt, băng y tế...'
VD: 'Thuốc ngoài danh mục BHYT là các thuốc không nằm trong Danh mục thuốc BHYT ban hành kèm QĐ...'
-> Mỗi khái niệm trong DANH SÁCH A (loại trừ) PHẢI được tra trong DANH SÁCH B để tìm các hạng mục con cụ thể.
-> Nếu trong DANH SÁCH B không tìm thấy định nghĩa, hãy tìm trong DANH SÁCH A xem có điều khoản nào giải thích không. Nếu vẫn không có, đánh dấu '[!] Cần xác nhận'.

------------------------------------------------
DANH SÁCH C - HẠN MỨC CHI TRẢ
------------------------------------------------
Mọi giới hạn chi trả: tối đa X VNĐ/năm, tối đa Y VNĐ/lần, tối đa Z% giá trị...

2.2. QUY TRÌNH SUY LUẬN BẮT BUỘC - MAP HÓA ĐƠN VÀO 3 DANH SÁCH

Sau khi đã đọc hết hợp đồng và xây xong 3 danh sách, với TỪNG MỖI MỤC trong hóa đơn (từ Bước 1), thực hiện:

BƯỚC 2(A) - TRA DANH SÁCH A (điều khoản loại trừ):
  - Mục trong hóa đơn có trùng tên trực tiếp với bất kỳ hạng mục nào trong DANH SÁCH A không?
    -> Có -> KHẤU TRỪ. Ghi rõ: tên mục + số tiền + điều khoản + trang.
    -> Không -> chuyển sang BƯỚC 2(B).

BƯỚC 2(B) - TRA DANH SÁCH B (khái niệm/định nghĩa) - KIỂM TRA KHẤU TRỪ GIÁN TIẾP:
  - Mục trong hóa đơn có thuộc bất kỳ khái niệm/định nghĩa nào trong DANH SÁCH B không?
    -> DUYỆT TỪNG khái niệm trong DANH SÁCH B:
      - Khái niệm này có liệt kê/dịnh nghĩa/bao gồm mục trong hóa đơn không?
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
  - Nếu mục trong hóa đơn bị khấu trừ qua bất kỳ bước 2(A)/2(B)/2(C) nào -> đưa vào bảng kết quả.
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

- KHÔNG BỎ SÓT: Nếu hợp đồng dài 100 trang, bạn vẫn đọc hết và tìm hết mọi khoản khấu trừ.
- TRUY CHUỖI ĐẾN TẬN CẤP LÁ: Nếu A bị khấu trừ và A chứa B, C - kiểm tra B, C trong hóa đơn. Nếu B chứa B1, B2 - tiếp tục kiểm tra B1, B2. Nếu B1 được định nghĩa gồm B1a, B1b - tiếp tục. Đi đến tận cùng.
- THAM CHIẾU CHÉO: Điều X dẫn đến Điều Y -> phải đọc cả Y. Định nghĩa ở trang 5 tham chiếu phụ lục ở trang 12 -> phải đọc cả trang 12.
- KHÔNG SUY ĐOÁN: Chỉ khấu trừ khi có cơ sở rõ ràng trong hợp đồng. Nếu không chắc, đánh dấu '[!] Cần xác nhận'.
- GHI NGUỒN: Mỗi kết luận khấu trừ phải kèm số điều khoản + số trang trong hợp đồng.
- KIỂM TRA CHÉO BẮT BUỘC: Với MỖI MỤC trong hóa đơn, bạn PHẢI kiểm tra cả 3 danh sách A, B, C. Không được bỏ qua bước nào.

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
- Dòng 0 = tổng tiền ban đầu (chưa khấu trừ gì). Cột 'Tiền còn lại' = TỔNG CỘNG.
- Mỗi dòng khấu trừ = một hạng mục cụ thể trong hóa đơn bị khấu trừ.
- Cột 'Lí do' PHẢI ghi rõ: (a) điều khoản hợp đồng gì, (b) vì sao khoản trong hóa đơn bị khấu trừ theo điều khoản đó. Trích dẫn nguyên văn hoặc tóm tắt sát điều khoản.
- Cột 'Nguồn điều khoản' = số điều khoản + số trang (nếu có) trong hợp đồng.
- Cột 'Tiền còn lại' = chạy tích lũy: dòng 1 = Tổng - KH1; dòng 2 = (Tổng-KH1) - KH2; v.v.
- Dòng cuối (KQ) = tổng cộng khấu trừ và số tiền cuối cùng còn lại.
- Số tiền: định dạng có dấu phẩy (VD: 1.500.000.000). Đơn vị VNĐ.
- Nếu KHÔNG có khoản nào bị khấu trừ: chỉ xuất dòng 0 và dòng KQ với '0' cho tổng khấu trừ, và ghi 'Không có khoản khấu trừ, khách hàng nhận toàn bộ [số tiền] VNĐ.'
- Nếu CÓ khoản không chắc chắn: vẫn đưa vào bảng nhưng ghi '[!] Cần xác nhận' ở cột Lí do.

NGUYÊN TẮC TỔNG QUÁT:
1. Đọc hết, nhớ hết - không bỏ sót bất kỳ dòng nào trong hóa đơn hay điều khoản nào trong hợp đồng.
2. Suy luận đến tận gốc - khấu trừ gián tiếp, khấu trừ nhúng, khấu trừ theo điều kiện, vượt hạn mức đều phải kiểm tra.
3. Trích dẫn nguồn - mọi kết luận phải có điều khoản hợp đồng làm căn cứ.
4. Chính xác tuyệt đối về con số - không làm tròn, không ước lượng, không 'khoảng'.
5. Chỉ xuất bảng - kết quả cuối cùng là một bảng duy nhất, không kèm lời giải thích bên ngoài.
'''
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
                contract_text = pdf_text[:30000]
            else:
                # PDF scan -> chuyển thành ảnh
                contract_images, total_pages = pdf_pages_to_images(contract_path, max_pages=20)
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
        "content": "Bạn là chuyên gia kiểm toán hợp đồng bảo hiểm PJICO cao cấp. LUÔN trả lời bằng tiếng Việt. Nhiệm vụ: ĐỌC TOÀN BỘ hóa đơn (ghi nhớ từng dòng, từng con số) -> ĐỌC TOÀN BỘ hợp đồng (mọi trang, mọi điều khoản, phụ lục, đính chính) -> XÂY DỰNG 3 DANH SÁCH TRONG ĐẦU: (A) Điều khoản loại trừ, (B) Khái niệm/định nghĩa/danh mục, (C) Hạn mức chi trả -> MAP TỪNG MỤC trong hóa đơn vào 3 danh sách đó theo quy trình 2(A) -> 2(B) -> 2(C). ĐẶC BIỆT: khoản trong hóa đơn có thể KHÔNG TRÙNG TÊN trực tiếp với điều khoản loại trừ, nhưng có THUỘC một khái niệm/định nghĩa bị loại trừ (khấu trừ gián tiếp). Phải KẾT NỐI thông tin giữa các trang: loại trừ ở trang 4 nói 'thiết bị y tế' + định nghĩa ở trang 7 nói 'Sanlein thuộc thiết bị y tế' -> Sanlein bị khấu trừ. Mọi kết luận phải có điều khoản hợp đồng làm căn cứ. CHÍNH XÁC TUYỆT ĐỐI về con số - không làm tròn, không ước lượng. Output cuối cùng là MỘT BẢNG DUY NHẤT theo mẫu, không kèm lời giải thích bên ngoài. KHÔNG trả lời 'không có khấu trừ' nếu chưa kiểm tra kỹ tất cả trang hợp đồng."
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
        "max_tokens": 16000,
        "think": False
    }

    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=300
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

        # Content rỗng, reasoning có nội dung -> tìm phần BẢNG cuối cùng (output nằm cuối reasoning)
        markers = ["**Tổng chi phí", "| # |", "| STT |", "**Tổng khấu trừ", "Không có khoản khấu trừ", "Tổng chi phí theo", "Tiền bồi thường thực nhận"]
        last_match_idx = -1
        for marker in markers:
            idx = reasoning.rfind(marker)
            if idx > last_match_idx:
                last_match_idx = idx
        if last_match_idx >= 0:
            return {"success": True, "response": reasoning[last_match_idx:][:5000].strip(), "error": ""}

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
            return {"success": True, "response": "\n".join(answer_lines)[:5000], "error": ""}

        # Last resort: lấy 2000 ký tự cuối
        return {"success": True, "response": reasoning[-2000:].strip(), "error": ""}

    except requests.exceptions.Timeout:
        return {"success": False, "response": "", "error": "AI xử lý quá thời gian (timeout 300s)"}
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