# -*- coding: utf-8 -*-
"""
PJICO Insurance - Đánh giá tiếp nhận bồi thường V.0.5
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
    page_title="PJICO Đánh giá tiếp nhận bồi thường V.0.5",
    page_icon="🏠",
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

def normalize_text(text):
    if not text: return ""
    text = text.strip().lower()
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    return text

YES_WORDS = ["co", "duoc", "yes", "dung", "roi", "phai", "chinhxac", "dungroi", "chacchan"]
NO_WORDS = ["khong", "chua", "no", "khong co", "chua co", "khong phai"]

def is_yes(text):
    t = normalize_text(text)
    return any(w == t or w in t for w in YES_WORDS)

def is_no(text):
    t = normalize_text(text)
    return any(w == t or w in t for w in NO_WORDS)

def match_answer(user_answer, expected):
    ua = normalize_text(user_answer)
    ex = normalize_text(expected)
    if ua == ex: return True
    if ex in ["co", "yes"]: return is_yes(user_answer)
    if ex in ["khong", "no"]: return is_no(user_answer)
    return ex in ua

INCIDENT_KEYWORDS = [
    "chay", "no", "tai nan", "bao hiem", "nha", "xe", "bao",
    "lu", "trom", "cuop", "dong dat", "giong", "ngap",
    "suc khoe", "om", "dau", "vien", "kinh doanh", "gian doan",
    "combo", "360", "phu gia", "family", "tnds", "trach nhiem",
    "thuong tich", "tu vong", "thiet hai",
    "dot nhap", "bao lua", "loc", "set", "con nguoi", "than the",
    "ket hop", "cong nhan", "nha may", "ung thu", "hiem ngheo",
]

def extract_name(text):
    m = re.search(r'(?:t[oô]i|m[iì]nh|em|anh|ch[iị])\s+t[eê]n\s+(?:l[aà]\s+)?([A-ZÀ-Ỵa-zà-ỹ]+(?:\s+[A-ZÀ-Ỵa-zà-ỹ]+){0,3})', text, re.IGNORECASE)
    if m: return m.group(1).strip()
    m = re.search(r't[eê]n\s+(?:l[aà]\s+)?([A-ZÀ-Ỵa-zà-ỹ]+(?:\s+[A-ZÀ-Ỵa-zà-ỹ]+){0,3})', text, re.IGNORECASE)
    if m: return m.group(1).strip()
    text_clean = text.strip()
    words = text_clean.split()
    text_norm = normalize_text(text_clean)
    has_incident = any(normalize_text(k) in text_norm for k in INCIDENT_KEYWORDS)
    if not has_incident and 1 <= len(words) <= 4: return text_clean
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
    if "log_dir" not in st.session_state:
        st.session_state.log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "claim_logs")

init_state()

# --- AIML Kernel ---
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

def normalize_text(text):
    """Bỏ dấu tiếng Việt để match AIML pattern."""
    if not text:
        return ""
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    return text.upper().strip()

def aiml_respond(user_input):
    """Gửi input qua AIML kernel, trả về response."""
    kernel = get_aiml_kernel()
    if kernel is None:
        return None
    normalized = normalize_text(user_input)
    response = kernel.respond(normalized)
    return response if response else None

def add_message(role, content):
    st.session_state.messages.append({"role": role, "content": content, "time": datetime.now().isoformat()})

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
        reasons.append(f"❌ Tuổi của người được bảo hiểm là {age}, không nằm trong phạm vi ({min_age}-{max_age} tuổi) → Không đạt điều kiện")
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
            reasons.append(f"❌ {q['question']} → Trả lời: '{answer}' → Không đạt điều kiện tiếp nhận bồi thường")
    return {"passed": passed, "reasons": reasons, "failed_questions": failed}

def save_claim_log(product, answers, result):
    os.makedirs(st.session_state.log_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = re.sub(r'[^\w]', '_', st.session_state.customer_name or "khach_hang")
    # Lưu vào folder con theo kết quả
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
    st.session_state.messages = []
    st.session_state.current_product = None
    st.session_state.q_index = 0
    st.session_state.answers = OrderedDict()
    st.session_state.finished = False
    st.session_state.result = None
    st.session_state.started = False
    st.session_state.waiting_for_text = False
    st.session_state.customer_name = ""
    st.session_state.asked_name = False

with st.sidebar:
    _logo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "pjico_logo.png")
    if os.path.exists(_logo):
        st.image(_logo, width=200)
    st.markdown("## 🏠 PJICO Đánh giá tiếp nhận bồi thường")
    st.markdown("### Version 0.5")
    st.markdown("---")
    st.markdown("### Sản phẩm bảo hiểm:")
    for p in PRODUCTS:
        st.markdown(f"**{p['name']}**")
        st.caption(f"💰 {p['price']}")
        st.caption(f"🔗 [Link]({p['url']})")
        st.markdown("")
    st.markdown("---")
    if st.button("🔄 Bắt đầu lại"):
        reset_session()
        st.rerun()
    st.markdown("---")
    st.markdown("### 📁 Thư mục log:")
    st.code(st.session_state.log_dir)
    if os.path.exists(st.session_state.log_dir):
        passed_dir = os.path.join(st.session_state.log_dir, "được_thông_qua")
        failed_dir = os.path.join(st.session_state.log_dir, "chưa_được_thông_qua")
        passed_files = [f for f in os.listdir(passed_dir) if f.endswith(".json")] if os.path.exists(passed_dir) else []
        failed_files = [f for f in os.listdir(failed_dir) if f.endswith(".json")] if os.path.exists(failed_dir) else []
        st.metric("✅ Được thông qua", len(passed_files))
        st.metric("❌ Chưa được thông qua", len(failed_files))

_logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "pjico_logo.png")
_logo_html = f'<img src="file/{_logo_path}" alt="PJICO">' if os.path.exists(_logo_path) else ''
st.markdown(f'<div class="pjico-header">{_logo_html}<div><h1>BẢO HIỂM PJICO</h1><p>Tổng Công ty Cổ phần Bảo hiểm Petrolimex | Đánh giá điều kiện tiếp nhận bồi thường V.0.5</p></div></div>', unsafe_allow_html=True)
st.markdown("---")

if not st.session_state.started:
    add_message("assistant", "Xin chào! 👋 Tôi là trợ lý đánh giá tiếp nhận bồi thường PJICO.\n\nVui lòng nhập **tên** của anh/chị.")
    st.session_state.started = True

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
            verdict = "✅ **ĐỦ ĐIỀU KIỆN TIẾP NHẬN BỒI THƯỜNG**"
            detail = "Hồ sơ của anh/chị đã đủ điều kiện để tiếp nhận bồi thường. Vui lòng liên hệ PJICO để được hướng dẫn nộp hồ sơ chính thức."
        else:
            verdict = "❌ **KHÔNG ĐỦ ĐIỀU KIỆN TIẾP NHẬN BỒI THƯỜNG**"
            detail = "Dựa trên thông tin cung cấp, hồ sơ chưa đủ điều kiện để tiếp nhận bồi thường.\n\n**Lý do:**\n"
            for r in result["reasons"]:
                detail += f"- {r}\n"
        summary = f"""
