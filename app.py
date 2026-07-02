# -*- coding: utf-8 -*-

"""

Insurance - ÄÃ¡nh giÃ¡ tiáº¿p nháº­n bá»“i thÆ°á»ng V.0.6

- Bot chat tá»± nhiÃªn nhÆ° trá»£ lÃ½ áº£o

- Chá»‰ khi khÃ¡ch nháº¯c sá»± cá»‘ báº£o hiá»ƒm â†’ há»i cÃ³ muá»‘n Ä‘Ã¡nh giÃ¡ tiáº¿p nháº­n bá»“i thÆ°á»ng

- KhÃ¡ch Ä‘á»“ng Ã½ â†’ má»›i vÃ o luá»“ng Ä‘Ã¡nh giÃ¡

"""



import json

import os

import re

import unicodedata

from datetime import datetime

from collections import OrderedDict



import streamlit as st



try:

    import aiml

    AIML_AVAILABLE = True

except ImportError:

    AIML_AVAILABLE = False



from insurance_products import PRODUCTS, get_product_by_id, get_product_by_keyword
from offices import get_offices_by_city, get_all_cities

try:
    import importlib
    import ai_deduction
    importlib.reload(ai_deduction)
    from ai_deduction import analyze_deduction, save_reply, has_api_key as ai_has_key
    AI_DEDUCTION_AVAILABLE = True
except ImportError:
    AI_DEDUCTION_AVAILABLE = False



st.set_page_config(

    page_title="Trá»£ lÃ½ áº£o V.0.6",

    page_icon="",

    layout="centered",

    initial_sidebar_state="expanded",

)



st.markdown("""

<style>

.stApp > header { background-color: #002B70; }

.stApp { background: linear-gradient(180deg, #f5f5f5 0%, #ffffff 100%); }

section[data-testid="stSidebar"] { background-color: #002B70 !important; }

section[data-testid="stSidebar"] * { color: #ffffff !important; }

section[data-testid="stSidebar"] .stButton > button {

    background-color: #f58220; color: white !important;

    border: none; border-radius: 5px; font-weight: 600;

}

section[data-testid="stSidebar"] .stButton > button:hover { background-color: #FAB68D; }

section[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.2); }

section[data-testid="stSidebar"] code { color: #FAB68D !important; background-color: rgba(255,255,255,0.1); }

section[data-testid="stSidebar"] .stMetric-value { color: #FAB68D !important; }

.-header {

    background-color: #002B70; color: white;

    padding: 15px 25px; border-radius: 0 0 10px 10px;

    margin-bottom: 20px; text-align: center;

    display: flex; align-items: center; justify-content: center; gap: 15px;

}

.-header img { height: 50px; }

.-header h1 { color: white; font-size: 22px; margin: 0; font-weight: 700; }

.-header p { color: #FAB68D; font-size: 13px; margin: 5px 0 0 0; }

.stButton > button { background-color: #002B70; color: white; border: none; border-radius: 5px; font-weight: 600; }

.stButton > button:hover { background-color: #003a8c; }

a { color: #f58220; }

.stApp { font-family: 'Open Sans', 'Roboto', Arial, sans-serif; }

.stChatInput > div > div > textarea { border: 2px solid #002B70 !important; border-radius: 8px !important; }

</style>

""", unsafe_allow_html=True)



# ============================================================

# UTILITY FUNCTIONS

# ============================================================



def normalize_text(text):

    """Bá» dáº¥u tiáº¿ng Viá»‡t, lowercase, strip."""

    if not text: return ""

    text = text.strip().lower()

    text = unicodedata.normalize('NFD', text)

    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')

    return text



def normalize_aiml(text):

    """Bá» dáº¥u tiáº¿ng Viá»‡t, UPPERCASE, strip â€” cho AIML pattern matching."""

    if not text: return ""

    text = unicodedata.normalize('NFD', text)

    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')

    return text.upper().strip()



YES_WORDS = ["co", "duoc", "yes", "dung", "roi", "phai", "chinhxac", "dungroi", "chacchan", "ung", "yeah"]

NO_WORDS = ["khong", "no", "nope", "khong co", "chua co", "khong phai"]



def is_yes(text):

    t = normalize_text(text)

    return any(w == t or w in t for w in YES_WORDS)



def is_no(text):

    t = normalize_text(text)

    # "chÆ°a" riÃªng â†’ khÃ´ng pháº£i "khÃ´ng" trong ngá»¯ cáº£nh claim

    if t == "chua" or t.startswith("chua "): return False

    return any(w == t or w in t for w in NO_WORDS)



def match_answer(user_answer, expected):

    ua = normalize_text(user_answer)

    ex = normalize_text(expected)

    if ua == ex: return True

    if ex in ["co", "yes"]: return is_yes(user_answer)

    if ex in ["khong", "no"]: return is_no(user_answer)

    return ex in ua



# Tá»« khÃ³a phÃ¡t hiá»‡n sá»± cá»‘ báº£o hiá»ƒm

INCIDENT_KEYWORDS = [

    "chay", "no", "tai nan", "bao hiem", "nha", "xe", "bao",

    "lu", "trom", "cuop", "dong dat", "giong", "ngap",

    "suc khoe", "om", "dau", "vien", "kinh doanh", "gian doan",

    "combo", "360", "phu gia", "family", "tnds", "trach nhiem",

    "thuong tich", "tu vong", "thiet hai",

    "dot nhap", "bao lua", "loc", "set", "con nguoi", "than the",

    "ket hop", "cong nhan", "nha may", "ung thu", "hiem ngheo",

    "bi thuong", "bi om", "nhap vien", "cap cuu", "dot quy",

    "nhoi mau", "suy than", "beo ben", "chay nha", "ngap nuoc",

    "bi cuop", "mat cua", "vo kin", "thiet hai nha",

    "kiem tra boi thuong", "danh gia boi thuong",

    "danh gia dieu kien", "tiep nhan boi thuong",

    "yeu cau boi thuong", "ho so boi thuong",

    "boi thuong bao hiem", "boi thuong nha",

    "boi thuong xe", "boi thuong suc khoe",

    "boi thuong tai nan", "boi thuong du lich",

    "boi thuong ung thu", "boi thuong hiem ngheo",

    "boi thuong lao dong", "boi thuong hoc sinh",

    "boi thuong dien", "boi thuong phe gia",

]



# Tá»« khÃ³a chá»‰ khÃ¡ch muá»‘n Ä‘Ã¡nh giÃ¡ bá»“i thÆ°á»ng trá»±c tiáº¿p

CLAIM_REQUEST_KEYWORDS = [

    "danh gia dieu kien", "danh gia boi thuong", "tiep nhan boi thuong",

    "yeu cau boi thuong", "dang ky boi thuong", "ho so boi thuong",

    "danh gia dieu kien tiep nhan", "danh gia dieu kien boi thuong",

    "kiem tra boi thuong", "xu ly boi thuong",

]



GREETING_WORDS = [

    "xin chao", "chao", "hello", "hi", "chao ban", "chao anh", "chao chi",

    "chao em", "xin chao ban", "xin chao anh", "xin chao chi", "xin chao em",

    "hey", "halo", "toloi", "toi day", "chao you",

]



def is_greeting(text):

    """Kiá»ƒm tra xem input cÃ³ pháº£i lÃ  cÃ¢u chÃ o hay khÃ´ng."""

    t = normalize_text(text)

    t_lower = t.lower().strip()

    for gw in GREETING_WORDS:

        if t_lower == gw or t_lower.startswith(gw + " ") or gw + " " in t_lower:

            has_incident = any(normalize_text(k) in t_lower for k in INCIDENT_KEYWORDS)

            if not has_incident:

                return True

    return False



def has_incident(text):

    """Kiá»ƒm tra xem input cÃ³ nháº¯c Ä‘áº¿n sá»± cá»‘ báº£o hiá»ƒm khÃ´ng."""

    t = normalize_text(text)

    return any(normalize_text(k) in t for k in INCIDENT_KEYWORDS)



def has_claim_request(text):

    """Kiá»ƒm tra xem user cÃ³ trá»±c tiáº¿p yÃªu cáº§u Ä‘Ã¡nh giÃ¡ bá»“i thÆ°á»ng khÃ´ng."""

    t = normalize_text(text)

    return any(normalize_text(k) in t for k in CLAIM_REQUEST_KEYWORDS)



def extract_name(text):

    """TrÃ­ch xuáº¥t tÃªn khÃ¡ch hÃ ng tá»« input."""

    text_clean = text.strip()

    if is_greeting(text_clean):

        return ""

    # "tÃ´i tÃªn lÃ  X", "mÃ¬nh tÃªn lÃ  X", "em tÃªn lÃ  X"...

    m = re.search(r'(?:t[oÃ´]i|m[iÃ¬]nh|em|anh|ch[iá»‹])\s+t[eÃª]n\s+(?:l[aÃ ]\s+)?([A-Za-zÃ€-á»¹]+(?:\s+[A-Za-zÃ€-á»¹]+){0,3})', text, re.IGNORECASE)

    if m: return m.group(1).strip()

    # "tÃªn tÃ´i lÃ  X", "tÃªn em lÃ  X"...

    m = re.search(r't[eÃª]n\s+(?:t[oÃ´]i|m[iÃ¬]nh|em|anh|ch[iá»‹])\s+(?:l[aÃ ]\s+)?([A-Za-zÃ€-á»¹]+(?:\s+[A-Za-zÃ€-á»¹]+){0,3})', text, re.IGNORECASE)

    if m: return m.group(1).strip()

    # "tÃªn lÃ  X"

    m = re.search(r't[eÃª]n\s+(?:l[aÃ ]\s+)?([A-Za-zÃ€-á»¹]+(?:\s+[A-Za-zÃ€-á»¹]+){0,3})', text, re.IGNORECASE)

    if m: return m.group(1).strip()

    # "tÃ´i lÃ  X", "mÃ¬nh lÃ  X", "em lÃ  X"...

    m = re.search(r'(?:t[oÃ´]i|m[iÃ¬]nh|em)\s+l[aÃ ]\s+([A-Za-zÃ€-á»¹]+(?:\s+[A-Za-zÃ€-á»¹]+){0,3})', text, re.IGNORECASE)

    if m: return m.group(1).strip()

    # Náº¿u input ngáº¯n (1-4 tá»«), khÃ´ng chá»©a sá»± cá»‘, khÃ´ng pháº£i cÃ¢u há»i â†’ cÃ³ thá»ƒ lÃ  tÃªn

    words = text_clean.split()

    text_norm = normalize_text(text_clean)

    has_inc = any(normalize_text(k) in text_norm for k in INCIDENT_KEYWORDS)

    # Kiá»ƒm tra cÃ³ pháº£i cÃ¢u há»i khÃ´ng (cÃ³ dáº¥u ?)

    is_question = '?' in text_clean

    if not has_inc and not is_question and 1 <= len(words) <= 4: return text_clean

    return ""



PRODUCT_KEYWORDS = {

    "combo360_o_to": ["combo 360", "combo360", "360 o to", "nha gia dinh o to", "bao ve nha gia dinh o to", "o to"],

    "combo360_xe_may": ["combo 360 xe may", "combo360 xe may", "360 xe may", "nha gia dinh xe may", "bao ve nha gia dinh xe may", "xe may"],

    "phu_gia": ["phu gia", "chay no", "nha o", "dong dat", "chay no toan dien"],

    "family_care": ["family care", "familycare", "suc khoe", "kham chua benh", "y te", "noi tru", "ngoai tru", "vien phi", "omet", "om dau"],

    "tnds_moto": ["tnds", "trach nhiem dan su", "mo to", "xe gan may", "lai xe", "nguoi ngoi tren xe"],

    "gian_doan_kd": ["gian doan", "kinh doanh", "loi nhuan", "doanh thu", "gian doan kinh doanh"],

    "ket_hop_con_nguoi": ["ket hop con nguoi", "than the", "bao hiem than the", "con nguoi", "tai nan con nguoi", "cong nhan", "doanh nghiep", "nha may", "om dau benh tat", "tu vong", "thuong tich", "nam vien", "phau thuat"],

    "ung_thu": ["ung thu", "benh ung thu", "cancer"],

    "hiem_ngheo": ["hiem ngheo", "benh hiem ngheo", "nhoi mau", "dot quy", "suy than", "parkinson"],

    "tai_nan_2424": ["tai nan 24", "24/24", "tai nan con nguoi 24", "tai nan lao dong"],

    "tai_nan_cao": ["tai nan con nguoi muc trach nhiem cao", "trach nhiem cao", "muc trach nhiem cao"],

    "tai_nan_nguoi_su_dung_dien": ["tai nan nguoi su dung dien", "nguoi su dung dien", "tai nan dien", "bao hiem dien", "dong dien", "su dung dien"],

    "boi_thuong_nguoi_lao_dong": ["boi thuong nguoi lao dong", "nguoi lao dong", "tai nan lao dong", "benh nghe nghiep", "tra thuong nguoi lao dong", "bao hiem lao dong"],

    "suc_khoe_nguoi_vay": ["suc khoe nguoi vay", "nguoi vay", "bao hiem nguoi vay", "suc khoe vay", "tin dung", "vay tin dung"],

    "hoc_sinh_sinh_vien": ["hoc sinh", "sinh vien", "há»c sinh", "sinh viÃªn", "bao hiem hoc sinh", "bao hiem sinh vien", "24/24 hoc sinh", "tai nan hoc sinh"],

    "du_lich_trong_nuoc": ["du lich", "du lich trong nuoc", "bao hiem du lich", "travel", "nghá»‰ mat", "tham quan"],

    "du_lich_quoc_te": ["du lich quoc te", "bao hiem du lich quoc te", "travel international", "quoc te", "nuoc ngoai"],

    "cham_soc_suc_khoe_y_te": ["cham soc suc khoe", "ho tro y te", "suc khoe", "y te", "chÄƒm sÃ³c sá»©c khá»e", "há»— trá»£ y táº¿", "tai nan 383", "bao hiem tai nan"],

    "care_plus": ["care plus", "careplus", "chÄƒm sÃ³c sá»©c khá»e quá»‘c táº¿", "cham soc suc khoe quoc te", "suc khoe quoc te", "y te quoc te"],

    "trach_nhiem_cong_cong": ["trach nhiem cong cong", "trÃ¡ch nhiá»‡m cÃ´ng cá»™ng", "cong cong", "cÃ´ng cá»™ng", "public liability"],

}



