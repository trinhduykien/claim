# -*- coding: utf-8 -*-
"""
AI Deduction Analysis Pipeline - 3-tier Map-Reduce-Merge
Tier 1 (MAP): Kimi reads invoice + contract images in parallel
Tier 2 (REDUCE): GLM analyzes each chunk independently in parallel
Tier 3 (MERGE): GLM manager cross-references everything
"""

import os
import sys
import json
import base64
import time
import re
import threading
import traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

def _load_api_key():
    """Load API key from streamlit secrets, env, or file."""
    # 1. Streamlit secrets
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "ollama_api_key" in st.secrets:
            return st.secrets["ollama_api_key"]
    except Exception:
        pass
    # 2. Environment variable
    env_key = os.environ.get("OLLAMA_API_KEY") or os.environ.get("API_KEY")
    if env_key:
        return env_key
    # 3. File
    key_file = Path(__file__).parent / ".kimi_api_key"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    return ""


API_KEY = _load_api_key()
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "https://ollama.com/v1")
VISION_MODEL = "kimi-k2.6:cloud"
ANALYSIS_MODEL = "glm-5.2:cloud"
REPLY_DIR = Path(__file__).parent / "reply"
CONTRACT_CHUNK_SIZE = 10

# Ensure reply directory exists
REPLY_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# UTILITY FUNCTIONS
# ---------------------------------------------------------------------------

def has_api_key():
    """Check if API key is available."""
    return bool(API_KEY)


def encode_image_to_base64(image_path):
    """Encode an image file to base64 string."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def extract_pdf_text(pdf_path):
    """Extract text from a PDF. Returns (text, has_text)."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(pdf_path)
            text = ""
            for page in reader.pages:
                text += page.extract_text() or ""
            return text, bool(text.strip())
        except ImportError:
            return "", False

    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text() or ""
    doc.close()
    return text, bool(text.strip())


def pdf_pages_to_images(pdf_path, dpi=200):
    """Convert PDF pages to images. Returns list of (image_path, page_num)."""
    try:
        import fitz
    except ImportError:
        raise RuntimeError("PyMuPDF (fitz) is required for PDF to image conversion")

    doc = fitz.open(pdf_path)
    results = []
    tmp_dir = Path(pdf_path).parent / f"_tmp_{Path(pdf_path).stem}"
    tmp_dir.mkdir(exist_ok=True)

    for i, page in enumerate(doc):
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        img_path = tmp_dir / f"page_{i+1:03d}.png"
        pix.save(str(img_path))
        results.append((str(img_path), i + 1))

    doc.close()
    return results


# ---------------------------------------------------------------------------
# VIETNAMESE TEXT EXTRACTION FROM REASONING
# ---------------------------------------------------------------------------

def _count_vietnamese_chars(text):
    """Count characters in Vietnamese Unicode ranges."""
    count = 0
    for ch in text:
        cp = ord(ch)
        if (0x00C0 <= cp <= 0x024F) or (0x1E00 <= cp <= 0x1EFF):
            count += 1
    return count


def _extract_vietnamese_text(reasoning):
    """
    Filter out English thinking tokens and keep only Vietnamese text.
    Find the first line with >= 3 Vietnamese characters as the start.
    """
    if not reasoning:
        return ""

    lines = reasoning.split("\n")
    start_idx = -1
    for i, line in enumerate(lines):
        if _count_vietnamese_chars(line) >= 3:
            start_idx = i
            break

    if start_idx == -1:
        # No Vietnamese found, return as-is stripped
        return reasoning.strip()

    # Collect from start_idx onwards, filter out pure-English lines
    result_lines = []
    for line in lines[start_idx:]:
        stripped = line.strip()
        if not stripped:
            result_lines.append("")
            continue
        # Keep lines that have some Vietnamese or are short (likely data/numbers)
        vc = _count_vietnamese_chars(stripped)
        if vc >= 1 or len(stripped) < 80:
            result_lines.append(stripped)
        else:
            # Skip long English-only lines (thinking tokens)
            pass

    return "\n".join(result_lines).strip()


# ---------------------------------------------------------------------------
# MODEL CALL FUNCTIONS
# ---------------------------------------------------------------------------

