# -*- coding: utf-8 -*-
with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    # Block 1: "Tôi chưa xác định... Vui lòng chọn:" + product list + "(Gõ tên"
    if i < len(lines) and 'add_message("assistant", (' in line and i+1 < len(lines) and 'Cảm ơn {name}! 😊' in lines[i+1]:
        new_lines.append('                    add_message("assistant", (\n')
        new_lines.append('                        f"Cảm ơn {name}! 😊\\n\\n"\n')
        new_lines.append('                        "Tôi chưa xác định được loại bảo hiểm anh/chị muốn mua.\\n\\n"\n')
        new_lines.append('                        "Vui lòng chọn loại bảo hiểm ở thanh cuộn bên dưới 👇"\n')
        new_lines.append('                    ))\n')
        new_lines.append('                    st.session_state.waiting_for_text = True\n')
        # Skip until st.session_state.waiting_for_text = True
        while i < len(lines) and 'waiting_for_text = True' not in lines[i]:
            i += 1
        i += 1
        continue
    # Block 2: "Tôi chưa rõ thông tin" + product list
    if 'Tôi chưa rõ thông tin' in line:
        new_lines.append('                add_message("assistant", (\n')
        new_lines.append('                    "Tôi chưa rõ thông tin. Vui lòng cho biết **tên** của anh/chị và chọn loại bảo hiểm ở thanh cuộn bên dưới 👇"\n')
        new_lines.append('                ))\n')
        new_lines.append('                st.session_state.waiting_for_text = True\n')
        # Skip until waiting_for_text = True
        while i < len(lines) and 'waiting_for_text = True' not in lines[i]:
            i += 1
        i += 1
        continue
    # Block 3: "Cảm ơn {st.session_state.customer_name}! 😊" + product list
    if 'add_message("assistant", (' in line and i+1 < len(lines) and 'customer_name}! 😊' in lines[i+1]:
        new_lines.append('            add_message("assistant", (\n')
        new_lines.append('                f"Cảm ơn {st.session_state.customer_name}! 😊\\n\\n"\n')
        new_lines.append('                "Tôi chưa xác định được loại bảo hiểm anh/chị muốn mua.\\n\\n"\n')
        new_lines.append('                "Vui lòng chọn loại bảo hiểm ở thanh cuộn bên dưới 👇"\n')
        new_lines.append('            ))\n')
        new_lines.append('            st.session_state.waiting_for_text = True\n')
        while i < len(lines) and 'waiting_for_text = True' not in lines[i]:
            i += 1
        i += 1
        continue
    new_lines.append(line)
    i += 1

with open('app.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print('OK')