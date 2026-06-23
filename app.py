# -*- coding: utf-8 -*-

"""

PJICO Insurance - Đánh giá tiếp nhận bồi thường V.0.6

- Bot chat tự nhiên như trợ lý ảo

- Chỉ khi khách nhắc sự cố bảo hiểm → hỏi có muốn đánh giá tiếp nhận bồi thường

- Khách đồng ý → mới vào luồng đánh giá

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



st.set_page_config(

    page_title="PJICO Trợ lý ảo V.0.6",

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

.pjico-header {

    background-color: #002B70; color: white;

    padding: 15px 25px; border-radius: 0 0 10px 10px;

    margin-bottom: 20px; text-align: center;

    display: flex; align-items: center; justify-content: center; gap: 15px;

}

.pjico-header img { height: 50px; }

.pjico-header h1 { color: white; font-size: 22px; margin: 0; font-weight: 700; }

.pjico-header p { color: #FAB68D; font-size: 13px; margin: 5px 0 0 0; }

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

    """Bỏ dấu tiếng Việt, lowercase, strip."""

    if not text: return ""

    text = text.strip().lower()

    text = unicodedata.normalize('NFD', text)

    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')

    return text



def normalize_aiml(text):

    """Bỏ dấu tiếng Việt, UPPERCASE, strip — cho AIML pattern matching."""

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

    # "chưa" riêng → không phải "không" trong ngữ cảnh claim

    if t == "chua" or t.startswith("chua "): return False

    return any(w == t or w in t for w in NO_WORDS)



def match_answer(user_answer, expected):

    ua = normalize_text(user_answer)

    ex = normalize_text(expected)

    if ua == ex: return True

    if ex in ["co", "yes"]: return is_yes(user_answer)

    if ex in ["khong", "no"]: return is_no(user_answer)

    return ex in ua



# Từ khóa phát hiện sự cố bảo hiểm

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



# Từ khóa chỉ khách muốn đánh giá bồi thường trực tiếp

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

    """Kiểm tra xem input có phải là câu chào hay không."""

    t = normalize_text(text)

    t_lower = t.lower().strip()

    for gw in GREETING_WORDS:

        if t_lower == gw or t_lower.startswith(gw + " ") or gw + " " in t_lower:

            has_incident = any(normalize_text(k) in t_lower for k in INCIDENT_KEYWORDS)

            if not has_incident:

                return True

    return False



def has_incident(text):

    """Kiểm tra xem input có nhắc đến sự cố bảo hiểm không."""

    t = normalize_text(text)

    return any(normalize_text(k) in t for k in INCIDENT_KEYWORDS)



def has_claim_request(text):

    """Kiểm tra xem user có trực tiếp yêu cầu đánh giá bồi thường không."""

    t = normalize_text(text)

    return any(normalize_text(k) in t for k in CLAIM_REQUEST_KEYWORDS)



def extract_name(text):

    """Trích xuất tên khách hàng từ input."""

    text_clean = text.strip()

    if is_greeting(text_clean):

        return ""

    # "tôi tên là X", "mình tên là X", "em tên là X"...

    m = re.search(r'(?:t[oô]i|m[iì]nh|em|anh|ch[iị])\s+t[eê]n\s+(?:l[aà]\s+)?([A-Za-zÀ-ỹ]+(?:\s+[A-Za-zÀ-ỹ]+){0,3})', text, re.IGNORECASE)

    if m: return m.group(1).strip()

    # "tên tôi là X", "tên em là X"...

    m = re.search(r't[eê]n\s+(?:t[oô]i|m[iì]nh|em|anh|ch[iị])\s+(?:l[aà]\s+)?([A-Za-zÀ-ỹ]+(?:\s+[A-Za-zÀ-ỹ]+){0,3})', text, re.IGNORECASE)

    if m: return m.group(1).strip()

    # "tên là X"

    m = re.search(r't[eê]n\s+(?:l[aà]\s+)?([A-Za-zÀ-ỹ]+(?:\s+[A-Za-zÀ-ỹ]+){0,3})', text, re.IGNORECASE)

    if m: return m.group(1).strip()

    # "tôi là X", "mình là X", "em là X"...

    m = re.search(r'(?:t[oô]i|m[iì]nh|em)\s+l[aà]\s+([A-Za-zÀ-ỹ]+(?:\s+[A-Za-zÀ-ỹ]+){0,3})', text, re.IGNORECASE)

    if m: return m.group(1).strip()

    # Nếu input ngắn (1-4 từ), không chứa sự cố, không phải câu hỏi → có thể là tên

    words = text_clean.split()

    text_norm = normalize_text(text_clean)

    has_inc = any(normalize_text(k) in text_norm for k in INCIDENT_KEYWORDS)

    # Kiểm tra có phải câu hỏi không (có dấu ?)

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

    "hoc_sinh_sinh_vien": ["hoc sinh", "sinh vien", "học sinh", "sinh viên", "bao hiem hoc sinh", "bao hiem sinh vien", "24/24 hoc sinh", "tai nan hoc sinh"],

    "du_lich_trong_nuoc": ["du lich", "du lich trong nuoc", "bao hiem du lich", "travel", "nghỉ mat", "tham quan"],

    "du_lich_quoc_te": ["du lich quoc te", "bao hiem du lich quoc te", "travel international", "quoc te", "nuoc ngoai"],

    "cham_soc_suc_khoe_y_te": ["cham soc suc khoe", "ho tro y te", "suc khoe", "y te", "chăm sóc sức khỏe", "hỗ trợ y tế", "tai nan 383", "bao hiem tai nan"],

    "care_plus": ["care plus", "careplus", "chăm sóc sức khỏe quốc tế", "cham soc suc khoe quoc te", "suc khoe quoc te", "y te quoc te"],

    "trach_nhiem_cong_cong": ["trach nhiem cong cong", "trách nhiệm công cộng", "cong cong", "công cộng", "public liability"],

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

    if "chat_mode" not in st.session_state: st.session_state.chat_mode = True # True = chat tự nhiên

    if "log_dir" not in st.session_state:

        st.session_state.log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "claim_logs")

    if "waiting_for_welcome_choice" not in st.session_state: st.session_state.waiting_for_welcome_choice = False
    if "waiting_for_product_choice" not in st.session_state: st.session_state.waiting_for_product_choice = False
    st.session_state.waiting_for_faq_choice = False
    if "waiting_for_faq_choice" not in st.session_state: st.session_state.waiting_for_faq_choice = False
    if "waiting_for_product_choice" not in st.session_state: st.session_state.waiting_for_product_choice = False



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

    """Gửi input qua AIML kernel, trả về response."""

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

        reasons.append(f" Tuổi của người được bảo hiểm là {age}, không nằm trong phạm vi ({min_age}-{max_age} tuổi) → Không đạt điều kiện")

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

                reasons.append(f"Chưa trả lời câu hỏi: {q['question']}")

                passed = False

            continue

        answer = answers[qid]

        fail_if = q.get("fail_if")

        if fail_if and match_answer(answer, fail_if):

            passed = False

            failed.append(qid)

            reasons.append(f" {q['question']} → Trả lời: '{answer}' → Không đạt điều kiện tiếp nhận bồi thường")

    return {"passed": passed, "reasons": reasons, "failed_questions": failed}



def save_claim_log(product, answers, result):

    os.makedirs(st.session_state.log_dir, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    safe = re.sub(r'[^\w]', '_', st.session_state.customer_name or "khach_hang")

    if result.get("passed"):

        sub_dir = os.path.join(st.session_state.log_dir, "được_thông_qua")

    else:

        sub_dir = os.path.join(st.session_state.log_dir, "chưa_được_thông_qua")

    os.makedirs(sub_dir, exist_ok=True)

    fp = os.path.join(sub_dir, f"claim_{safe}_{product['id']}_{ts}.json")

    log = {"timestamp": datetime.now().isoformat(), "customer_name": st.session_state.customer_name,

           "product": {"id": product["id"], "name": product["name"], "url": product["url"]},

           "answers": dict(answers), "result": result}

    with open(fp, "w", encoding="utf-8") as f:

        json.dump(log, f, ensure_ascii=False, indent=2)

    return fp



def reset_session():

    """Reset về trạng thái chat tự nhiên, giữ tên khách hàng."""

    st.session_state.messages = []

    st.session_state.current_product = None

    st.session_state.q_index = 0

    st.session_state.answers = OrderedDict()

    st.session_state.finished = False

    st.session_state.result = None

    st.session_state.started = False

    st.session_state.waiting_for_text = False

    st.session_state.waiting_for_product_choice = False

    st.session_state.asked_evaluate = False

    st.session_state.chat_mode = True



def full_reset():

    """Reset hoàn toàn, xóa cả tên."""

    reset_session()

    st.session_state.customer_name = ""

    st.session_state.asked_name = False



# ============================================================

# SIDEBAR

# ============================================================



with st.sidebar:

    _logo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "pjico_logo.png")

    if os.path.exists(_logo):

        st.image(_logo, width=200)

    st.markdown("## PJICO Trợ lý ảo")

    st.markdown("### Version 0.6")

    st.markdown("---")

    st.markdown("### Sản phẩm bảo hiểm:")

    for p in PRODUCTS:

        st.markdown(f"**{p['name']}**")

        st.caption(f" {p['price']}")

        st.caption(f" [Link]({p['url']})")

        st.markdown("")

    st.markdown("---")

    if st.button(" Bắt đầu lại"):

        full_reset()

        st.rerun()

    st.markdown("---")

    st.markdown("### Thư mục log:")

    st.code(st.session_state.log_dir)

    if os.path.exists(st.session_state.log_dir):

        passed_dir = os.path.join(st.session_state.log_dir, "được_thông_qua")

        failed_dir = os.path.join(st.session_state.log_dir, "chưa_được_thông_qua")

        passed_files = [f for f in os.listdir(passed_dir) if f.endswith(".json")] if os.path.exists(passed_dir) else []

        failed_files = [f for f in os.listdir(failed_dir) if f.endswith(".json")] if os.path.exists(failed_dir) else []

        st.metric(" Được thông qua", len(passed_files))

        st.metric(" Chưa được thông qua", len(failed_files))



# ============================================================

# HEADER

# ============================================================



_logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "pjico_logo.png")

_logo_html = f'<img src="file/{_logo_path}" alt="PJICO">' if os.path.exists(_logo_path) else ''

st.markdown(f'<div class="pjico-header">{_logo_html}<div><h1>BẢO HIỂM PJICO</h1><p>Tổng Công ty Cổ phần Bảo hiểm Petrolimex | Trợ lý ảo V.0.6</p></div></div>', unsafe_allow_html=True)

st.markdown("---")



# ============================================================

# WELCOME MESSAGE

# ============================================================



if not st.session_state.started:

    add_message("assistant", (

        "Xin chào! Tôi là trợ lý ảo PJICO. \n\n"

        "Tôi có thể hỗ trợ anh/chị các nhu cầu sau.\n"

        "Vui lòng **chọn một lựa chọn** bên dưới nhé! "

    ))

    st.session_state.started = True

    st.session_state.waiting_for_welcome_choice = True



# ============================================================

# AUTO-RENDER QUESTIONS / RESULTS (khi đang trong claim flow)

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

            prompt = f"**Câu {q_index + 1}/{len(questions)}:** {q['question']}"

            add_message("assistant", prompt)



elif current_product and st.session_state.finished and st.session_state.result:

    last_msg = st.session_state.messages[-1] if st.session_state.messages else None

    if not (last_msg and last_msg["role"] == "assistant" and "KẾT QUẢ" in last_msg["content"]):

        result = st.session_state.result

        product = current_product

        if result["passed"]:

            verdict = " **ĐỦ ĐIỀU KIỆN TIẾP NHẬN BỒI THƯỜNG**"

            detail = "Hồ sơ của anh/chị đã đủ điều kiện để tiếp nhận bồi thường. Vui lòng liên hệ PJICO để được hướng dẫn nộp hồ sơ chính thức."

        else:

            verdict = " **KHÔNG ĐỦ ĐIỀU KIỆN TIẾP NHẬN BỒI THƯỜNG**"

            detail = "Dựa trên thông tin cung cấp, hồ sơ chưa đủ điều kiện để tiếp nhận bồi thường.\n\n**Lý do:**\n"

            for r in result["reasons"]:

                detail += f"- {r}\n"

        summary = f"""

