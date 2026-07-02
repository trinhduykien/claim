# -*- coding: utf-8 -*-
"""
AI Deduction Analysis Module cho Claim Bot
Pipeline 3 táº§ng (Map-Reduce-Merge):
  TIER 1 (MAP):    Kimi K2.6 Ä‘á»c áº£nh hÃ³a Ä‘Æ¡n + chunks há»£p Ä‘á»“ng song song (threading)
  TIER 2 (REDUCE): GLM-5.2 phÃ¢n tÃ­ch tá»«ng chunk song song (threading)
  TIER 3 (MERGE):  GLM-5.2 tá»•ng há»£p káº¿t quáº£ -> xuáº¥t báº£ng kháº¥u trá»« cuá»‘i cÃ¹ng
- Äá»c API key tá»«: Streamlit secrets -> env var -> file local
- LÆ°u cÃ¢u tráº£ lá»i vÃ o thÆ° má»¥c "tráº£ lá»i"
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

# Streamlit availability â€” dÃ¹ng cho st.status (perceived wait). Fallback im láº·ng náº¿u khÃ´ng cÃ³.
_ST = None
try:
    import streamlit as _st_module
    _ST = _st_module
except Exception:
    _ST = None

# CÃ¡ch 1: Streamlit Cloud Secrets
try:
    if _ST is not None:
        _secrets_key = _ST.secrets.get("ollama_api_key", None)
        if _secrets_key:
            API_KEY = _secrets_key.strip()
except Exception:
    pass

# CÃ¡ch 2: Environment variable
if not API_KEY:
    API_KEY = os.environ.get("OLLAMA_API_KEY", "")

# CÃ¡ch 3: File local
if not API_KEY:
    _key_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".kimi_api_key")
    if os.path.exists(_key_file):
        with open(_key_file, "r", encoding="utf-8") as f:
            API_KEY = f.read().strip()

OLLAMA_BASE_URL = "https://ollama.com/v1"

# Model cho tá»«ng pipeline
VISION_MODEL = "kimi-k2.6:cloud"     # Tier 1: Ä‘á»c áº£nh, trÃ­ch xuáº¥t text
ANALYSIS_MODEL = "glm-5.2:cloud"     # Tier 2, 3: phÃ¢n tÃ­ch kháº¥u trá»«, xuáº¥t báº£ng

REPLY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tráº£ lá»i")


def _log(msg):
    """Log timing/progress ra console â€” khÃ´ng áº£nh hÆ°á»Ÿng káº¿t quáº£."""
    print(f"[ai_deduction] {msg}", flush=True)


class _NoopStatus:
    """Fallback context manager khi khÃ´ng cÃ³ Streamlit (cháº¡y headless/CLI)."""
    def __enter__(self):
        return self
    def __exit__(self, *exc):
        return False
    def update(self, *a, **k):
        pass


def _status(label):
    """Tráº£ vá» context manager hiá»ƒn thá»‹ tiáº¿n trÃ¬nh pha (st.status) náº¿u cÃ³ Streamlit."""
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
    """Äá»c text tá»« PDF. Tráº£ vá» None náº¿u lÃ  áº£nh scan hoáº·c text quÃ¡ Ã­t."""
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


def extract_pdf_text_and_image_pages(pdf_path, max_pages=100):
    """TÃ¡ch PDF thÃ nh 2 nhÃ³m: trang cÃ³ text (dÃ¹ng luÃ´n) vÃ  trang cáº§n Kimi Ä‘á»c áº£nh.
    
    Trang cÃ³ text (dÃ¹ Ã­t/placeholder) â†’ giá»¯ text VáºªN gá»­i áº£nh cho Kimi â†’ gá»™p cáº£ hai.
    Trang hoÃ n toÃ n rá»—ng â†’ chá»‰ gá»­i áº£nh cho Kimi.
    
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
            if page_text:
                # CÃ³ text â†’ giá»¯ text láº¡i
                text_pages[i + 1] = page_text  # 1-based page number
            # LuÃ´n gá»­i áº£nh cho Kimi Ä‘á»ƒ Ä‘á»c ná»™i dung áº£nh (ká»ƒ cáº£ trang cÃ³ text)
            image_page_indices.append(i)  # 0-based index for image conversion
        doc.close()
    except Exception:
        pass
    
    return text_pages, image_page_indices


def pdf_pages_to_images_by_indices(pdf_path, page_indices):
    """Chá»‰ chuyá»ƒn cÃ¡c trang Ä‘Æ°á»£c chá»‰ Ä‘á»‹nh (0-based index) thÃ nh áº£nh base64."""
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
    """Chuyá»ƒn tá»‘i Ä‘a max_pages trang PDF thÃ nh áº£nh base64."""
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
# TIER 1: KIMI K2.6 â€” Äá»ŒC áº¢NH, TRÃCH XUáº¤T TEXT
# ============================================================

def build_extraction_prompt_invoice():
    """Prompt cho Kimi Ä‘á»c áº£nh hÃ³a Ä‘Æ¡n vÃ  trÃ­ch xuáº¥t text cÃ³ cáº¥u trÃºc."""
    return """Báº¡n lÃ  chuyÃªn gia trÃ­ch xuáº¥t dá»¯ liá»‡u tá»« áº£nh hÃ³a Ä‘Æ¡n/viá»‡n phÃ­. Nhiá»‡m vá»¥: Äá»ŒC áº¢NH HÃ“A ÄÆ N vÃ  trÃ­ch xuáº¥t TOÃ€N Bá»˜ ná»™i dung thÃ nh text cÃ³ cáº¥u trÃºc.

YÃŠU Cáº¦U:
1. Äá»c tá»«ng dÃ²ng trÃªn hÃ³a Ä‘Æ¡n, khÃ´ng bá» sÃ³t báº¥t ká»³ dÃ²ng nÃ o.
2. Vá»›i má»—i háº¡ng má»¥c, ghi rÃµ: tÃªn má»¥c, mÃ´ táº£ (náº¿u cÃ³), Ä‘Æ¡n vá»‹ tÃ­nh, sá»‘ lÆ°á»£ng, Ä‘Æ¡n giÃ¡, thÃ nh tiá»n.
3. Ghi rÃµ cÃ¡c khoáº£n thuáº¿, phÃ­ khÃ¡c náº¿u cÃ³.
4. Ghi rÃµ Tá»”NG Cá»˜NG (tá»•ng sá»‘ tiá»n).
5. Giá»¯ nguyÃªn sá»‘ liá»‡u chÃ­nh xÃ¡c - khÃ´ng lÃ m trÃ²n, khÃ´ng Æ°á»›c lÆ°á»£ng.

YÃŠU Cáº¦U Äáº¶C BIá»†T Vá»€ TÃŠN THUá»C / HÃ€NG Má»¤C Y Táº¾:
- TÃªn thuá»‘c pháº£i Ä‘Æ°á»£c Ä‘á»c CHÃNH XÃC tá»«ng chá»¯ cÃ¡i. Äáº·c biá»‡t chÃº Ã½ cÃ¡c kÃ½ tá»± dá»… nháº§m: b/d, n/h, m/n, l/i, o/a.
- Náº¿u tÃªn thuá»‘c in trÃªn hÃ³a Ä‘Æ¡n cÃ³ dáº¥u hoáº·c khÃ´ng dáº¥u, ghi nguyÃªn vÄƒn nhÆ° in.
- Náº¿u khÃ´ng cháº¯c vá» má»™t chá»¯ trong tÃªn thuá»‘c, ghi [?] sau chá»¯ Ä‘Ã³ Ä‘á»ƒ Ä‘Ã¡nh dáº¥u cáº§n kiá»ƒm tra.
- KhÃ´ng Ä‘Æ°á»£c tá»± Ã½ "sá»­a" tÃªn thuá»‘c theo Ã½ hiá»ƒu - pháº£i ghi Ä‘Ãºng nhá»¯ng gÃ¬ in trÃªn hÃ³a Ä‘Æ¡n.
- PhÃ¢n loáº¡i rÃµ má»—i má»¥c: thuá»‘c, váº­t tÆ° y táº¿, dá»‹ch vá»¥ y táº¿, hay loáº¡i khÃ¡c.

Äá»ŠNH Dáº NG XUáº¤T (báº¯t buá»™c theo máº«u):

=== HÃ“A ÄÆ N ===
Tá»•ng tiá»n: [sá»‘ tá»•ng cá»™ng trÃªn hÃ³a Ä‘Æ¡n]

DANH SÃCH Má»¤C:
1. [TÃªn má»¥c] | [Loáº¡i: thuá»‘c/váº­t tÆ° y táº¿/dá»‹ch vá»¥/khÃ¡c] | [MÃ´ táº£] | [Sá»‘ lÆ°á»£ng] | [ÄÆ¡n giÃ¡] | [ThÃ nh tiá»n]
2. [TÃªn má»¥c] | [Loáº¡i: thuá»‘c/váº­t tÆ° y táº¿/dá»‹ch vá»¥/khÃ¡c] | [MÃ´ táº£] | [Sá»‘ lÆ°á»£ng] | [ÄÆ¡n giÃ¡] | [ThÃ nh tiá»n]
...
N. [TÃªn má»¥c] | [Loáº¡i: thuá»‘c/váº­t tÆ° y táº¿/dá»‹ch vá»¥/khÃ¡c] | [MÃ´ táº£] | [Sá»‘ lÆ°á»£ng] | [ÄÆ¡n giÃ¡] | [ThÃ nh tiá»n]

(thuáº¿/phÃ­ náº¿u cÃ³)
Thuáº¿ VAT: [sá»‘ tiá»n]
Tá»•ng sau thuáº¿: [sá»‘ tiá»n]
=== Háº¾T HÃ“A ÄÆ N ===

Chá»‰ xuáº¥t káº¿t quáº£ theo Ä‘á»‹nh dáº¡ng trÃªn. KhÃ´ng thÃªm lá»i giáº£i thÃ­ch."""


def build_extraction_prompt_contract(num_pages):
    """Prompt cho Kimi Ä‘á»c áº£nh há»£p Ä‘á»“ng vÃ  trÃ­ch xuáº¥t text cÃ³ cáº¥u trÃºc."""
    return f"""Báº¡n lÃ  chuyÃªn gia trÃ­ch xuáº¥t dá»¯ liá»‡u tá»« áº£nh há»£p Ä‘á»“ng báº£o hiá»ƒm. Nhiá»‡m vá»¥: Äá»ŒC Táº¤T Cáº¢ {num_pages} TRANG áº¢NH Há»¢P Äá»’NG vÃ  trÃ­ch xuáº¥t TOÃ€N Bá»˜ ná»™i dung thÃ nh text cÃ³ cáº¥u trÃºc.

YÃŠU Cáº¦U:
1. Äá»c tá»«ng trang tá»« trang 1 Ä‘áº¿n trang {num_pages}, khÃ´ng bá» sÃ³t trang nÃ o.
2. Vá»›i má»—i trang, trÃ­ch xuáº¥t toÃ n bá»™ text trÃªn trang Ä‘Ã³.
3. Giá»¯ nguyÃªn sá»‘ Ä‘iá»u khoáº£n, sá»‘ trang, Ä‘á»‹nh nghÄ©a, danh má»¥c.
4. KhÃ´ng tÃ³m táº¯t, khÃ´ng rÃºt gá»n - ghi nguyÃªn vÄƒn ná»™i dung.

Äá»ŠNH Dáº NG XUáº¤T (báº¯t buá»™c theo máº«u):

=== Há»¢P Äá»’NG ===

--- Trang 1 ---
[ná»™i dung nguyÃªn vÄƒn trang 1]

--- Trang 2 ---
[ná»™i dung nguyÃªn vÄƒn trang 2]

...

--- Trang {num_pages} ---
[ná»™i dung nguyÃªn vÄƒn trang {num_pages}]

=== Háº¾T Há»¢P Äá»’NG ===

Chá»‰ xuáº¥t káº¿t quáº£ theo Ä‘á»‹nh dáº¡ng trÃªn. KhÃ´ng thÃªm lá»i giáº£i thÃ­ch."""