def call_vision_model(messages, max_tokens=8000, timeout=180):
    """Call Kimi vision model via OpenAI-compatible API. Returns text response."""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": VISION_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.1,
        "stream": False,
    }

    url = f"{OLLAMA_BASE_URL}/chat/completions"
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()

    choice = data["choices"][0]
    message = choice.get("message", {})

    # Check for reasoning field (thinking models)
    reasoning = message.get("reasoning") or message.get("reasoning_content") or ""
    content = message.get("content", "")

    if reasoning and not content:
        # Fallback: extract Vietnamese from reasoning
        extracted = _extract_vietnamese_text(reasoning)
        if extracted:
            # Truncate to 15KB
            if len(extracted.encode("utf-8")) > 15360:
                extracted = extracted[:15000]
            return extracted

    if content:
        if len(content.encode("utf-8")) > 15360:
            content = content[:15000]
        return content

    # Last resort
    if reasoning:
        extracted = _extract_vietnamese_text(reasoning)
        if len(extracted.encode("utf-8")) > 15360:
            extracted = extracted[:15000]
        return extracted

    return ""


def call_analysis_model(messages, max_tokens=6000, timeout=180):
    """Call GLM analysis model. Returns text response."""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": ANALYSIS_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.1,
        "stream": False,
    }

    url = f"{OLLAMA_BASE_URL}/chat/completions"
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()

    choice = data["choices"][0]
    message = choice.get("message", {})

    reasoning = message.get("reasoning") or message.get("reasoning_content") or ""
    content = message.get("content", "")

    if reasoning and not content:
        extracted = _extract_vietnamese_text(reasoning)
        if extracted:
            if len(extracted.encode("utf-8")) > 8192:
                extracted = extracted[:8000]
            return extracted

    if content:
        if len(content.encode("utf-8")) > 8192:
            content = content[:8000]
        return content

    if reasoning:
        extracted = _extract_vietnamese_text(reasoning)
        if len(extracted.encode("utf-8")) > 8192:
            extracted = extracted[:8000]
        return extracted

    return ""


# ---------------------------------------------------------------------------
# TIER 1 - MAP: KIMI READS IMAGES
# ---------------------------------------------------------------------------

def build_invoice_prompt():
    """Build prompt for Kimi to read invoice images."""
    return (
        "Bạn là chuyên gia đọc hóa đơn y tế. Hãy đọc các hình ảnh hóa đơn bên dưới "
        "và xuất kết quả theo định dạng sau:\n\n"
        "1. THÔNG TIN HÓA ĐƠN:\n"
        "   - Số hóa đơn\n"
        "   - Ngày phát hành\n"
        "   - Đơn vị bán thuốc / phương thức thanh toán\n"
        "   - Bệnh nhân / Mã thẻ BHYT (nếu có)\n\n"
        "2. CHI TIẾT HÀNG HÓA:\n"
        "   Tiến hành đọc TỪNG DÒNG hàng hóa trong hóa đơn.\n"
        "   Với mỗi dòng, xuất:\n"
        "   - STT\n"
        "   - TÊN HÀNG (đọc chính xác tên thuốc / vật tư y tế / dịch vụ)\n"
        "   - ĐƠN VỊ TÍNH\n"
        "   - SỐ LƯỢNG\n"
        "   - ĐƠN GIÁ\n"
        "   - THÀNH TIỀN\n\n"
        "3. TỔNG CỘNG: Tổng tiền toàn hóa đơn\n\n"
        "LƯU Ý QUAN TRỌNG:\n"
        "- Đọc CHÍNH XÁC tên thuốc, không được suy đoán hay viết lại.\n"
        "- Nếu không rõ tên thuốc, ghi '[KHÔNG RÕ]'.\n"
        "- Phân loại mỗi dòng vào 1 trong 4 nhóm:\n"
        "  + THUỐC: thuốc chữa bệnh (tên thuốc + hàm lượng + đóng gói)\n"
        "  + VẬT TƯ Y TẾ: băng tiêm, dung dịch, găng tay, gạc xô, tăm y tế...\n"
        "  + DỊCH VỤ: khám bệnh, xét nghiệm, tiền phòng, tiền công...\n"
        "  + KHÁC: không thuộc 3 nhóm trên\n\n"
        "Xuất kết quả dạng văn bản, rõ ràng, có cấu trúc."
    )