---
## 📋 KẾT QUẢ ĐÁNH GIÁ ĐIỀU KIỆN TIẾP NHẬN BỒI THƯỜNG

**Sản phẩm:** {product['name']}

{verdict}

{detail}

**Tóm tắt câu trả lời:**
"""
        for q in product["claim_questions"]:
            ans = st.session_state.answers.get(q["id"], "(chưa trả lời)")
            summary += f"- **{q['question']}**: {ans}\n"
        log_path = save_claim_log(product, dict(st.session_state.answers), result)
        summary += f"\n📁 Thông tin đã lưu: `{os.path.basename(log_path)}`\n"
        summary += "\nAnh/chị có muốn đánh giá sản phẩm khác không? Nhấn **🔄 Bắt đầu lại** ở sidebar."
        add_message("assistant", summary)

        # Nút tải kết quả về máy user
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
            label="📥 Tải kết quả (JSON)",
            data=log_json.encode("utf-8"),
            file_name=filename,
            mime="application/json",
            use_container_width=True,
        )
        # Tải summary text
        st.download_button(
            label="📄 Tải kết quả (Text)",
            data=summary.encode("utf-8"),
            file_name=f"claim_{safe_name}_{product['id']}_{ts}.txt",
            mime="text/plain",
            use_container_width=True,
        )

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- Radio button cho câu hỏi có options ---
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
            if st.button("✅ Xác nhận", key=f"q_{q['id']}_btn", use_container_width=True):
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

# Selectbox chon san pham khi waiting_for_text
if st.session_state.current_product is None and st.session_state.waiting_for_text:
    st.markdown("**Vui lòng chọn loại bảo hiểm:**")
    product_options = [p["name"] for p in PRODUCTS]
    col1, col2 = st.columns([3, 1])
    with col1:
        selected_product = st.selectbox("Chọn sản phẩm:", product_options, key="product_select", label_visibility="collapsed")
    with col2:
        st.write("")
        if st.button("✅ Xác nhận", key="confirm_product"):
            product = None
            for p in PRODUCTS:
                if p["name"] == selected_product:
                    product = p
                    break
            if product:
                add_message("user", selected_product)
                st.session_state.current_product = product
                st.session_state.waiting_for_text = False
                add_message("assistant", (
                    f"Đã chọn: **{product['name']}** ✅\n\n"
                    f"Bắt đầu đánh giá điều kiện tiếp nhận bồi thường. Vui lòng trả lời từng câu nhé!\n\n---\n"
                ))
                st.rerun()
    st.markdown("*↑ Chọn sản phẩm và bấm Xác nhận*")
    user_input = None
else:
    user_input = st.chat_input("Nhập tin nhắn...")

if user_input:
    add_message("user", user_input)

    if st.session_state.current_product is None and not st.session_state.waiting_for_text:
        name = extract_name(user_input)
        if name and not st.session_state.customer_name:
            st.session_state.customer_name = name
        product = detect_product_smart(user_input)
        if product:
            st.session_state.current_product = product
            name_display = st.session_state.customer_name or "anh/chị"
            add_message("assistant", (
                f"Cảm ơn {name_display}! 📝\n\n"
                f"Tôi đã xác nhận anh/chị muốn yêu cầu bồi thường sản phẩm:\n"
                f"**{product['name']}**\n\n"
                f"💰 Phí: {product['price']}\n"
                f"🔗 Chi tiết: {product['url']}\n\n"
                f"Để đánh giá điều kiện tiếp nhận bồi thường, tôi sẽ hỏi một số câu hỏi. Vui lòng trả lời từng câu nhé!\n\n---\n"
            ))
        elif not st.session_state.customer_name and not st.session_state.asked_name:
            st.session_state.asked_name = True
            add_message("assistant", (
                "Cảm ơn anh/chị đã liên hệ! 😊\n\n"
                "Vui lòng cho biết **tên** và **loại bảo hiểm** anh/chị muốn yêu cầu bồi thường nhé.\n\n"
                "**Ví dụ:** 'Cường, tôi muốn yêu cầu bồi thường bảo hiểm nhà ở combo 360'"
            ))
        elif not st.session_state.customer_name and st.session_state.asked_name:
            name = extract_name(user_input)
            if not name:
                words = user_input.strip().split()
                text_norm = normalize_text(user_input)
                has_incident = any(normalize_text(k) in text_norm for k in INCIDENT_KEYWORDS)
                if not has_incident and len(words) <= 4:
                    name = user_input.strip()
            if name:
                st.session_state.customer_name = name
                product = detect_product_smart(user_input)
                if product:
                    st.session_state.current_product = product
                    add_message("assistant", (
                        f"Cảm ơn {name}! 📝\n\n"
                        f"Sản phẩm: **{product['name']}**\n\n"
                        f"💰 Phí: {product['price']}\n\n"
                        f"Bắt đầu đánh giá điều kiện tiếp nhận bồi thường nhé!\n\n---\n"
                    ))
                else:
                    st.session_state.waiting_for_text = True
            else:
                st.session_state.waiting_for_text = True
        else:
            st.session_state.waiting_for_text = True

    elif st.session_state.current_product is None and st.session_state.waiting_for_text:
        # Selectbox handles this now
        pass

    elif st.session_state.current_product and not st.session_state.finished:
        product = st.session_state.current_product
        questions = product["claim_questions"]
        q = questions[st.session_state.q_index]
        raw_answer = user_input.strip()

        # Dùng AIML để match câu trả lời tự nhiên
        aiml_response = aiml_respond(raw_answer)
        matched_answer = None

        if aiml_response:
            if aiml_response.startswith("__ANSWER__:"):
                matched_answer = aiml_response.replace("__ANSWER__:", "", 1).strip()
            elif aiml_response == "__RESTART__":
                st.session_state.current_product = None
                st.session_state.q_index = 0
                st.session_state.answers = OrderedDict()
                st.session_state.finished = False
                st.session_state.result = None
                st.session_state.waiting_for_text = True
                add_message("assistant", "🔄 Đã bắt đầu lại. Vui lòng chọn loại bảo hiểm ở thanh cuộn bên dưới.")
                st.rerun()

        # Nếu câu có options, thử match với AIML trước, rồi fallback
        if "options" in q:
            if matched_answer and matched_answer in q["options"]:
                st.session_state.answers[q["id"]] = matched_answer
                add_message("user", raw_answer)
                st.session_state.q_index += 1
                if st.session_state.q_index >= len(questions):
                    result = evaluate_claim(dict(st.session_state.answers), product)
                    st.session_state.result = result
                    st.session_state.finished = True
                st.rerun()
            else:
                # AIML không match được, nhắc user chọn từ radio
                add_message("assistant", "⚠️ Vui lòng chọn đáp án từ danh sách bên dưới rồi bấm **Xác nhận** nhé.")
                st.rerun()
        else:
            # Câu hỏi type=text (như hỏi tuổi) — dùng raw_answer
            st.session_state.answers[q["id"]] = raw_answer
            add_message("user", raw_answer)
            st.session_state.q_index += 1
            if st.session_state.q_index >= len(questions):
                result = evaluate_claim(dict(st.session_state.answers), product)
                st.session_state.result = result
                st.session_state.finished = True
            st.rerun()