def detect_product_smart(text):

    product = get_product_by_keyword(text)

    if product: return product

    text_norm = normalize_text(text)

    scores = {}

    for pid, kws in PRODUCT_KEYWORDS.items():

        score = sum(1 for kw in kws if normalize_text(kw) in text_norm)

        if score > 0: scores[pid] = score

    if scores:

        return get_product_by_id(max(scores, key=scores.get))

    return None



# ============================================================

# SESSION STATE

# ============================================================



def init_state():

    if "messages" not in st.session_state: st.session_state.messages = []

    if "current_product" not in st.session_state: st.session_state.current_product = None

    if "q_index" not in st.session_state: st.session_state.q_index = 0

    if "answers" not in st.session_state: st.session_state.answers = OrderedDict()

    if "finished" not in st.session_state: st.session_state.finished = False

    if "result" not in st.session_state: st.session_state.result = None

    if "started" not in st.session_state: st.session_state.started = False

    if "waiting_for_text" not in st.session_state: st.session_state.waiting_for_text = False

    if "customer_name" not in st.session_state: st.session_state.customer_name = ""

    if "asked_name" not in st.session_state: st.session_state.asked_name = False

    if "asked_evaluate" not in st.session_state: st.session_state.asked_evaluate = False

    if "chat_mode" not in st.session_state: st.session_state.chat_mode = True # True = chat tá»± nhiÃªn

    if "log_dir" not in st.session_state:

        st.session_state.log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "claim_logs")

    # ThÆ° má»¥c lÆ°u áº£nh vÃ  há»£p Ä‘á»“ng
    _base_dir = os.path.dirname(os.path.abspath(__file__))
    if "photo_dir" not in st.session_state:
        st.session_state.photo_dir = os.path.join(_base_dir, "áº£nh")
    if "contract_dir" not in st.session_state:
        st.session_state.contract_dir = os.path.join(_base_dir, "Há»£p Ä‘á»“ng")
    if "reply_dir" not in st.session_state:
        st.session_state.reply_dir = os.path.join(_base_dir, "tráº£ lá»i")

    if "waiting_for_welcome_choice" not in st.session_state: st.session_state.waiting_for_welcome_choice = False
    if "waiting_for_product_choice" not in st.session_state: st.session_state.waiting_for_product_choice = False
    if "waiting_for_faq_choice" not in st.session_state: st.session_state.waiting_for_faq_choice = False
    if "waiting_for_continue_choice" not in st.session_state: st.session_state.waiting_for_continue_choice = False
    if "waiting_for_city_choice" not in st.session_state: st.session_state.waiting_for_city_choice = False
    if "show_rating_widget" not in st.session_state: st.session_state.show_rating_widget = False
    if "show_quick_replies" not in st.session_state: st.session_state.show_quick_replies = False

    # --- Upload flow state (sau khi claim PASSED) ---
    if "upload_phase" not in st.session_state: st.session_state.upload_phase = None  # None | "upload" | "analyzing" | "done"
    if "uploaded_photos" not in st.session_state: st.session_state.uploaded_photos = []
    if "uploaded_contract" not in st.session_state: st.session_state.uploaded_contract = None
    if "ai_deduction_result" not in st.session_state: st.session_state.ai_deduction_result = None
    if "ai_reply_path" not in st.session_state: st.session_state.ai_reply_path = None
    if "last_claim_log" not in st.session_state: st.session_state.last_claim_log = None



init_state()



# ============================================================

# AIML KERNEL

# ============================================================



_aiml_kernel = None



def get_aiml_kernel():

    global _aiml_kernel

    if _aiml_kernel is not None:

        return _aiml_kernel

    if not AIML_AVAILABLE:

        return None

    kernel = aiml.Kernel()

    kernel.setTextEncoding(None)

    aiml_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_aiml.xml")

    if os.path.exists(aiml_path):

        kernel.learn(aiml_path)

        _aiml_kernel = kernel

    return _aiml_kernel



def aiml_respond(user_input):

    """Gá»­i input qua AIML kernel, tráº£ vá» response."""

    kernel = get_aiml_kernel()

    if kernel is None:

        return None

    normalized = normalize_aiml(user_input)

    response = kernel.respond(normalized)

    return response if response else None



def add_message(role, content):

    st.session_state.messages.append({"role": role, "content": content, "time": datetime.now().isoformat()})



# ============================================================

# CLAIM EVALUATION

# ============================================================



AGE_RANGES = {

    "combo360_o_to": None, "combo360_xe_may": None, "phu_gia": None,

    "family_care": (15, 65, "patient_age"), "tnds_moto": None, "gian_doan_kd": None,

    "ket_hop_con_nguoi": (1, 60, "victim_age"), "ung_thu": (1, 65, "patient_age"),

    "hiem_ngheo": (1, 65, "patient_age"), "tai_nan_2424": (16, 70, "victim_age"),

    "tai_nan_cao": (18, 65, "victim_age"),

    "tai_nan_nguoi_su_dung_dien": None,

    "boi_thuong_nguoi_lao_dong": None,

    "suc_khoe_nguoi_vay": None,

    "hoc_sinh_sinh_vien": None,

    "du_lich_trong_nuoc": None,

    "du_lich_quoc_te": None,

    "cham_soc_suc_khoe_y_te": None,

    "care_plus": None,

    "trach_nhiem_cong_cong": None,

}



def check_age(answers, product_id):

    reasons = []

    r = AGE_RANGES.get(product_id)

    if not r: return reasons

    min_age, max_age, age_field = r

    raw = answers.get(age_field, "")

    if not raw: return reasons

    nums = re.findall(r'\d+', str(raw))

    if not nums: return reasons

    age = int(nums[0])

    if age < min_age or age > max_age:

        reasons.append(f" Tuá»•i cá»§a ngÆ°á»i Ä‘Æ°á»£c báº£o hiá»ƒm lÃ  {age}, khÃ´ng náº±m trong pháº¡m vi ({min_age}-{max_age} tuá»•i) â†’ KhÃ´ng Ä‘áº¡t Ä‘iá»u kiá»‡n")

    return reasons



def evaluate_claim(answers, product):

    reasons = []

    failed = []

    passed = True

    age_reasons = check_age(answers, product["id"])

    if age_reasons:

        passed = False

        reasons.extend(age_reasons)

    for q in product["claim_questions"]:

        qid = q["id"]

        if qid not in answers:

            if q.get("required"):

                reasons.append(f"ChÆ°a tráº£ lá»i cÃ¢u há»i: {q['question']}")

                passed = False

            continue

        answer = answers[qid]

        fail_if = q.get("fail_if")

        if fail_if and match_answer(answer, fail_if):

            passed = False

            failed.append(qid)

            reasons.append(f" {q['question']} â†’ Tráº£ lá»i: '{answer}' â†’ KhÃ´ng Ä‘áº¡t Ä‘iá»u kiá»‡n tiáº¿p nháº­n bá»“i thÆ°á»ng")

    return {"passed": passed, "reasons": reasons, "failed_questions": failed}



def save_claim_log(product, answers, result):

    os.makedirs(st.session_state.log_dir, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    safe = re.sub(r'[^\w]', '_', st.session_state.customer_name or "khach_hang")

    if result.get("passed"):

        sub_dir = os.path.join(st.session_state.log_dir, "Ä‘Æ°á»£c_thÃ´ng_qua")

    else:

        sub_dir = os.path.join(st.session_state.log_dir, "chÆ°a_Ä‘Æ°á»£c_thÃ´ng_qua")

    os.makedirs(sub_dir, exist_ok=True)

    fp = os.path.join(sub_dir, f"claim_{safe}_{product['id']}_{ts}.json")

    log = {"timestamp": datetime.now().isoformat(), "customer_name": st.session_state.customer_name,

           "product": {"id": product["id"], "name": product["name"], "url": product["url"]},

           "answers": dict(answers), "result": result}

    with open(fp, "w", encoding="utf-8") as f:

        json.dump(log, f, ensure_ascii=False, indent=2)

    return fp



def reset_session():

    """Reset vá» tráº¡ng thÃ¡i chat tá»± nhiÃªn, giá»¯ tÃªn khÃ¡ch hÃ ng."""

    st.session_state.messages = []

    st.session_state.current_product = None

    st.session_state.q_index = 0

    st.session_state.answers = OrderedDict()

    st.session_state.finished = False

    st.session_state.result = None

    st.session_state.started = False

    st.session_state.waiting_for_text = False

    st.session_state.waiting_for_product_choice = False
    st.session_state.waiting_for_city_choice = False
    st.session_state.asked_evaluate = False

    st.session_state.chat_mode = True

    # Reset upload flow
    st.session_state.upload_phase = None
    st.session_state.uploaded_photos = []
    st.session_state.uploaded_contract = None
    st.session_state.ai_deduction_result = None
    st.session_state.ai_reply_path = None
    st.session_state.last_claim_log = None



def full_reset():

    """Reset hoÃ n toÃ n, xÃ³a cáº£ tÃªn."""

    reset_session()

    st.session_state.customer_name = ""

    st.session_state.asked_name = False



# ============================================================

# SIDEBAR

# ============================================================



with st.sidebar:

    _logo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "_logo.png")

    if os.path.exists(_logo):

        st.image(_logo, width=200)

    st.markdown("## Trá»£ lÃ½ áº£o")

    st.markdown("### Version 0.6")

    st.markdown("---")

    st.markdown("### Sáº£n pháº©m báº£o hiá»ƒm:")

    for p in PRODUCTS:

        st.markdown(f"**{p['name']}**")

        st.caption(f" {p['price']}")

        st.caption(f" [Link]({p['url']})")

        st.markdown("")

    st.markdown("---")

    if st.button(" Báº¯t Ä‘áº§u láº¡i"):

        full_reset()

        st.rerun()

    st.markdown("---")

    st.markdown("### ðŸŒ NgÃ´n ngá»¯ / Language:")

    st.caption("Tiáº¿ng Viá»‡t (máº·c Ä‘á»‹nh) | English via hotline 1900 54 54 55")

    st.markdown("---")

    st.markdown("### ThÆ° má»¥c log:")

    st.code(st.session_state.log_dir)

    if os.path.exists(st.session_state.log_dir):

        passed_dir = os.path.join(st.session_state.log_dir, "Ä‘Æ°á»£c_thÃ´ng_qua")

        failed_dir = os.path.join(st.session_state.log_dir, "chÆ°a_Ä‘Æ°á»£c_thÃ´ng_qua")

        passed_files = [f for f in os.listdir(passed_dir) if f.endswith(".json")] if os.path.exists(passed_dir) else []

        failed_files = [f for f in os.listdir(failed_dir) if f.endswith(".json")] if os.path.exists(failed_dir) else []

        st.metric(" ÄÆ°á»£c thÃ´ng qua", len(passed_files))

        st.metric(" ChÆ°a Ä‘Æ°á»£c thÃ´ng qua", len(failed_files))



# ============================================================

# HEADER

# ============================================================



_logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "_logo.png")

_logo_html = f'<img src="file/{_logo_path}" alt="">' if os.path.exists(_logo_path) else ''

st.markdown(f'<div class="-header">{_logo_html}<div><h1>Báº¢O HIá»‚M </h1><p>Tá»•ng CÃ´ng ty Cá»• pháº§n Báº£o hiá»ƒm Petrolimex | Trá»£ lÃ½ áº£o V.0.6</p></div></div>', unsafe_allow_html=True)

st.markdown("---")



# ============================================================

# WELCOME MESSAGE

# ============================================================



if not st.session_state.started:

    add_message("assistant", (

        "Xin chÃ o! TÃ´i lÃ  trá»£ lÃ½ áº£o . \n\n"

        "TÃ´i cÃ³ thá»ƒ há»— trá»£ anh/chá»‹ cÃ¡c nhu cáº§u sau.\n"

        "Vui lÃ²ng **chá»n má»™t lá»±a chá»n** bÃªn dÆ°á»›i nhÃ©! "

    ))

    st.session_state.started = True

    st.session_state.waiting_for_welcome_choice = True



