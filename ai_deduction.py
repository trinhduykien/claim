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
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "https://api.ollama.com/v1")
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
        "Ban la chuyen gia doc hoa don y te. Hay doc cac hinh anh hoa don ben duoi "
        "va xuat ket qua theo dinh dang sau:\n\n"
        "1. THONG TIN HOA DON:\n"
        "   - So hoa don\n"
        "   - Ngay phat hanh\n"
        "   - Don vi ban thuoc / phuong thuc thanh toan\n"
        "   - Benh nhan / Ma the BHYT (neu co)\n\n"
        "2. CHI TIET HANG HOA:\n"
        "   Tien hanh doc TUNG DONG hang hoa trong hoa don.\n"
        "   Voi moi dong, xuat:\n"
        "   - STT\n"
        "   - TEN HANG (doc chinh xac ten thuoc / vat tu y te / dich vu)\n"
        "   - DON VI TINH\n"
        "   - SO LUONG\n"
        "   - DON GIA\n"
        "   - THANH TIEN\n\n"
        "3. TONG CONG: Tong tien toan hoa don\n\n"
        "LUU Y QUAN TRONG:\n"
        "- Doc CHINH XAC ten thuoc, khong duoc suy doan hay viet lai.\n"
        "- Neu khong ro ten thuoc, ghi '[KHONG RO]'.\n"
        "- Phan loai moi dong vao 1 trong 4 nhom:\n"
        "  + THUOC: thuoc chua benh (ten thuoc + ham luong + dong goi)\n"
        "  + VAT TU Y TE: bang tiem, dong ruou, gang tay, ga xo, tam y te...\n"
        "  + DICH VU: kham benh, xet nghiem, tien phong, tien cong...\n"
        "  + KHAC: khong thuoc 3 nhom tren\n\n"
        "Xuat ket qua dang van ban, ro rang, co cau truc."
    )