def call_vision_model(messages, max_tokens=8000, timeout=300):
    """Gá»i vision model (Kimi K2.6) qua Ollama Cloud API."""
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

        # Æ¯u tiÃªn content
        if content_text.strip():
            return {"success": True, "text": content_text.strip(), "error": ""}

        # Fallback: reasoning cÃ³ ná»™i dung â€” lá»c thinking tiáº¿ng Anh, giá»¯ text tiáº¿ng Viá»‡t
        if reasoning.strip():
            lines = reasoning.split("\n")
            # Kimi thÆ°á»ng: thinking tiáº¿ng Anh á»Ÿ Ä‘áº§u, text tiáº¿ng Viá»‡t á»Ÿ sau
            # Heuristic: tÃ¬m dÃ²ng Ä‘áº§u tiÃªn cÃ³ >= 3 kÃ½ tá»± tiáº¿ng Viá»‡t (cÃ³ dáº¥u)
            # KÃ½ tá»± tiáº¿ng Viá»‡t: 0x00C0-0x024F (Latin Extended), 0x1E00-0x1EFF
            start_idx = 0
            for i, line in enumerate(lines):
                stripped = line.strip()
                if not stripped or len(stripped) < 10:
                    continue
                # Äáº¿m kÃ½ tá»± tiáº¿ng Viá»‡t (cÃ³ dáº¥u)
                viet_chars = sum(1 for c in stripped if 0x00C0 <= ord(c) <= 0x024F or 0x1E00 <= ord(c) <= 0x1EFF)
                # DÃ²ng cÃ³ >= 3 kÃ½ tá»± tiáº¿ng Viá»‡t -> likely lÃ  ná»™i dung trÃ­ch xuáº¥t
                if viet_chars >= 3:
                    start_idx = i
                    break
            result_text = "\n".join(lines[start_idx:]).strip()
            if not result_text or len(result_text) < 50:
                result_text = reasoning.strip()
            if len(result_text) > 15000:
                result_text = result_text[:15000]
            return {"success": True, "text": result_text, "error": ""}

        return {"success": False, "text": "", "error": "AI khÃ´ng tráº£ vá» ná»™i dung."}

    except requests.exceptions.Timeout:
        return {"success": False, "text": "", "error": f"Vision model timeout ({timeout}s)"}
    except requests.exceptions.HTTPError as e:
        return {"success": False, "text": "", "error": f"HTTP error: {e.response.status_code} - {e.response.text[:200]}"}
    except Exception as e:
        return {"success": False, "text": "", "error": str(e)}


def extract_invoice_text(photo_paths):
    """Tier 1a: DÃ¹ng Kimi K2.6 Ä‘á»c áº£nh hÃ³a Ä‘Æ¡n -> trÃ­ch xuáº¥t text."""
    prompt = build_extraction_prompt_invoice()

    content = [{"type": "text", "text": prompt}]
    for photo_path in photo_paths:
        if os.path.exists(photo_path):
            try:
                content.append({"type": "image_url", "image_url": {"url": encode_image_to_base64(photo_path)}})
            except Exception as e:
                content.append({"type": "text", "text": f"[KhÃ´ng thá»ƒ Ä‘á»c áº£nh: {str(e)}]"})

    messages = [
        {"role": "system", "content": "Báº¡n lÃ  chuyÃªn gia trÃ­ch xuáº¥t dá»¯ liá»‡u tá»« áº£nh. Äá»c chÃ­nh xÃ¡c tá»«ng dÃ²ng. Tráº£ lá»i báº±ng tiáº¿ng Viá»‡t. Chá»‰ xuáº¥t káº¿t quáº£ theo Ä‘á»‹nh dáº¡ng yÃªu cáº§u."},
        {"role": "user", "content": content}
    ]

    return call_vision_model(messages, max_tokens=8000, timeout=180)


def extract_contract_text_from_images(contract_images, num_pages, batch_size=4):
    """Tier 1b: DÃ¹ng Kimi K2.6 Ä‘á»c áº£nh há»£p Ä‘á»“ng -> trÃ­ch xuáº¥t text.
    Chia thÃ nh batch Ä‘á»ƒ trÃ¡nh bá»‹ cáº¯t ná»™i dung."""
    all_extracted_text = []
    total_images = len(contract_images)

    # Náº¿u Ã­t trang, gá»­i 1 láº§n
    if total_images <= batch_size:
        prompt = build_extraction_prompt_contract(num_pages)
        content = [{"type": "text", "text": prompt}]
        for img_b64 in contract_images:
            content.append({"type": "image_url", "image_url": {"url": img_b64}})

        messages = [
            {"role": "system", "content": "Báº¡n lÃ  chuyÃªn gia trÃ­ch xuáº¥t dá»¯ liá»‡u tá»« áº£nh há»£p Ä‘á»“ng báº£o hiá»ƒm. Äá»c chÃ­nh xÃ¡c tá»«ng trang. Tráº£ lá»i báº±ng tiáº¿ng Viá»‡t. Chá»‰ xuáº¥t káº¿t quáº£ theo Ä‘á»‹nh dáº¡ng yÃªu cáº§u. KHÃ”NG bá» sÃ³t trang nÃ o."},
            {"role": "user", "content": content}
        ]

        return call_vision_model(messages, max_tokens=10000, timeout=180)

    # Náº¿u nhiá»u trang, chia thÃ nh batch
    num_batches = (total_images + batch_size - 1) // batch_size

    for batch_idx in range(num_batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, total_images)
        batch_images = contract_images[start:end]
        batch_num_pages = end - start
        page_start = start + 1
        page_end = end

        prompt = f"""Báº¡n lÃ  chuyÃªn gia trÃ­ch xuáº¥t dá»¯ liá»‡u tá»« áº£nh há»£p Ä‘á»“ng báº£o hiá»ƒm. Nhiá»‡m vá»¥: Äá»ŒC {batch_num_pages} TRANG áº¢NH (tá»« trang {page_start} Ä‘áº¿n trang {page_end}) vÃ  trÃ­ch xuáº¥t TOÃ€N Bá»˜ ná»™i dung.

YÃŠU Cáº¦U:
1. Äá»c tá»«ng trang, khÃ´ng bá» sÃ³t.
2. Giá»¯ nguyÃªn sá»‘ Ä‘iá»u khoáº£n, Ä‘á»‹nh nghÄ©a, danh má»¥c.
3. KhÃ´ng tÃ³m táº¯t - ghi nguyÃªn vÄƒn.

Äá»ŠNH Dáº NG XUáº¤T:
--- Trang {page_start} ---
[ná»™i dung]
--- Trang {page_start + 1} ---
[ná»™i dung]
...
--- Trang {page_end} ---
[ná»™i dung]

Chá»‰ xuáº¥t káº¿t quáº£. KhÃ´ng thÃªm giáº£i thÃ­ch."""

        content = [{"type": "text", "text": prompt}]
        for img_b64 in batch_images:
            content.append({"type": "image_url", "image_url": {"url": img_b64}})

        messages = [
            {"role": "system", "content": "Báº¡n lÃ  chuyÃªn gia trÃ­ch xuáº¥t dá»¯ liá»‡u tá»« áº£nh há»£p Ä‘á»“ng báº£o hiá»ƒm. Äá»c chÃ­nh xÃ¡c tá»«ng trang. Tráº£ lá»i báº±ng tiáº¿ng Viá»‡t. Chá»‰ xuáº¥t káº¿t quáº£ theo Ä‘á»‹nh dáº¡ng. KHÃ”NG bá» sÃ³t trang nÃ o."},
            {"role": "user", "content": content}
        ]

        result = call_vision_model(messages, max_tokens=8000, timeout=180)

        if result["success"]:
            all_extracted_text.append(result["text"])
        else:
            # Náº¿u batch fail, ghi lá»—i nhÆ°ng tiáº¿p tá»¥c batch khÃ¡c
            all_extracted_text.append(f"[Batch {batch_idx + 1} (trang {page_start}-{page_end}) trÃ­ch xuáº¥t tháº¥t báº¡i: {result['error']}]")

    # GhÃ©p táº¥t cáº£ batch láº¡i
    combined_text = "\n\n".join(all_extracted_text)
    return {"success": True, "text": combined_text, "error": ""}


# ============================================================
# TIER 2: GLM-5.2 â€” PHÃ‚N TÃCH Tá»ªNG CHUNK (REDUCE)
# ============================================================

def build_invoice_analysis_prompt(invoice_text):
    """Prompt Ä‘Æ¡n giáº£n cho GLM phÃ¢n tÃ­ch hÃ³a Ä‘Æ¡n â€” phÃ¢n loáº¡i tá»«ng má»¥c."""
    return f"""Báº¡n lÃ  chuyÃªn gia phÃ¢n tÃ­ch hÃ³a Ä‘Æ¡n y táº¿. Äá»c ná»™i dung hÃ³a Ä‘Æ¡n dÆ°á»›i Ä‘Ã¢y vÃ  phÃ¢n loáº¡i tá»«ng háº¡ng má»¥c.

Ná»˜I DUNG HÃ“A ÄÆ N:
{invoice_text}

YÃŠU Cáº¦U:
1. Äá»c toÃ n bá»™ hÃ³a Ä‘Æ¡n.
2. Vá»›i Má»–I má»¥c, xÃ¡c Ä‘á»‹nh loáº¡i thuá»™c má»™t trong: THUOC (thuá»‘c - cÃ³ hoáº¡t cháº¥t Ä‘iá»u trá»‹), VAT TU Y TE (váº­t tÆ° y táº¿ - bÄƒng gáº¡c, á»‘ng tiÃªm, dá»¥ng cá»¥ váº­t lÃ½), DICH VU Y TE (dá»‹ch vá»¥ y táº¿ - khÃ¡m, xÃ©t nghiá»‡m, pháº«u thuáº­t), KHAC (loáº¡i khÃ¡c - thá»±c pháº©m chá»©c nÄƒng, má»¹ pháº©m...).
3. Liá»‡t kÃª tá»«ng má»¥c vá»›i: tÃªn má»¥c, sá»‘ tiá»n thÃ nh tiá»n, loáº¡i Ä‘Ã£ phÃ¢n loáº¡i.
4. Ghi rÃµ tá»•ng tiá»n hÃ³a Ä‘Æ¡n.

Äá»ŠNH Dáº NG XUáº¤T:
=== PHÃ‚N TÃCH HÃ“A ÄÆ N ===
Tá»•ng tiá»n: [sá»‘ tá»•ng]

1. [TÃªn má»¥c] | [ThÃ nh tiá»n] | [Loáº¡i: THUOC/VAT TU Y TE/DICH VU Y TE/KHAC]
2. [TÃªn má»¥c] | [ThÃ nh tiá»n] | [Loáº¡i: THUOC/VAT TU Y TE/DICH VU Y TE/KHAC]
...

=== Háº¾T PHÃ‚N TÃCH ===

Chá»‰ xuáº¥t káº¿t quáº£ theo Ä‘á»‹nh dáº¡ng trÃªn. KhÃ´ng thÃªm lá»i giáº£i thÃ­ch."""