# ============================================================

# AUTO-RENDER QUESTIONS / RESULTS (khi Ä‘ang trong claim flow)

# ============================================================



current_product = st.session_state.current_product

q_index = st.session_state.q_index



if current_product and not st.session_state.finished:

    questions = current_product["claim_questions"]

    if q_index < len(questions):

        q = questions[q_index]

        last_msg = st.session_state.messages[-1] if st.session_state.messages else None

        already_asked = last_msg and last_msg["role"] == "assistant" and q["question"] in last_msg["content"]

        if not already_asked:

            prompt = f"**CÃ¢u {q_index + 1}/{len(questions)}:** {q['question']}"

            add_message("assistant", prompt)



elif current_product and st.session_state.finished and st.session_state.result:

    last_msg = st.session_state.messages[-1] if st.session_state.messages else None

    if not (last_msg and last_msg["role"] == "assistant" and "Káº¾T QUáº¢" in last_msg["content"]):

        result = st.session_state.result

        product = current_product

        if result["passed"]:

            verdict = " **Äá»¦ ÄIá»€U KIá»†N TIáº¾P NHáº¬N Bá»’I THÆ¯á»œNG**"

            detail = "Há»“ sÆ¡ cá»§a anh/chá»‹ Ä‘Ã£ Ä‘á»§ Ä‘iá»u kiá»‡n Ä‘á»ƒ tiáº¿p nháº­n bá»“i thÆ°á»ng. Vui lÃ²ng liÃªn há»‡ Ä‘á»ƒ Ä‘Æ°á»£c hÆ°á»›ng dáº«n ná»™p há»“ sÆ¡ chÃ­nh thá»©c."

        else:

            verdict = " **KHÃ”NG Äá»¦ ÄIá»€U KIá»†N TIáº¾P NHáº¬N Bá»’I THÆ¯á»œNG**"

            detail = "Dá»±a trÃªn thÃ´ng tin cung cáº¥p, há»“ sÆ¡ chÆ°a Ä‘á»§ Ä‘iá»u kiá»‡n Ä‘á»ƒ tiáº¿p nháº­n bá»“i thÆ°á»ng.\n\n**LÃ½ do:**\n"

            for r in result["reasons"]:

                detail += f"- {r}\n"

        summary = f"""

---

## Káº¾T QUáº¢ ÄÃNH GIÃ ÄIá»€U KIá»†N TIáº¾P NHáº¬N Bá»’I THÆ¯á»œNG



**Sáº£n pháº©m:** {product['name']}



{verdict}



{detail}



**TÃ³m táº¯t cÃ¢u tráº£ lá»i:**

"""

        for q in product["claim_questions"]:

            ans = st.session_state.answers.get(q["id"], "(chÆ°a tráº£ lá»i)")

            summary += f"- **{q['question']}**: {ans}\n"

        log_path = save_claim_log(product, dict(st.session_state.answers), result)

        summary += f"\n ThÃ´ng tin Ä‘Ã£ lÆ°u: `{os.path.basename(log_path)}`\n"

        summary += "\nAnh/chá»‹ cáº§n há»— trá»£ gÃ¬ thÃªm khÃ´ng áº¡?"

        add_message("assistant", summary)

        # Chá»‰ set waiting_for_continue_choice náº¿u KHÃ”NG pháº£i claim passed
        # (claim passed sáº½ chuyá»ƒn sang upload flow, khÃ´ng cáº§n continue choice ngay)
        if not result.get("passed"):
            st.session_state.waiting_for_continue_choice = True



        import json as _json

        log_data = {

            "timestamp": datetime.now().isoformat(),

            "customer_name": st.session_state.customer_name,

            "product": {"id": product["id"], "name": product["name"]},

            "answers": dict(st.session_state.answers),

            "result": result,

        }

        log_json = _json.dumps(log_data, ensure_ascii=False, indent=2)

        safe_name = re.sub(r'[^\w]', '_', st.session_state.customer_name or "khach_hang")

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        filename = f"claim_{safe_name}_{product['id']}_{ts}.json"

        st.download_button(

            label=" Táº£i káº¿t quáº£ (JSON)",

            data=log_json.encode("utf-8"),

            file_name=filename,

            mime="application/json",

            use_container_width=True,

        )

        st.download_button(

            label=" Táº£i káº¿t quáº£ (Text)",

            data=summary.encode("utf-8"),

            file_name=f"claim_{safe_name}_{product['id']}_{ts}.txt",

            mime="text/plain",

            use_container_width=True,

        )



# ============================================================

# RENDER CHAT MESSAGES

# ============================================================



for msg in st.session_state.messages:

    with st.chat_message(msg["role"]):

        st.markdown(msg["content"])



# ============================================================

# UPLOAD FLOW â€” Khi claim Äá»¦ ÄIá»€U KIá»†N â†’ cho upload áº£nh + há»£p Ä‘á»“ng + AI phÃ¢n tÃ­ch kháº¥u trá»«

# ============================================================



if (current_product and st.session_state.finished and st.session_state.result
        and st.session_state.result.get("passed") and not st.session_state.upload_phase):



    # LÆ°u claim log data Ä‘á»ƒ dÃ¹ng cho AI

    if not st.session_state.last_claim_log:

        st.session_state.last_claim_log = {

            "timestamp": datetime.now().isoformat(),

            "customer_name": st.session_state.customer_name,

            "product": {"id": current_product["id"], "name": current_product["name"]},

            "answers": dict(st.session_state.answers),

            "result": st.session_state.result,

        }



    add_message("assistant", (

        " Há»“ sÆ¡ cá»§a anh/chá»‹ Ä‘Ã£ **Äá»¦ ÄIá»€U KIá»†N** tiáº¿p nháº­n bá»“i thÆ°á»ng!\n\n"

        "Äá»ƒ phÃ¢n tÃ­ch cÃ¡c khoáº£n kháº¥u trá»« trong tiá»n bá»“i thÆ°á»ng, vui lÃ²ng:\n"

        "1. **Upload áº£nh thiá»‡t háº¡i** (áº£nh hiá»‡n trÆ°á»ng, tÃ i sáº£n bá»‹ hÆ° há»ng...)\n"

        "2. **Upload há»£p Ä‘á»“ng báº£o hiá»ƒm** (áº£nh hoáº·c file)\n"

        "Sau Ä‘Ã³ tÃ´i sáº½ dÃ¹ng AI Ä‘á»ƒ phÃ¢n tÃ­ch vÃ  thÃ´ng bÃ¡o káº¿t quáº£ kháº¥u trá»« cho anh/chá»‹.\n\n"

        "ðŸ‘‰ Cuá»™n xuá»‘ng bÃªn dÆ°á»›i Ä‘á»ƒ upload nhÃ©!"

    ))

    st.session_state.upload_phase = "upload"

    st.rerun()



# ============================================================

# UPLOAD UI â€” File uploaders cho áº£nh + há»£p Ä‘á»“ng

# ============================================================

if st.session_state.upload_phase == "upload":



    st.markdown("---")

    st.markdown("### ðŸ“¸ Upload áº£nh thiá»‡t háº¡i")

    uploaded_photos = st.file_uploader(

        "Chá»n má»™t hoáº·c nhiá»u áº£nh thiá»‡t háº¡i (JPG, PNG):",

        type=["jpg", "jpeg", "png", "gif", "webp"],

        accept_multiple_files=True,

        key="photo_uploader"

    )



    st.markdown("### ðŸ“„ Upload há»£p Ä‘á»“ng báº£o hiá»ƒm")

    uploaded_contract = st.file_uploader(

        "Chá»n file há»£p Ä‘á»“ng (áº£nh JPG/PNG hoáº·c PDF):",

        type=["jpg", "jpeg", "png", "gif", "webp", "pdf"],

        accept_multiple_files=False,

        key="contract_uploader"

    )



    col_a, col_b = st.columns(2)



    with col_a:

        if st.button("ðŸ”„ PhÃ¢n tÃ­ch kháº¥u trá»«", key="analyze_btn", use_container_width=True,

                     disabled=(not uploaded_photos and not uploaded_contract)):



            # LÆ°u áº£nh vÃ o thÆ° má»¥c "áº£nh"

            photo_paths = []

            if uploaded_photos:

                os.makedirs(st.session_state.photo_dir, exist_ok=True)

                ts = datetime.now().strftime("%Y%m%d_%H%M%S")

                safe_name = re.sub(r'[^\w]', '_', st.session_state.customer_name or "khach_hang")

                for idx, photo in enumerate(uploaded_photos):

                    ext = os.path.splitext(photo.name)[1] or ".jpg"

                    fname = f"photo_{safe_name}_{ts}_{idx+1}{ext}"

                    fpath = os.path.join(st.session_state.photo_dir, fname)

                    with open(fpath, "wb") as f:

                        f.write(photo.getbuffer())

                    photo_paths.append(fpath)

                st.session_state.uploaded_photos = photo_paths



            # LÆ°u há»£p Ä‘á»“ng vÃ o thÆ° má»¥c "Há»£p Ä‘á»“ng"

            contract_path = None

            if uploaded_contract:

                os.makedirs(st.session_state.contract_dir, exist_ok=True)

                ts = datetime.now().strftime("%Y%m%d_%H%M%S")

                safe_name = re.sub(r'[^\w]', '_', st.session_state.customer_name or "khach_hang")

                ext = os.path.splitext(uploaded_contract.name)[1] or ".jpg"

                fname = f"contract_{safe_name}_{ts}{ext}"

                fpath = os.path.join(st.session_state.contract_dir, fname)

                with open(fpath, "wb") as f:

                    f.write(uploaded_contract.getbuffer())

                contract_path = fpath

                st.session_state.uploaded_contract = contract_path



            if not photo_paths and not contract_path:

                st.warning("Vui lÃ²ng upload Ã­t nháº¥t 1 áº£nh hoáº·c há»£p Ä‘á»“ng Ä‘á»ƒ phÃ¢n tÃ­ch!")

            else:

                st.session_state.upload_phase = "analyzing"

                st.rerun()



    with col_b:

        if st.button("â­ï¸ Bá» qua", key="skip_upload_btn", use_container_width=True):

            st.session_state.upload_phase = None

            st.session_state.waiting_for_continue_choice = True

            add_message("assistant", "Dáº¡! Anh/chá»‹ cÃ³ thá»ƒ upload áº£nh vÃ  há»£p Ä‘á»“ng sau. Anh/chá»‹ cáº§n há»— trá»£ gÃ¬ thÃªm khÃ´ng áº¡?")

            st.rerun()



# ============================================================

# AI ANALYZING â€” Gá»i AI phÃ¢n tÃ­ch kháº¥u trá»«

# ============================================================

