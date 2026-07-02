# AI Claim Chatbot - Streamlit App

## CÃ i Ä‘áº·t & cháº¡y

```bash
cd D:\WORK\idea
pip install streamlit openai
python -m streamlit run app.py
```

## YÃªu cáº§u

### CÃ¡ch 1: DÃ¹ng Ollama local (miá»…n phÃ­)

```bash
# CÃ i Ollama: https://ollama.com
ollama serve
ollama pull qwen2.5:7b   # hoáº·c llama3.1:8b, glm4:9b...
```

Máº·c Ä‘á»‹nh app sáº½ káº¿t ná»‘i `http://localhost:11434/v1`, model `qwen2.5:7b`.

### CÃ¡ch 2: DÃ¹ng OpenAI API

Set environment variable:
```bash
set OPENAI_API_KEY=sk-xxxxx
set CLAIM_MODEL=gpt-4o-mini
```

Hoáº·c chá»‰nh trá»±c tiáº¿p trong sidebar cá»§a app.

## CÃ¡ch hoáº¡t Ä‘á»™ng

1. KhÃ¡ch hÃ ng má»Ÿ web â†’ chatbot AI chÃ o há»i
2. KhÃ¡ch mÃ´ táº£ sá»± cá»‘ (vd: "nhÃ  tÃ´i bá»‹ chÃ¡y, tÃ´i cÃ³ mua báº£o hiá»ƒm nhÃ  á»Ÿ combo 360")
3. AI tá»± nháº­n diá»‡n sáº£n pháº©m báº£o hiá»ƒm phÃ¹ há»£p
4. AI há»i linh hoáº¡t nhÆ° Ä‘Ã¡nh giÃ¡ viÃªn tháº­t â€” má»—i láº§n 1-2 cÃ¢u, Ä‘á»£i tráº£ lá»i rá»“i há»i tiáº¿p
5. Khi Ä‘á»§ thÃ´ng tin â†’ AI Ä‘Ã¡nh giÃ¡ vÃ  káº¿t luáº­n:
   - âœ… **Äá»¦ ÄIá»€U KIá»†N TIáº¾P NHáº¬N Bá»’I THÆ¯á»œNG**
   - âŒ **KHÃ”NG Äá»¦ ÄIá»€U KIá»†N TIáº¾P NHáº¬N Bá»’I THÆ¯á»œNG** + lÃ½ do
6. Há»“ sÆ¡ tá»± Ä‘á»™ng lÆ°u vÃ o `claim_logs/` dáº¡ng JSON

## Sáº£n pháº©m báº£o hiá»ƒm Ä‘Ã£ nháº­p liá»‡u

11 sáº£n pháº©m tá»« https://www..com.vn/san-pham:

1. Combo 360Â° NhÃ  â€“ Gia Ä‘Ã¬nh â€“ Ã” tÃ´ (599k/nÄƒm)
2. Combo 360Â° NhÃ  â€“ Gia Ä‘Ã¬nh â€“ Xe mÃ¡y (199k/nÄƒm)
3. ChÃ¡y ná»• toÃ n diá»‡n nhÃ  á»Ÿ PhÃº Gia
4. Sá»©c khá»e gia Ä‘Ã¬nh Family Care (2-11.2 triá»‡u/nÄƒm)
5. TNDS chá»§ xe mÃ´ tÃ´/xe gáº¯n mÃ¡y
6. GiÃ¡n Ä‘oáº¡n kinh doanh
7. Káº¿t há»£p con ngÆ°á»i (Báº£o hiá»ƒm thÃ¢n thá»ƒ)
8. Bá»‡nh ung thÆ°
9. Bá»‡nh hiá»ƒm nghÃ¨o
10. Tai náº¡n con ngÆ°á»i 24/24
11. Tai náº¡n con ngÆ°á»i má»©c trÃ¡ch nhiá»‡m cao

## Cáº¥u trÃºc file

```
D:\WORK\idea\
â”œâ”€â”€ app.py                  # App Streamlit AI chatbot
â”œâ”€â”€ insurance_products.py   # Dá»¯ liá»‡u sáº£n pháº©m + Ä‘iá»u kiá»‡n tiáº¿p nháº­n bá»“i thÆ°á»ng
â”œâ”€â”€ requirements.txt
â”œâ”€â”€ README.md
â””â”€â”€ claim_logs/             # ThÆ° má»¥c lÆ°u há»“ sÆ¡ (tá»± táº¡o)
    â””â”€â”€ claim_*.json
```

## TÃ¹y chá»‰nh

- Äá»•i model: chá»‰nh trong sidebar hoáº·c set env `CLAIM_MODEL`
- Äá»•i API endpoint: chá»‰nh trong sidebar hoáº·c set env `OLLAMA_BASE_URL`
- ThÃªm sáº£n pháº©m: thÃªm vÃ o `PRODUCTS` trong `insurance_products.py`

python -m streamlit run D:\WORK\idea\app.py

cd D:\WORK\idea
rd /s /q __pycache__
python -m streamlit run app.py