def build_contract_analysis_prompt(contract_chunk_text, chunk_idx):
    """Prompt Ä‘Æ¡n giáº£n cho GLM phÃ¢n tÃ­ch 1 chunk há»£p Ä‘á»“ng â€” trÃ­ch xuáº¥t A, B, C."""
    return f"""Báº¡n lÃ  chuyÃªn gia phÃ¢n tÃ­ch há»£p Ä‘á»“ng báº£o hiá»ƒm y táº¿. Äá»c Ä‘oáº¡n há»£p Ä‘á»“ng dÆ°á»›i Ä‘Ã¢y vÃ  trÃ­ch xuáº¥t 3 loáº¡i thÃ´ng tin.

ÄOáº N Há»¢P Äá»’NG (Pháº§n {chunk_idx + 1}):
{contract_chunk_text}

YÃŠU Cáº¦U: TrÃ­ch xuáº¥t 3 danh sÃ¡ch sau tá»« Ä‘oáº¡n há»£p Ä‘á»“ng nÃ y:

DANH SÃCH A - ÄIá»€U KHOáº¢N LOáº I TRá»ª:
Má»i Ä‘iá»u khoáº£n nÃ³i vá» viá»‡c KHÃ”NG bá»“i thÆ°á»ng / loáº¡i trá»« / khÃ´ng chi tráº£.
Ghi rÃµ: ná»™i dung Ä‘iá»u khoáº£n, sá»‘ Ä‘iá»u khoáº£n, sá»‘ trang.

DANH SÃCH B - KHÃI NIá»†M / Äá»ŠNH NGHÄ¨A / DANH Má»¤C:
Má»i Ä‘á»‹nh nghÄ©a thuáº­t ngá»¯, liá»‡t kÃª danh má»¥c, giáº£i thÃ­ch khÃ¡i niá»‡m.
VD: 'Thiáº¿t bá»‹ y táº¿ há»— trá»£ Ä‘iá»u trá»‹ bao gá»“m: ...'
Ghi rÃµ: khÃ¡i niá»‡m Ä‘Æ°á»£c Ä‘á»‹nh nghÄ©a, ná»™i dung Ä‘á»‹nh nghÄ©a, sá»‘ trang.

DANH SÃCH C - Háº N Má»¨C CHI TRáº¢:
Má»i giá»›i háº¡n chi tráº£: tá»‘i Ä‘a X VNÄ/nÄƒm, tá»‘i Ä‘a Y VNÄ/láº§n, tá»‘i Ä‘a Z%...
Ghi rÃµ: ná»™i dung háº¡n má»©c, sá»‘ Ä‘iá»u khoáº£n, sá»‘ trang.

Äá»ŠNH Dáº NG XUáº¤T:
=== PHÃ‚N TÃCH Há»¢P Äá»’NG (Pháº§n {chunk_idx + 1}) ===

DANH SÃCH A - ÄIá»€U KHOáº¢N LOáº I TRá»ª:
- [Ná»™i dung] | Äiá»u khoáº£n: [sá»‘] | Trang: [sá»‘]
- [Ná»™i dung] | Äiá»u khoáº£n: [sá»‘] | Trang: [sá»‘]
(náº¿u khÃ´ng cÃ³, ghi: KhÃ´ng phÃ¡t hiá»‡n)

DANH SÃCH B - KHÃI NIá»†M / Äá»ŠNH NGHÄ¨A:
- [KhÃ¡i niá»‡m]: [Ná»™i dung Ä‘á»‹nh nghÄ©a] | Trang: [sá»‘]
- [KhÃ¡i niá»‡m]: [Ná»™i dung Ä‘á»‹nh nghÄ©a] | Trang: [sá»‘]
(náº¿u khÃ´ng cÃ³, ghi: KhÃ´ng phÃ¡t hiá»‡n)

DANH SÃCH C - Háº N Má»¨C CHI TRáº¢:
- [Ná»™i dung háº¡n má»©c] | Äiá»u khoáº£n: [sá»‘] | Trang: [sá»‘]
- [Ná»™i dung háº¡n má»©c] | Äiá»u khoáº£n: [sá»‘] | Trang: [sá»‘]
(náº¿u khÃ´ng cÃ³, ghi: KhÃ´ng phÃ¡t hiá»‡n)

=== Háº¾T PHÃ‚N TÃCH ===

Chá»‰ xuáº¥t káº¿t quáº£ theo Ä‘á»‹nh dáº¡ng trÃªn. KhÃ´ng thÃªm lá»i giáº£i thÃ­ch."""


def call_analysis_model(messages, max_tokens=12000, timeout=600):
    """Gá»i analysis model (GLM-5.2) qua Ollama Cloud API."""
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

        # Æ¯u tiÃªn content
        if content_text.strip():
            return {"success": True, "text": content_text.strip(), "error": ""}

        # Fallback: reasoning cÃ³ ná»™i dung -> tÃ¬m báº£ng cuá»‘i cÃ¹ng
        if reasoning.strip():
            markers = ["**Tá»•ng chi phÃ­", "| # |", "| STT |", "**Tá»•ng kháº¥u trá»«", "KhÃ´ng cÃ³ khoáº£n kháº¥u trá»«", "Tá»•ng chi phÃ­ theo", "Tiá»n bá»“i thÆ°á»ng thá»±c nháº­n"]
            last_match_idx = -1
            for marker in markers:
                idx = reasoning.rfind(marker)
                if idx > last_match_idx:
                    last_match_idx = idx
            if last_match_idx >= 0:
                return {"success": True, "text": reasoning[last_match_idx:][:5000].strip(), "error": ""}

            # Fallback: tÃ¬m pháº§n cuá»‘i cÃ³ dáº¥u hiá»‡u tráº£ lá»i (báº£ng)
            lines = reasoning.split("\n")
            answer_lines = []
            in_answer = False
            for line in lines:
                if any(m in line for m in ["**Tá»•ng", "| # |", "| STT", "| 1 ", "| 1  ", "KhÃ´ng cÃ³ khoáº£n", "Tiá»n bá»“i thÆ°á»ng", "Tiá»n cÃ²n láº¡i"]):
                    in_answer = True
                if in_answer:
                    answer_lines.append(line)

            if answer_lines:
                return {"success": True, "text": "\n".join(answer_lines)[:5000], "error": ""}

            return {"success": True, "text": reasoning[-2000:].strip(), "error": ""}

        return {"success": False, "text": "", "error": "AI khÃ´ng tráº£ vá» ná»™i dung."}

    except requests.exceptions.Timeout:
        return {"success": False, "text": "", "error": f"Analysis model timeout ({timeout}s)"}
    except requests.exceptions.HTTPError as e:
        return {"success": False, "text": "", "error": f"HTTP error: {e.response.status_code} - {e.response.text[:200]}"}
    except Exception as e:
        return {"success": False, "text": "", "error": str(e)}


# ============================================================
# TIER 3: GLM-5.2 â€” MERGE & XUáº¤T Báº¢NG CUá»I CÃ™NG
# ============================================================