---

## KẾT QUẢ ĐÁNH GIÁ ĐIỀU KIỆN TIẾP NHẬN BỒI THƯỜNG



**Sản phẩm:** {product['name']}



{verdict}



{detail}



**Tóm tắt câu trả lời:**

"""

        for q in product["claim_questions"]:

            ans = st.session_state.answers.get(q["id"], "(chưa trả lời)")

            summary += f"- **{q['question']}**: {ans}\n"

        log_path = save_claim_log(product, dict(st.session_state.answers), result)

        summary += f"\n Thông tin đã lưu: `{os.path.basename(log_path)}`\n"

        summary += "\nAnh/chị có muốn đánh giá sản phẩm khác không? Nhấn ** Bắt đầu lại** ở sidebar."

        add_message("assistant", summary)



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

            label=" Tải kết quả (JSON)",

            data=log_json.encode("utf-8"),

            file_name=filename,

            mime="application/json",

            use_container_width=True,

        )

        st.download_button(

            label=" Tải kết quả (Text)",

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

# WELCOME RADIO BUTTONS — Chọn nhu cầu hỗ trợ

# ============================================================



if st.session_state.waiting_for_welcome_choice and not st.session_state.current_product and not st.session_state.waiting_for_text:

    welcome_options = [

        " Tư vấn các sản phẩm bảo hiểm",

        " Giải đáp thắc mắc về bồi thường",

        " Đánh giá điều kiện tiếp nhận bồi thường",

    ]

    welcome_selected = st.radio(

        "Chọn nhu cầu hỗ trợ:",

        welcome_options,

        key="welcome_radio",

        label_visibility="collapsed",

    )

    if st.button(" Xác nhận", key="welcome_confirm_btn", use_container_width=True):

        st.session_state.waiting_for_welcome_choice = False

        add_message("user", welcome_selected)

        if "Đánh giá điều kiện tiếp nhận" in welcome_selected:

            st.session_state.asked_evaluate = True

            st.session_state.waiting_for_text = True

            add_message("assistant", (

                "Dạ! Anh/chị muốn **đánh giá điều kiện tiếp nhận bồi thường**. \n\n"

                "Vui lòng chọn loại bảo hiểm ở thanh cuộn bên dưới nhé!"

            ))

        elif "Tư vấn" in welcome_selected:

            st.session_state.waiting_for_product_choice = True

            add_message("assistant", (

                "Dạ! Tôi có thể tư vấn về các sản phẩm bảo hiểm PJICO.\n\n"

                "Vui lòng **chọn sản phẩm** bên dưới để biết thêm chi tiết!"

            ))

        elif "Giải đáp" in welcome_selected:

            st.session_state.waiting_for_faq_choice = True

            add_message("assistant", (

                "Dạ! Tôi có thể giải đáp thắc mắc của anh/chị.\n\n"

                "Vui lòng **chọn chủ đề** bên dưới để biết thêm chi tiết!"

            ))


# ============================================================

# FAQ CHOICE RADIO BUTTONS — Chọn chủ đề giải đáp

# ============================================================



if st.session_state.waiting_for_faq_choice and not st.session_state.current_product and not st.session_state.waiting_for_text and not st.session_state.waiting_for_product_choice:

    faq_options = [

        "Quy trình bồi thường PJICO",

        "Thông tin liên hệ",

        "Giờ làm việc",

        "Mức bồi thường, phí bảo hiểm",

    ]

    faq_selected = st.radio(

        "Chọn chủ đề:",

        faq_options,

        key="faq_radio",

        label_visibility="collapsed",

    )

    if st.button(" Xác nhận", key="faq_confirm_btn", use_container_width=True):

        st.session_state.waiting_for_faq_choice = False

        add_message("user", faq_selected)

        if "Quy trình" in faq_selected:

            add_message("assistant", (

                "Quy trình bồi thường PJICO:\n\n"

                "1. Thông báo sự cố cho PJICO (trong thời hạn quy định)\n"

                "2. Chuẩn bị hồ sơ yêu cầu bồi thường\n"

                "3. PJICO tiếp nhận và thẩm định hồ sơ\n"

                "4. Thanh toán bồi thường\n\n"

                "Anh/chị cần hỗ trợ gì thêm không ạ?"

            ))

        elif "Thông tin liên hệ" in faq_selected:

            add_message("assistant", (

                "Thông tin liên hệ PJICO:\n\n"

                "Tổng đài: 1900 5555 58\n"

                "Website: https://www.pjico.com.vn\n"

                "Email: info@pjico.com.vn\n"

                "Trụ sở chính: Tầng 8, tòa nhà VPI, 218 Nguyễn Trãi, Thanh Xuân, Hà Nội\n\n"

                "Anh/chị cần hỗ trợ gì thêm không ạ?"

            ))

        elif "Giờ làm việc" in faq_selected:

            add_message("assistant", (

                "Giờ làm việc của PJICO:\n\n"

                "Thứ 2 - Thứ 6: 8:00 - 17:00\n"

                "Thứ 7: 8:00 - 12:00\n"

                "Chủ nhật: Nghỉ\n\n"

                "Tuy nhiên, trợ lý ảo sẵn sàng hỗ trợ anh/chị 24/7!\n\n"

                "Anh/chị cần hỗ trợ gì thêm không ạ?"

            ))

        elif "Mức bồi thường" in faq_selected:

            add_message("assistant", (

                "Mức bồi thường và phí bảo hiểm:\n\n"

                "Mức bồi thường phụ thuộc vào sản phẩm và số tiền bảo hiểm ghi trong hợp đồng.\n\n"

                "Phi bảo hiểm tham khảo:\n"

                "- Combo 360 ô tô: 599.000đ/năm\n"

                "- Combo 360 xe máy: 199.000đ/năm\n"

                "- Family Care: 2-11.2 triệu/năm\n"

                "- Các sản phẩm khác: theo thỏa thuận/biểu phí\n\n"

                "Anh/chị cần hỗ trợ gì thêm không ạ?"

            ))

        st.rerun()



# ============================================================

# PRODUCT CHOICE RADIO BUTTONS — Chọn sản phẩm tư vấn

# ============================================================



if st.session_state.waiting_for_product_choice and not st.session_state.current_product and not st.session_state.waiting_for_text:

    product_options = [p["name"] for p in PRODUCTS]

    col1, col2 = st.columns([3, 1])

    with col1:

        product_selected = st.selectbox(

            "Chọn sản phẩm bảo hiểm:",

            product_options,

            key="product_tuvan_select",

            label_visibility="collapsed",

        )

    with col2:

        st.write("")

    if st.button(" Xác nhận", key="product_tuvan_confirm_btn", use_container_width=True):

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

                f"Phí: {selected_p['price']}\n\n"

                f"Chi tiết: {selected_p['url']}\n\n"

            )

            if selected_p.get('description'):

                info += f"Mô tả: {selected_p['description']}\n\n"

            if selected_p.get('coverage'):

                info += "Phạm vi bảo vệ:\n"

                for c in selected_p['coverage']:

                    info += f"- {c}\n"

                info += "\n"

            if selected_p.get('exclusions'):

                info += "Loại trừ:\n"

                for e in selected_p['exclusions']:

                    info += f"- {e}\n"

                info += "\n"

            add_message("assistant", info)

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

            st.markdown("**Chọn đáp án:**")

            options = q["options"]

            has_khac = any("khác" in opt.lower() for opt in options)

            khac_options = [opt for opt in options if "khác" in opt.lower()]

            radio_options = list(options)

            selected = st.radio(

                "Chọn đáp án:",

                radio_options,

                key=radio_key,

                label_visibility="collapsed",

            )

            other_text = ""

            is_khac_selected = has_khac and selected in khac_options

            if is_khac_selected:

                other_text = st.text_input("Vui lòng ghi rõ:", key=text_key, placeholder="Nhập nội dung khác...")

            if st.button(" Xác nhận", key=f"q_{q['id']}_btn", use_container_width=True):

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

# SELECTBOX CHO SẢN PHẨM (khi waiting_for_text)

# ============================================================



if st.session_state.current_product is None and st.session_state.waiting_for_text:

    st.markdown("**Vui lòng chọn loại bảo hiểm:**")

    product_options = [p["name"] for p in PRODUCTS]

    col1, col2 = st.columns([3, 1])

    with col1:

        selected_product = st.selectbox("Chọn sản phẩm:", product_options, key="product_select", label_visibility="collapsed")

    with col2:

        st.write("")

        if st.button(" Xác nhận", key="confirm_product"):

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

                    f"Đã chọn: **{product['name']}** \n\n"

                    f"Bắt đầu đánh giá điều kiện tiếp nhận bồi thường. Vui lòng trả lời từng câu nhé!\n\n---\n"

                ))

                st.rerun()

    st.markdown("*↑ Chọn sản phẩm và bấm Xác nhận*")

    user_input = None

else:

    user_input = st.chat_input("Nhập tin nhắn...")



# ============================================================

# MAIN MESSAGE HANDLER

# ============================================================



if user_input:

    add_message("user", user_input)



    # ============================================================

    # CASE 3: ĐANG TRONG CLAIM FLOW — trả lời câu hỏi

    # ============================================================

    if st.session_state.current_product and not st.session_state.finished:

        product = st.session_state.current_product

        questions = product["claim_questions"]

        q = questions[st.session_state.q_index]

        raw_answer = user_input.strip()



        # Dùng AIML để match câu trả lời

        aiml_response = aiml_respond(raw_answer)

        matched_answer = None



        if aiml_response:

            if aiml_response.startswith("__ANSWER__:"):

                matched_answer = aiml_response.replace("__ANSWER__:", "", 1).strip()

            elif aiml_response == "__RESTART__":

                reset_session()

                add_message("assistant", " Đã bắt đầu lại. Anh/chị cần hỗ trợ gì ạ? ")

                st.rerun()

            elif aiml_response.startswith("__CLAIM_REQUEST__"):

                # Khách muốn đánh giá lại → chuyển sang chọn sản phẩm

                st.session_state.waiting_for_text = True

                name_display = st.session_state.customer_name or "anh/chị"

                add_message("assistant", f"Dạ {name_display}! Vui lòng chọn loại bảo hiểm ở thanh cuộn bên dưới. ")

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

                # AIML không match → kiểm tra raw_answer có match option không

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

                    add_message("assistant", " Vui lòng chọn đáp án từ danh sách bên dưới rồi bấm **Xác nhận** nhé.")

                    st.rerun()

        else:

            # Câu hỏi type=text (như hỏi tuổi)

            st.session_state.answers[q["id"]] = raw_answer

            st.session_state.q_index += 1

            if st.session_state.q_index >= len(questions):

                result = evaluate_claim(dict(st.session_state.answers), product)

                st.session_state.result = result

                st.session_state.finished = True

            st.rerun()



    # ============================================================

    # CASE 2: Đang waiting_for_text (chọn sản phẩm)

    # ============================================================

    elif st.session_state.current_product is None and st.session_state.waiting_for_text:

        # Cho phép user chat tự do, không chỉ chọn từ selectbox

        # Kiểm tra AIML

        aiml_resp = aiml_respond(user_input)



        # Nếu AIML trả về __CLAIM_REQUEST__ → giữ nguyên selectbox

        if aiml_resp and aiml_resp.startswith("__CLAIM_REQUEST__"):

            pass # Selectbox sẽ hiển thị

        elif aiml_resp and not aiml_resp.startswith("__"):

            # AIML có câu trả lời tự nhiên → hiển thị

            add_message("assistant", aiml_resp)

            st.rerun()

        else:

            # Kiểm tra có sự cố không

            if has_incident(user_input) or has_claim_request(user_input):

                product = detect_product_smart(user_input)

                if product:

                    st.session_state.current_product = product

                    st.session_state.waiting_for_text = False

                    st.session_state.chat_mode = False

                    name_display = st.session_state.customer_name or "anh/chị"

                    add_message("assistant", (

                        f"Dạ {name_display}! \n\n"

                        f"Tôi đã xác nhận sản phẩm: **{product['name']}**\n\n"

                        f" Phí: {product['price']}\n"

                        f" Chi tiết: {product['url']}\n\n"

                        f"Bắt đầu đánh giá điều kiện tiếp nhận bồi thường nhé!\n\n---\n"

                    ))

                    st.rerun()

                else:

                    add_message("assistant", (

                        "Tôi nhận thấy anh/chị đang nhắc đến sự cố bảo hiểm. \n"

                        "Tuy nhiên tôi chưa xác định được sản phẩm cụ thể.\n"

                        "Vui lòng chọn sản phẩm từ danh sách bên dưới nhé!"

                    ))

                    st.rerun()

            else:

                # Chat tự nhiên

                add_message("assistant", (

                    "Anh/chị có thể chọn sản phẩm bảo hiểm từ danh sách bên dưới, "

                    "hoặc hỏi tôi bất cứ điều gì về PJICO! "

                ))

                st.rerun()



    # ============================================================

    # CASE 1: CHAT MODE TỰ NHIÊN (chưa trong claim flow)

    # ============================================================

    elif st.session_state.chat_mode and st.session_state.current_product is None and not st.session_state.waiting_for_text:



        # --- 1a: Chưa có tên ---

        if not st.session_state.customer_name:

            aiml_resp = aiml_respond(user_input)

            greeting = is_greeting(user_input)

            name = extract_name(user_input)

            incident = has_incident(user_input)

            claim_req = has_claim_request(user_input)



            # Thử extract tên trước

            name = extract_name(user_input)



            # 1. Có sự cố → hỏi có muốn đánh giá (ưu tiên cao nhất)

            if incident or claim_req:

                if name:

                    st.session_state.customer_name = name

                    st.session_state.asked_name = True

                    st.session_state.asked_evaluate = True

                    add_message("assistant", (

                        f"Chào {name}! Tôi nghe thấy anh/chị đang gặp sự cố.\n\n"

                        f"Anh/chị có cần tôi **đánh giá điều kiện tiếp nhận bồi thường** cho sự cố này không ạ?\n\n"

                        f"• Gõ **có** để bắt đầu đánh giá\n"

                        f"• Gõ **không** nếu chỉ muốn hỏi thêm"

                    ))

                elif st.session_state.customer_name:

                    # Đã có tên từ trước

                    st.session_state.asked_evaluate = True

                    add_message("assistant", (

                        f"Tôi nghe thấy anh/chị đang gặp sự cố. \n\n"

                        f"Anh/chị có cần tôi **đánh giá điều kiện tiếp nhận bồi thường** cho sự cố này không ạ?\n\n"

                        f"• Gõ **có** để bắt đầu đánh giá\n"

                        f"• Gõ **không** nếu chỉ muốn hỏi thêm"

                    ))

                else:

                    st.session_state.asked_name = True

                    st.session_state.asked_evaluate = True

                    add_message("assistant", (

                        "Tôi nghe thấy anh/chị đang gặp sự cố. \n\n"

                        "Anh/chị cho biết **tên** nhé, tôi sẽ hỗ trợ đánh giá điều kiện tiếp nhận bồi thường cho anh/chị!"

                    ))

                st.rerun()



            # 2. Có tên → set tên, chào hỏi

            if name and not st.session_state.customer_name:

                st.session_state.customer_name = name

                st.session_state.asked_name = True

                add_message("assistant", (

                    f"Chào {name}! Rất vui được gặp anh/chị.\n\n"

                    f"Tôi có thể:\n"

                    f"• Tư vấn sản phẩm bảo hiểm\n"

                    f"• Giải đáp thắc mắc về bồi thường\n"

                    f"• Đánh giá điều kiện tiếp nhận bồi thường\n\n"

                    f"Anh/chị cần hỗ trợ gì ạ?"

                ))

                st.rerun()



            # 3. Câu chào → chào lại + hỏi tên (nếu chưa có)

            if greeting:

                if not st.session_state.asked_name:

                    st.session_state.asked_name = True

                    add_message("assistant", (

                        "Xin chào! Cảm ơn anh/chị đã liên hệ PJICO.\n\n"

                        "Anh/chị cho biết **tên** để tôi tiện hỗ trợ nhé! "

                    ))

                else:

                    add_message("assistant", (

                        "Xin chào! Cảm ơn anh/chị đã liên hệ PJICO.\n\n"

                        "Anh/chị cho biết **tên** nhé, hoặc mô tả sự cố "

                        "nếu cần đánh giá bồi thường!"

                    ))

                st.rerun()



            # 4. AIML trả lời tự nhiên (không phải pattern đặc biệt)

            if aiml_resp and not aiml_resp.startswith("__"):

                # Nếu AIML đã set tên (TOI LA * / TOI TEN LA *) → lưu tên từ AIML predicate

                if not st.session_state.customer_name:

                    kernel = get_aiml_kernel()

                    if kernel:

                        aiml_name = kernel.getPredicate("customername")

                        if aiml_name:

                            st.session_state.customer_name = aiml_name

                            st.session_state.asked_name = True

                add_message("assistant", aiml_resp)

                st.rerun()



            # 5. AIML trả về __CLAIM_REQUEST__

            if aiml_resp and aiml_resp.startswith("__CLAIM_REQUEST__"):

                st.session_state.asked_evaluate = True

                name_display = st.session_state.customer_name or "anh/chị"

                add_message("assistant", (

                    f"Dạ {name_display}! Anh/chị có muốn tôi **đánh giá điều kiện tiếp nhận bồi thường** không ạ?\n\n"

                    f"• Gõ **có** để bắt đầu\n"

                    f"• Gõ **không** nếu chưa cần"

                ))

                st.rerun()



            # 6. AIML trả về __RESTART__

            if aiml_resp and aiml_resp == "__RESTART__":

                reset_session()

                add_message("assistant", " Đã bắt đầu lại. Anh/chị cần hỗ trợ gì ạ? ")

                st.rerun()



            # 7. Fallback

            if not st.session_state.asked_name:

                st.session_state.asked_name = True

                add_message("assistant", (

                    "Cảm ơn anh/chị đã liên hệ PJICO! \n\n"

                    "Anh/chị cho biết **tên** nhé, hoặc mô tả sự cố "

                    "nếu cần đánh giá bồi thường!"

                ))

            elif not st.session_state.customer_name:

                # Lần 2+ → set tên mặc định

                st.session_state.customer_name = "Khách hàng"

                add_message("assistant", (

                    "Không sao! Tôi có thể tư vấn bảo hiểm, "

                    "giải đáp thắc mắc, hoặc đánh giá điều kiện bồi thường. "

                    "Anh/chị cần gì ạ?"

                ))

            else:

                name_display = st.session_state.customer_name

                add_message("assistant", (

                    f"{name_display} ơi, tôi chưa hiểu rõ. \n"

                    f"Anh/chị cần hỗ trợ gì ạ?"

                ))

            st.rerun()



        # --- 1b: Đã có tên, đang chat tự nhiên ---

        else:

            name_display = st.session_state.customer_name

            aiml_resp = aiml_respond(user_input)

            incident = has_incident(user_input)

            claim_req = has_claim_request(user_input)



            # Kiểm tra user có đồng ý đánh giá (sau khi bot hỏi "có muốn đánh giá không")

            if st.session_state.asked_evaluate:

                st.session_state.asked_evaluate = False

                if is_yes(user_input):

                    # Đồng ý → vào claim flow

                    product = detect_product_smart(user_input)

                    # Nếu không detect được product từ câu hiện tại, thử dùng lại input trước

                    if not product:

                        # Thử search trong các tin nhắn gần đây

                        for msg in reversed(st.session_state.messages):

                            if msg["role"] == "user":

                                product = detect_product_smart(msg["content"])

                                if product:

                                    break

                    if product:

                        st.session_state.current_product = product

                        st.session_state.chat_mode = False

                        add_message("assistant", (

                            f"Dạ {name_display}! \n\n"

                            f"Sản phẩm: **{product['name']}**\n\n"

                            f" Phí: {product['price']}\n"

                            f" Chi tiết: {product['url']}\n\n"

                            f"Bắt đầu đánh giá điều kiện tiếp nhận bồi thường nhé!\n\n---\n"

                        ))

                    else:

                        # Không detect được product → hiện selectbox

                        st.session_state.waiting_for_text = True

                        add_message("assistant", (

                            f"Dạ {name_display}! Vui lòng chọn loại bảo hiểm ở thanh cuộn bên dưới. "

                        ))

                    st.rerun()

                elif is_no(user_input):

                    # Không muốn đánh giá → quay lại chat

                    add_message("assistant", (

                        f"Dạ không sao {name_display}! "

                        f"Tôi luôn sẵn sàng hỗ trợ khi anh/chị cần. "

                        f"Anh/chị muốn hỏi gì khác không ạ?"

                    ))

                    st.rerun()

                else:

                    # Trả lời không rõ → hỏi lại

                    add_message("assistant", (

                        f"{name_display} ơi, anh/chị có muốn tôi đánh giá điều kiện tiếp nhận bồi thường không ạ?\n\n"

                        f"• Gõ **có** để bắt đầu\n"

                        f"• Gõ **không** nếu chưa cần"

                    ))

                    st.session_state.asked_evaluate = True

                    st.rerun()



            # Phát hiện sự cố bảo hiểm → hỏi có muốn đánh giá

            elif incident or claim_req:

                st.session_state.asked_evaluate = True

                product = detect_product_smart(user_input)

                if product:

                    add_message("assistant", (

                        f"Tôi nghe thấy anh/chị đang gặp sự cố. \n\n"

                        f"Có vẻ như anh/chị đang liên quan đến sản phẩm: **{product['name']}**\n\n"

                        f"Anh/chị có cần tôi **đánh giá điều kiện tiếp nhận bồi thường** không ạ?\n\n"

                        f"• Gõ **có** để bắt đầu đánh giá\n"

                        f"• Gõ **không** nếu chỉ muốn hỏi thêm"

                    ))

                else:

                    add_message("assistant", (

                        f"Tôi nghe thấy anh/chị đang gặp sự cố. \n\n"

                        f"Anh/chị có cần tôi **đánh giá điều kiện tiếp nhận bồi thường** không ạ?\n\n"

                        f"• Gõ **có** để bắt đầu đánh giá\n"

                        f"• Gõ **không** nếu chỉ muốn hỏi thêm"

                    ))

                st.rerun()



            # AIML có câu trả lời tự nhiên

            elif aiml_resp and not aiml_resp.startswith("__"):

                add_message("assistant", aiml_resp)

                st.rerun()



            # AIML trả về __CLAIM_REQUEST__

            elif aiml_resp and aiml_resp.startswith("__CLAIM_REQUEST__"):

                st.session_state.asked_evaluate = True

                add_message("assistant", (

                    f"Dạ {name_display}! Anh/chị có muốn tôi **đánh giá điều kiện tiếp nhận bồi thường** không ạ?\n\n"

                    f"• Gõ **có** để bắt đầu\n"

                    f"• Gõ **không** nếu chưa cần"

                ))

                st.rerun()



            # AIML trả về __RESTART__

            elif aiml_resp and aiml_resp == "__RESTART__":

                reset_session()

                add_message("assistant", " Đã bắt đầu lại. Anh/chị cần hỗ trợ gì ạ? ")

                st.rerun()



            # Fallback — chat tự nhiên

            else:

                add_message("assistant", (

                    f"{name_display} ơi, tôi chưa hiểu rõ ý anh/chị. \n\n"

                    f"Tôi có thể:\n"

                    f"• Tư vấn sản phẩm bảo hiểm\n"

                    f"• Giải đáp thắc mắc về bồi thường\n"

                    f"• Đánh giá điều kiện tiếp nhận bồi thường\n\n"

                    f"Anh/chị cần hỗ trợ gì ạ?"

                ))

                st.rerun()



    # ============================================================

    # CASE 4: Claim flow đã xong → quay lại chat

    # ============================================================

    elif st.session_state.current_product and st.session_state.finished:

        # Cho phép user chat tiếp hoặc bắt đầu lại

        aiml_resp = aiml_respond(user_input)



        if aiml_resp and aiml_resp == "__RESTART__":

            reset_session()

            add_message("assistant", " Đã bắt đầu lại. Anh/chị cần hỗ trợ gì ạ? ")

            st.rerun()

        elif aiml_resp and aiml_resp.startswith("__CLAIM_REQUEST__"):

            reset_session()

            st.session_state.waiting_for_text = True

            name_display = st.session_state.customer_name or "anh/chị"

            add_message("assistant", f"Dạ {name_display}! Vui lòng chọn loại bảo hiểm ở thanh cuộn bên dưới. ")

            st.rerun()

        elif aiml_resp and not aiml_resp.startswith("__"):

            add_message("assistant", aiml_resp)

            st.rerun()

        elif has_incident(user_input) or has_claim_request(user_input):

            # Quay lại đánh giá sản phẩm khác

            st.session_state.asked_evaluate = True

            product = detect_product_smart(user_input)

            name_display = st.session_state.customer_name or "anh/chị"

            if product:

                add_message("assistant", (

                    f"Dạ {name_display}! Có vẻ như anh/chị muốn đánh giá sản phẩm: **{product['name']}**\n\n"

                    f"Anh/chị có muốn tôi **đánh giá điều kiện tiếp nhận bồi thường** không ạ?\n\n"

                    f"• Gõ **có** để bắt đầu\n"

                    f"• Gõ **không** nếu chưa cần"

                ))

            else:

                add_message("assistant", (

                    f"Anh/chị có muốn tôi **đánh giá điều kiện tiếp nhận bồi thường** không ạ?\n\n"

                    f"• Gõ **có** để bắt đầu\n"

                    f"• Gõ **không** nếu chỉ muốn hỏi thêm"

                ))

            st.rerun()

        else:

            # Chat tự nhiên sau khi xong claim

            name_display = st.session_state.customer_name or "anh/chị"

            add_message("assistant", (

                f"Cảm ơn {name_display}! Anh/chị cần hỗ trợ gì thêm không ạ? "

                f"Có thể nhấn ** Bắt đầu lại** để đánh giá sản phẩm khác."

            ))

            st.rerun()