def build_contract_chunk_prompt(page_start, page_end):
    """Build prompt for Kimi to read contract pages."""
    return (
        f"Bạn là chuyên gia phân tích hợp đồng bảo hiểm. Hãy đọc các trang hợp đồng "
        f"từ trang {page_start} đến trang {page_end} trong hình ảnh bên dưới.\n\n"
        "Hãy xuất toàn bộ nội dung văn bản của các trang này, bao gồm:\n\n"
        "1. Tiêu đề mục, điều khoản, số điều\n"
        "2. Nội dung chi tiết của mỗi điều khoản\n"
        "3. Các bảng, danh mục, định nghĩa (nếu có)\n"
        "4. Các mục loại trừ, giới hạn trả tiền, điều kiện\n\n"
        "LƯU Ý:\n"
        "- Đọc nguyên văn, không tóm tắt hay bỏ qua.\n"
        "- Giữ nguyên số điều, số trang tham chiếu.\n"
        "- Nếu có bảng, xuất theo định dạng bảng.\n"
        "- Nếu không đọc được phần nào, ghi '[KHÔNG ĐỌC ĐƯỢC]'.\n\n"
        "Xuất kết quả dạng văn bản đầy đủ."
    )


def kimi_read_invoice(photo_paths):
    """Kimi reads invoice images and returns extracted text."""
    prompt = build_invoice_prompt()
    content_parts = [{"type": "text", "text": prompt}]

    for path in photo_paths:
        b64 = encode_image_to_base64(path)
        content_parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64}"}
        })

    messages = [{"role": "user", "content": content_parts}]
    return call_vision_model(messages, max_tokens=8000, timeout=200)


def kimi_read_contract_chunk(chunk_images, page_start, page_end):
    """Kimi reads a chunk of contract pages and returns extracted text."""
    prompt = build_contract_chunk_prompt(page_start, page_end)
    content_parts = [{"type": "text", "text": prompt}]

    for img_path, _page_num in chunk_images:
        b64 = encode_image_to_base64(img_path)
        content_parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64}"}
        })

    messages = [{"role": "user", "content": content_parts}]
    return call_vision_model(messages, max_tokens=8000, timeout=300)


# ---------------------------------------------------------------------------
# TIER 2 - REDUCE: GLM ANALYZES EACH CHUNK
# ---------------------------------------------------------------------------

def build_invoice_analysis_prompt(invoice_text, claim_data):
    """Build prompt for GLM to analyze invoice text against claim data."""
    claim_info = json.dumps(claim_data, ensure_ascii=False, indent=2) if claim_data else "Không có thông tin yêu cầu"

    return (
        "Bạn là chuyên gia thanh tra bảo hiểm y tế. Bạn nhận được nội dung hóa đơn "
        "và thông tin yêu cầu trả tiền. Hãy phân tích và phân loại từng mặt hàng.\n\n"
        "=== NỘI DUNG HÓA ĐƠN ===\n"
        f"{invoice_text}\n\n"
        "=== THÔNG TIN YÊU CẦU TRẢ TIỀN ===\n"
        f"{claim_info}\n\n"
        "=== NHIỆM VỤ ===\n"
        "1. Phân loại mỗi mặt hàng vào 1 trong 4 nhóm:\n"
        "   - THUỐC: thuốc chữa bệnh (cần tên thuốc + hàm lượng + đóng gói)\n"
        "   - VẬT TƯ Y TẾ: băng tiêm, dung dịch, găng tay, tăm y tế, gạc xô...\n"
        "   - DỊCH VỤ: khám bệnh, xét nghiệm, tiền phòng, tiền công...\n"
        "   - KHÁC: không thuộc 3 nhóm trên\n\n"
        "2. Với mỗi mặt hàng, xuất:\n"
        "   - STT\n"
        "   - TÊN HÀNG\n"
        "   - PHÂN LOẠI (THUỐC / VẬT TƯ Y TẾ / DỊCH VỤ / KHÁC)\n"
        "   - SỐ LƯỢNG\n"
        "   - ĐƠN GIÁ\n"
        "   - THÀNH TIỀN\n"
        "   - GHI CHÚ (nếu có vấn đề về tên hàng, số lượng, đơn giá)\n\n"
        "3. Kiểm tra tổng tiền hợp đồng không.\n\n"
        "LƯU Ý PHÂN LOẠI:\n"
        "- THUỐC khác THIẾT BỊ Y TẾ: máy hút đờm, máy đo huyết áp là thiết bị, không phải thuốc.\n"
        "- THIẾT BỊ Y TẾ khác VẬT TƯ Y TẾ: thiết bị có thể tái sử dụng, vật tư y tế dùng 1 lần.\n"
        "- Nếu tên hàng ghi 'thuốc' nhưng thực chất là vật tư y tế, phân loại đúng.\n\n"
        "Xuất kết quả dạng bảng, rõ ràng."
    )