def build_analysis_prompt(claim_data, invoice_text, contract_text):
    """XÃ¢y prompt phÃ¢n tÃ­ch kháº¥u trá»« cho GLM-5.2 â€” chá»‰ nháº­n text, khÃ´ng nháº­n áº£nh."""
    product_name = claim_data.get("product", {}).get("name", "KhÃ´ng rÃµ")
    answers = claim_data.get("answers", {})

    prompt = f'''Báº N LÃ€ CHUYÃŠN GIA KIá»‚M TOÃN Há»¢P Äá»’NG Báº¢O HIá»‚M CAO Cáº¤P.
NHIá»†M Vá»¤: PhÃ¢n tÃ­ch kháº¥u trá»« bá»“i thÆ°á»ng báº±ng cÃ¡ch Ä‘á»‘i chiáº¿u hÃ³a Ä‘Æ¡n vá»›i há»£p Ä‘á»“ng, suy luáº­n logic (ká»ƒ cáº£ kháº¥u trá»« giÃ¡n tiáº¿p/nhÃºng), rá»“i xuáº¥t ra Má»˜T Báº¢NG DUY NHáº¤T theo máº«u quy Ä‘á»‹nh.

Báº¡n lÃ m viá»‡c theo 3 BÆ¯á»šC Báº®T BUá»˜C, khÃ´ng bá» qua bÆ°á»›c nÃ o, khÃ´ng rÃºt gá»n, khÃ´ng tÃ³m táº¯t - Ä‘á»c TOÃ€N VÄ‚N tÃ i liá»‡u.

THÃ”NG TIN Há»’ SÆ :
- Sáº£n pháº©m báº£o hiá»ƒm: {product_name}
- KhÃ¡ch hÃ ng: {claim_data.get('customer_name', 'KhÃ´ng rÃµ')}
- Loáº¡i sá»± cá»‘: {answers.get('incident_type', 'KhÃ´ng rÃµ')}

===============================================
BÆ¯á»šC 1 - Äá»ŒC VÃ€ GHI NHá»š TOÃ€N Bá»˜ HÃ“A ÄÆ N
===============================================

DÆ°á»›i Ä‘Ã¢y lÃ  ná»™i dung hÃ³a Ä‘Æ¡n Ä‘Ã£ Ä‘Æ°á»£c trÃ­ch xuáº¥t tá»« áº£nh:

{invoice_text}

Äá»c TOÃ€N Bá»˜ hÃ³a Ä‘Æ¡n. Vá»›i Má»–I má»¥c, ghi nhá»›:
- TÃªn má»¥c / háº¡ng má»¥c
- MÃ´ táº£ chi tiáº¿t (náº¿u cÃ³)
- ÄÆ¡n vá»‹ tÃ­nh vÃ  sá»‘ lÆ°á»£ng (náº¿u cÃ³)
- ÄÆ¡n giÃ¡ (náº¿u cÃ³)
- ThÃ nh tiá»n

TÃ­nh vÃ  ghi nhá»›:
- Tá»”NG TIá»€N TRÆ¯á»šC THUáº¾ (náº¿u cÃ³)
- TIá»€N THUáº¾ (náº¿u cÃ³)
- Tá»”NG TIá»€N SAU THUáº¾ (= Tá»”NG Cá»˜NG)

[!] Báº¡n pháº£i ghi nhá»› CHÃNH XÃC Tá»ªNG CON Sá». KhÃ´ng Ä‘Æ°á»£c tÃ³m táº¯t, khÃ´ng Ä‘Æ°á»£c gá»™p má»¥c náº¿u khÃ´ng cháº¯c cháº¯n.

===============================================
BÆ¯á»šC 2 - Äá»ŒC TOÃ€N Bá»˜ Há»¢P Äá»’NG & XÃ‚Y Báº¢NG TRA Cá»¨U
===============================================

DÆ°á»›i Ä‘Ã¢y lÃ  ná»™i dung há»£p Ä‘á»“ng Ä‘Ã£ Ä‘Æ°á»£c trÃ­ch xuáº¥t tá»« áº£nh:

{contract_text}

Äá»c TOÃ€N Bá»˜ há»£p Ä‘á»“ng - má»i Ä‘iá»u khoáº£n, phá»¥ lá»¥c, Ä‘Ã­nh chÃ­nh. KhÃ´ng Ä‘Æ°á»£c bá» qua báº¥t ká»³ Ä‘iá»u khoáº£n nÃ o.

[!] ÄIá»€U QUAN TRá»ŒNG NHáº¤T: ThÃ´ng tin loáº¡i trá»« vÃ  thÃ´ng tin Ä‘á»‹nh nghÄ©a THÆ¯á»œNG Náº°M á»ž CÃC TRANG KHÃC NHAU. Báº¡n KHÃ”NG ÄÆ¯á»¢C chá»‰ Ä‘á»c tá»«ng trang riÃªng láº». Báº¡n PHáº¢I tá»•ng há»£p thÃ´ng tin tá»« Táº¤T Cáº¢ cÃ¡c trang, káº¿t ná»‘i chÃºng láº¡i, rá»“i má»›i suy luáº­n.

2.1. XÃ‚Y Dá»°NG 3 DANH SÃCH Báº®T BUá»˜C (lÃ m trong Ä‘áº§u, khÃ´ng xuáº¥t ra)

DANH SÃCH A - ÄIá»€U KHOáº¢N LOáº I TRá»ª:
Má»i Ä‘iá»u khoáº£n nÃ³i vá» viá»‡c KHÃ”NG bá»“i thÆ°á»ng / loáº¡i trá»« / khÃ´ng chi tráº£.
Háº¡ng má»¥c bá»‹ loáº¡i trá»« cÃ³ thá»ƒ lÃ :
  - TÃªn trá»±c tiáº¿p: 'KhÃ´ng bá»“i thÆ°á»ng thuá»‘c ngoÃ i danh má»¥c'
  - TÃªn nhÃ³m/khÃ¡i niá»‡m: 'KhÃ´ng bá»“i thÆ°á»ng thiáº¿t bá»‹ y táº¿ há»— trá»£ Ä‘iá»u trá»‹'
  -> Vá»›i tÃªn nhÃ³m, báº¡n PHáº¢I tra trong DANH SÃCH B Ä‘á»ƒ xem nhÃ³m Ä‘Ã³ bao gá»“m nhá»¯ng háº¡ng má»¥c cá»¥ thá»ƒ nÃ o.

DANH SÃCH B - KHÃI NIá»†M / Äá»ŠNH NGHÄ¨A / DANH Má»¤C:
Má»i trang Ä‘á»‹nh nghÄ©a thuáº­t ngá»¯, liá»‡t kÃª danh má»¥c, giáº£i thÃ­ch khÃ¡i niá»‡m.
VD: 'Thiáº¿t bá»‹ y táº¿ há»— trá»£ Ä‘iá»u trá»‹ bao gá»“m: ...'
-> Má»—i khÃ¡i niá»‡m trong DANH SÃCH A (loáº¡i trá»«) PHáº¢I Ä‘Æ°á»£c tra trong DANH SÃCH B Ä‘á»ƒ tÃ¬m cÃ¡c háº¡ng má»¥c con cá»¥ thá»ƒ.
-> LÆ°u Ã½: Ä‘á»‹nh nghÄ©a trong há»£p Ä‘á»“ng cÃ³ thá»ƒ KHÃ”NG bao gá»“m thuá»‘c. Pháº£i Ä‘á»c ká»¹ xem Ä‘á»‹nh nghÄ©a ghi gÃ¬.

DANH SÃCH C - Háº N Má»¨C CHI TRáº¢:
Má»i giá»›i háº¡n chi tráº£: tá»‘i Ä‘a X VNÄ/nÄƒm, tá»‘i Ä‘a Y VNÄ/láº§n, tá»‘i Ä‘a Z% giÃ¡ trá»‹...

2.2. QUY TRÃŒNH SUY LUáº¬N Báº®T BUá»˜C - MAP HÃ“A ÄÆ N VÃ€O 3 DANH SÃCH

Vá»›i Tá»ªNG Má»–I Má»¤C trong hÃ³a Ä‘Æ¡n, thá»±c hiá»‡n:

BÆ¯á»šC 2(A) - TRA DANH SÃCH A (Ä‘iá»u khoáº£n loáº¡i trá»«):
  - Má»¥c trong hÃ³a Ä‘Æ¡n cÃ³ trÃ¹ng tÃªn trá»±c tiáº¿p vá»›i báº¥t ká»³ háº¡ng má»¥c nÃ o trong DANH SÃCH A khÃ´ng?
    -> CÃ³ -> KHáº¤U TRá»ª. Ghi rÃµ: tÃªn má»¥c + sá»‘ tiá»n + Ä‘iá»u khoáº£n + trang.
    -> KhÃ´ng -> chuyá»ƒn sang BÆ¯á»šC 2(B).

BÆ¯á»šC 2(B) - TRA DANH SÃCH B (khÃ¡i niá»‡m/Ä‘á»‹nh nghÄ©a) - KIá»‚M TRA KHáº¤U TRá»ª GIÃN TIáº¾P:
  - Má»¥c trong hÃ³a Ä‘Æ¡n cÃ³ thuá»™c báº¥t ká»³ khÃ¡i niá»‡m/Ä‘á»‹nh nghÄ©a nÃ o trong DANH SÃCH B khÃ´ng?
    -> DUYá»†T Tá»ªNG khÃ¡i niá»‡m trong DANH SÃCH B:
      - KhÃ¡i niá»‡m nÃ y cÃ³ liá»‡t kÃª/bao gá»“m má»¥c trong hÃ³a Ä‘Æ¡n khÃ´ng?
      - KhÃ¡i niá»‡m nÃ y cÃ³ bá»‹ NHáº®C Äáº¾N trong DANH SÃCH A (tá»©c lÃ  khÃ¡i niá»‡m Ä‘Ã³ bá»‹ loáº¡i trá»«) khÃ´ng?
      -> Náº¾U Cáº¢ HAI Äá»€U CÃ“: má»¥c trong hÃ³a Ä‘Æ¡n thuá»™c khÃ¡i niá»‡m bá»‹ loáº¡i trá»« -> KHáº¤U TRá»ª (giÃ¡n tiáº¿p).
        Ghi rÃµ: tÃªn má»¥c + sá»‘ tiá»n + khÃ¡i niá»‡m trung gian + Ä‘iá»u khoáº£n loáº¡i trá»« + trang.
      -> Chá»‰ cÃ³ 1/2: khÃ´ng Ä‘á»§ cÆ¡ sá»Ÿ, chuyá»ƒn sang khÃ¡i niá»‡m tiáº¿p theo.
  - Sau khi duyá»‡t háº¿t DANH SÃCH B mÃ  váº«n khÃ´ng tÃ¬m tháº¥y -> chuyá»ƒn sang BÆ¯á»šC 2(C).

BÆ¯á»šC 2(C) - TRA DANH SÃCH C (háº¡n má»©c chi tráº£):
  - Má»¥c trong hÃ³a Ä‘Æ¡n cÃ³ thuá»™c má»™t háº¡ng má»¥c cÃ³ háº¡n má»©c trong DANH SÃCH C khÃ´ng?
  - Sá»‘ tiá»n cÃ³ vÆ°á»£t háº¡n má»©c khÃ´ng?
    -> VÆ°á»£t -> pháº§n vÆ°á»£t bá»‹ KHáº¤U TRá»ª.
    -> KhÃ´ng vÆ°á»£t -> khÃ´ng kháº¥u trá»«.

BÆ¯á»šC 2(D) - Káº¾T LUáº¬N:
  - Náº¿u má»¥c bá»‹ kháº¥u trá»« qua báº¥t ká»³ bÆ°á»›c 2(A)/2(B)/2(C) nÃ o -> Ä‘Æ°a vÃ o báº£ng káº¿t quáº£.
  - Náº¿u khÃ´ng bá»‹ kháº¥u trá»« qua báº¥t ká»³ bÆ°á»›c nÃ o -> KHÃ”NG Ä‘Æ°a vÃ o báº£ng.

2.3. NGUYÃŠN Táº®C PHÃ‚N LOáº I Äá»I TÆ¯á»¢NG â€” CHá»ˆ Dá»°A VÃ€O Há»¢P Äá»’NG, KHÃ”NG Tá»° Ã PHÃ‚N LOáº I

[!] NGUYÃŠN Táº®C Tá»I THáº¤U â€” KHÃ”NG ÄÆ¯á»¢C PHÃ‚N LOáº I Äá»I TÆ¯á»¢NG Tá»ª KIáº¾N THá»¨C NGOÃ€I Há»¢P Äá»’NG:
- Báº¡n KHÃ”NG ÄÆ¯á»¢C tá»± Ã½ phÃ¢n loáº¡i má»™t má»¥c trong hÃ³a Ä‘Æ¡n lÃ  'thuá»‘c', 'thá»±c pháº©m chá»©c nÄƒng', 'thiáº¿t bá»‹ y táº¿' hay báº¥t ká»³ loáº¡i nÃ o dá»±a trÃªn kiáº¿n thá»©c cá»§a báº¡n.
- Báº¡n CHá»ˆ ÄÆ¯á»¢C dÃ¹ng thÃ´ng tin tá»« chÃ­nh há»£p Ä‘á»“ng: náº¿u há»£p Ä‘á»“ng ghi háº¡ng má»¥c Ä‘Ã³ thuá»™c nhÃ³m bá»‹ loáº¡i trá»« â†’ kháº¥u trá»«. Náº¿u há»£p Ä‘á»“ng KHÃ”NG nháº¯c Ä‘áº¿n háº¡ng má»¥c Ä‘Ã³ â†’ KHÃ”NG kháº¥u trá»«.
- KHÃ”NG ÄÆ¯á»¢C dÃ¹ng lÃ½ do 'lÃ  thá»±c pháº©m chá»©c nÄƒng', 'khÃ´ng pháº£i thuá»‘c', 'khÃ´ng cÃ³ tÃ¡c dá»¥ng Ä‘iá»u trá»‹' hoáº·c báº¥t ká»³ phÃ¢n loáº¡i y táº¿ nÃ o mÃ  há»£p Ä‘á»“ng KHÃ”NG ghi rÃµ.
- LÃ­ do kháº¥u trá»« PHáº¢I lÃ  trÃ­ch dáº«n nguyÃªn vÄƒn Ä‘iá»u khoáº£n há»£p Ä‘á»“ng, KHÃ”NG ÄÆ¯á»¢C bá»• sung lÃ½ do riÃªng.

  CÃ¡ch xÃ¡c Ä‘á»‹nh Ä‘Ãºng:
  a) Há»£p Ä‘á»“ng ghi TÃŠN Cá»¤ THá»‚ bá»‹ loáº¡i trá»« (vd: 'Sanlein'):
     â†’ Kháº¥u trá»« Ä‘Ãºng tÃªn Ä‘Ã³. LÃ­ do = 'Há»£p Ä‘á»“ng ghi rÃµ loáº¡i trá»« [tÃªn háº¡ng má»¥c] táº¡i [sá»‘ Ä‘iá»u khoáº£n], trang [sá»‘]'.
     â†’ KHÃ”NG ÄÆ¯á»¢C bá»• sung thÃªm lÃ½ do nhÆ° 'vÃ¬ lÃ  thá»±c pháº©m chá»©c nÄƒng' hay 'vÃ¬ khÃ´ng pháº£i thuá»‘c'.
     â†’ KHÃ”NG ÄÆ¯á»¢C kÃ©o theo háº¡ng má»¥c khÃ¡c khÃ´ng Ä‘Æ°á»£c nháº¯c trong há»£p Ä‘á»“ng.

  b) Há»£p Ä‘á»“ng ghi NHÃ“M/LOáº I bá»‹ loáº¡i trá»« (vd: 'thuá»‘c nhá» máº¯t', 'váº­t tÆ° y táº¿ tiÃªu hao'):
     â†’ Kháº¥u trá»« má»i háº¡ng má»¥c trong hÃ³a Ä‘Æ¡n THá»°C Sá»° thuá»™c nhÃ³m/loáº¡i Ä‘Ã³.
     â†’ Viá»‡c xÃ¡c Ä‘á»‹nh thuá»™c nhÃ³m hay khÃ´ng PHáº¢I dá»±a vÃ o Ä‘á»‹nh nghÄ©a trong há»£p Ä‘á»“ng (DANH SÃCH B), KHÃ”NG dá»±a vÃ o kiáº¿n thá»©c bÃªn ngoÃ i.
     â†’ Náº¿u há»£p Ä‘á»“ng Ä‘á»‹nh nghÄ©a nhÃ³m Ä‘Ã³ + liá»‡t kÃª cÃ¡c háº¡ng má»¥c con â†’ chá»‰ kháº¥u trá»« háº¡ng má»¥c con Ä‘Æ°á»£c liá»‡t kÃª.
     â†’ Náº¿u há»£p Ä‘á»“ng Ä‘á»‹nh nghÄ©a nhÃ³m Ä‘Ã³ mÃ  KHÃ”NG liá»‡t kÃª háº¡ng má»¥c con â†’ chá»‰ kháº¥u trá»« khi tÃªn háº¡ng má»¥c trong hÃ³a Ä‘Æ¡n trÃ¹ng khá»›p vá»›i tÃªn nhÃ³m.

  c) Há»£p Ä‘á»“ng KHÃ”NG nháº¯c Ä‘áº¿n háº¡ng má»¥c (khÃ´ng tÃªn cá»¥ thá»ƒ, khÃ´ng nhÃ³m chá»©a nÃ³):
     â†’ KHÃ”NG KHáº¤U TRá»ª. KhÃ´ng Ä‘Æ°á»£c tá»± phÃ¢n loáº¡i Ä‘á»ƒ tÃ¬m lÃ½ do kháº¥u trá»«.

  [!] TUYá»†T Äá»I KHÃ”NG:
  - Tá»± suy 'A lÃ  thá»±c pháº©m chá»©c nÄƒng â†’ khÃ´ng pháº£i thuá»‘c â†’ khÃ´ng chi tráº£' â†’ Há»ŽI Há»¢P Äá»’NG cÃ³ ghi váº­y khÃ´ng? Náº¿u khÃ´ng â†’ KHÃ”NG KHáº¤U TRá»ª.
  - Tá»± suy 'A tÆ°Æ¡ng tá»± B nÃªn cÅ©ng bá»‹ loáº¡i trá»«' â†’ Há»ŽI Há»¢P Äá»’NG cÃ³ ghi A khÃ´ng? Náº¿u khÃ´ng â†’ KHÃ”NG KHáº¤U TRá»ª.
  - Bá»• sung lÃ­ do ngoÃ i Ä‘iá»u khoáº£n há»£p Ä‘á»“ng (vd: 'vÃ¬ khÃ´ng cÃ³ hoáº¡t cháº¥t Ä‘iá»u trá»‹', 'vÃ¬ lÃ  thá»±c pháº©m chá»©c nÄƒng') â†’ CHá»ˆ dÃ¹ng lÃ­ do tá»« há»£p Ä‘á»“ng.

2.4. VÃ Dá»¤ MINH Há»ŒA (Ä‘á»ƒ hiá»ƒu cÃ¡ch suy luáº­n, KHÃ”NG Ä‘Æ°á»£c dÃ¹ng vÃ­ dá»¥ nÃ y lÃ m khuÃ´n cá»‘ Ä‘á»‹nh):

  TÃ¬nh huá»‘ng 1 â€” Kháº¥u trá»« khi há»£p Ä‘á»“ng ghi TÃŠN Cá»¤ THá»‚:
  - HÃ³a Ä‘Æ¡n cÃ³: 'Sanlein 0.3% 5ml (SL: 2) - 264.600 VNÄ'
  - Há»£p Ä‘á»“ng ghi: 'VÃ  loáº¡i trá»« thÃªm má»¥c 10' (Trang 4), Má»¥c 10 = 'Sanlein' (Trang 7/8)
  â†’ KHáº¤U TRá»ª Sanlein. LÃ­ do = 'Há»£p Ä‘á»“ng ghi rÃµ loáº¡i trá»« Sanlein táº¡i Má»¥c 10 (Trang 4/7/8)'.
  â†’ KHÃ”NG Bá»” SUNG lÃ­ do 'vÃ¬ Sanlein lÃ  thá»±c pháº©m chá»©c nÄƒng' hay báº¥t ká»³ lÃ­ do nÃ o khÃ¡c.
  â†’ KHÃ”NG KÃ‰O THEO Liposic hay báº¥t ká»³ thuá»‘c nÃ o khÃ¡c khÃ´ng Ä‘Æ°á»£c nháº¯c trong há»£p Ä‘á»“ng.

  TÃ¬nh huá»‘ng 2 â€” Kháº¥u trá»« khi há»£p Ä‘á»“ng ghi NHÃ“M:
  - Há»£p Ä‘á»“ng ghi: 'KhÃ´ng bá»“i thÆ°á»ng thuá»‘c nhá» máº¯t' (Ä‘iá»u khoáº£n X, trang Y)
  - HÃ³a Ä‘Æ¡n cÃ³: 'Sanlein 0.3% 5ml' vÃ  'Liposic Eye gel 2% 10g'
  â†’ Cáº£ hai Ä‘á»u lÃ  thuá»‘c nhá» máº¯t â†’ KHáº¤U TRá»ª cáº£ hai. LÃ­ do = 'Há»£p Ä‘á»“ng loáº¡i trá»« thuá»‘c nhá» máº¯t (Ä‘iá»u khoáº£n X, trang Y)'.

  TÃ¬nh huá»‘ng 3 â€” KHÃ”NG kháº¥u trá»« khi há»£p Ä‘á»“ng KHÃ”NG nháº¯c:
  - HÃ³a Ä‘Æ¡n cÃ³: 'Liposic Eye gel 2% 10g - 69.550 VNÄ'
  - Há»£p Ä‘á»“ng chá»‰ ghi loáº¡i trá»« 'Sanlein' (Má»¥c 10), KHÃ”NG nháº¯c 'Liposic', khÃ´ng nháº¯c 'thuá»‘c nhá» máº¯t'
  â†’ KHÃ”NG KHáº¤U TRá»ª Liposic. LÃ­ do = 'Há»£p Ä‘á»“ng khÃ´ng ghi loáº¡i trá»« Liposic'.
  â†’ KHÃ”NG ÄÆ¯á»¢C tá»± suy 'Liposic tÆ°Æ¡ng tá»± Sanlein nÃªn cÅ©ng bá»‹ loáº¡i trá»«'.
  â†’ KHÃ”NG ÄÆ¯á»¢C tá»± suy 'Liposic lÃ  thá»±c pháº©m chá»©c nÄƒng nÃªn khÃ´ng chi tráº£'.

  TÃ¬nh huá»‘ng 4 â€” Kháº¥u trá»« giÃ¡n tiáº¿p Há»¢P Lá»† (dá»±a trÃªn Ä‘á»‹nh nghÄ©a trong há»£p Ä‘á»“ng):
  - HÃ³a Ä‘Æ¡n cÃ³: 'BÄƒng gáº¡c y táº¿ - 50.000 VNÄ'
  - Há»£p Ä‘á»“ng loáº¡i trá»«: 'váº­t tÆ° y táº¿ tiÃªu hao' (Trang 4)
  - Há»£p Ä‘á»“ng Ä‘á»‹nh nghÄ©a: 'váº­t tÆ° y táº¿ tiÃªu hao bao gá»“m: bÄƒng gáº¡c, bÃ´ng y táº¿, á»‘ng tiÃªm...' (Trang 7)
  â†’ KHáº¤U TRá»ª bÄƒng gáº¡c. LÃ­ do = 'Há»£p Ä‘á»“ng loáº¡i trá»« váº­t tÆ° y táº¿ tiÃªu hao (Trang 4), Ä‘á»‹nh nghÄ©a bao gá»“m bÄƒng gáº¡c (Trang 7)'.

  [!] ÄÃ¢y chá»‰ lÃ  vÃ­ dá»¥ vá» cÃ¡ch suy luáº­n. Báº¡n PHáº¢I Ã¡p dá»¥ng cho Tá»ªNG Má»¤C trong hÃ³a Ä‘Æ¡n, vá»›i Tá»ªNG KHÃI NIá»†M trong há»£p Ä‘á»“ng â€” dá»±a trÃªn Ná»˜I DUNG THá»°C Táº¾ cá»§a há»£p Ä‘á»“ng, khÃ´ng dá»±a trÃªn vÃ­ dá»¥.

2.5. NGUYÃŠN Táº®C SUY LUáº¬N

- KHÃ”NG Bá»Ž SÃ“T: Äá»c háº¿t má»i Ä‘iá»u khoáº£n, tÃ¬m háº¿t má»i khoáº£n kháº¥u trá»«.
- TRUY CHUá»–I Äáº¾N Táº¬N Cáº¤P LÃ: A bá»‹ kháº¥u trá»« chá»©a B, C -> kiá»ƒm tra B, C. B chá»©a B1, B2 -> tiáº¿p tá»¥c. Äi Ä‘áº¿n táº­n cÃ¹ng.
- THAM CHIáº¾U CHÃ‰O: Äiá»u X dáº«n Ä‘áº¿n Äiá»u Y -> pháº£i Ä‘á»c cáº£ Y.
- KHÃ”NG SUY ÄOÃN: Chá»‰ kháº¥u trá»« khi cÃ³ cÆ¡ sá»Ÿ rÃµ rÃ ng. Náº¿u khÃ´ng cháº¯c, Ä‘Ã¡nh dáº¥u '[!] Cáº§n xÃ¡c nháº­n'.
- KHÃ”NG Tá»° Ã Má»ž Rá»˜NG KHÃI NIá»†M: Kháº¥u trá»« theo Ä‘Ãºng loáº¡i Ä‘á»‘i tÆ°á»£ng. Thuá»‘c â‰  thiáº¿t bá»‹ y táº¿ â‰  váº­t tÆ° y táº¿. Chá»‰ kháº¥u trá»« khi há»£p Ä‘á»“ng THá»°C Sá»° Ã¡p dá»¥ng cho loáº¡i Ä‘á»‘i tÆ°á»£ng Ä‘Ã³.
- GHI NGUá»’N: Má»—i káº¿t luáº­n kháº¥u trá»« pháº£i kÃ¨m sá»‘ Ä‘iá»u khoáº£n + sá»‘ trang trong há»£p Ä‘á»“ng.
- KIá»‚M TRA CHÃ‰O Báº®T BUá»˜C: Má»–I Má»¤C trong hÃ³a Ä‘Æ¡n PHáº¢I kiá»ƒm tra cáº£ 3 danh sÃ¡ch A, B, C.

2.6. NGUYÃŠN Táº®C Äá»ŒC NGÃ€Y â€” QUAN TRá»ŒNG

- Äá»ŒC NGÃ€Y CHÃNH XÃC: Pháº£i Ä‘á»c Ä‘Ãºng ngÃ y/thÃ¡ng/nÄƒm trÃªn hÃ³a Ä‘Æ¡n vÃ  há»£p Ä‘á»“ng. KhÃ´ng Ä‘Æ°á»£c hoÃ¡n Ä‘á»•i ngÃ y/thÃ¡ng, khÃ´ng Ä‘Æ°á»£c sá»­a nÄƒm.
  VD: '26/06/2025' pháº£i Ä‘á»c lÃ  26 thÃ¡ng 06 nÄƒm 2025, KHÃ”NG pháº£i '25/06/2026' hay '06/26/2025'.
- KIá»‚M TRA Äá»ŠNH Dáº NG NGÃ€Y: HÃ³a Ä‘Æ¡n Viá»‡t Nam dÃ¹ng Ä‘á»‹nh dáº¡ng dd/mm/yyyy. Náº¿u tháº¥y sá»‘ > 12 á»Ÿ vá»‹ trÃ­ Ä‘áº§u â†’ Ä‘Ã³ lÃ  ngÃ y, khÃ´ng pháº£i thÃ¡ng.
- KHI SO SÃNH THá»œI Háº N: Äá»c chÃ­nh xÃ¡c ngÃ y báº¯t Ä‘áº§u hiá»‡u lá»±c báº£o hiá»ƒm vÃ  ngÃ y Ä‘iá»u trá»‹. Chá»‰ kháº¥u trá»« khi ngÃ y Ä‘iá»u trá»‹ THá»°C Sá»° náº±m ngoÃ i thá»i háº¡n báº£o hiá»ƒm. KhÃ´ng Ä‘Æ°á»£c Ä‘oÃ¡n hay sá»­a ngÃ y.

2.7. NGUYÃŠN Táº®C Äá»˜C Láº¬P Má»–I Má»¤C â€” KHÃ”NG KÃ‰O THEO â€” LUáº¬T Báº®T BUá»˜C

[!] ÄÃ‚Y LÃ€ LUáº¬T Cá»¨NG â€” KHÃ”NG CÃ“ NGOáº I Lá»†:

- Má»–I Má»¤C trong hÃ³a Ä‘Æ¡n PHáº¢I Ä‘Æ°á»£c Ä‘Ã¡nh giÃ¡ Äá»˜C Láº¬P 100%. Káº¿t quáº£ cá»§a má»¥c nÃ y KHÃ”NG áº¢NH HÆ¯á»žNG Ä‘áº¿n má»¥c khÃ¡c.
- KHÃ”NG ÄÆ¯á»¢C kÃ©o theo: náº¿u há»£p Ä‘á»“ng chá»‰ ghi loáº¡i trá»« 'Sanlein' â†’ CHá»ˆ kháº¥u trá»« Sanlein. KHÃ”NG ÄÆ¯á»¢C kháº¥u trá»« 'Liposic' hay báº¥t ká»³ má»¥c nÃ o khÃ¡c vá»›i lÃ­ do 'tÆ°Æ¡ng tá»± Sanlein', 'cÃ¹ng loáº¡i vá»›i Sanlein', 'cÃ¹ng lÃ  thá»±c pháº©m chá»©c nÄƒng nhÆ° Sanlein'.
- KHÃ”NG ÄÆ¯á»¢C dÃ¹ng káº¿t quáº£ cá»§a má»¥c nÃ y lÃ m tiá»n Ä‘á» cho má»¥c khÃ¡c: 'A bá»‹ kháº¥u trá»« â†’ B cÅ©ng bá»‹ kháº¥u trá»« vÃ¬ giá»‘ng A' â†’ NGHIÃŠM Cáº¤M.
- Má»–I Má»¤C PHáº¢I Tá»° CÃ“ cÆ¡ sá»Ÿ riÃªng tá»« há»£p Ä‘á»“ng: náº¿u há»£p Ä‘á»“ng KHÃ”NG nháº¯c Ä‘áº¿n má»¥c Ä‘Ã³ (khÃ´ng tÃªn cá»¥ thá»ƒ, khÃ´ng nhÃ³m chá»©a nÃ³) â†’ KHÃ”NG KHáº¤U TRá»ª, dÃ¹ má»i má»¥c khÃ¡c trong hÃ³a Ä‘Æ¡n cÃ³ bá»‹ kháº¥u trá»«.
- Äá»ƒ kháº¥u trá»« má»™t má»¥c, báº¡n PHáº¢I tÃ¬m Ä‘Æ°á»£c ÄIá»€U KHOáº¢N Cá»¤ THá»‚ trong há»£p Ä‘á»“ng Ã¡p dá»¥ng cho CHÃNH Má»¤C ÄÃ“ (trÃ¹ng tÃªn trá»±c tiáº¿p hoáº·c thuá»™c nhÃ³m Ä‘Æ°á»£c Ä‘á»‹nh nghÄ©a trong há»£p Ä‘á»“ng).

VÃ Dá»¤ SAI (TUYá»†T Äá»I KHÃ”NG LÃ€M):
- Há»£p Ä‘á»“ng ghi loáº¡i trá»« 'Sanlein' â†’ kháº¥u trá»« Sanlein â†’ kÃ©o thÃªm Liposic vÃ¬ 'cÃ¹ng loáº¡i' â†’ SAI. Liposic chá»‰ bá»‹ kháº¥u trá»« náº¿u há»£p Ä‘á»“ng CÅ¨NG ghi Liposic hoáº·c ghi nhÃ³m chá»©a Liposic.
- Há»£p Ä‘á»“ng ghi loáº¡i trá»« 'Sanlein' vá»›i lÃ­ do 'Sanlein lÃ  thá»±c pháº©m chá»©c nÄƒng' â†’ kháº¥u trá»« Sanlein â†’ kÃ©o thÃªm Liposic vÃ¬ 'cÅ©ng lÃ  thá»±c pháº©m chá»©c nÄƒng' â†’ SAI. Liposic chá»‰ bá»‹ kháº¥u trá»« náº¿u há»£p Ä‘á»“ng CÅ¨NG ghi Liposic.

VÃ Dá»¤ ÄÃšNG:
- Há»£p Ä‘á»“ng ghi loáº¡i trá»« 'Sanlein' (Má»¥c 10) â†’ KHáº¤U TRá»ª Sanlein. KHÃ”NG kháº¥u trá»« Liposic (há»£p Ä‘á»“ng khÃ´ng nháº¯c).
- Há»£p Ä‘á»“ng ghi loáº¡i trá»« 'thuá»‘c nhá» máº¯t' (cáº£ nhÃ³m) â†’ KHáº¤U TRá»ª cáº£ Sanlein vÃ  Liposic (cÃ¹ng thuá»™c nhÃ³m thuá»‘c nhá» máº¯t).
- Há»£p Ä‘á»“ng khÃ´ng nháº¯c 'Liposic' â†’ KHÃ”NG KHáº¤U TRá»ª Liposic, DÃ™ Sanlein bá»‹ kháº¥u trá»«.

===============================================
BÆ¯á»šC 3 - XUáº¤T Báº¢NG Káº¾T QUáº¢
===============================================

Xuáº¥t DUY NHáº¤T Má»˜T Báº¢NG theo Ä‘Ãºng máº«u bÃªn dÆ°á»›i. KhÃ´ng viáº¿t thÃªm lá»i dáº«n, khÃ´ng giáº£i thÃ­ch bÃªn ngoÃ i báº£ng. Chá»‰ hiá»‡n báº£ng.

Äá»ŠNH Dáº NG Báº¢NG (Báº®T BUá»˜C - lÃ m Ä‘Ãºng máº«u):

**Tá»•ng chi phÃ­ theo hÃ³a Ä‘Æ¡n:** [sá»‘ tiá»n] VNÄ

| # | Tá»•ng tiá»n ban Ä‘áº§u | Má»¥c bá»‹ kháº¥u trá»« | Sá»‘ tiá»n bá»‹ kháº¥u trá»« (VNÄ) | LÃ­ do bá»‹ kháº¥u trá»« | Nguá»“n Ä‘iá»u khoáº£n | Tiá»n cÃ²n láº¡i |
|---|---|---|---|---|---|---|
| 0 | [Tá»”NG Cá»˜NG tá»« hÃ³a Ä‘Æ¡n] | - | - | - | - | [Tá»”NG Cá»˜NG] |
| 1 | | [tÃªn háº¡ng má»¥c] | [sá»‘ tiá»n] | [lÃ­ do: trÃ­ch dáº«n Ä‘iá»u khoáº£n + giáº£i thÃ­ch vÃ¬ sao khoáº£n trong hÃ³a Ä‘Æ¡n bá»‹ kháº¥u trá»«] | [Äiá»u khoáº£n/trang] | [Tá»•ng - KH1] |
| 2 | | [tÃªn háº¡ng má»¥c] | [sá»‘ tiá»n] | [lÃ­ do: trÃ­ch dáº«n Ä‘iá»u khoáº£n + giáº£i thÃ­ch] | [Äiá»u khoáº£n/trang] | [Tá»•ng-KH1 - KH2] |
| ... | | | | | | |
| **KQ** | | **Tá»”NG KHáº¤U TRá»ª** | **[tá»•ng cá»™ng]** | | | **[tiá»n cuá»‘i cÃ¹ng cÃ²n láº¡i]** |

**Tá»•ng kháº¥u trá»«:** [sá»‘ tiá»n] VNÄ
**Tiá»n bá»“i thÆ°á»ng thá»±c nháº­n:** [Tá»•ng - Kháº¥u trá»«] = [sá»‘ tiá»n] VNÄ

QUY Táº®C XUáº¤T Báº¢NG:
- DÃ²ng 0 = tá»•ng tiá»n ban Ä‘áº§u. Cá»™t 'Tiá»n cÃ²n láº¡i' = Tá»”NG Cá»˜NG.
- Má»—i dÃ²ng kháº¥u trá»« = má»™t háº¡ng má»¥c cá»¥ thá»ƒ trong hÃ³a Ä‘Æ¡n bá»‹ kháº¥u trá»«.
- Cá»™t 'LÃ­ do' PHáº¢I ghi rÃµ: (a) Ä‘iá»u khoáº£n há»£p Ä‘á»“ng gÃ¬, (b) vÃ¬ sao khoáº£n trong hÃ³a Ä‘Æ¡n bá»‹ kháº¥u trá»« theo Ä‘iá»u khoáº£n Ä‘Ã³.
- Cá»™t 'Nguá»“n Ä‘iá»u khoáº£n' = sá»‘ Ä‘iá»u khoáº£n + sá»‘ trang (náº¿u cÃ³).
- Cá»™t 'Tiá»n cÃ²n láº¡i' = cháº¡y tÃ­ch lÅ©y: dÃ²ng 1 = Tá»•ng - KH1; dÃ²ng 2 = (Tá»•ng-KH1) - KH2; v.v.
- DÃ²ng cuá»‘i (KQ) = tá»•ng cá»™ng kháº¥u trá»« vÃ  sá»‘ tiá»n cuá»‘i cÃ¹ng cÃ²n láº¡i.
- Sá»‘ tiá»n: Ä‘á»‹nh dáº¡ng cÃ³ dáº¥u pháº©y (VD: 1.500.000.000). ÄÆ¡n vá»‹ VNÄ.
- Náº¿u KHÃ”NG cÃ³ khoáº£n nÃ o bá»‹ kháº¥u trá»«: chá»‰ xuáº¥t dÃ²ng 0 vÃ  dÃ²ng KQ vá»›i '0' cho tá»•ng kháº¥u trá»«, ghi 'KhÃ´ng cÃ³ khoáº£n kháº¥u trá»«, khÃ¡ch hÃ ng nháº­n toÃ n bá»™ [sá»‘ tiá»n] VNÄ.'
- Náº¿u CÃ“ khoáº£n khÃ´ng cháº¯c cháº¯n: váº«n Ä‘Æ°a vÃ o báº£ng nhÆ°ng ghi '[!] Cáº§n xÃ¡c nháº­n' á»Ÿ cá»™t LÃ­ do.

NGUYÃŠN Táº®C Tá»”NG QUÃT:
1. Äá»c háº¿t, nhá»› háº¿t - khÃ´ng bá» sÃ³t báº¥t ká»³ dÃ²ng nÃ o trong hÃ³a Ä‘Æ¡n hay Ä‘iá»u khoáº£n nÃ o trong há»£p Ä‘á»“ng.
2. Suy luáº­n Ä‘áº¿n táº­n gá»‘c - kháº¥u trá»« giÃ¡n tiáº¿p, kháº¥u trá»« nhÃºng, kháº¥u trá»« theo Ä‘iá»u kiá»‡n, vÆ°á»£t háº¡n má»©c Ä‘á»u pháº£i kiá»ƒm tra.
3. KHÃ”NG Tá»° Ã Má»ž Rá»˜NG KHÃI NIá»†M - kháº¥u trá»« Ä‘Ãºng loáº¡i Ä‘á»‘i tÆ°á»£ng: thuá»‘c lÃ  thuá»‘c, thiáº¿t bá»‹ lÃ  thiáº¿t bá»‹, váº­t tÆ° lÃ  váº­t tÆ°. Chá»‰ kháº¥u trá»« khi há»£p Ä‘á»“ng thá»±c sá»± Ã¡p dá»¥ng cho loáº¡i Ä‘á»‘i tÆ°á»£ng Ä‘Ã³.
4. TrÃ­ch dáº«n nguá»“n - má»i káº¿t luáº­n pháº£i cÃ³ Ä‘iá»u khoáº£n há»£p Ä‘á»“ng lÃ m cÄƒn cá»©.
5. ChÃ­nh xÃ¡c tuyá»‡t Ä‘á»‘i vá» con sá»‘ - khÃ´ng lÃ m trÃ²n, khÃ´ng Æ°á»›c lÆ°á»£ng, khÃ´ng 'khoáº£ng'.
6. Äá»ŒC NGÃ€Y CHÃNH XÃC - dd/mm/yyyy, khÃ´ng hoÃ¡n Ä‘á»•i, khÃ´ng sá»­a nÄƒm. Chá»‰ kháº¥u trá»« khi THá»°C Sá»° ngoÃ i thá»i háº¡n.
7. Má»–I Má»¤C Äá»˜C Láº¬P - khÃ´ng kÃ©o theo má»¥c khÃ¡c vÃ o kháº¥u trá»«. Má»—i má»¥c pháº£i tá»± cÃ³ cÆ¡ sá»Ÿ riÃªng.
8. Chá»‰ xuáº¥t báº£ng - káº¿t quáº£ cuá»‘i cÃ¹ng lÃ  má»™t báº£ng duy nháº¥t, khÃ´ng kÃ¨m lá»i giáº£i thÃ­ch bÃªn ngoÃ i.
'''
    return prompt