if st.session_state.upload_phase == "analyzing":



    with st.spinner("ðŸ¤– AI Ä‘ang phÃ¢n tÃ­ch áº£nh vÃ  há»£p Ä‘á»“ng, vui lÃ²ng Ä‘á»£i..."):



        if not AI_DEDUCTION_AVAILABLE:

            ai_result = {

                "success": False,

                "response": "",

                "error": "Module ai_deduction khÃ´ng kháº£ dá»¥ng. Vui lÃ²ng cÃ i Ä‘áº·t: pip install requests"

            }

        elif not ai_has_key():

            ai_result = {

                "success": False,

                "response": "",

                "error": ("ChÆ°a cáº¥u hÃ¬nh API key. "

                          "Vui lÃ²ng thÃªm key vÃ o Streamlit Cloud Secrets (key: ollama_api_key) "

                          "hoáº·c táº¡o file .kimi_api_key (local).")

            }

        else:

            claim_data = st.session_state.last_claim_log or {

                "customer_name": st.session_state.customer_name,

                "product": {"id": current_product["id"], "name": current_product["name"]},

                "answers": dict(st.session_state.answers),

                "result": st.session_state.result,

            }

            ai_result = analyze_deduction(

                claim_data=claim_data,

                photo_paths=st.session_state.uploaded_photos,

                contract_path=st.session_state.uploaded_contract

            )



    if ai_result["success"]:

        # LÆ°u cÃ¢u tráº£ lá»i AI

        photo_names = [os.path.basename(p) for p in st.session_state.uploaded_photos]

        contract_name = os.path.basename(st.session_state.uploaded_contract) if st.session_state.uploaded_contract else None

        ai_text = ai_result.get("response", "")

        # Fallback náº¿u AI tráº£ vá» rá»—ng
        if not ai_text or not ai_text.strip():
            ai_text = ("AI Ä‘Ã£ xá»­ lÃ½ nhÆ°ng khÃ´ng tráº£ vá» ná»™i dung. "
                       "Vui lÃ²ng liÃªn há»‡ qua tá»•ng Ä‘Ã i 1900 54 54 55 "
                       "Ä‘á»ƒ Ä‘Æ°á»£c nhÃ¢n viÃªn há»— trá»£ phÃ¢n tÃ­ch kháº¥u trá»«.")

        reply_path = save_reply(

            claim_data=st.session_state.last_claim_log or {},

            ai_response=ai_text,

            photo_names=photo_names,

            contract_name=contract_name

        )

        st.session_state.ai_reply_path = reply_path

        st.session_state.ai_deduction_result = ai_text



        # Hiá»ƒn thá»‹ káº¿t quáº£ AI cho khÃ¡ch hÃ ng â€” full ná»™i dung
        ai_message = f"""

---

## ðŸ¤– Káº¾T QUáº¢ PHÃ‚N TÃCH KHáº¤U TRá»ª Bá»’I THÆ¯á»œNG



{ai_text}



---

 ThÃ´ng tin Ä‘Ã£ lÆ°u: `{os.path.basename(reply_path)}`

"""

        add_message("assistant", ai_message)

        # Hiá»ƒn thá»‹ nÃºt download ngay sau chat messages
        with open(reply_path, "r", encoding="utf-8") as f:
            reply_content = f.read()
        st.download_button(
            label="ðŸ“¥ Táº£i káº¿t quáº£ phÃ¢n tÃ­ch (Markdown)",
            data=reply_content.encode("utf-8"),
            file_name=os.path.basename(reply_path),
            mime="text/markdown",
            use_container_width=True,
        )

        # Git auto-push (chá»‰ cháº¡y á»Ÿ local, khÃ´ng cháº¡y trÃªn Streamlit Cloud)
        is_cloud = os.environ.get("STREAMLIT_SHARING", "") or os.environ.get("HOSTNAME", "").startswith("streamlit")
        if not is_cloud:
            try:
                import subprocess
                git_dir = os.path.dirname(os.path.abspath(__file__))
                subprocess.run(["git", "add", "-A"], cwd=git_dir, capture_output=True, timeout=30)
                commit_msg = f"feat: add claim photos + contract + AI deduction reply for {st.session_state.customer_name or 'customer'} [{datetime.now().strftime('%Y-%m-%d %H:%M')}]"
                subprocess.run(["git", "commit", "-m", commit_msg], cwd=git_dir, capture_output=True, timeout=30)
                subprocess.run(["git", "push", "origin"], cwd=git_dir, capture_output=True, timeout=60)
                add_message("assistant", " ÄÃ£ Ä‘á»“ng bá»™ dá»¯ liá»‡u lÃªn GitHub repository.")
            except Exception as e:
                add_message("assistant", f"âš ï¸ KhÃ´ng thá»ƒ push lÃªn GitHub: {str(e)}")
        else:
            add_message("assistant", " ÄÃ£ lÆ°u káº¿t quáº£ phÃ¢n tÃ­ch. Äá»ƒ push GitHub, cháº¡y app local.")



    else:

        add_message("assistant", (

            f"âš ï¸ KhÃ´ng thá»ƒ phÃ¢n tÃ­ch kháº¥u trá»«: {ai_result['error']}\n\n"

            "Anh/chá»‹ cÃ³ thá»ƒ thá»­ láº¡i sau hoáº·c liÃªn há»‡ qua tá»•ng Ä‘Ã i 1900 54 54 55 "

            "Ä‘á»ƒ Ä‘Æ°á»£c nhÃ¢n viÃªn há»— trá»£ trá»±c tiáº¿p."

        ))



    st.session_state.upload_phase = "done"

    st.session_state.waiting_for_continue_choice = True

    st.rerun()







# ============================================================

# QUICK REPLY BAR â€” CÃ¢u gá»£i Ã½ nhanh sau má»—i tin nháº¯n trá»£ lÃ½

# ============================================================

if st.session_state.messages and not st.session_state.current_product and not st.session_state.finished:

    if st.session_state.waiting_for_welcome_choice or st.session_state.waiting_for_continue_choice:

        last_msg = st.session_state.messages[-1] if st.session_state.messages else None

        if last_msg and last_msg["role"] == "assistant":

            st.markdown("**CÃ¢u gá»£i Ã½ nhanh:**")

            qr_col1, qr_col2, qr_col3, qr_col4 = st.columns(4)

            quick_labels = ["TÆ° váº¥n sáº£n pháº©m", "Giáº£i Ä‘Ã¡p tháº¯c máº¯c", "ÄÃ¡nh giÃ¡ bá»“i thÆ°á»ng", "Tra cá»©u há»“ sÆ¡"]

            quick_patterns = ["TU VAN SAN PHAM BAO HIEM", "GIAI DAP THAC MAC", "DANH GIA BOI THUONG", "TRA CUU HO SO"]

            with qr_col1:

                if st.button(quick_labels[0], key=f"qr_{len(st.session_state.messages)}_0"):

                    add_message("user", quick_labels[0])

                    st.session_state.waiting_for_welcome_choice = False

                    st.session_state.waiting_for_continue_choice = False

                    st.session_state.waiting_for_product_choice = True

                    add_message("assistant", "Dáº¡! Vui lÃ²ng **chá»n sáº£n pháº©m** bÃªn dÆ°á»›i Ä‘á»ƒ biáº¿t thÃªm chi tiáº¿t!")

                    st.rerun()

            with qr_col2:

                if st.button(quick_labels[1], key=f"qr_{len(st.session_state.messages)}_1"):

                    add_message("user", quick_labels[1])

                    st.session_state.waiting_for_welcome_choice = False

                    st.session_state.waiting_for_continue_choice = False

                    st.session_state.waiting_for_faq_choice = True

                    add_message("assistant", "Dáº¡! Vui lÃ²ng **chá»n chá»§ Ä‘á»** bÃªn dÆ°á»›i Ä‘á»ƒ biáº¿t thÃªm chi tiáº¿t!")

                    st.rerun()

            with qr_col3:

                if st.button(quick_labels[2], key=f"qr_{len(st.session_state.messages)}_2"):

                    add_message("user", quick_labels[2])

                    st.session_state.waiting_for_welcome_choice = False

                    st.session_state.waiting_for_continue_choice = False

                    st.session_state.asked_evaluate = True

                    st.session_state.waiting_for_text = True

                    add_message("assistant", "Dáº¡! Vui lÃ²ng chá»n loáº¡i báº£o hiá»ƒm á»Ÿ thanh cuá»™n bÃªn dÆ°á»›i nhÃ©!")

                    st.rerun()

            with qr_col4:

                if st.button(quick_labels[3], key=f"qr_{len(st.session_state.messages)}_3"):

                    add_message("user", quick_labels[3])

                    st.session_state.waiting_for_welcome_choice = False

                    st.session_state.waiting_for_continue_choice = False

                    add_message("assistant", (

                        "Dáº¡! Anh/chá»‹ cÃ³ thá»ƒ tra cá»©u tráº¡ng thÃ¡i há»“ sÆ¡ bá»“i thÆ°á»ng:\n\n"

                        "1. Website: https://www..com.vn â†’ \"Tra cá»©u há»“ sÆ¡\"\n"

                        "2. Tá»•ng Ä‘Ã i: 1900 54 54 55\n\n"

                        "Anh/chá»‹ cÃ³ mÃ£ há»“ sÆ¡ khÃ´ng áº¡?"

                    ))

                    st.session_state.waiting_for_continue_choice = True

                    st.rerun()



# ============================================================

# RATING WIDGET â€” ÄÃ¡nh giÃ¡ tráº£i nghiá»‡m (khi user chá»n ÄÃ¡nh giÃ¡ tráº£i nghiá»‡m)

# ============================================================

if st.session_state.get("show_rating_widget", False) and st.session_state.waiting_for_continue_choice:

    st.markdown("**ÄÃ¡nh giÃ¡ tráº£i nghiá»‡m vá»›i trá»£ lÃ½ áº£o :**")

    rating = st.slider("Chá»n sá»‘ sao (1-5)", min_value=1, max_value=5, value=5, key="rating_slider")

    if st.button(" Gá»­i Ä‘Ã¡nh giÃ¡", key="submit_rating_btn", use_container_width=True):

        st.session_state.show_rating_widget = False

        add_message("user", f"ÄÃ¡nh giÃ¡: {rating} sao")

        if rating >= 4:

            add_message("assistant", (
                f"Cáº£m Æ¡n anh/chá»‹ Ä‘Ã£ Ä‘Ã¡nh giÃ¡ {rating} sao! Ráº¥t vui vÃ¬ mang láº¡i tráº£i nghiá»‡m tá»‘t. "

                "luÃ´n sáºµn sÃ ng há»— trá»£ anh/chá»‹!"

            ))

        elif rating == 3:

            add_message("assistant", (
                f"Cáº£m Æ¡n anh/chá»‹ Ä‘Ã£ Ä‘Ã¡nh giÃ¡ {rating} sao! ChÃºng tÃ´i sáº½ cá»‘ gáº¯ng cáº£i thiá»‡n Ä‘á»ƒ mang láº¡i tráº£i nghiá»‡m tá»‘t hÆ¡n."

            ))

        else:

            add_message("assistant", (
                f"Cáº£m Æ¡n anh/chá»‹ Ä‘Ã£ Ä‘Ã¡nh giÃ¡ {rating} sao! ChÃºng tÃ´i ráº¥t tiáº¿c vÃ¬ tráº£i nghiá»‡m chÆ°a tá»‘t. "

                "Anh/chá»‹ cÃ³ thá»ƒ liÃªn há»‡ tá»•ng Ä‘Ã i 1900 54 54 55 Ä‘á»ƒ Ä‘Æ°á»£c há»— trá»£ trá»±c tiáº¿p."

            ))

        st.rerun()



# ============================================================

# WELCOME RADIO BUTTONS â€” Chá»n nhu cáº§u há»— trá»£

# ============================================================



if st.session_state.waiting_for_welcome_choice and not st.session_state.current_product and not st.session_state.waiting_for_text:

    welcome_options = [

        " TÆ° váº¥n cÃ¡c sáº£n pháº©m báº£o hiá»ƒm",

        " Giáº£i Ä‘Ã¡p tháº¯c máº¯c thÆ°á»ng gáº·p",

        " ÄÃ¡nh giÃ¡ Ä‘iá»u kiá»‡n tiáº¿p nháº­n bá»“i thÆ°á»ng",

        " Tra cá»©u tráº¡ng thÃ¡i há»“ sÆ¡ bá»“i thÆ°á»ng",

        " TÃ¬m Ä‘áº¡i lÃ½/vÄƒn phÃ²ng gáº§n nháº¥t",

        " ÄÃ¡nh giÃ¡ tráº£i nghiá»‡m vá»›i trá»£ lÃ½ áº£o",

    ]

    welcome_selected = st.radio(

        "Chá»n nhu cáº§u há»— trá»£:",

        welcome_options,

        key="welcome_radio",

        label_visibility="collapsed",

    )

    if st.button(" XÃ¡c nháº­n", key="welcome_confirm_btn", use_container_width=True):

        st.session_state.waiting_for_welcome_choice = False

        add_message("user", welcome_selected)

        if "ÄÃ¡nh giÃ¡ Ä‘iá»u kiá»‡n tiáº¿p nháº­n" in welcome_selected:

            st.session_state.asked_evaluate = True

            st.session_state.waiting_for_text = True

            add_message("assistant", (

                "Dáº¡! Anh/chá»‹ muá»‘n **Ä‘Ã¡nh giÃ¡ Ä‘iá»u kiá»‡n tiáº¿p nháº­n bá»“i thÆ°á»ng**. \n\n"

                "Vui lÃ²ng chá»n loáº¡i báº£o hiá»ƒm á»Ÿ thanh cuá»™n bÃªn dÆ°á»›i nhÃ©!"

            ))

        elif "TÆ° váº¥n" in welcome_selected:

            st.session_state.waiting_for_product_choice = True

            add_message("assistant", (

                "Dáº¡! TÃ´i cÃ³ thá»ƒ tÆ° váº¥n vá» cÃ¡c sáº£n pháº©m báº£o hiá»ƒm .\n\n"

                "Vui lÃ²ng **chá»n sáº£n pháº©m** bÃªn dÆ°á»›i Ä‘á»ƒ biáº¿t thÃªm chi tiáº¿t!"

            ))

        elif "Giáº£i Ä‘Ã¡p" in welcome_selected:

            st.session_state.waiting_for_faq_choice = True

            add_message("assistant", (

                "Dáº¡! TÃ´i cÃ³ thá»ƒ giáº£i Ä‘Ã¡p tháº¯c máº¯c cá»§a anh/chá»‹.\n\n"

                "Vui lÃ²ng **chá»n chá»§ Ä‘á»** bÃªn dÆ°á»›i Ä‘á»ƒ biáº¿t thÃªm chi tiáº¿t!"

            ))

        elif "Tra cá»©u tráº¡ng thÃ¡i" in welcome_selected:

            add_message("assistant", (

                "Dáº¡! Anh/chá»‹ muá»‘n **tra cá»©u tráº¡ng thÃ¡i há»“ sÆ¡ bá»“i thÆ°á»ng**.\n\n"

                "Anh/chá»‹ cÃ³ thá»ƒ:\n"

                "1. Truy cáº­p website https://www..com.vn, má»¥c \"Tra cá»©u há»“ sÆ¡\"\n"

                "2. Gá»i tá»•ng Ä‘Ã i 1900 54 54 55 Ä‘á»ƒ Ä‘Æ°á»£c nhÃ¢n viÃªn tra cá»©u\n\n"

                "Anh/chá»‹ cÃ³ mÃ£ há»“ sÆ¡ bá»“i thÆ°á»ng khÃ´ng áº¡? Vui lÃ²ng cung cáº¥p mÃ£ há»“ sÆ¡ Ä‘á»ƒ tÃ´i há»— trá»£!"

            ))

            st.session_state.waiting_for_continue_choice = True

        elif "TÃ¬m Ä‘áº¡i lÃ½" in welcome_selected or "vÄƒn phÃ²ng" in welcome_selected.lower():

            add_message("assistant", (

                "Dáº¡! Äá»ƒ tÃ¬m Ä‘áº¡i lÃ½/vÄƒn phÃ²ng gáº§n nháº¥t, anh/chá»‹ cÃ³ thá»ƒ:\n\n"

                "1. Truy cáº­p website https://www..com.vn, má»¥c \"Máº¡ng lÆ°á»›i\"\n"

                "2. Gá»i tá»•ng Ä‘Ã i 1900 54 54 55 Ä‘á»ƒ Ä‘á»‹nh vá»‹ vÄƒn phÃ²ng gáº§n nháº¥t\n"

                "3. TÃ¬m kiáº¿m \"+ tÃªn tá»‰nh/thÃ nh phá»‘\" trÃªn Google Maps\n\n"

                "cÃ³ vÄƒn phÃ²ng trÃªn toÃ n bá»™ 63 tá»‰nh thÃ nh. Anh/chá»‹ Ä‘ang á»Ÿ tá»‰nh/thÃ nh phá»‘ nÃ o áº¡?"

            ))
            st.session_state.waiting_for_city_choice = True
            st.rerun()
        elif "ÄÃ¡nh giÃ¡ tráº£i nghiá»‡m" in welcome_selected:

            add_message("assistant", (

                "Dáº¡! Anh/chá»‹ muá»‘n **Ä‘Ã¡nh giÃ¡ tráº£i nghiá»‡m** vá»›i trá»£ lÃ½ áº£o .\n\n"

                "Vui lÃ²ng chá»n má»©c Ä‘Ã¡nh giÃ¡ bÃªn dÆ°á»›i nhÃ©!"

            ))

            st.session_state.show_rating_widget = True

            st.session_state.waiting_for_continue_choice = True

        st.rerun()