def build_contract_analysis_prompt(contract_chunk_text, page_start, page_end):
    """Build prompt for GLM to analyze a contract chunk."""
    return (
        f"Bạn là chuyên gia phân tích hợp đồng bảo hiểm y tế. "
        f"Hãy phân tích nội dung hợp đồng từ trang {page_start} đến trang {page_end}.\n\n"
        f"=== NỘI DUNG HỢP ĐỒNG (TRANG {page_start}-{page_end}) ===\n"
        f"{contract_chunk_text}\n\n"
        "=== NHIỆM VỤ ===\n"
        "Hãy trích xuất 3 loại thông tin sau:\n\n"
        "A. MỤC LOẠI TRỪ (EXCLUSIONS):\n"
        "   - Các điều kiện, bệnh, tình trạng KHÔNG ĐƯỢC trả tiền\n"
        "   - Các hạn chế bảo hiểm\n"
        "   - Các điều kiện bắt buộc không được trả\n\n"
        "B. ĐỊNH NGHĨA (DEFINITIONS):\n"
        "   - Định nghĩa các thuật ngữ y tế, bảo hiểm\n"
        "   - Định nghĩa 'thuốc', 'vật tư y tế', 'dịch vụ y tế'\n"
        "   - Định nghĩa 'bệnh có sẵn', 'bệnh mãn tính', 'cấp cứu'...\n\n"
        "C. GIỚI HẠN TRẢ TIỀN (LIMITS):\n"
        "   - Mức trả tối đa cho từng loại chi phí\n"
        "   - Tỷ lệ trả (80%, 90%, 100%...)\n"
        "   - Hạn mức trả cho từng loại thuốc / dịch vụ\n"
        "   - Miễn thường (deductible)\n\n"
        "Xuất kết quả theo cấu trúc:\n"
        "A. MỤC LOẠI TRỪ:\n  ...\n"
        "B. ĐỊNH NGHĨA:\n  ...\n"
        "C. GIỚI HẠN TRẢ TIỀN:\n  ...\n\n"
        "Nếu không có thông tin nào, ghi 'Không có' cho phần đó."
    )


def glm_analyze_invoice(invoice_text, claim_data):
    """GLM analyzes invoice. Returns analysis text."""
    prompt = build_invoice_analysis_prompt(invoice_text, claim_data)
    messages = [
        {"role": "system", "content": "Bạn là chuyên gia thanh tra bảo hiểm y tế Việt Nam."},
        {"role": "user", "content": prompt},
    ]
    return call_analysis_model(messages, max_tokens=4000, timeout=120)


def glm_analyze_contract_chunk(chunk_text, page_start, page_end):
    """GLM analyzes a contract chunk. Returns analysis text."""
    prompt = build_contract_analysis_prompt(chunk_text, page_start, page_end)
    messages = [
        {"role": "system", "content": "Bạn là chuyên gia phân tích hợp đồng bảo hiểm y tế Việt Nam."},
        {"role": "user", "content": prompt},
    ]
    return call_analysis_model(messages, max_tokens=4000, timeout=120)


# ---------------------------------------------------------------------------
# TIER 3 - MERGE: GLM MANAGER CROSS-REFERENCES
# ---------------------------------------------------------------------------

