# YTMP3 Bot v6

## วิธีติดตั้ง
```bash
git clone <repo>
cd ytmp3-bot-v6
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env   # ใส่ BOT_TOKEN และ ADMIN_ID
python3 bot.py
```

## ฟีเจอร์
- ดาวน์โหลด YouTube เป็น MP3
- เลือกส่ง DM / กลุ่ม
- ฝังปกและ metadata
- แสดง % การดาวน์โหลด
- ระบบคำสั่งพิเศษ (ช่วยเหลือ/ติดต่อแอดมิน)