# ============================================================

# FAQ CHOICE RADIO BUTTONS â€” Chá»n chá»§ Ä‘á» giáº£i Ä‘Ã¡p

# ============================================================



if st.session_state.waiting_for_faq_choice and not st.session_state.current_product and not st.session_state.waiting_for_text and not st.session_state.waiting_for_product_choice:

    faq_options = [

        "Quy trÃ¬nh bá»“i thÆ°á»ng ",

        "ThÃ´ng tin liÃªn há»‡",

        "Giá» lÃ m viá»‡c",

        "Má»©c bá»“i thÆ°á»ng, phÃ­ báº£o hiá»ƒm",

        "Há»“ sÆ¡ bá»“i thÆ°á»ng cáº§n gÃ¬",

        "Thá»i gian xá»­ lÃ½ bá»“i thÆ°á»ng",

        "ÄÃ³ng phÃ­ báº£o hiá»ƒm á»Ÿ Ä‘Ã¢u",

        "HÆ°á»›ng dáº«n khiáº¿u náº¡i",

        "NÃ³i chuyá»‡n vá»›i nhÃ¢n viÃªn",

        "Khuyáº¿n mÃ£i, Æ°u Ä‘Ã£i",

        "Há»§y/Ä‘á»•i báº£o hiá»ƒm",

        "Cáº­p nháº­t thÃ´ng tin cÃ¡ nhÃ¢n",

    ]

    col1, col2 = st.columns([3, 1])

    with col1:

        faq_selected = st.selectbox(

            "Chá»n chá»§ Ä‘á»:",

            faq_options,

            key="faq_selectbox",

            label_visibility="collapsed",

        )

    with col2:

        st.write("")

    if st.button(" XÃ¡c nháº­n", key="faq_confirm_btn", use_container_width=True):

        st.session_state.waiting_for_faq_choice = False

        add_message("user", faq_selected)

        if "Quy trÃ¬nh" in faq_selected:

            add_message("assistant", (

                "Quy trÃ¬nh bá»“i thÆ°á»ng :\n\n"

                "1. ThÃ´ng bÃ¡o sá»± cá»‘ cho (trong thá»i háº¡n quy Ä‘á»‹nh)\n"

                "2. Chuáº©n bá»‹ há»“ sÆ¡ yÃªu cáº§u bá»“i thÆ°á»ng\n"

                "3. tiáº¿p nháº­n vÃ  tháº©m Ä‘á»‹nh há»“ sÆ¡\n"

                "4. Thanh toÃ¡n bá»“i thÆ°á»ng\n\n"

                "Anh/chá»‹ cáº§n há»— trá»£ gÃ¬ thÃªm khÃ´ng áº¡?"

            ))

        elif "ThÃ´ng tin liÃªn há»‡" in faq_selected:

            add_message("assistant", (

                "ThÃ´ng tin liÃªn há»‡ :\n\n"

                "Tá»•ng CÃ´ng ty Cá»• pháº§n Báº£o hiá»ƒm Petrolimex\n"

                "Trá»¥ sá»Ÿ chÃ­nh: Táº§ng 21-22, tÃ²a nhÃ  Mipec, 229 TÃ¢y SÆ¡n, PhÆ°á»ng Kim LiÃªn, HÃ  Ná»™i\n"

                "Email: @petrolimex.com.vn\n"

                "Äiá»‡n thoáº¡i: (024) 3776-0867\n"

                "Tá»•ng Ä‘Ã i: 1900 54 54 55\n"

                "Website: https://www..com.vn\n\n"

                "Anh/chá»‹ cáº§n há»— trá»£ gÃ¬ thÃªm khÃ´ng áº¡?"

            ))

        elif "Giá» lÃ m viá»‡c" in faq_selected:

            add_message("assistant", (

                "Giá» lÃ m viá»‡c cá»§a :\n\n"

                "Thá»© 2 - Thá»© 6: 8:00 - 17:00\n"

                "Thá»© 7: 8:00 - 12:00\n"

                "Chá»§ nháº­t: Nghá»‰\n\n"

                "Tuy nhiÃªn, trá»£ lÃ½ áº£o sáºµn sÃ ng há»— trá»£ anh/chá»‹ 24/7!\n\n"

                "Anh/chá»‹ cáº§n há»— trá»£ gÃ¬ thÃªm khÃ´ng áº¡?"

            ))

        elif "Má»©c bá»“i thÆ°á»ng" in faq_selected:

            add_message("assistant", (

                "Má»©c bá»“i thÆ°á»ng vÃ  phÃ­ báº£o hiá»ƒm:\n\n"

                "Má»©c bá»“i thÆ°á»ng phá»¥ thuá»™c vÃ o sáº£n pháº©m vÃ  sá»‘ tiá»n báº£o hiá»ƒm ghi trong há»£p Ä‘á»“ng.\n\n"

                "Phi báº£o hiá»ƒm tham kháº£o:\n"

                "- Combo 360 Ã´ tÃ´: 599.000Ä‘/nÄƒm\n"

                "- Combo 360 xe mÃ¡y: 199.000Ä‘/nÄƒm\n"

                "- Family Care: 2-11.2 triá»‡u/nÄƒm\n"

                "- CÃ¡c sáº£n pháº©m khÃ¡c: theo thá»a thuáº­n/biá»ƒu phÃ­\n\n"

                "Anh/chá»‹ cáº§n há»— trá»£ gÃ¬ thÃªm khÃ´ng áº¡?"

            ))

        elif "Há»“ sÆ¡ bá»“i thÆ°á»ng" in faq_selected:

            add_message("assistant", (

                "Há»“ sÆ¡ yÃªu cáº§u bá»“i thÆ°á»ng thÆ°á»ng gá»“m:\n\n"

                "- Giáº¥y yÃªu cáº§u bá»“i thÆ°á»ng\n"

                "- Giáº¥y chá»©ng nháº­n báº£o hiá»ƒm/há»£p Ä‘á»“ng\n"

                "- Giáº¥y tá» thÃ¢n nhÃ¢n (CCCD/CMND)\n"

                "- BiÃªn báº£n sá»± cá»‘ (cÃ´ng an, chá»¯a chÃ¡y, y táº¿...)\n"

                "- Há»“ sÆ¡ y táº¿, bá»‡nh Ã¡n, hÃ³a Ä‘Æ¡n\n"

                "- áº¢nh thiá»‡t háº¡i (náº¿u cÃ³)\n\n"

                "Anh/chá»‹ cáº§n há»— trá»£ gÃ¬ thÃªm khÃ´ng áº¡?"

            ))

        elif "Thá»i gian xá»­ lÃ½" in faq_selected:

            add_message("assistant", (

                "Thá»i gian xá»­ lÃ½ bá»“i thÆ°á»ng :\n\n"

                "- Tiáº¿p nháº­n há»“ sÆ¡: 1-3 ngÃ y lÃ m viá»‡c\n"

                "- Tháº©m Ä‘á»‹nh há»“ sÆ¡: 5-15 ngÃ y lÃ m viá»‡c (tÃ¹y Ä‘á»™ phá»©c táº¡p)\n"

                "- Thanh toÃ¡n bá»“i thÆ°á»ng: trong vÃ²ng 15 ngÃ y sau khi cÃ³ káº¿t luáº­n tháº©m Ä‘á»‹nh\n\n"

                "Anh/chá»‹ cáº§n há»— trá»£ gÃ¬ thÃªm khÃ´ng áº¡?"

            ))

        elif "ÄÃ³ng phÃ­" in faq_selected:

            add_message("assistant", (

                "ÄÃ³ng phÃ­ báº£o hiá»ƒm :\n\n"

                "- Qua ngÃ¢n hÃ ng (chuyá»ƒn khoáº£n)\n"

                "- Qua vÃ­ Ä‘iá»‡n tá»­ (Momo, ZaloPay, VNPay...)\n"

                "- Qua Ä‘áº¡i lÃ½ báº£o hiá»ƒm \n"

                "- Qua tá»•ng Ä‘Ã i 1900 54 54 55 Ä‘á»ƒ Ä‘Æ°á»£c hÆ°á»›ng dáº«n\n\n"

                "Anh/chá»‹ cáº§n há»— trá»£ gÃ¬ thÃªm khÃ´ng áº¡?"

            ))

        elif "khiáº¿u náº¡i" in faq_selected.lower():

            add_message("assistant", (

                "Quy trÃ¬nh khiáº¿u náº¡i bá»“i thÆ°á»ng :\n\n"

                "1. LiÃªn há»‡ Ä‘á»ƒ pháº£n Ã¡nh káº¿t quáº£ tháº©m Ä‘á»‹nh\n"

                "2. sáº½ xem xÃ©t láº¡i há»“ sÆ¡ trong vÃ²ng 15 ngÃ y\n"

                "3. Náº¿u khÃ´ng Ä‘á»“ng Ã½, anh/chá»‹ cÃ³ thá»ƒ khiáº¿u náº¡i lÃªn Cá»¥c Quáº£n lÃ½/Kiem soÃ¡t báº£o hiá»ƒm\n\n"

                "Tá»•ng Ä‘Ã i há»— trá»£: 1900 54 54 55\n\n"

                "Anh/chá»‹ cáº§n há»— trá»£ gÃ¬ thÃªm khÃ´ng áº¡?"

            ))

        elif "nhÃ¢n viÃªn" in faq_selected.lower():

            add_message("assistant", (

                "Äá»ƒ nÃ³i chuyá»‡n vá»›i nhÃ¢n viÃªn , anh/chá»‹ vui lÃ²ng:\n\n"

                "- Gá»i tá»•ng Ä‘Ã i: 1900 54 54 55\n"

                "- Email: @petrolimex.com.vn\n"

                "- Chat trá»±c tiáº¿p táº¡i website: https://www..com.vn\n\n"

                "Anh/chá»‹ cáº§n há»— trá»£ gÃ¬ thÃªm khÃ´ng áº¡?"

            ))

        elif "Khuyáº¿n mÃ£i" in faq_selected or "Æ°u Ä‘Ã£i" in faq_selected.lower():

            add_message("assistant", (

                "ChÆ°Æ¡ng trÃ¬nh khuyáº¿n mÃ£i hiá»‡n táº¡i:\n\n"

                "- thÆ°á»ng cÃ³ chÆ°Æ¡ng trÃ¬nh Æ°u Ä‘Ã£i theo thá»i gian vÃ  Ä‘á»‘i tÆ°á»£ng khÃ¡ch hÃ ng\n\n"

                "- Vui lÃ²ng liÃªn há»‡ tá»•ng Ä‘Ã i 1900 54 54 55 hoáº·c xem website https://www..com.vn\n\n"

                "Anh/chá»‹ cáº§n há»— trá»£ gÃ¬ thÃªm khÃ´ng áº¡?"

            ))

        elif "Há»§y" in faq_selected or "Ä‘á»•i báº£o hiá»ƒm" in faq_selected.lower():

            add_message("assistant", (

                "Há»§y/Ä‘á»•i báº£o hiá»ƒm:\n\n"

                "- Anh/chá»‹ cÃ³ thá»ƒ liÃªn há»‡ Ä‘á»ƒ há»§y hoáº·c Ä‘á»•i sáº£n pháº©m báº£o hiá»ƒm\n"

                "- TÃ¹y thuá»™c Ä‘iá»u kiá»‡n há»£p Ä‘á»“ng, viá»‡c há»§y cÃ³ thá»ƒ cÃ³ phÃ­ tÆ°Æ¡ng á»©ng\n\n"

                "- Tá»•ng Ä‘Ã i: 1900 54 54 55\n\n"

                "Anh/chá»‹ cáº§n há»— trá»£ gÃ¬ thÃªm khÃ´ng áº¡?"

            ))

        elif "Cáº­p nháº­t" in faq_selected:

            add_message("assistant", (

                "Cáº­p nháº­t thÃ´ng tin cÃ¡ nhÃ¢n:\n\n"

                "- Anh/chá»‹ cÃ³ thá»ƒ liÃªn há»‡ Ä‘á»ƒ cáº­p nháº­t thÃ´ng tin (chuyá»ƒn nhÃ , Ä‘á»•i SÄT, Ä‘á»•i tÃªn...)\n"

                "- Tá»•ng Ä‘Ã i: 1900 54 54 55\n"

                "- Email: @petrolimex.com.vn\n\n"

                "Anh/chá»‹ cáº§n há»— trá»£ gÃ¬ thÃªm khÃ´ng áº¡?"

            ))

        st.session_state.waiting_for_continue_choice = True

        st.rerun()



