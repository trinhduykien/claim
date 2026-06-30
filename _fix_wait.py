# -*- coding: utf-8 -*-
with open('app.py', 'r', encoding='utf-8') as f:
    c = f.read()

old = """    elif st.session_state.current_product is None and st.session_state.waiting_for_text:
        text_norm = normalize_text(user_input)
        product = None
        if user_input.strip().isdigit():
            idx = int(user_input.strip()) - 1
            if 0 <= idx < len(PRODUCTS):
                product = PRODUCTS[idx]
        if not product:
            for p in PRODUCTS:
                p_norm = normalize_text(p["name"])
                if p_norm in text_norm or text_norm in p_norm:
                    product = p
                    break
                if p["id"] in text_norm:
                    product = p
                    break
        if not product:
            product = detect_product_smart(user_input)
        if product:
            st.session_state.current_product = product
            st.session_state.waiting_for_text = False
            add_message("assistant", (
                f"Đã chọn: **{product['name']}** ✅\\n\\n"
                f"Bắt đầu đánh giá điều kiện mua. Vui lòng trả lời từng câu nhé!\\n\\n---\\n"
            ))
        else:
            add_message("assistant", "Không nhận diện được. Vui lòng gõ tên hoặc số thứ tự sản phẩm trong danh sách trên.")"""

new = """    elif st.session_state.current_product is None and st.session_state.waiting_for_text:
        # Selectbox handles this now
        pass"""

if old in c:
    c = c.replace(old, new)
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(c)
    print('OK')
else:
    print('NOT FOUND')