def build_contract_chunk_prompt(page_start, page_end):
    """Build prompt for Kimi to read contract pages."""
    return (
        f"Ban la chuyen gia phan tich hop dong bao hiem. Hay doc cac trang hop dong "
        f"tu trang {page_start} den trang {page_end} trong hinh anh ben duoi.\n\n"
        "Hay xuat toan bo noi dung van ban cua cac trang nay, bao gom:\n\n"
        "1. Tieu de muc, dieu khoan, so dieu\n"
        "2. Noi dung chi tiet cua moi dieu khoan\n"
        "3. Cac bang, danh muc, dinh nghia (neu co)\n"
        "4. Cac muc loai tru, gioi han tra tien, dieu kien\n\n"
        "LUU Y:\n"
        "- Doc nguyen van, khong tom tat hay bo qua.\n"
        "- Giu nguyen so dieu, so trang tham chieu.\n"
        "- Neu co bang, xuat theo dinh dang bang.\n"
        "- Neu khong doc duoc phan nao, ghi '[KHONG DOC DUOC]'.\n\n"
        "Xuat ket qua dang van ban day du."
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
    claim_info = json.dumps(claim_data, ensure_ascii=False, indent=2) if claim_data else "Khong co thong tin yeu cau"

    return (
        "Ban la chuyen gia thanh tra bao hiem y te. Ban nhan duoc noi dung hoa don "
        "va thong tin yeu cau tra tien. Hay phan tich va phan loai tung mat hang.\n\n"
        "=== NOI DUNG HOA DON ===\n"
        f"{invoice_text}\n\n"
        "=== THONG TIN YEU CAU TRA TIEN ===\n"
        f"{claim_info}\n\n"
        "=== NHIEM VU ===\n"
        "1. Phan loai moi mat hang vao 1 trong 4 nhom:\n"
        "   - THUOC: thuoc chua benh (can ten thuoc + ham luong + dong goi)\n"
        "   - VAT TU Y TE: bang tiem, dong ruou, gang tay, tam y te, ga xo...\n"
        "   - DICH VU: kham benh, xet nghiem, tien phong, tien cong...\n"
        "   - KHAC: khong thuoc 3 nhom tren\n\n"
        "2. Voi moi mat hang, xuat:\n"
        "   - STT\n"
        "   - TEN HANG\n"
        "   - PHAN LOAI (THUOC / VAT TU Y TE / DICH VU / KHAC)\n"
        "   - SO LUONG\n"
        "   - DON GIA\n"
        "   - THANH TIEN\n"
        "   - GHI CHU (neu co van de ve ten hang, so luong, don gia)\n\n"
        "3. Kiem tra tong tien hop don khong.\n\n"
        "LUU Y PHAN LOAI:\n"
        "- THUOC khac THIET BI Y TE: may hut dam, may do huyet ap la thiet bi, khong phai thuoc.\n"
        "- THIET BI Y TE khac VAT TU Y TE: thiet bi co the tai su dung, vat tu y te dung 1 lan.\n"
        "- Neu ten hang ghi 'thuoc' nhung thuc chat la vat tu y te, phan loai dung.\n\n"
        "Xuat ket qua dang bang, ro rang."
    )


def build_contract_analysis_prompt(contract_chunk_text, page_start, page_end):
    """Build prompt for GLM to analyze a contract chunk."""
    return (
        f"Ban la chuyen gia phan tich hop dong bao hiem y te. "
        f"Hay phan tich noi dung hop dong tu trang {page_start} den trang {page_end}.\n\n"
        f"=== NOI DUNG HOP DONG (TRANG {page_start}-{page_end}) ===\n"
        f"{contract_chunk_text}\n\n"
        "=== NHIEM VU ===\n"
        "Hay trich xuat 3 loai thong tin sau:\n\n"
        "A. MUC LOAI TRU (EXCLUSIONS):\n"
        "   - Cac dieu kien, benh, tinh trang KHONG DUOC tra tien\n"
        "   - Cac han che bao hiem\n"
        "   - Cac dieu kien bat buoc khong duoc tra\n\n"
        "B. DINH NGHIA (DEFINITIONS):\n"
        "   - Dinh nghia cac thuat ngu y te, bao hiem\n"
        "   - Dinh nghia 'thuoc', 'vat tu y te', 'dich vu y te'\n"
        "   - Dinh nghia 'benh co san', 'benh man tinh', 'cap cuu'...\n\n"
        "C. GIOI HAN TRA TIEN (LIMITS):\n"
        "   - Muc tra toi da cho tung loai chi phi\n"
        "   - Ty le tra (80%, 90%, 100%...)\n"
        "   - Han muc tra cho tung loai thuoc / dich vu\n"
        "   - Mien thuong (deductible)\n\n"
        "Xuat ket qua theo cau truc:\n"
        "A. MUC LOAI TRU:\n  ...\n"
        "B. DINH NGHIA:\n  ...\n"
        "C. GIOI HAN TRA TIEN:\n  ...\n\n"
        "Neu khong co thong tin nao, ghi 'Khong co' cho phan do."
    )


def glm_analyze_invoice(invoice_text, claim_data):
    """GLM analyzes invoice. Returns analysis text."""
    prompt = build_invoice_analysis_prompt(invoice_text, claim_data)
    messages = [
        {"role": "system", "content": "Ban la chuyen gia thanh tra bao hiem y te Viet Nam."},
        {"role": "user", "content": prompt},
    ]
    return call_analysis_model(messages, max_tokens=4000, timeout=120)


def glm_analyze_contract_chunk(chunk_text, page_start, page_end):
    """GLM analyzes a contract chunk. Returns analysis text."""
    prompt = build_contract_analysis_prompt(chunk_text, page_start, page_end)
    messages = [
        {"role": "system", "content": "Ban la chuyen gia phan tich hop dong bao hiem y te Viet Nam."},
        {"role": "user", "content": prompt},
    ]
    return call_analysis_model(messages, max_tokens=4000, timeout=120)


# ---------------------------------------------------------------------------
# TIER 3 - MERGE: GLM MANAGER CROSS-REFERENCES
# ---------------------------------------------------------------------------

def build_merge_prompt(claim_data, invoice_analysis, contract_analyses):
    """Build the final merge prompt for the GLM manager."""
    claim_info = json.dumps(claim_data, ensure_ascii=False, indent=2) if claim_data else "Khong co"

    contract_text = "\n\n".join(contract_analyses) if contract_analyses else "Khong co phan tich hop dong"

    return (
        "Ban la QUAN LY CAP CAO cua bo phan thanh tra bao hiem y te. "
        "Cac truong phong da phan tich hoa don va hop dong. "
        "Bay gio ban tong hop tat ca, tham chieu cheo va ra quyet dinh tra tien cuoi cung.\n\n"
        "=== THONG TIN YEU CAU TRA TIEN ===\n"
        f"{claim_info}\n\n"
        "=== BAO CAO PHAN TICH HOA DON ===\n"
        f"{invoice_analysis}\n\n"
        "=== CAC BAO CAO PHAN TICH HOP DONG ===\n"
        f"{contract_text}\n\n"
        "=== NHIEM VU CUOI CUNG ===\n"
        "1. THAM CHIEU CHEO: So sanh tung mat hang trong hoa don voi:\n"
        "   - Muc loai tru trong hop dong -> neu trung -> KHONG TRA\n"
        "   - Gioi han tra tien trong hop dong -> neu vuot -> GIOI HAN\n"
        "   - Dinh nghia trong hop dong -> phan loai dung/sai\n\n"
        "2. KET QA PHAN LOAI XAC NHAN:\n"
        "   - THUOC: thuoc chua benh (ten + ham luong + dong goi)\n"
        "   - THIET BI Y TE: may hut dam, may do huyet ap... (KHONG phai thuoc)\n"
        "   - VAT TU Y TE: bang tiem, dong ruou, gang tay... (KHONG phai thiet bi)\n"
        "   - DICH VU: kham benh, xet nghiem, tien cong...\n"
        "   - KHAC: khong thuoc cac nhom tren\n\n"
        "3. DEDUCTION GIÁN TIẾP (INDIRECT DEDUCTION):\n"
        "   - Neu 1 mat hang THUOC bi loai tru, cac vat tu y te lien quan "
        "     (bang tiem, dong ruou...) cung co the bi loai tru.\n"
        "   - Neu dich vu bi loai tru, cac thuoc/vat tu phuc vu dich vu do "
        "     cung xem xet loai tru.\n"
        "   - Ghi ro ly do deduction gian tiep.\n\n"
        "4. BANG KET QA TRA TIEN:\n"
        "   Xuat bang voi cac cot:\n"
        "   | STT | TEN HANG | PHAN LOAI | SO LUONG | DON GIA | THANH TIEN | "
        "   " + "TY LE TRA | TIEN TRA | LY DO DEDUCTION | GHI CHU |\n\n"
        "   - TY LE TRA: 0% (loai tru) / 50% / 80% / 100% ...\n"
        "   - TIEN TRA = THANH TIEN x TY LE TRA\n"
        "   - LY DO DEDUCTION: tom tat ly do (muc loai tru, vuot gioi han, "
        "     sai phan loai, deduction gian tiep...)\n\n"
        "5. TONG KET:\n"
        "   - TONG TIEN HOA DON\n"
        "   - TONG TIEN TRA\n"
        "   - TONG TIEN DEDUCTION\n"
        "   - TY LE TRA TOAN BO\n\n"
        "6. KIEN NGHI:\n"
        "   - Neu can bo sung giay to, ghi ro\n"
        "   - Neu co van de can lam ro, ghi ro\n\n"
        "Hay xuat bao cao day du, ro rang, co cau truc tot."
    )


def glm_merge_analysis(claim_data, invoice_analysis, contract_analyses):
    """GLM manager merges all analyses. Returns final report text."""
    prompt = build_merge_prompt(claim_data, invoice_analysis, contract_analyses)
    messages = [
        {
            "role": "system",
            "content": (
                "Ban la quan ly cap cao bo phan thanh tra bao hiem y te Viet Nam. "
                "Ban tong hop cac bao cao va ra quyet dinh tra tien cuoi cung."
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
                "error": "Khong co API key. Vui long cau hinh API_KEY.",
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
                errors_t1[name] = f"Timeout khi doc {name}"

        # --- Collect Tier 1 results ---
        invoice_text = results_t1.get("invoice", "")
        if "invoice" in errors_t1 and not invoice_text:
            invoice_text = f"[LOI DOC HOA DON: {errors_t1['invoice']}]"

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
                contract_texts.append((f"[LOI DOC HOP DONG CHUNK {idx}: {errors_t1[key]}]", 0, 0))

        # ===================================================================
        # TIER 2 - REDUCE: GLM ANALYZES EACH CHUNK IN PARALLEL
        # ===================================================================

        invoice_analysis = ""
        contract_analyses = []

        threads_t2 = []
        results_t2 = {}
        errors_t2 = {}

        # --- Invoice analysis thread ---
        if invoice_text and not invoice_text.startswith("[LOI"):
            def _analyze_invoice():
                try:
                    results_t2["invoice"] = glm_analyze_invoice(invoice_text, claim_data)
                except Exception as e:
                    errors_t2["invoice"] = str(e)

            t_ia = threading.Thread(target=_analyze_invoice, daemon=True)
            threads_t2.append(("invoice", t_ia))
        else:
            results_t2["invoice"] = "[KHONG CO HOA DON DE PHAN TICH]"

        # --- Contract analysis threads ---
        for idx, (ctext, ps, pe) in enumerate(contract_texts):
            if ctext and not ctext.startswith("[LOI"):
                def _analyze_contract(_text=ctext, _ps=ps, _pe=pe, _idx=idx):
                    try:
                        results_t2[f"contract_{_idx}"] = glm_analyze_contract_chunk(_text, _ps, _pe)
                    except Exception as e:
                        errors_t2[f"contract_{_idx}"] = str(e)

                t = threading.Thread(target=_analyze_contract, daemon=True)
                threads_t2.append((f"contract_{idx}", t))
            else:
                results_t2[f"contract_{idx}"] = f"[KHONG CO NOI DUNG HOP DONG CHUNK {idx}]"

        # --- Start all threads ---
        for name, t in threads_t2:
            t.start()

        # --- Join with 180s timeout each ---
        for name, t in threads_t2:
            t.join(timeout=180)
            if t.is_alive():
                errors_t2[name] = f"Timeout khi phan tich {name}"

        # --- Collect Tier 2 results ---
        invoice_analysis = results_t2.get("invoice", "")
        if "invoice" in errors_t2 and not invoice_analysis:
            invoice_analysis = f"[LOI PHAN TICH HOA DON: {errors_t2['invoice']}]"

        for idx in range(len(contract_texts)):
            key = f"contract_{idx}"
            if key in results_t2:
                contract_analyses.append(results_t2[key])
            elif key in errors_t2:
                contract_analyses.append(f"[LOI PHAN TICH HOP DONG CHUNK {idx}: {errors_t2[key]}]")
            else:
                contract_analyses.append("")

        # ===================================================================
        # TIER 3 - MERGE: GLM MANAGER
        # ===================================================================

        if not invoice_analysis and not any(contract_analyses):
            return {
                "success": False,
                "response": "",
                "error": "Khong co du lieu de tong hop. Thu phan tich that bai o tat ca cac tang.",
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
    lines.append(f"# Ket Qua Phan Tich Deduction - {claim_id}")
    lines.append("")
    lines.append(f"**Thoi gian:** {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("## Thong Tin Yeu Cau")
    lines.append("")
    if isinstance(claim_data, dict):
        for k, v in claim_data.items():
            lines.append(f"- **{k}:** {v}")
    else:
        lines.append(str(claim_data))
    lines.append("")
    lines.append("## File Dinh Kem")
    lines.append("")
    lines.append(f"**Hop dong:** {contract_name}")
    lines.append("")
    if photo_names:
        lines.append("**Hoa don / Anh:**")
        for name in photo_names:
            lines.append(f"- {name}")
    else:
        lines.append("**Hoa don / Anh:** Khong co")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Ket Qua Phan Tich AI")
    lines.append("")
    lines.append(ai_response)
    lines.append("")
    lines.append("---")
    lines.append(f"*File duoc tao tu dong boi AI Deduction Pipeline*")

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