# ============================================================

# CITY CHOICE SELECTBOX â€” Chá»n tá»‰nh/thÃ nh phá»‘ Ä‘á»ƒ tÃ¬m vÄƒn phÃ²ng 

# ============================================================



if st.session_state.waiting_for_city_choice and not st.session_state.current_product and not st.session_state.waiting_for_text:

    city_options = get_all_cities()

    col1, col2 = st.columns([3, 1])

    with col1:

        city_selected = st.selectbox(

            "Chá»n tá»‰nh/thÃ nh phá»‘:",

            city_options,

            key="city_selectbox",

            label_visibility="collapsed",

        )

    with col2:

        st.write("")

    if st.button(" XÃ¡c nháº­n", key="city_confirm_btn", use_container_width=True):

        st.session_state.waiting_for_city_choice = False

        add_message("user", city_selected)

        offices = get_offices_by_city(city_selected)

        if offices:

            office_text = f"Dáº¡! ÄÃ¢y lÃ  danh sÃ¡ch vÄƒn phÃ²ng táº¡i **{city_selected}**:\n\n"

            for i, office in enumerate(offices, 1):

                office_text += f"**{i}. {office['name']}**\n"

                office_text += f"   Äá»‹a chá»‰: {office['address']}\n"

                office_text += f"   Äiá»‡n thoáº¡i: {office['phone']}\n\n"

            office_text += "Anh/chá»‹ cÃ³ thá»ƒ liÃªn há»‡ trá»±c tiáº¿p hoáº·c gá»i tá»•ng Ä‘Ã i **1900 54 54 55** Ä‘á»ƒ Ä‘Æ°á»£c há»— trá»£.\n\n"

            office_text += "Anh/chá»‹ cáº§n há»— trá»£ gÃ¬ thÃªm khÃ´ng áº¡?"

            add_message("assistant", office_text)

        else:

            add_message("assistant", (

                f"Xin lá»—i, tÃ´i chÆ°a tÃ¬m tháº¥y vÄƒn phÃ²ng táº¡i **{city_selected}**.\n\n"

                "Anh/chá»‹ cÃ³ thá»ƒ gá»i tá»•ng Ä‘Ã i 1900 54 54 55 Ä‘á»ƒ Ä‘Æ°á»£c Ä‘á»‹nh vá»‹ vÄƒn phÃ²ng gáº§n nháº¥t.\n\n"

                "Anh/chá»‹ cáº§n há»— trá»£ gÃ¬ thÃªm khÃ´ng áº¡?"

            ))

        st.session_state.waiting_for_continue_choice = True

        st.rerun()



# ============================================================

# PRODUCT CHOICE RADIO BUTTONS â€” Chá»n sáº£n pháº©m tÆ° váº¥n

# ============================================================



if st.session_state.waiting_for_product_choice and not st.session_state.current_product and not st.session_state.waiting_for_text:

    product_options = [p["name"] for p in PRODUCTS]

    col1, col2 = st.columns([3, 1])

    with col1:

        product_selected = st.selectbox(

            "Chá»n sáº£n pháº©m báº£o hiá»ƒm:",

            product_options,

            key="product_tuvan_select",

            label_visibility="collapsed",

        )

    with col2:

        st.write("")

    if st.button(" XÃ¡c nháº­n", key="product_tuvan_confirm_btn", use_container_width=True):

        st.session_state.waiting_for_product_choice = False

        add_message("user", product_selected)

        # Find product info

        selected_p = None

        for p in PRODUCTS:

            if p["name"] == product_selected:

                selected_p = p

                break

        if selected_p:

            info = (

                f"**{selected_p['name']}**\n\n"

                f"PhÃ­: {selected_p['price']}\n\n"

                f"Chi tiáº¿t: {selected_p['url']}\n\n"

            )

            if selected_p.get('description'):

                info += f"MÃ´ táº£: {selected_p['description']}\n\n"

            if selected_p.get('coverage'):

                info += "Pháº¡m vi báº£o vá»‡:\n"

                for c in selected_p['coverage']:

                    info += f"- {c}\n"

                info += "\n"

            if selected_p.get('exclusions'):

                info += "Loáº¡i trá»«:\n"

                for e in selected_p['exclusions']:

                    info += f"- {e}\n"

                info += "\n"

            add_message("assistant", info)

            st.session_state.waiting_for_continue_choice = True

        st.rerun()



# ============================================================

# CONTINUE CHOICE RADIO BUTTONS â€” Anh/chá»‹ cáº§n há»— trá»£ gÃ¬ thÃªm khÃ´ng?

# ============================================================



if st.session_state.waiting_for_continue_choice and not st.session_state.waiting_for_text and not st.session_state.upload_phase:

    continue_options = ["CÃ³", "KhÃ´ng"]

    continue_selected = st.radio(

        "Anh/chá»‹ cáº§n há»— trá»£ gÃ¬ thÃªm khÃ´ng áº¡?",

        continue_options,

        key="continue_radio",

        label_visibility="visible",

    )

    if st.button(" XÃ¡c nháº­n", key="continue_confirm_btn", use_container_width=True):

        st.session_state.waiting_for_continue_choice = False

        add_message("user", continue_selected)

        if continue_selected == "CÃ³":

            st.session_state.current_product = None

            st.session_state.finished = False

            st.session_state.result = None

            st.session_state.q_index = 0

            st.session_state.answers = OrderedDict()

            st.session_state.waiting_for_welcome_choice = True

            add_message("assistant", (

                "Dáº¡! Vui lÃ²ng **chá»n nhu cáº§u há»— trá»£** bÃªn dÆ°á»›i nhÃ©!"

            ))

        else:

            st.session_state.current_product = None

            st.session_state.finished = False

            st.session_state.result = None

            st.session_state.q_index = 0

            st.session_state.answers = OrderedDict()

            add_message("assistant", (

                "Cáº£m Æ¡n anh/chá»‹ Ä‘Ã£ sá»­ dá»¥ng dá»‹ch vá»¥ cá»§a ! ChÃºc anh/chá»‹ má»™t ngÃ y tá»‘t lÃ nh!"

            ))

        st.rerun()



# ============================================================

# RADIO BUTTONS FOR CLAIM QUESTIONS

# ============================================================



if current_product and not st.session_state.finished:

    questions = current_product["claim_questions"]

    if q_index < len(questions):

        q = questions[q_index]

        if "options" in q:

            radio_key = f"q_{q['id']}_radio"

            text_key = f"q_{q['id']}_text"

            st.markdown("**Chá»n Ä‘Ã¡p Ã¡n:**")

            options = q["options"]

            has_khac = any("khÃ¡c" in opt.lower() for opt in options)

            khac_options = [opt for opt in options if "khÃ¡c" in opt.lower()]

            radio_options = list(options)

            selected = st.radio(

                "Chá»n Ä‘Ã¡p Ã¡n:",

                radio_options,

                key=radio_key,

                label_visibility="collapsed",

            )

            other_text = ""

            is_khac_selected = has_khac and selected in khac_options

            if is_khac_selected:

                other_text = st.text_input("Vui lÃ²ng ghi rÃµ:", key=text_key, placeholder="Nháº­p ná»™i dung khÃ¡c...")

            if st.button(" XÃ¡c nháº­n", key=f"q_{q['id']}_btn", use_container_width=True):

                if is_khac_selected:

                    final_answer = other_text.strip() if other_text.strip() else selected

                else:

                    final_answer = selected

                st.session_state.answers[q["id"]] = final_answer

                st.session_state.q_index += 1

                add_message("user", final_answer)

                if st.session_state.q_index >= len(questions):

                    result = evaluate_claim(dict(st.session_state.answers), current_product)

                    st.session_state.result = result

                    st.session_state.finished = True

                st.rerun()



# ============================================================

# SELECTBOX CHO Sáº¢N PHáº¨M (khi waiting_for_text)

# ============================================================



if st.session_state.current_product is None and st.session_state.waiting_for_text:

    st.markdown("**Vui lÃ²ng chá»n loáº¡i báº£o hiá»ƒm:**")

    product_options = [p["name"] for p in PRODUCTS]

    col1, col2 = st.columns([3, 1])

    with col1:

        selected_product = st.selectbox("Chá»n sáº£n pháº©m:", product_options, key="product_select", label_visibility="collapsed")

    with col2:

        st.write("")

        if st.button(" XÃ¡c nháº­n", key="confirm_product"):

            product = None

            for p in PRODUCTS:

                if p["name"] == selected_product:

                    product = p

                    break

            if product:

                add_message("user", selected_product)

                st.session_state.current_product = product

                st.session_state.waiting_for_text = False

                st.session_state.chat_mode = False

                add_message("assistant", (

                    f"ÄÃ£ chá»n: **{product['name']}** \n\n"

                    f"Báº¯t Ä‘áº§u Ä‘Ã¡nh giÃ¡ Ä‘iá»u kiá»‡n tiáº¿p nháº­n bá»“i thÆ°á»ng. Vui lÃ²ng tráº£ lá»i tá»«ng cÃ¢u nhÃ©!\n\n---\n"

                ))

                st.rerun()

    st.markdown("*â†‘ Chá»n sáº£n pháº©m vÃ  báº¥m XÃ¡c nháº­n*")

    user_input = None

else:

    user_input = st.chat_input("Nháº­p tin nháº¯n...")



# ============================================================

# MAIN MESSAGE HANDLER

# ============================================================



