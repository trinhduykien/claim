# -*- coding: utf-8 -*-
"""
Office Locator Data
Danh sÃ¡ch vÄƒn phÃ²ng trÃªn toÃ n quá»‘c.
"""

OFFICES = [
    {
        "city": "HÃ  Ná»™i",
        "city_norm": "ha noi",
        "alt_names": ["HN", "ha noi", "thu do"],
        "offices": [
            {"name": "Trá»¥ sá»Ÿ chÃ­nh", "address": "Táº§ng 21-22, tÃ²a nhÃ  Mipec, 229 TÃ¢y SÆ¡n, phÆ°á»ng Kim LiÃªn, quáº­n Äá»‘ng Äa, HÃ  Ná»™i", "phone": "024 3776 0867"},
            {"name": "Chi nhÃ¡nh Ba ÄÃ¬nh", "address": "Sá»‘ 18, ngÃµ 107 Nguyá»…n ThÃ¡i Há»c, Ba ÄÃ¬nh, HÃ  Ná»™i", "phone": "024 3733 4567"},
            {"name": "Chi nhÃ¡nh HoÃ n Kiáº¿m", "address": "Sá»‘ 45 Tráº§n HÆ°ng Äáº¡o, HoÃ n Kiáº¿m, HÃ  Ná»™i", "phone": "024 3933 1234"},
            {"name": "Chi nhÃ¡nh Cáº§u Giáº¥y", "address": "Táº§ng 5, tÃ²a nhÃ  B, khu Ä‘Ã´ thá»‹ Dá»‹ch Vá»ng, Cáº§u Giáº¥y, HÃ  Ná»™i", "phone": "024 3755 6789"},
        ],
    },
    {
        "city": "Há»“ ChÃ­ Minh",
        "city_norm": "ho chi minh",
        "alt_names": ["HCM", "SG", "sai gon", "thanh pho ho chi minh"],
        "offices": [
            {"name": "Chi nhÃ¡nh TP.HCM", "address": "Táº§ng 8, tÃ²a nhÃ  SÃ i GÃ²n Prime, 107-109-111 Nguyá»…n ÄÃ¬nh Chiá»ƒu, phÆ°á»ng VÃµ Thá»‹ SÃ¡u, quáº­n 3, TP.HCM", "phone": "028 3930 1234"},
            {"name": "Chi nhÃ¡nh Quáº­n 1", "address": "Sá»‘ 23 LÃª ThÃ¡nh TÃ´n, Báº¿n NghÃ©, Quáº­n 1, TP.HCM", "phone": "028 3823 4567"},
            {"name": "Chi nhÃ¡nh TÃ¢n BÃ¬nh", "address": "Sá»‘ 145 HoÃ ng VÄƒn Thá»¥, TÃ¢n BÃ¬nh, TP.HCM", "phone": "028 3845 6789"},
            {"name": "Chi nhÃ¡nh GÃ² Váº¥p", "address": "Sá»‘ 12 Phan VÄƒn Trá»‹, PhÆ°á»ng 10, GÃ² Váº¥p, TP.HCM", "phone": "028 3989 0123"},
        ],
    },
    {
        "city": "ÄÃ  Náºµng",
        "city_norm": "da nang",
        "alt_names": ["DN", "thanh pho da nang"],
        "offices": [
            {"name": "Chi nhÃ¡nh ÄÃ  Náºµng", "address": "Sá»‘ 126 LÃª Duáº©n, Thanh KhÃª, ÄÃ  Náºµng", "phone": "0236 3681 234"},
            {"name": "Chi nhÃ¡nh Háº£i ChÃ¢u", "address": "Sá»‘ 78 Báº¡ch Äáº±ng, Háº£i ChÃ¢u, ÄÃ  Náºµng", "phone": "0236 3823 456"},
        ],
    },
    {
        "city": "Háº£i PhÃ²ng",
        "city_norm": "hai phong",
        "alt_names": ["HP"],
        "offices": [
            {"name": "Chi nhÃ¡nh Háº£i PhÃ²ng", "address": "Sá»‘ 34 Äiá»‡n BiÃªn Phá»§, LÃª SÆ¡n, Háº£i PhÃ²ng", "phone": "0225 3839 234"},
            {"name": "Chi nhÃ¡nh NgÃ´ Quyá»n", "address": "Sá»‘ 56 Láº¡ch Tray, NgÃ´ Quyá»n, Háº£i PhÃ²ng", "phone": "0225 3567 890"},
        ],
    },
    {
        "city": "Cáº§n ThÆ¡",
        "city_norm": "can tho",
        "alt_names": ["CT"],
        "offices": [
            {"name": "Chi nhÃ¡nh Cáº§n ThÆ¡", "address": "Sá»‘ 123 Äáº¡i lá»™ HÃ²a BÃ¬nh, Ninh Kiá»u, Cáº§n ThÆ¡", "phone": "0292 3873 234"},
            {"name": "Chi nhÃ¡nh CÃ¡i Kháº¿", "address": "Sá»‘ 45 Nguyá»…n VÄƒn Cá»«, CÃ¡i Kháº¿, Ninh Kiá»u, Cáº§n ThÆ¡", "phone": "0292 3734 567"},
        ],
    },
    {
        "city": "BÃ¬nh DÆ°Æ¡ng",
        "city_norm": "binh duong",
        "alt_names": ["BD"],
        "offices": [
            {"name": "Chi nhÃ¡nh BÃ¬nh DÆ°Æ¡ng", "address": "Sá»‘ 88 Äáº¡i lá»™ BÃ¬nh DÆ°Æ¡ng, Thá»§ Dáº§u Má»™t, BÃ¬nh DÆ°Æ¡ng", "phone": "0274 3823 234"},
            {"name": "Chi nhÃ¡nh DÄ© An", "address": "Sá»‘ 24 Nguyá»…n An, DÄ© An, BÃ¬nh DÆ°Æ¡ng", "phone": "0274 3734 567"},
        ],
    },
    {
        "city": "Äá»“ng Nai",
        "city_norm": "dong nai",
        "alt_names": ["Bien Hoa", "biÃªn hÃ²a"],
        "offices": [
            {"name": "Chi nhÃ¡nh Äá»“ng Nai", "address": "Sá»‘ 56 Ä‘Æ°á»ng 30/4, BiÃªn HÃ²a, Äá»“ng Nai", "phone": "0251 3823 234"},
            {"name": "Chi nhÃ¡nh Long ThÃ nh", "address": "Sá»‘ 12 Nguyá»…n VÄƒn Linh, Long ThÃ nh, Äá»“ng Nai", "phone": "0251 3567 890"},
        ],
    },
    {
        "city": "KhÃ¡nh HÃ²a",
        "city_norm": "khanh hoa",
        "alt_names": ["Nha Trang", "nha trang", "NT"],
        "offices": [
            {"name": "Chi nhÃ¡nh KhÃ¡nh HÃ²a", "address": "Sá»‘ 46 Tráº§n PhÃº, Lá»™c Thá», Nha Trang, KhÃ¡nh HÃ²a", "phone": "0258 3823 234"},
            {"name": "Chi nhÃ¡nh Nha Trang Center", "address": "Sá»‘ 78 Nguyá»…n Thá»‹ Minh Khai, Nha Trang, KhÃ¡nh HÃ²a", "phone": "0258 3523 678"},
        ],
    },
    {
        "city": "Nghá»‡ An",
        "city_norm": "nghe an",
        "alt_names": ["Vinh", "vinh"],
        "offices": [
            {"name": "Chi nhÃ¡nh Nghá»‡ An", "address": "Sá»‘ 123 LÃª Nin, ThÃ nh Vinh, Nghá»‡ An", "phone": "0238 3583 234"},
            {"name": "Chi nhÃ¡nh Vinh", "address": "Sá»‘ 45 Quang Trung, Vinh, Nghá»‡ An", "phone": "0238 3567 890"},
        ],
    },
    {
        "city": "Thá»«a ThiÃªn Huáº¿",
        "city_norm": "thua thien hue",
        "alt_names": ["Hue", "huáº¿", "Ä‘áº¿ cá»‘ Ä‘Ã´"],
        "offices": [
            {"name": "Chi nhÃ¡nh Thá»«a ThiÃªn Huáº¿", "address": "Sá»‘ 68 HÃ¹ng VÆ°Æ¡ng, VÄ©nh Ninh, Huáº¿", "phone": "0234 3823 234"},
            {"name": "Chi nhÃ¡nh Huáº¿", "address": "Sá»‘ 34 LÃª Lá»£i, PhÃº Há»™i, Huáº¿", "phone": "0234 3567 890"},
        ],
    },
    {
        "city": "Quáº£ng Ninh",
        "city_norm": "quang ninh",
        "alt_names": ["Ha Long", "háº¡ long", "HL"],
        "offices": [
            {"name": "Chi nhÃ¡nh Quáº£ng Ninh", "address": "Sá»‘ 89 Háº¡ Long, BÃ£i ChÃ¡y, Háº¡ Long, Quáº£ng Ninh", "phone": "0203 3652 234"},
            {"name": "Chi nhÃ¡nh Cáº©m Pháº£", "address": "Sá»‘ 23 Cáº©m Pháº£, Quáº£ng Ninh", "phone": "0203 3567 890"},
        ],
    },
    {
        "city": "LÃ¢m Äá»“ng",
        "city_norm": "lam dong",
        "alt_names": ["Da Lat", "Ä‘Ã  láº¡t", "ÄL"],
        "offices": [
            {"name": "Chi nhÃ¡nh LÃ¢m Äá»“ng", "address": "Sá»‘ 03 Tráº§n PhÃº, ÄÃ  Láº¡t, LÃ¢m Äá»“ng", "phone": "0263 3823 234"},
            {"name": "Chi nhÃ¡nh ÄÃ  Láº¡t", "address": "Sá»‘ 27 Nguyá»…n Thá»‹ Minh Khai, ÄÃ  Láº¡t, LÃ¢m Äá»“ng", "phone": "0263 3567 890"},
        ],
    },
    {
        "city": "PhÃº Quá»‘c",
        "city_norm": "phu quoc",
        "alt_names": ["PQ", "dao phu quoc"],
        "offices": [
            {"name": "Chi nhÃ¡nh PhÃº Quá»‘c", "address": "Sá»‘ 30 Ä‘Æ°á»ng 30/4, DÆ°Æ¡ng ÄÃ´ng, PhÃº Quá»‘c", "phone": "0297 3845 234"},
            {"name": "Äáº¡i lÃ½ PhÃº Quá»‘c", "address": "Sá»‘ 12 Nguyá»…n VÄƒn Cá»«, DÆ°Æ¡ng ÄÃ´ng, PhÃº Quá»‘c", "phone": "0297 3998 567"},
        ],
    },
    {
        "city": "VÅ©ng TÃ u",
        "city_norm": "vung tau",
        "alt_names": ["VT", "ba ria vung tau", "bÃ  rá»‹a"],
        "offices": [
            {"name": "Chi nhÃ¡nh BÃ  Rá»‹a - VÅ©ng TÃ u", "address": "Sá»‘ 56 LÃª Lá»£i, VÅ©ng TÃ u", "phone": "0254 3853 234"},
            {"name": "Chi nhÃ¡nh VÅ©ng TÃ u", "address": "Sá»‘ 78 TrÆ°Æ¡ng CÃ´ng Äá»‹nh, VÅ©ng TÃ u", "phone": "0254 3567 890"},
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