def build_merge_prompt(claim_data, invoice_analysis, contract_analyses):
    """Build the final merge prompt for the GLM manager."""
    claim_info = json.dumps(claim_data, ensure_ascii=False, indent=2) if claim_data else "Không có"
    contract_text = "\n\n".join(contract_analyses) if contract_analyses else "Không có phân tích hợp đồng"

    return (
        "Bạn là trưởng phòng kiểm toán bảo hiểm PJICO. "
        "Các nhân viên đã phân tích hóa đơn và hợp đồng. "
        "Bây giờ bạn tổng hợp tất cả, đối chiếu hóa đơn với hợp đồng, "
        "tìm các khoản khấu trừ và xuất BẢNG DUY NHẤT theo mẫu quy định.\n\n"
        "=== THÔNG TIN HỒ SƠ ===\n"
        f"{claim_info}\n\n"
        "=== BÁO CÁO PHÂN TÍCH HÓA ĐƠN ===\n"
        f"{invoice_analysis}\n\n"
        "=== CÁC BÁO CÁO PHÂN TÍCH HỢP ĐỒNG ===\n"
        f"{contract_text}\n\n"
        "=== NHIỆM VỤ CỦA BẠN ===\n"
        "Bạn có 2 báo cáo: hóa đơn đã phân loại + hợp đồng đã trích xuất điều khoản.\n"
        "Nhiệm vụ: đối chiếu từng mục hóa đơn với hợp đồng, tìm khoản khấu trừ, xuất bảng cuối.\n\n"
        "QUY TRÌNH SUY LUẬN BẮT BUỘC:\n\n"
        "Với TỪNG MỤC trong hóa đơn:\n\n"
        "BƯỚC A - TRA ĐIỀU KHOẢN LOẠI TRỪ TRỰC TIẾP:\n"
        "  - Mục có trùng tên trực tiếp với điều khoản loại trừ không?\n"
        "  -> Có -> KHẤU TRỪ. Ghi: tên + số tiền + điều khoản + trang.\n"
        "  -> Không -> sang BƯỚC B.\n\n"
        "BƯỚC B - TRA KHÁI NIỆM/ĐỊNH NGHĨA (KHẤU TRỪ GIÁN TIẾP):\n"
        "  - Mục có thuộc khái niệm/định nghĩa nào trong hợp đồng không?\n"
        "  - Khái niệm đó có bị loại trừ không?\n"
        "  -> CẢ HAI -> KHẤU TRỪ gián tiếp. Ghi: tên + số tiền + khái niệm trung gian + điều khoản + trang.\n"
        "  -> Không -> sang BƯỚC C.\n\n"
        "BƯỚC C - TRA HẠN MỨC CHI TRẢ:\n"
        "  - Mục có hạn mức không? Vượt hạn mức không?\n"
        "  -> Vượt -> phần vượt bị KHẤU TRỪ.\n"
        "  -> Không -> không khấu trừ.\n\n"
        "NGUYÊN TẮC PHÂN LOẠI ĐỐI TƯỢNG - QUAN TRỌNG:\n"
        "  - THUỐC (có hoạt chất điều trị) != VẬT TƯ Y TẾ (dụng cụ vật lý) != THIẾT BỊ Y TẾ != DỊCH VỤ\n"
        "  - Đường dùng KHÔNG xác định loại: thuốc nhỏ mắt vẫn là THUỐC\n"
        "  - KHÔNG TÙY Y MỞ RỘNG khái niệm: hợp đồng loại trừ 'thiết bị y tế' -> KHÔNG khấu trừ THUỐC theo điều khoản đó\n"
        "  - Chỉ khấu trừ khi hợp đồng THỰC SỰ áp dụng cho loại đối tượng đó\n"
        "  - KẾT NỐI thông tin giữa các trang: loại trừ ở trang 4 + định nghĩa ở trang 7 -> suy luận\n\n"
        "XUẤT BẢNG THEO MẪU (BẮT BUỘC - làm đúng mẫu):\n\n"
        "**Tổng chi phí theo hóa đơn:** [số tiền] VND\n\n"
        "| # | Tổng tiền ban đầu | Mục bị khấu trừ | Số tiền bị khấu trừ (VND) | Lí do bị khấu trừ | Nguồn điều khoản | Tiền còn lại |\n"
        "|---|---|---|---|---|---|---|\n"
        "| 0 | [TỔNG] | - | - | - | - | [TỔNG] |\n"
        "| 1 | | [tên] | [số] | [lí do: điều khoản + giải thích] | [Điều khoản/trang] | [Tổng - KH1] |\n"
        "| 2 | | [tên] | [số] | [lí do] | [Điều khoản/trang] | [Tổng-KH1-KH2] |\n"
        "| **KQ** | | **TỔNG KHẤU TRỪ** | **[tổng]** | | | **[còn lại]** |\n\n"
        "**Tổng khấu trừ:** [số] VND\n"
        "**Tiền bồi thường thực nhận:** [Tổng - Khấu trừ] = [số] VND\n\n"
        "QUY TẮC XUẤT BẢNG:\n"
        "  - Dòng 0 = tổng tiền ban đầu. Cột 'Tiền còn lại' = TỔNG.\n"
        "  - Mỗi dòng khấu trừ = 1 hạng mục cụ thể trong hóa đơn bị khấu trừ.\n"
        "  - Cột 'Lí do' phải ghi rõ: (a) điều khoản hợp đồng gì, (b) trích dẫn nguyên văn điều khoản, "
        "(c) giải thích vì sao khoản trong hóa đơn bị khấu trừ theo điều khoản đó, "
        "(d) nếu là khấu trừ gián tiếp thì ghi rõ khái niệm trung gian.\n"
        "  - Lí do phải chi tiết, đầy đủ, để người đọc hiểu rõ vì sao khoản đó bị khấu trừ.\n"
        "  - Cột 'Tiền còn lại' chạy tích lũy: dòng 1 = Tổng - KH1; dòng 2 = (Tổng-KH1) - KH2.\n"
        "  - Số tiền có dấu phẩy (VD: 1.500.000). Đơn vị VND.\n"
        "  - KHÔNG có khoản nào bị khấu trừ -> xuất dòng 0 + KQ với '0', ghi 'Không có khoản khấu trừ, khách hàng nhận toàn bộ [số] VND.'\n"
        "  - Không chắc -> ghi '[!] Cần xác nhận' ở cột Lí do.\n\n"
        "NGUYÊN TẮC BẮT BUỘC:\n"
        "  1. Chỉ xuất BẢNG - không kèm lời giải thích, không kiểm nghị, không yêu cầu bổ sung hồ sơ.\n"
        "  2. Không kiểm tra nhân quả giữa sự kiện bảo hiểm và chi phí y tế - đó không phải nhiệm vụ của bạn.\n"
        "  3. Bạn chỉ làm 1 việc: đối chiếu hóa đơn với hợp đồng -> tìm khoản khấu trừ -> xuất bảng.\n"
        "  4. Không tùy ý mở rộng khái niệm: thuốc là thuốc, thiết bị là thiết bị, vật tư là vật tư.\n"
        "  5. Chính xác tuyệt đối về con số - không làm tròn, không ước lượng.\n"
        "  6. Nếu hợp đồng không có đủ điều khoản (trích xuất thất bại) -> không khấu trừ, ghi 'Không có đủ điều khoản hợp đồng để khấu trừ'.\n"
        "  7. Toàn bộ output phải bằng tiếng Việt có dấu (có diacritics).\n"
    )