# ============================================================
# PIPELINE CHÃNH: 3 Táº¦NG (MAP-REDUCE-MERGE)
# ============================================================

def analyze_deduction(claim_data, photo_paths, contract_path):
    """Pipeline 3 táº§ng: Tier 1 (Map) -> Tier 2 (Reduce) -> Tier 3 (Merge)."""

    if not has_api_key():
        return {
            "success": False,
            "response": "",
            "error": "ChÆ°a cáº¥u hÃ¬nh API key. Vui lÃ²ng thÃªm key vÃ o Streamlit Cloud Secrets (key: ollama_api_key) hoáº·c táº¡o file .kimi_api_key (local)."
        }

    try:
        import threading
        t_total = time.perf_counter()

        # ============================================================
        # TIER 1 (MAP): KIMI Äá»ŒC áº¢NH HÃ“A ÄÆ N + CHUNKS Há»¢P Äá»’NG SONG SONG
        # Chunk 5 trang/call + ThreadPoolExecutor(max_workers=6) Ä‘á»ƒ cap concurrency.
        # Tá»•ng text trÃ­ch xuáº¥t KHÃ”NG Ä‘á»•i -> accuracy giá»¯ nguyÃªn.
        # ============================================================

        # Chuáº©n bá»‹ chunks há»£p Ä‘á»“ng cho Kimi
        contract_chunks_images = []  # list of (images_batch, num_pages_in_batch)
        # DÃ¹ng cho trang cÃ³ text (khÃ´ng cáº§n Kimi)
        contract_text_pages = {}  # {page_num: text}

        if contract_path and os.path.exists(contract_path):
            ext = os.path.splitext(contract_path)[1].lower().lstrip(".")
            if ext == "pdf":
                # TÃ¡ch trang cÃ³ text vÃ  trang chá»‰ cÃ³ áº£nh
                text_pages, image_page_indices = extract_pdf_text_and_image_pages(contract_path, max_pages=100)
                contract_text_pages = text_pages

                if image_page_indices:
                    # CÃ³ trang áº£nh scan â†’ chuyá»ƒn sang áº£nh cho Kimi Ä‘á»c
                    contract_images, total_pages = pdf_pages_to_images_by_indices(contract_path, image_page_indices)
                    if contract_images:
                        chunk_size = 5
                        for i in range(0, len(contract_images), chunk_size):
                            batch = contract_images[i:i + chunk_size]
                            # LÆ°u page indices (0-based) cá»§a chunk nÃ y Ä‘á»ƒ gá»™p text sau
                            batch_page_indices = image_page_indices[i:i + chunk_size]
                            contract_chunks_images.append((batch, len(batch), batch_page_indices))
            elif ext in ("jpg", "jpeg", "png", "gif", "webp"):
                img_b64 = encode_image_to_base64(contract_path)
                contract_chunks_images.append(([img_b64], 1, [0]))

        n_contract_chunks = len(contract_chunks_images)
        has_invoice = bool(photo_paths)

        def _read_invoice():
            if not photo_paths:
                return {"success": False, "text": "", "error": "KhÃ´ng cÃ³ áº£nh"}
            any_photo = [p for p in photo_paths if os.path.exists(p)]
            if not any_photo:
                return {"success": False, "text": "", "error": "KhÃ´ng tÃ¬m tháº¥y file áº£nh"}
            return extract_invoice_text(any_photo)

        def _read_contract_chunk(images_batch, num_pages_batch):
            return extract_contract_text_from_images(images_batch, num_pages_batch, batch_size=5)

        t_tier1 = time.perf_counter()
        tier1_label = "Äang Ä‘á»c áº£nh há»£p Ä‘á»“ng & hÃ³a Ä‘Æ¡n (Tier 1)..."
        if contract_text_pages and not n_contract_chunks:
            tier1_label = "Há»£p Ä‘á»“ng cÃ³ sáºµn text â€” Ä‘ang Ä‘á»c hÃ³a Ä‘Æ¡n (Tier 1)..."
        elif contract_text_pages and n_contract_chunks:
            tier1_label = "Äang Ä‘á»c text + áº£nh há»£p Ä‘á»“ng & hÃ³a Ä‘Æ¡n (Tier 1)..."
        elif not n_contract_chunks:
            tier1_label = "Äang Ä‘á»c hÃ³a Ä‘Æ¡n (Tier 1)..."

        with _status(tier1_label) as status:
            invoice_result = None
            contract_chunk_results = [None] * n_contract_chunks

            ex = ThreadPoolExecutor(max_workers=6)
            fut_invoice = ex.submit(_read_invoice) if has_invoice else None
            fut_contracts = {
                ex.submit(_read_contract_chunk, imgs, np): idx
                for idx, (imgs, np, _) in enumerate(contract_chunks_images)
            }

            # Chá» invoice (timeout 200s)
            if fut_invoice is not None:
                try:
                    invoice_result = fut_invoice.result(timeout=200)
                except Exception as e:
                    invoice_result = {"success": False, "text": "", "error": f"Tier 1 invoice timeout/error: {e}"}

            # Chá» contract chunks (timeout tá»•ng 600s)
            try:
                for fut in as_completed(fut_contracts, timeout=600):
                    idx = fut_contracts[fut]
                    try:
                        contract_chunk_results[idx] = fut.result()
                    except Exception as e:
                        contract_chunk_results[idx] = {"success": False, "text": "", "error": f"Tier 1 chunk {idx + 1}: {e}"}
            except Exception:
                # timeout tá»•ng -> cÃ¡c chunk chÆ°a xong giá»¯ None -> xá»­ lÃ½ nhÆ° timeout bÃªn dÆ°á»›i
                pass

            # KhÃ´ng chá» thÃªm cÃ¡c future Ä‘ang cháº¡y (giá»¯ timeout cap nhÆ° báº£n cÅ©).
            ex.shutdown(wait=False)

            tier1_elapsed = time.perf_counter() - t_tier1
            _log(f"Tier 1 xong sau {tier1_elapsed:.1f}s "
                 f"(invoice={'cÃ³' if has_invoice else 'khÃ´ng'}, contract_chunks={n_contract_chunks}, "
                 f"text_pages={len(contract_text_pages)})")
            if status is not None and hasattr(status, "update"):
                try:
                    status.update(label=f"ÄÃ£ Ä‘á»c xong Tier 1 ({tier1_elapsed:.1f}s)")
                except Exception:
                    pass

        # Xá»­ lÃ½ káº¿t quáº£ invoice
        invoice_text = "(KhÃ´ng cÃ³ hÃ³a Ä‘Æ¡n)"
        if invoice_result and invoice_result.get("success") and invoice_result.get("text"):
            invoice_text = invoice_result["text"]
        elif invoice_result and not invoice_result.get("success") and photo_paths:
            # â”€â”€ RETRY 1 Láº¦N: Tier 1 Ä‘á»c hÃ³a Ä‘Æ¡n tháº¥t báº¡i (cold start API) â”€â”€
            _log(f"Tier 1 invoice tháº¥t báº¡i ({invoice_result.get('error', 'unknown')}) â€” retry...")
            any_photo = [p for p in photo_paths if os.path.exists(p)]
            if any_photo:
                with _status("Äang retry Ä‘á»c hÃ³a Ä‘Æ¡n (Tier 1 - láº§n 2)..."):
                    invoice_result = extract_invoice_text(any_photo)
                if invoice_result and invoice_result.get("success") and invoice_result.get("text"):
                    invoice_text = invoice_result["text"]
                    _log("Tier 1 invoice retry thÃ nh cÃ´ng")
                else:
                    return {
                        "success": False,
                        "response": "",
                        "error": f"Tier 1 (Ä‘á»c hÃ³a Ä‘Æ¡n) tháº¥t báº¡i sau retry: {invoice_result.get('error', 'unknown')}"
                    }
            else:
                return {
                    "success": False,
                    "response": "",
                    "error": f"Tier 1 (Ä‘á»c hÃ³a Ä‘Æ¡n) tháº¥t báº¡i: {invoice_result.get('error', 'unknown')}"
                }

        # Xá»­ lÃ½ káº¿t quáº£ contract â€” gá»™p text pages + image chunks theo Ä‘Ãºng thá»© tá»± trang
        contract_chunk_texts = []

        if contract_chunks_images:
            for idx, (imgs, np, batch_page_indices) in enumerate(contract_chunks_images):
                chunk_parts = []
                
                # ThÃªm text tá»« cÃ¡c trang cÃ³ text trong chunk nÃ y (trÆ°á»›c khi thÃªm text Kimi)
                for page_idx_0based in batch_page_indices:
                    page_num_1based = page_idx_0based + 1
                    if page_num_1based in contract_text_pages:
                        chunk_parts.append(f"\n--- Trang {page_num_1based} (text PDF) ---\n{contract_text_pages[page_num_1based]}")
                
                # ThÃªm káº¿t quáº£ Kimi Ä‘á»c áº£nh cho chunk nÃ y
                res = contract_chunk_results[idx] if idx < len(contract_chunk_results) else None
                if res and res.get("success") and res.get("text"):
                    chunk_parts.append(res["text"])
                elif res and not res.get("success"):
                    # â”€â”€ RETRY 1 Láº¦N: chunk tháº¥t báº¡i (cold start API) â”€â”€
                    _log(f"Tier 1 chunk {idx + 1} tháº¥t báº¡i ({res.get('error', 'unknown')}) â€” retry...")
                    with _status(f"Äang retry Ä‘á»c há»£p Ä‘á»“ng chunk {idx + 1}..."):
                        retry_res = _read_contract_chunk(imgs, np)
                    if retry_res and retry_res.get("success") and retry_res.get("text"):
                        chunk_parts.append(retry_res["text"])
                        _log(f"Tier 1 chunk {idx + 1} retry thÃ nh cÃ´ng")
                    else:
                        chunk_parts.append(f"[Chunk {idx + 1} trÃ­ch xuáº¥t tháº¥t báº¡i: {res.get('error', 'unknown')}")
                else:
                    # Timeout â€” retry 1 láº§n
                    _log(f"Tier 1 chunk {idx + 1} timeout â€” retry...")
                    with _status(f"Äang retry Ä‘á»c há»£p Ä‘á»“ng chunk {idx + 1}..."):
                        retry_res = _read_contract_chunk(imgs, np)
                    if retry_res and retry_res.get("success") and retry_res.get("text"):
                        chunk_parts.append(retry_res["text"])
                        _log(f"Tier 1 chunk {idx + 1} retry thÃ nh cÃ´ng")
                    else:
                        chunk_parts.append(f"[Chunk {idx + 1} khÃ´ng cÃ³ káº¿t quáº£ (timeout)]")
                
                contract_chunk_texts.append("\n".join(chunk_parts))
        elif not contract_text_pages and contract_path and os.path.exists(contract_path):
            contract_chunk_texts.append("(Há»£p Ä‘á»“ng trÃ­ch xuáº¥t tháº¥t báº¡i hoáº·c khÃ´ng thá»ƒ Ä‘á»c)")
        else:
            contract_chunk_texts.append("(KhÃ´ng cÃ³ há»£p Ä‘á»“ng Ä‘Ã­nh kÃ¨m)")

        # ============================================================
        # TIER 2 (Bá»Ž): Truyá»n tháº³ng text tá»« Tier 1 sang Tier 3
        # (NhÆ° v0.6 gá»‘c - GLM nháº­n raw text, Ä‘á»c trá»±c tiáº¿p -> giá»¯ accuracy)
        # ============================================================

        invoice_analysis = invoice_text
        contract_analyses = contract_chunk_texts

        # ============================================================
        # TIER 3 (MERGE): GLM PHÃ‚N TÃCH KHáº¤U TRá»ª -> XUáº¤T Báº¢NG CUá»I CÃ™NG
        # ============================================================

        contract_analyses_joined = "\n\n".join(contract_analyses)

        # Bá» giá»›i háº¡n text â€” gá»­i toÃ n bá»™ text há»£p Ä‘á»“ng cho GLM phÃ¢n tÃ­ch
        prompt = build_analysis_prompt(claim_data, invoice_analysis, contract_analyses_joined)

        system_msg = {
            "role": "system",
            "content": "Báº¡n lÃ  chuyÃªn gia kiá»ƒm toÃ¡n há»£p Ä‘á»“ng báº£o hiá»ƒm cao cáº¥p. LUÃ”N tráº£ lá»i báº±ng tiáº¿ng Viá»‡t. Nhiá»‡m vá»¥: Äá»ŒC TOÃ€N Bá»˜ text hÃ³a Ä‘Æ¡n (ghi nhá»› tá»«ng dÃ²ng, tá»«ng con sá»‘) -> Äá»ŒC TOÃ€N Bá»˜ text há»£p Ä‘á»“ng (má»i Ä‘iá»u khoáº£n, phá»¥ lá»¥c, Ä‘Ã­nh chÃ­nh) -> XÃ‚Y Dá»°NG 3 DANH SÃCH TRONG Äáº¦U: (A) Äiá»u khoáº£n loáº¡i trá»«, (B) KhÃ¡i niá»‡m/Ä‘á»‹nh nghÄ©a/danh má»¥c, (C) Háº¡n má»©c chi tráº£ -> MAP Tá»ªNG Má»¤C trong hÃ³a Ä‘Æ¡n vÃ o 3 danh sÃ¡ch theo quy trÃ¬nh 2(A) -> 2(B) -> 2(C). Äáº¶C BIá»†T: khoáº£n trong hÃ³a Ä‘Æ¡n cÃ³ thá»ƒ KHÃ”NG TRÃ™NG TÃŠN trá»±c tiáº¿p vá»›i Ä‘iá»u khoáº£n loáº¡i trá»«, nhÆ°ng cÃ³ THUá»˜C má»™t khÃ¡i niá»‡m/Ä‘á»‹nh nghÄ©a bá»‹ loáº¡i trá»« (kháº¥u trá»« giÃ¡n tiáº¿p). Pháº£i Káº¾T Ná»I thÃ´ng tin giá»¯a cÃ¡c trang. QUAN TRá»ŒNG NHáº¤T - LUáº¬T Cá»¨NG: (1) KHÃ”NG ÄÆ¯á»¢C Tá»° PHÃ‚N LOáº I Ä‘á»‘i tÆ°á»£ng (thuá»‘c/thá»±c pháº©m chá»©c nÄƒng/thiáº¿t bá»‹ y táº¿...) tá»« kiáº¿n thá»©c ngoÃ i há»£p Ä‘á»“ng. Chá»‰ Ä‘Æ°á»£c kháº¥u trá»« khi há»£p Ä‘á»“ng THá»°C Sá»° ghi rÃµ háº¡ng má»¥c Ä‘Ã³ bá»‹ loáº¡i trá»« (trÃ¹ng tÃªn trá»±c tiáº¿p hoáº·c thuá»™c nhÃ³m Ä‘Æ°á»£c Ä‘á»‹nh nghÄ©a trong há»£p Ä‘á»“ng). (2) KHÃ”NG ÄÆ¯á»¢C Bá»” SUNG lÃ­ do ngoÃ i Ä‘iá»u khoáº£n há»£p Ä‘á»“ng â€” náº¿u há»£p Ä‘á»“ng ghi loáº¡i trá»« 'Sanlein' thÃ¬ lÃ­ do lÃ  'há»£p Ä‘á»“ng ghi rÃµ loáº¡i trá»« Sanlein', KHÃ”NG ÄÆ¯á»¢C thÃªm 'vÃ¬ lÃ  thá»±c pháº©m chá»©c nÄƒng' hay báº¥t ká»³ lÃ­ do nÃ o khÃ¡c. (3) Má»–I Má»¤C Äá»˜C Láº¬P 100% â€” KHÃ”NG KÃ‰O THEO: náº¿u há»£p Ä‘á»“ng chá»‰ ghi 'Sanlein' thÃ¬ CHá»ˆ kháº¥u trá»« Sanlein, KHÃ”NG KHáº¤U TRá»ª Liposic hay má»¥c nÃ o khÃ¡c khÃ´ng Ä‘Æ°á»£c há»£p Ä‘á»“ng nháº¯c Ä‘áº¿n. (4) KHÃ”NG tráº£ lá»i 'khÃ´ng cÃ³ kháº¥u trá»«' náº¿u chÆ°a kiá»ƒm tra ká»¹ táº¥t cáº£ Ä‘iá»u khoáº£n há»£p Ä‘á»“ng. Má»i káº¿t luáº­n pháº£i cÃ³ Ä‘iá»u khoáº£n há»£p Ä‘á»“ng lÃ m cÄƒn cá»©. CHÃNH XÃC TUYá»†T Äá»I vá» con sá»‘ - khÃ´ng lÃ m trÃ²n, khÃ´ng Æ°á»›c lÆ°á»£ng. Äá»ŒC NGÃ€Y CHÃNH XÃC: hÃ³a Ä‘Æ¡n Viá»‡t Nam dÃ¹ng Ä‘á»‹nh dáº¡ng dd/mm/yyyy, khÃ´ng Ä‘Æ°á»£c hoÃ¡n Ä‘á»•i ngÃ y/thÃ¡ng hay sá»­a nÄƒm. Output cuá»‘i cÃ¹ng lÃ  Má»˜T Báº¢NG DUY NHáº¤T theo máº«u, khÃ´ng kÃ¨m lá»i giáº£i thÃ­ch bÃªn ngoÃ i."
        }
        user_msg = {"role": "user", "content": prompt}
        messages = [system_msg, user_msg]

        merge_result_box = {"result": None}

        def run_merge():
            merge_result_box["result"] = call_analysis_model(messages, max_tokens=16000, timeout=600)

        t_tier3 = time.perf_counter()
        with _status("Äang tá»•ng há»£p & xuáº¥t báº£ng kháº¥u trá»« (Tier 3)...") as status:
            t_merge = threading.Thread(target=run_merge)
            t_merge.start()
            t_merge.join(timeout=620)

            tier3_elapsed = time.perf_counter() - t_tier3
            _log(f"Tier 3 xong sau {tier3_elapsed:.1f}s")
            if status is not None and hasattr(status, "update"):
                try:
                    status.update(label=f"ÄÃ£ tá»•ng há»£p xong Tier 3 ({tier3_elapsed:.1f}s)")
                except Exception:
                    pass

        analysis_result = merge_result_box["result"]

        # â”€â”€ RETRY 1 Láº¦N náº¿u Tier 3 tráº£ vá» rá»—ng/tháº¥t báº¡i (cold start API) â”€â”€
        if not analysis_result or not analysis_result.get("success") or not analysis_result.get("text", "").strip():
            _log("Tier 3 láº§n 1 rá»—ng/tháº¥t báº¡i â€” retry láº§n 2...")
            retry_box = {"result": None}
            def run_merge_retry():
                retry_box["result"] = call_analysis_model(messages, max_tokens=16000, timeout=600)
            with _status("Äang retry tá»•ng há»£p (Tier 3 - láº§n 2)...") as status2:
                t_retry = threading.Thread(target=run_merge_retry)
                t_retry.start()
                t_retry.join(timeout=620)
                if status2 is not None and hasattr(status2, "update"):
                    try:
                        status2.update(label=f"Retry Tier 3 xong")
                    except Exception:
                        pass
            analysis_result = retry_box["result"]
            if analysis_result and analysis_result.get("success") and analysis_result.get("text", "").strip():
                _log("Tier 3 retry thÃ nh cÃ´ng")
            else:
                _log("Tier 3 retry váº«n tháº¥t báº¡i")

        _log(f"Tá»•ng thá»i gian analyze_deduction: {time.perf_counter() - t_total:.1f}s")

        if analysis_result and analysis_result.get("success") and analysis_result.get("text"):
            return {"success": True, "response": analysis_result["text"], "error": ""}
        elif analysis_result and not analysis_result.get("success"):
            return {"success": False, "response": "", "error": f"Tier 3 (merge) tháº¥t báº¡i: {analysis_result['error']}"}
        else:
            return {"success": False, "response": "", "error": "Tier 3 (merge) timeout hoáº·c khÃ´ng cÃ³ káº¿t quáº£"}

    except Exception as e:
        return {"success": False, "response": "", "error": str(e)}