if user_input:

    add_message("user", user_input)



    # ============================================================

    # CASE 3: ÄANG TRONG CLAIM FLOW â€” tráº£ lá»i cÃ¢u há»i

    # ============================================================

    if st.session_state.current_product and not st.session_state.finished:

        product = st.session_state.current_product

        questions = product["claim_questions"]

        q = questions[st.session_state.q_index]

        raw_answer = user_input.strip()



        # DÃ¹ng AIML Ä‘á»ƒ match cÃ¢u tráº£ lá»i

        aiml_response = aiml_respond(raw_answer)

        matched_answer = None



        if aiml_response:

            if aiml_response.startswith("__ANSWER__:"):

                matched_answer = aiml_response.replace("__ANSWER__:", "", 1).strip()

            elif aiml_response == "__RESTART__":

                reset_session()

                add_message("assistant", " ÄÃ£ báº¯t Ä‘áº§u láº¡i. Anh/chá»‹ cáº§n há»— trá»£ gÃ¬ áº¡? ")

                st.rerun()

            elif aiml_response.startswith("__CLAIM_REQUEST__"):

                # KhÃ¡ch muá»‘n Ä‘Ã¡nh giÃ¡ láº¡i â†’ chuyá»ƒn sang chá»n sáº£n pháº©m

                st.session_state.waiting_for_text = True

                name_display = st.session_state.customer_name or "anh/chá»‹"

                add_message("assistant", f"Dáº¡ {name_display}! Vui lÃ²ng chá»n loáº¡i báº£o hiá»ƒm á»Ÿ thanh cuá»™n bÃªn dÆ°á»›i. ")

                st.rerun()



        if "options" in q:

            if matched_answer and matched_answer in q["options"]:

                st.session_state.answers[q["id"]] = matched_answer

                st.session_state.q_index += 1

                if st.session_state.q_index >= len(questions):

                    result = evaluate_claim(dict(st.session_state.answers), product)

                    st.session_state.result = result

                    st.session_state.finished = True

                st.rerun()

            else:

                # AIML khÃ´ng match â†’ kiá»ƒm tra raw_answer cÃ³ match option khÃ´ng

                raw_norm = normalize_text(raw_answer)

                matched_opt = None

                for opt in q["options"]:

                    opt_norm = normalize_text(opt)

                    if raw_norm == opt_norm or opt_norm in raw_norm:

                        matched_opt = opt

                        break

                if matched_opt:

                    st.session_state.answers[q["id"]] = matched_opt

                    st.session_state.q_index += 1

                    if st.session_state.q_index >= len(questions):

                        result = evaluate_claim(dict(st.session_state.answers), product)

                        st.session_state.result = result

                        st.session_state.finished = True

                    st.rerun()

                else:

                    add_message("assistant", " Vui lÃ²ng chá»n Ä‘Ã¡p Ã¡n tá»« danh sÃ¡ch bÃªn dÆ°á»›i rá»“i báº¥m **XÃ¡c nháº­n** nhÃ©.")

                    st.rerun()

        else:

            # CÃ¢u há»i type=text (nhÆ° há»i tuá»•i)

            st.session_state.answers[q["id"]] = raw_answer

            st.session_state.q_index += 1

            if st.session_state.q_index >= len(questions):

                result = evaluate_claim(dict(st.session_state.answers), product)

                st.session_state.result = result

                st.session_state.finished = True

            st.rerun()



    # ============================================================

    # CASE 2: Äang waiting_for_text (chá»n sáº£n pháº©m)

    # ============================================================

    elif st.session_state.current_product is None and st.session_state.waiting_for_text:

        # Cho phÃ©p user chat tá»± do, khÃ´ng chá»‰ chá»n tá»« selectbox

        # Kiá»ƒm tra AIML

        aiml_resp = aiml_respond(user_input)



        # Náº¿u AIML tráº£ vá» __CLAIM_REQUEST__ â†’ giá»¯ nguyÃªn selectbox

        if aiml_resp and aiml_resp.startswith("__CLAIM_REQUEST__"):

            pass # Selectbox sáº½ hiá»ƒn thá»‹

        elif aiml_resp and not aiml_resp.startswith("__"):

            # AIML cÃ³ cÃ¢u tráº£ lá»i tá»± nhiÃªn â†’ hiá»ƒn thá»‹

            add_message("assistant", aiml_resp)

            st.rerun()

        else:

            # Kiá»ƒm tra cÃ³ sá»± cá»‘ khÃ´ng

            if has_incident(user_input) or has_claim_request(user_input):

                product = detect_product_smart(user_input)

                if product:

                    st.session_state.current_product = product

                    st.session_state.waiting_for_text = False

                    st.session_state.chat_mode = False

                    name_display = st.session_state.customer_name or "anh/chá»‹"

                    add_message("assistant", (

                        f"Dáº¡ {name_display}! \n\n"

                        f"TÃ´i Ä‘Ã£ xÃ¡c nháº­n sáº£n pháº©m: **{product['name']}**\n\n"

                        f" PhÃ­: {product['price']}\n"

                        f" Chi tiáº¿t: {product['url']}\n\n"

                        f"Báº¯t Ä‘áº§u Ä‘Ã¡nh giÃ¡ Ä‘iá»u kiá»‡n tiáº¿p nháº­n bá»“i thÆ°á»ng nhÃ©!\n\n---\n"

                    ))

                    st.rerun()

                else:

                    add_message("assistant", (

                        "TÃ´i nháº­n tháº¥y anh/chá»‹ Ä‘ang nháº¯c Ä‘áº¿n sá»± cá»‘ báº£o hiá»ƒm. \n"

                        "Tuy nhiÃªn tÃ´i chÆ°a xÃ¡c Ä‘á»‹nh Ä‘Æ°á»£c sáº£n pháº©m cá»¥ thá»ƒ.\n"

                        "Vui lÃ²ng chá»n sáº£n pháº©m tá»« danh sÃ¡ch bÃªn dÆ°á»›i nhÃ©!"

                    ))

                    st.rerun()

            else:

                # Chat tá»± nhiÃªn

                add_message("assistant", (

                    "Anh/chá»‹ cÃ³ thá»ƒ chá»n sáº£n pháº©m báº£o hiá»ƒm tá»« danh sÃ¡ch bÃªn dÆ°á»›i, "

                    "hoáº·c há»i tÃ´i báº¥t cá»© Ä‘iá»u gÃ¬ vá» ! "

                ))

                st.rerun()



    # ============================================================

    # CASE 1: CHAT MODE Tá»° NHIÃŠN (chÆ°a trong claim flow)

    # ============================================================

    elif st.session_state.chat_mode and st.session_state.current_product is None and not st.session_state.waiting_for_text:



        # --- 1city: Intercept city name when waiting_for_city_choice ---
        if st.session_state.waiting_for_city_choice:
            offices = get_offices_by_city(user_input)
            if offices:
                st.session_state.waiting_for_city_choice = False
                matched_city = user_input.strip()
                from offices import OFFICES as _OFFICES_LIST
                import unicodedata as _ud
                def _norm(t):
                    t = _ud.normalize('NFD', t)
                    return ''.join(c for c in t if _ud.category(c) != 'Mn').lower().strip()
                text_n = _norm(user_input)
                for o in _OFFICES_LIST:
                    if o["city_norm"] in text_n or text_n in o["city_norm"]:
                        matched_city = o["city"]
                        break
                    for alt in o.get("alt_names", []):
                        alt_n = _norm(alt)
                        if alt_n in text_n or text_n in alt_n:
                            matched_city = o["city"]
                            break
                office_text = f"Dáº¡! ÄÃ¢y lÃ  danh sÃ¡ch vÄƒn phÃ²ng táº¡i **{matched_city}**:\n\n"
                for i, office in enumerate(offices, 1):
                    office_text += f"**{i}. {office['name']}**\n"
                    office_text += f"   Äá»‹a chá»‰: {office['address']}\n"
                    office_text += f"   Äiá»‡n thoáº¡i: {office['phone']}\n\n"
                office_text += "Anh/chá»‹ cÃ³ thá»ƒ liÃªn há»‡ trá»±c tiáº¿p hoáº·c gá»i tá»•ng Ä‘Ã i **1900 54 54 55** Ä‘á»ƒ Ä‘Æ°á»£c há»— trá»£.\n\n"
                office_text += "Anh/chá»‹ cáº§n há»— trá»£ gÃ¬ thÃªm khÃ´ng áº¡?"
                add_message("assistant", office_text)
                st.session_state.waiting_for_continue_choice = True
                st.rerun()
            else:
                add_message("assistant", (
                    f"TÃ´i chÆ°a nháº­n ra tá»‰nh/thÃ nh phá»‘ tá»« \"{user_input}\". \n\n"
                    "Vui lÃ²ng **chá»n tá»‰nh/thÃ nh phá»‘** tá»« danh sÃ¡ch bÃªn dÆ°á»›i nhÃ©!"
                ))
                st.rerun()

        # --- 1a: ChÆ°a cÃ³ tÃªn ---

        if not st.session_state.customer_name:

            aiml_resp = aiml_respond(user_input)

            greeting = is_greeting(user_input)

            name = extract_name(user_input)

            incident = has_incident(user_input)

            claim_req = has_claim_request(user_input)



            # Thá»­ extract tÃªn trÆ°á»›c

            name = extract_name(user_input)



            # 1. CÃ³ sá»± cá»‘ â†’ há»i cÃ³ muá»‘n Ä‘Ã¡nh giÃ¡ (Æ°u tiÃªn cao nháº¥t)

            if incident or claim_req:

                if name:

                    st.session_state.customer_name = name

                    st.session_state.asked_name = True

                    st.session_state.asked_evaluate = True

                    add_message("assistant", (

                        f"ChÃ o {name}! TÃ´i nghe tháº¥y anh/chá»‹ Ä‘ang gáº·p sá»± cá»‘.\n\n"

                        f"Anh/chá»‹ cÃ³ cáº§n tÃ´i **Ä‘Ã¡nh giÃ¡ Ä‘iá»u kiá»‡n tiáº¿p nháº­n bá»“i thÆ°á»ng** cho sá»± cá»‘ nÃ y khÃ´ng áº¡?\n\n"

                        f"â€¢ GÃµ **cÃ³** Ä‘á»ƒ báº¯t Ä‘áº§u Ä‘Ã¡nh giÃ¡\n"

                        f"â€¢ GÃµ **khÃ´ng** náº¿u chá»‰ muá»‘n há»i thÃªm"

                    ))

                elif st.session_state.customer_name:

                    # ÄÃ£ cÃ³ tÃªn tá»« trÆ°á»›c

                    st.session_state.asked_evaluate = True

                    add_message("assistant", (

                        f"TÃ´i nghe tháº¥y anh/chá»‹ Ä‘ang gáº·p sá»± cá»‘. \n\n"

                        f"Anh/chá»‹ cÃ³ cáº§n tÃ´i **Ä‘Ã¡nh giÃ¡ Ä‘iá»u kiá»‡n tiáº¿p nháº­n bá»“i thÆ°á»ng** cho sá»± cá»‘ nÃ y khÃ´ng áº¡?\n\n"

                        f"â€¢ GÃµ **cÃ³** Ä‘á»ƒ báº¯t Ä‘áº§u Ä‘Ã¡nh giÃ¡\n"

                        f"â€¢ GÃµ **khÃ´ng** náº¿u chá»‰ muá»‘n há»i thÃªm"

                    ))

                else:

                    st.session_state.asked_name = True

                    st.session_state.asked_evaluate = True

                    add_message("assistant", (

                        "TÃ´i nghe tháº¥y anh/chá»‹ Ä‘ang gáº·p sá»± cá»‘. \n\n"

                        "Anh/chá»‹ cho biáº¿t **tÃªn** nhÃ©, tÃ´i sáº½ há»— trá»£ Ä‘Ã¡nh giÃ¡ Ä‘iá»u kiá»‡n tiáº¿p nháº­n bá»“i thÆ°á»ng cho anh/chá»‹!"

                    ))

                st.rerun()



            # 2. CÃ³ tÃªn â†’ set tÃªn, chÃ o há»i

            if name and not st.session_state.customer_name:

                st.session_state.customer_name = name

                st.session_state.asked_name = True

                add_message("assistant", (

                    f"ChÃ o {name}! Ráº¥t vui Ä‘Æ°á»£c gáº·p anh/chá»‹.\n\n"

                    f"TÃ´i cÃ³ thá»ƒ:\n"

                    f"â€¢ TÆ° váº¥n sáº£n pháº©m báº£o hiá»ƒm\n"

                    f"â€¢ Giáº£i Ä‘Ã¡p tháº¯c máº¯c thÆ°á»ng gáº·p\n"

                    f"â€¢ ÄÃ¡nh giÃ¡ Ä‘iá»u kiá»‡n tiáº¿p nháº­n bá»“i thÆ°á»ng\n\n"

                    f"Anh/chá»‹ cáº§n há»— trá»£ gÃ¬ áº¡?"

                ))

                st.rerun()



            # 3. CÃ¢u chÃ o â†’ chÃ o láº¡i + há»i tÃªn (náº¿u chÆ°a cÃ³)

            if greeting:

                if not st.session_state.asked_name:

                    st.session_state.asked_name = True

                    add_message("assistant", (

                        "Xin chÃ o! Cáº£m Æ¡n anh/chá»‹ Ä‘Ã£ liÃªn há»‡ .\n\n"

                        "Anh/chá»‹ cho biáº¿t **tÃªn** Ä‘á»ƒ tÃ´i tiá»‡n há»— trá»£ nhÃ©! "

                    ))

                else:

                    add_message("assistant", (

                        "Xin chÃ o! Cáº£m Æ¡n anh/chá»‹ Ä‘Ã£ liÃªn há»‡ .\n\n"

                        "Anh/chá»‹ cho biáº¿t **tÃªn** nhÃ©, hoáº·c mÃ´ táº£ sá»± cá»‘ "

                        "náº¿u cáº§n Ä‘Ã¡nh giÃ¡ bá»“i thÆ°á»ng!"

                    ))

                st.rerun()



            # 4. AIML tráº£ lá»i tá»± nhiÃªn (khÃ´ng pháº£i pattern Ä‘áº·c biá»‡t)

            if aiml_resp and not aiml_resp.startswith("__"):

                # Náº¿u AIML Ä‘Ã£ set tÃªn (TOI LA * / TOI TEN LA *) â†’ lÆ°u tÃªn tá»« AIML predicate

                if not st.session_state.customer_name:

                    kernel = get_aiml_kernel()

                    if kernel:

                        aiml_name = kernel.getPredicate("customername")

                        if aiml_name:

                            st.session_state.customer_name = aiml_name

                            st.session_state.asked_name = True

                add_message("assistant", aiml_resp)

                st.rerun()



            # 5. AIML tráº£ vá» __CLAIM_REQUEST__

            if aiml_resp and aiml_resp.startswith("__CLAIM_REQUEST__"):

                st.session_state.asked_evaluate = True

                name_display = st.session_state.customer_name or "anh/chá»‹"

                add_message("assistant", (

                    f"Dáº¡ {name_display}! Anh/chá»‹ cÃ³ muá»‘n tÃ´i **Ä‘Ã¡nh giÃ¡ Ä‘iá»u kiá»‡n tiáº¿p nháº­n bá»“i thÆ°á»ng** khÃ´ng áº¡?\n\n"

                    f"â€¢ GÃµ **cÃ³** Ä‘á»ƒ báº¯t Ä‘áº§u\n"

                    f"â€¢ GÃµ **khÃ´ng** náº¿u chÆ°a cáº§n"

                ))

                st.rerun()



            # 6. AIML tráº£ vá» __RESTART__

            if aiml_resp and aiml_resp == "__RESTART__":

                reset_session()

                add_message("assistant", " ÄÃ£ báº¯t Ä‘áº§u láº¡i. Anh/chá»‹ cáº§n há»— trá»£ gÃ¬ áº¡? ")

                st.rerun()



            # 7. Fallback

            if not st.session_state.asked_name:

                st.session_state.asked_name = True

                add_message("assistant", (

                    "Cáº£m Æ¡n anh/chá»‹ Ä‘Ã£ liÃªn há»‡ ! \n\n"

                    "Anh/chá»‹ cho biáº¿t **tÃªn** nhÃ©, hoáº·c mÃ´ táº£ sá»± cá»‘ "

                    "náº¿u cáº§n Ä‘Ã¡nh giÃ¡ bá»“i thÆ°á»ng!"

                ))

            elif not st.session_state.customer_name:

                # Láº§n 2+ â†’ set tÃªn máº·c Ä‘á»‹nh

                st.session_state.customer_name = "KhÃ¡ch hÃ ng"

                add_message("assistant", (

                    "KhÃ´ng sao! TÃ´i cÃ³ thá»ƒ tÆ° váº¥n báº£o hiá»ƒm, "

                    "giáº£i Ä‘Ã¡p tháº¯c máº¯c, hoáº·c Ä‘Ã¡nh giÃ¡ Ä‘iá»u kiá»‡n bá»“i thÆ°á»ng. "

                    "Anh/chá»‹ cáº§n gÃ¬ áº¡?"

                ))

            else:

                name_display = st.session_state.customer_name

                add_message("assistant", (

                    f"{name_display} Æ¡i, tÃ´i chÆ°a hiá»ƒu rÃµ. \n"

                    f"Anh/chá»‹ cáº§n há»— trá»£ gÃ¬ áº¡?"

                ))

            st.rerun()



        # --- 1b: ÄÃ£ cÃ³ tÃªn, Ä‘ang chat tá»± nhiÃªn ---

        else:

            name_display = st.session_state.customer_name

            aiml_resp = aiml_respond(user_input)

            incident = has_incident(user_input)

            claim_req = has_claim_request(user_input)



            # Kiá»ƒm tra user cÃ³ Ä‘á»“ng Ã½ Ä‘Ã¡nh giÃ¡ (sau khi bot há»i "cÃ³ muá»‘n Ä‘Ã¡nh giÃ¡ khÃ´ng")

            if st.session_state.asked_evaluate:

                st.session_state.asked_evaluate = False

                if is_yes(user_input):

                    # Äá»“ng Ã½ â†’ vÃ o claim flow

                    product = detect_product_smart(user_input)

                    # Náº¿u khÃ´ng detect Ä‘Æ°á»£c product tá»« cÃ¢u hiá»‡n táº¡i, thá»­ dÃ¹ng láº¡i input trÆ°á»›c

                    if not product:

                        # Thá»­ search trong cÃ¡c tin nháº¯n gáº§n Ä‘Ã¢y

                        for msg in reversed(st.session_state.messages):

                            if msg["role"] == "user":

                                product = detect_product_smart(msg["content"])

                                if product:

                                    break

                    if product:

                        st.session_state.current_product = product

                        st.session_state.chat_mode = False

                        add_message("assistant", (

                            f"Dáº¡ {name_display}! \n\n"

                            f"Sáº£n pháº©m: **{product['name']}**\n\n"

                            f" PhÃ­: {product['price']}\n"

                            f" Chi tiáº¿t: {product['url']}\n\n"

                            f"Báº¯t Ä‘áº§u Ä‘Ã¡nh giÃ¡ Ä‘iá»u kiá»‡n tiáº¿p nháº­n bá»“i thÆ°á»ng nhÃ©!\n\n---\n"

                        ))

                    else:

                        # KhÃ´ng detect Ä‘Æ°á»£c product â†’ hiá»‡n selectbox

                        st.session_state.waiting_for_text = True

                        add_message("assistant", (

                            f"Dáº¡ {name_display}! Vui lÃ²ng chá»n loáº¡i báº£o hiá»ƒm á»Ÿ thanh cuá»™n bÃªn dÆ°á»›i. "

                        ))

                    st.rerun()

                elif is_no(user_input):

                    # KhÃ´ng muá»‘n Ä‘Ã¡nh giÃ¡ â†’ quay láº¡i chat

                    add_message("assistant", (

                        f"Dáº¡ khÃ´ng sao {name_display}! "

                        f"TÃ´i luÃ´n sáºµn sÃ ng há»— trá»£ khi anh/chá»‹ cáº§n. "

                        f"Anh/chá»‹ muá»‘n há»i gÃ¬ khÃ¡c khÃ´ng áº¡?"

                    ))

                    st.rerun()

                else:

                    # Tráº£ lá»i khÃ´ng rÃµ â†’ há»i láº¡i

                    add_message("assistant", (

                        f"{name_display} Æ¡i, anh/chá»‹ cÃ³ muá»‘n tÃ´i Ä‘Ã¡nh giÃ¡ Ä‘iá»u kiá»‡n tiáº¿p nháº­n bá»“i thÆ°á»ng khÃ´ng áº¡?\n\n"

                        f"â€¢ GÃµ **cÃ³** Ä‘á»ƒ báº¯t Ä‘áº§u\n"

                        f"â€¢ GÃµ **khÃ´ng** náº¿u chÆ°a cáº§n"

                    ))

                    st.session_state.asked_evaluate = True

                    st.rerun()



            # PhÃ¡t hiá»‡n sá»± cá»‘ báº£o hiá»ƒm â†’ há»i cÃ³ muá»‘n Ä‘Ã¡nh giÃ¡

            elif incident or claim_req:

                st.session_state.asked_evaluate = True

                product = detect_product_smart(user_input)

                if product:

                    add_message("assistant", (

                        f"TÃ´i nghe tháº¥y anh/chá»‹ Ä‘ang gáº·p sá»± cá»‘. \n\n"

                        f"CÃ³ váº» nhÆ° anh/chá»‹ Ä‘ang liÃªn quan Ä‘áº¿n sáº£n pháº©m: **{product['name']}**\n\n"

                        f"Anh/chá»‹ cÃ³ cáº§n tÃ´i **Ä‘Ã¡nh giÃ¡ Ä‘iá»u kiá»‡n tiáº¿p nháº­n bá»“i thÆ°á»ng** khÃ´ng áº¡?\n\n"

                        f"â€¢ GÃµ **cÃ³** Ä‘á»ƒ báº¯t Ä‘áº§u Ä‘Ã¡nh giÃ¡\n"

                        f"â€¢ GÃµ **khÃ´ng** náº¿u chá»‰ muá»‘n há»i thÃªm"

                    ))

                else:

                    add_message("assistant", (

                        f"TÃ´i nghe tháº¥y anh/chá»‹ Ä‘ang gáº·p sá»± cá»‘. \n\n"

                        f"Anh/chá»‹ cÃ³ cáº§n tÃ´i **Ä‘Ã¡nh giÃ¡ Ä‘iá»u kiá»‡n tiáº¿p nháº­n bá»“i thÆ°á»ng** khÃ´ng áº¡?\n\n"

                        f"â€¢ GÃµ **cÃ³** Ä‘á»ƒ báº¯t Ä‘áº§u Ä‘Ã¡nh giÃ¡\n"

                        f"â€¢ GÃµ **khÃ´ng** náº¿u chá»‰ muá»‘n há»i thÃªm"

                    ))

                st.rerun()



            # AIML cÃ³ cÃ¢u tráº£ lá»i tá»± nhiÃªn

            elif aiml_resp and not aiml_resp.startswith("__"):

                add_message("assistant", aiml_resp)

                st.rerun()



            # AIML tráº£ vá» __CLAIM_REQUEST__

            elif aiml_resp and aiml_resp.startswith("__CLAIM_REQUEST__"):

                st.session_state.asked_evaluate = True

                add_message("assistant", (

                    f"Dáº¡ {name_display}! Anh/chá»‹ cÃ³ muá»‘n tÃ´i **Ä‘Ã¡nh giÃ¡ Ä‘iá»u kiá»‡n tiáº¿p nháº­n bá»“i thÆ°á»ng** khÃ´ng áº¡?\n\n"

                    f"â€¢ GÃµ **cÃ³** Ä‘á»ƒ báº¯t Ä‘áº§u\n"

                    f"â€¢ GÃµ **khÃ´ng** náº¿u chÆ°a cáº§n"

                ))

                st.rerun()



            # AIML tráº£ vá» __RESTART__

            elif aiml_resp and aiml_resp == "__RESTART__":

                reset_session()

                add_message("assistant", " ÄÃ£ báº¯t Ä‘áº§u láº¡i. Anh/chá»‹ cáº§n há»— trá»£ gÃ¬ áº¡? ")

                st.rerun()



            # Fallback â€” chat tá»± nhiÃªn

            else:

                add_message("assistant", (

                    f"{name_display} Æ¡i, tÃ´i chÆ°a hiá»ƒu rÃµ Ã½ anh/chá»‹. \n\n"

                    f"TÃ´i cÃ³ thá»ƒ:\n"

                    f"â€¢ TÆ° váº¥n sáº£n pháº©m báº£o hiá»ƒm\n"

                    f"â€¢ Giáº£i Ä‘Ã¡p tháº¯c máº¯c thÆ°á»ng gáº·p\n"

                    f"â€¢ ÄÃ¡nh giÃ¡ Ä‘iá»u kiá»‡n tiáº¿p nháº­n bá»“i thÆ°á»ng\n\n"

                    f"Anh/chá»‹ cáº§n há»— trá»£ gÃ¬ áº¡?"

                ))

                st.rerun()



    # ============================================================

    # CASE 4: Claim flow Ä‘Ã£ xong â†’ quay láº¡i chat

    # ============================================================

    elif st.session_state.current_product and st.session_state.finished:

        # Cho phÃ©p user chat tiáº¿p hoáº·c báº¯t Ä‘áº§u láº¡i

        aiml_resp = aiml_respond(user_input)



        if aiml_resp and aiml_resp == "__RESTART__":

            reset_session()

            add_message("assistant", " ÄÃ£ báº¯t Ä‘áº§u láº¡i. Anh/chá»‹ cáº§n há»— trá»£ gÃ¬ áº¡? ")

            st.rerun()

        elif aiml_resp and aiml_resp.startswith("__CLAIM_REQUEST__"):

            reset_session()

            st.session_state.waiting_for_text = True

            name_display = st.session_state.customer_name or "anh/chá»‹"

            add_message("assistant", f"Dáº¡ {name_display}! Vui lÃ²ng chá»n loáº¡i báº£o hiá»ƒm á»Ÿ thanh cuá»™n bÃªn dÆ°á»›i. ")

            st.rerun()

        elif aiml_resp and not aiml_resp.startswith("__"):

            add_message("assistant", aiml_resp)

            st.rerun()

        elif has_incident(user_input) or has_claim_request(user_input):

            # Quay láº¡i Ä‘Ã¡nh giÃ¡ sáº£n pháº©m khÃ¡c

            st.session_state.asked_evaluate = True

            product = detect_product_smart(user_input)

            name_display = st.session_state.customer_name or "anh/chá»‹"

            if product:

                add_message("assistant", (

                    f"Dáº¡ {name_display}! CÃ³ váº» nhÆ° anh/chá»‹ muá»‘n Ä‘Ã¡nh giÃ¡ sáº£n pháº©m: **{product['name']}**\n\n"

                    f"Anh/chá»‹ cÃ³ muá»‘n tÃ´i **Ä‘Ã¡nh giÃ¡ Ä‘iá»u kiá»‡n tiáº¿p nháº­n bá»“i thÆ°á»ng** khÃ´ng áº¡?\n\n"

                    f"â€¢ GÃµ **cÃ³** Ä‘á»ƒ báº¯t Ä‘áº§u\n"

                    f"â€¢ GÃµ **khÃ´ng** náº¿u chÆ°a cáº§n"

                ))

            else:

                add_message("assistant", (

                    f"Anh/chá»‹ cÃ³ muá»‘n tÃ´i **Ä‘Ã¡nh giÃ¡ Ä‘iá»u kiá»‡n tiáº¿p nháº­n bá»“i thÆ°á»ng** khÃ´ng áº¡?\n\n"

                    f"â€¢ GÃµ **cÃ³** Ä‘á»ƒ báº¯t Ä‘áº§u\n"

                    f"â€¢ GÃµ **khÃ´ng** náº¿u chá»‰ muá»‘n há»i thÃªm"

                ))

            st.rerun()

        else:

            # Chat tá»± nhiÃªn sau khi xong claim

            name_display = st.session_state.customer_name or "anh/chá»‹"

            add_message("assistant", (

                f"Cáº£m Æ¡n {name_display}! Anh/chá»‹ cáº§n há»— trá»£ gÃ¬ thÃªm khÃ´ng áº¡? "

                f"CÃ³ thá»ƒ nháº¥n ** Báº¯t Ä‘áº§u láº¡i** Ä‘á»ƒ Ä‘Ã¡nh giÃ¡ sáº£n pháº©m khÃ¡c."

            ))

            st.rerun()