def glm_merge_analysis(claim_data, invoice_analysis, contract_analyses):
    """GLM manager merges all analyses. Returns final report text."""
    prompt = build_merge_prompt(claim_data, invoice_analysis, contract_analyses)
    messages = [
        {
            "role": "system",
            "content": (
                "Bạn là quản lý cấp cao bộ phận thanh tra bảo hiểm y tế Việt Nam. "
                "Bạn tổng hợp các báo cáo và ra quyết định trả tiền cuối cùng."
            ),
        },
        {"role": "user", "content": prompt},
    ]
    return call_analysis_model(messages, max_tokens=6000, timeout=240)


# ---------------------------------------------------------------------------
# MAIN PIPELINE
# ---------------------------------------------------------------------------

def analyze_deduction(claim_data, photo_paths, contract_path):
    """
    Main 3-tier Map-Reduce-Merge pipeline.

    Args:
        claim_data: dict with claim information
        photo_paths: list of paths to invoice photo images
        contract_path: path to contract PDF or image(s)

    Returns:
        dict: {"success": bool, "response": str, "error": str}
    """
    try:
        # --- Check API key ---
        if not has_api_key():
            return {
                "success": False,
                "response": "",
                "error": "Không có API key. Vui lòng cấu hình API_KEY.",
            }

        # --- Prepare invoice images ---
        invoice_images = []
        if photo_paths:
            for p in photo_paths:
                if Path(p).exists():
                    invoice_images.append(p)

        # --- Prepare contract images and text ---
        contract_images = []  # list of (image_path, page_num)
        contract_text_direct = ""  # if PDF has text, skip Kimi
        contract_is_scanned = True

        if contract_path and Path(contract_path).exists():
            ext = Path(contract_path).suffix.lower()

            if ext == ".pdf":
                # Try extracting text first
                text, has_text = extract_pdf_text(contract_path)
                if has_text:
                    contract_text_direct = text
                    contract_is_scanned = False
                else:
                    # Scanned PDF -> convert to images
                    contract_images = pdf_pages_to_images(contract_path)
                    contract_is_scanned = True
            elif ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"):
                # Single image contract
                contract_images = [(contract_path, 1)]
                contract_is_scanned = True
            else:
                # Unknown format, try as PDF
                try:
                    text, has_text = extract_pdf_text(contract_path)
                    if has_text:
                        contract_text_direct = text
                        contract_is_scanned = False
                    else:
                        contract_images = pdf_pages_to_images(contract_path)
                        contract_is_scanned = True
                except Exception:
                    pass

        # --- Split contract images into chunks ---
        contract_chunks = []  # list of (chunk_images, page_start, page_end)
        contract_text_chunks = []  # for text-based PDF: list of (text, page_start, page_end)

        if contract_is_scanned and contract_images:
            total_pages = len(contract_images)
            for i in range(0, total_pages, CONTRACT_CHUNK_SIZE):
                chunk = contract_images[i:i + CONTRACT_CHUNK_SIZE]
                page_start = chunk[0][1]
                page_end = chunk[-1][1]
                contract_chunks.append((chunk, page_start, page_end))
        elif not contract_is_scanned and contract_text_direct:
            # Split text into chunks by approximate page count
            total_pages_est = max(1, len(contract_text_direct) // 3000)
            chunk_size = max(1, len(contract_text_direct) // max(1, total_pages_est // CONTRACT_CHUNK_SIZE + 1))
            for i in range(0, len(contract_text_direct), chunk_size * 3000):
                chunk_text = contract_text_direct[i:i + chunk_size * 3000]
                page_start = (i // 3000) + 1
                page_end = ((i + chunk_size * 3000) // 3000) + 1
                contract_text_chunks.append((chunk_text, page_start, page_end))

        # ===================================================================
        # TIER 1 - MAP: KIMI READS INVOICE + CONTRACT IN PARALLEL
        # ===================================================================

        invoice_text = ""
        contract_texts = []  # list of (text, page_start, page_end)

        threads_t1 = []
        results_t1 = {}
        errors_t1 = {}

        # --- Invoice thread ---
        if invoice_images:
            def _read_invoice():
                try:
                    results_t1["invoice"] = kimi_read_invoice(invoice_images)
                except Exception as e:
                    errors_t1["invoice"] = str(e)

            t_inv = threading.Thread(target=_read_invoice, daemon=True)
            threads_t1.append(("invoice", t_inv))
        else:
            results_t1["invoice"] = ""

        # --- Contract chunk threads ---
        if contract_is_scanned and contract_chunks:
            for idx, (chunk_imgs, ps, pe) in enumerate(contract_chunks):
                def _read_contract(_imgs=chunk_imgs, _ps=ps, _pe=pe, _idx=idx):
                    try:
                        results_t1[f"contract_{_idx}"] = (kimi_read_contract_chunk(_imgs, _ps, _pe), _ps, _pe)
                    except Exception as e:
                        errors_t1[f"contract_{_idx}"] = str(e)

                t = threading.Thread(target=_read_contract, daemon=True)
                threads_t1.append((f"contract_{idx}", t))
        elif not contract_is_scanned and contract_text_chunks:
            # Text already extracted, no Kimi needed
            for idx, (ctext, ps, pe) in enumerate(contract_text_chunks):
                results_t1[f"contract_{idx}"] = (ctext, ps, pe)

        # --- Start all threads ---
        for name, t in threads_t1:
            t.start()

        # --- Join with timeouts ---
        for name, t in threads_t1:
            if name == "invoice":
                t.join(timeout=200)
            else:
                t.join(timeout=600)

            if t.is_alive():
                errors_t1[name] = f"Timeout khi đọc {name}"

        # --- Collect Tier 1 results ---
        invoice_text = results_t1.get("invoice", "")
        if "invoice" in errors_t1 and not invoice_text:
            invoice_text = f"[LỖI ĐỌC HÓA ĐƠN: {errors_t1['invoice']}]"

        # Collect contract texts in order
        num_contract_chunks = len(contract_chunks) if contract_is_scanned else len(contract_text_chunks)
        for idx in range(num_contract_chunks):
            key = f"contract_{idx}"
            if key in results_t1:
                val = results_t1[key]
                if isinstance(val, tuple):
                    contract_texts.append(val)  # (text, page_start, page_end)
                else:
                    contract_texts.append((val, 0, 0))
            elif key in errors_t1:
                contract_texts.append((f"[LỖI ĐỌC HỢP ĐỒNG CHUNK {idx}: {errors_t1[key]}]", 0, 0))

        # ===================================================================
        # TIER 2 - REDUCE: GLM ANALYZES EACH CHUNK IN PARALLEL
        # ===================================================================

        invoice_analysis = ""
        contract_analyses = []

        threads_t2 = []
        results_t2 = {}
        errors_t2 = {}

        # --- Invoice analysis thread ---
        if invoice_text and not invoice_text.startswith("[LỖI"):
            def _analyze_invoice():
                try:
                    results_t2["invoice"] = glm_analyze_invoice(invoice_text, claim_data)
                except Exception as e:
                    errors_t2["invoice"] = str(e)

            t_ia = threading.Thread(target=_analyze_invoice, daemon=True)
            threads_t2.append(("invoice", t_ia))
        else:
            results_t2["invoice"] = "[KHÔNG CÓ HÓA ĐƠN ĐỂ PHÂN TÍCH]"

        # --- Contract analysis threads ---
        for idx, (ctext, ps, pe) in enumerate(contract_texts):
            if ctext and not ctext.startswith("[LỖI"):
                def _analyze_contract(_text=ctext, _ps=ps, _pe=pe, _idx=idx):
                    try:
                        results_t2[f"contract_{_idx}"] = glm_analyze_contract_chunk(_text, _ps, _pe)
                    except Exception as e:
                        errors_t2[f"contract_{_idx}"] = str(e)

                t = threading.Thread(target=_analyze_contract, daemon=True)
                threads_t2.append((f"contract_{idx}", t))
            else:
                results_t2[f"contract_{idx}"] = f"[KHÔNG CÓ NỘI DUNG HỢP ĐỒNG CHUNK {idx}]"

        # --- Start all threads ---
        for name, t in threads_t2:
            t.start()

        # --- Join with 180s timeout each ---
        for name, t in threads_t2:
            t.join(timeout=180)
            if t.is_alive():
                errors_t2[name] = f"Timeout khi phân tích {name}"

        # --- Collect Tier 2 results ---
        invoice_analysis = results_t2.get("invoice", "")
        if "invoice" in errors_t2 and not invoice_analysis:
            invoice_analysis = f"[LỖI PHÂN TÍCH HÓA ĐƠN: {errors_t2['invoice']}]"

        for idx in range(len(contract_texts)):
            key = f"contract_{idx}"
            if key in results_t2:
                contract_analyses.append(results_t2[key])
            elif key in errors_t2:
                contract_analyses.append(f"[LỖI PHÂN TÍCH HỢP ĐỒNG CHUNK {idx}: {errors_t2[key]}]")
            else:
                contract_analyses.append("")

        # ===================================================================
        # TIER 3 - MERGE: GLM MANAGER
        # ===================================================================

        if not invoice_analysis and not any(contract_analyses):
            return {
                "success": False,
                "response": "",
                "error": "Không có dữ liệu để tổng hợp. Thử phân tích thất bại ở tất cả các tầng.",
            }

        merge_response = glm_merge_analysis(claim_data, invoice_analysis, contract_analyses)

        return {
            "success": True,
            "response": merge_response,
            "error": "",
        }

    except Exception as e:
        tb = traceback.format_exc()
        return {
            "success": False,
            "response": "",
            "error": f"{str(e)}\n\n{tb}",
        }


# ---------------------------------------------------------------------------
# SAVE REPLY
# ---------------------------------------------------------------------------

def save_reply(claim_data, ai_response, photo_names, contract_name):
    """
    Save the AI response to REPLY_DIR as a markdown file.

    Args:
        claim_data: dict with claim info
        ai_response: str, the AI's response text
        photo_names: list of str, invoice photo file names
        contract_name: str, contract file name

    Returns:
        str: path to saved file
    """
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    claim_id = ""
    if isinstance(claim_data, dict):
        claim_id = claim_data.get("claim_id") or claim_data.get("ma_yeu_cau") or claim_data.get("id") or "unknown"
    else:
        claim_id = "unknown"

    # Clean claim_id for filename
    safe_id = re.sub(r"[^\w\-]", "_", str(claim_id))
    filename = f"reply_{safe_id}_{timestamp}.md"
    filepath = REPLY_DIR / filename

    lines = []
    lines.append(f"# Kết Quả Phân Tích Deduction - {claim_id}")
    lines.append("")
    lines.append(f"**Thời gian:** {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("## Thông Tin Yêu Cầu")
    lines.append("")
    if isinstance(claim_data, dict):
        for k, v in claim_data.items():
            lines.append(f"- **{k}:** {v}")
    else:
        lines.append(str(claim_data))
    lines.append("")
    lines.append("## File Đính Kèm")
    lines.append("")
    lines.append(f"**Hợp đồng:** {contract_name}")
    lines.append("")
    if photo_names:
        lines.append("**Hóa đơn / Ảnh:**")
        for name in photo_names:
            lines.append(f"- {name}")
    else:
        lines.append("**Hóa đơn / Ảnh:** Không có")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Kết Quả Phân Tích AI")
    lines.append("")
    lines.append(ai_response)
    lines.append("")
    lines.append("---")
    lines.append(f"*File được tạo tự động bởi AI Deduction Pipeline*")

    content = "\n".join(lines)
    filepath.write_text(content, encoding="utf-8")
    return str(filepath)


# ---------------------------------------------------------------------------
# MODULE ENTRY POINT
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Quick test
    print(f"API Key available: {has_api_key()}")
    print(f"Vision model: {VISION_MODEL}")
    print(f"Analysis model: {ANALYSIS_MODEL}")
    print(f"Reply dir: {REPLY_DIR}")
    print(f"Contract chunk size: {CONTRACT_CHUNK_SIZE}")
    print("Module ready.")