# ============================================================
# LÆ¯U Káº¾T QUáº¢
# ============================================================

def save_reply(claim_data, ai_response, photo_names, contract_name):
    """LÆ°u cÃ¢u tráº£ lá»i AI vÃ o thÆ° má»¥c tráº£ lá»i."""
    os.makedirs(REPLY_DIR, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = re.sub(r'[^\w]', '_', claim_data.get("customer_name", "khach_hang"))
    product_id = claim_data.get("product", {}).get("id", "unknown")

    filename = f"reply_{safe_name}_{product_id}_{ts}.md"
    filepath = os.path.join(REPLY_DIR, filename)

    content = f"""# PhÃ¢n tÃ­ch khoáº£n kháº¥u trá»« bá»“i thÆ°á»ng

**KhÃ¡ch hÃ ng:** {claim_data.get('customer_name', 'KhÃ´ng rÃµ')}
**Sáº£n pháº©m:** {claim_data.get('product', {}).get('name', 'KhÃ´ng rÃµ')}
**Thá»i gian:** {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}

## áº¢nh thiá»‡t háº¡i Ä‘Ã­nh kÃ¨m:
"""
    for name in photo_names:
        content += f"- {name}\n"

    content += f"""
## Há»£p Ä‘á»“ng Ä‘Ã­nh kÃ¨m:
- {contract_name or 'KhÃ´ng cÃ³'}

## PhÃ¢n tÃ­ch AI:
{ai_response}
"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return filepath
