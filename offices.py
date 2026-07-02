# -*- coding: utf-8 -*-
"""
Office Locator Data
Danh sách văn phòng trên toàn quốc.
"""

OFFICES = [
    {
        "city": "Hà Nội",
        "city_norm": "ha noi",
        "alt_names": ["HN", "ha noi", "thu do"],
        "offices": [
            {"name": "Trụ sở chính", "address": "Tầng 21-22, tòa nhà Mipec, 229 Tây Sơn, phường Kim Liên, quận Đống Đa, Hà Nội", "phone": "024 3776 0867"},
            {"name": "Chi nhánh Ba Đình", "address": "Số 18, ngõ 107 Nguyễn Thái Học, Ba Đình, Hà Nội", "phone": "024 3733 4567"},
            {"name": "Chi nhánh Hoàn Kiếm", "address": "Số 45 Trần Hưng Đạo, Hoàn Kiếm, Hà Nội", "phone": "024 3933 1234"},
            {"name": "Chi nhánh Cầu Giấy", "address": "Tầng 5, tòa nhà B, khu đô thị Dịch Vọng, Cầu Giấy, Hà Nội", "phone": "024 3755 6789"},
        ],
    },
    {
        "city": "Hồ Chí Minh",
        "city_norm": "ho chi minh",
        "alt_names": ["HCM", "SG", "sai gon", "thanh pho ho chi minh"],
        "offices": [
            {"name": "Chi nhánh TP.HCM", "address": "Tầng 8, tòa nhà Sài Gòn Prime, 107-109-111 Nguyễn Đình Chiểu, phường Võ Thị Sáu, quận 3, TP.HCM", "phone": "028 3930 1234"},
            {"name": "Chi nhánh Quận 1", "address": "Số 23 Lê Thánh Tôn, Bến Nghé, Quận 1, TP.HCM", "phone": "028 3823 4567"},
            {"name": "Chi nhánh Tân Bình", "address": "Số 145 Hoàng Văn Thụ, Tân Bình, TP.HCM", "phone": "028 3845 6789"},
            {"name": "Chi nhánh Gò Vấp", "address": "Số 12 Phan Văn Trị, Phường 10, Gò Vấp, TP.HCM", "phone": "028 3989 0123"},
        ],
    },
    {
        "city": "Đà Nẵng",
        "city_norm": "da nang",
        "alt_names": ["DN", "thanh pho da nang"],
        "offices": [
            {"name": "Chi nhánh Đà Nẵng", "address": "Số 126 Lê Duẩn, Thanh Khê, Đà Nẵng", "phone": "0236 3681 234"},
            {"name": "Chi nhánh Hải Châu", "address": "Số 78 Bạch Đằng, Hải Châu, Đà Nẵng", "phone": "0236 3823 456"},
        ],
    },
    {
        "city": "Hải Phòng",
        "city_norm": "hai phong",
        "alt_names": ["HP"],
        "offices": [
            {"name": "Chi nhánh Hải Phòng", "address": "Số 34 Điện Biên Phủ, Lê Sơn, Hải Phòng", "phone": "0225 3839 234"},
            {"name": "Chi nhánh Ngô Quyền", "address": "Số 56 Lạch Tray, Ngô Quyền, Hải Phòng", "phone": "0225 3567 890"},
        ],
    },
    {
        "city": "Cần Thơ",
        "city_norm": "can tho",
        "alt_names": ["CT"],
        "offices": [
            {"name": "Chi nhánh Cần Thơ", "address": "Số 123 Đại lộ Hòa Bình, Ninh Kiều, Cần Thơ", "phone": "0292 3873 234"},
            {"name": "Chi nhánh Cái Khế", "address": "Số 45 Nguyễn Văn Cừ, Cái Khế, Ninh Kiều, Cần Thơ", "phone": "0292 3734 567"},
        ],
    },
    {
        "city": "Bình Dương",
        "city_norm": "binh duong",
        "alt_names": ["BD"],
        "offices": [
            {"name": "Chi nhánh Bình Dương", "address": "Số 88 Đại lộ Bình Dương, Thủ Dầu Một, Bình Dương", "phone": "0274 3823 234"},
            {"name": "Chi nhánh Dĩ An", "address": "Số 24 Nguyễn An, Dĩ An, Bình Dương", "phone": "0274 3734 567"},
        ],
    },
    {
        "city": "Đồng Nai",
        "city_norm": "dong nai",
        "alt_names": ["Bien Hoa", "biên hòa"],
        "offices": [
            {"name": "Chi nhánh Đồng Nai", "address": "Số 56 đường 30/4, Biên Hòa, Đồng Nai", "phone": "0251 3823 234"},
            {"name": "Chi nhánh Long Thành", "address": "Số 12 Nguyễn Văn Linh, Long Thành, Đồng Nai", "phone": "0251 3567 890"},
        ],
    },
    {
        "city": "Khánh Hòa",
        "city_norm": "khanh hoa",
        "alt_names": ["Nha Trang", "nha trang", "NT"],
        "offices": [
            {"name": "Chi nhánh Khánh Hòa", "address": "Số 46 Trần Phú, Lộc Thọ, Nha Trang, Khánh Hòa", "phone": "0258 3823 234"},
            {"name": "Chi nhánh Nha Trang Center", "address": "Số 78 Nguyễn Thị Minh Khai, Nha Trang, Khánh Hòa", "phone": "0258 3523 678"},
        ],
    },
    {
        "city": "Nghệ An",
        "city_norm": "nghe an",
        "alt_names": ["Vinh", "vinh"],
        "offices": [
            {"name": "Chi nhánh Nghệ An", "address": "Số 123 Lê Nin, Thành Vinh, Nghệ An", "phone": "0238 3583 234"},
            {"name": "Chi nhánh Vinh", "address": "Số 45 Quang Trung, Vinh, Nghệ An", "phone": "0238 3567 890"},
        ],
    },
    {
        "city": "Thừa Thiên Huế",
        "city_norm": "thua thien hue",
        "alt_names": ["Hue", "huế", "đế cố đô"],
        "offices": [
            {"name": "Chi nhánh Thừa Thiên Huế", "address": "Số 68 Hùng Vương, Vĩnh Ninh, Huế", "phone": "0234 3823 234"},
            {"name": "Chi nhánh Huế", "address": "Số 34 Lê Lợi, Phú Hội, Huế", "phone": "0234 3567 890"},
        ],
    },
    {
        "city": "Quảng Ninh",
        "city_norm": "quang ninh",
        "alt_names": ["Ha Long", "hạ long", "HL"],
        "offices": [
            {"name": "Chi nhánh Quảng Ninh", "address": "Số 89 Hạ Long, Bãi Cháy, Hạ Long, Quảng Ninh", "phone": "0203 3652 234"},
            {"name": "Chi nhánh Cẩm Phả", "address": "Số 23 Cẩm Phả, Quảng Ninh", "phone": "0203 3567 890"},
        ],
    },
    {
        "city": "Lâm Đồng",
        "city_norm": "lam dong",
        "alt_names": ["Da Lat", "đà lạt", "ĐL"],
        "offices": [
            {"name": "Chi nhánh Lâm Đồng", "address": "Số 03 Trần Phú, Đà Lạt, Lâm Đồng", "phone": "0263 3823 234"},
            {"name": "Chi nhánh Đà Lạt", "address": "Số 27 Nguyễn Thị Minh Khai, Đà Lạt, Lâm Đồng", "phone": "0263 3567 890"},
        ],
    },
    {
        "city": "Phú Quốc",
        "city_norm": "phu quoc",
        "alt_names": ["PQ", "dao phu quoc"],
        "offices": [
            {"name": "Chi nhánh Phú Quốc", "address": "Số 30 đường 30/4, Dương Đông, Phú Quốc", "phone": "0297 3845 234"},
            {"name": "Đại lý Phú Quốc", "address": "Số 12 Nguyễn Văn Cừ, Dương Đông, Phú Quốc", "phone": "0297 3998 567"},
        ],
    },
    {
        "city": "Vũng Tàu",
        "city_norm": "vung tau",
        "alt_names": ["VT", "ba ria vung tau", "bà rịa"],
        "offices": [
            {"name": "Chi nhánh Bà Rịa - Vũng Tàu", "address": "Số 56 Lê Lợi, Vũng Tàu", "phone": "0254 3853 234"},
            {"name": "Chi nhánh Vũng Tàu", "address": "Số 78 Trương Công Định, Vũng Tàu", "phone": "0254 3567 890"},
        ],
    },
]


def get_offices_by_city(city_text):
    """Return list of offices matching the city text (fuzzy match)."""
    import unicodedata

    def normalize(t):
        t = unicodedata.normalize('NFD', t)
        return ''.join(c for c in t if unicodedata.category(c) != 'Mn').lower().strip()

    text_norm = normalize(city_text)
    for office in OFFICES:
        if office["city_norm"] in text_norm or text_norm in office["city_norm"]:
            return office["offices"]
        # Also check common abbreviations
        for alt in office.get("alt_names", []):
            alt_norm = normalize(alt)
            if alt_norm in text_norm or text_norm in alt_norm:
                return office["offices"]
    return None


def get_all_cities():
    """Return list of all city names."""
    return [o["city"] for o in OFFICES]