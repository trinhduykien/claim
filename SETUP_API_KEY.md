# HÆ°á»›ng dáº«n setup API Key cho AI Deduction Module

## âš ï¸ QUAN TRá»ŒNG: Báº£o máº­t API Key

**KHÃ”NG bao giá» dÃ¡n API key vÃ o chat, Discord, hay commit lÃªn GitHub.**

## CÃ¡ch 1: Environment Variable (khuyÃªn dÃ¹ng)

### PowerShell (táº¡m thá»i - máº¥t khi táº¯t terminal)
```powershell
$env:KIMI_API_KEY = "your-key-here"
streamlit run app.py
```

### PowerShell (vÄ©nh viá»…n - cho user hiá»‡n táº¡i)
```powershell
[System.Environment]::SetEnvironmentVariable("KIMI_API_KEY", "your-api-key-here", "User")
```
â†’ Restart terminal Ä‘á»ƒ Ã¡p dá»¥ng.

## CÃ¡ch 2: File local (khÃ´ng commit lÃªn git)

Táº¡o file `.kimi_api_key` trong cÃ¹ng thÆ° má»¥c vá»›i `app.py`:
```
your-api-key-here
```

File nÃ y Ä‘Ã£ Ä‘Æ°á»£c thÃªm vÃ o `.gitignore` â†’ sáº½ khÃ´ng bá»‹ push lÃªn GitHub.

## Kiá»ƒm tra

Sau khi setup, cháº¡y app vÃ  thá»­:
1. HoÃ n táº¥t Ä‘Ã¡nh giÃ¡ claim â†’ káº¿t quáº£ "Äá»¦ ÄIá»€U KIá»†N"
2. Upload áº£nh + há»£p Ä‘á»“ng
3. Báº¥m "PhÃ¢n tÃ­ch kháº¥u trá»«" â†’ AI sáº½ xá»­ lÃ½

Náº¿u chÆ°a cÃ³ API key, app sáº½ hiá»ƒn thá»‹ thÃ´ng bÃ¡o lá»—i hÆ°á»›ng dáº«n.
