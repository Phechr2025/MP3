
# เว็บดาวน์โหลด YouTube → MP3/MP4 (เว็บไซต์ mp3,4 v1)

**ไม่มี Telegram Bot**. ใช้ Flask + yt-dlp พร้อมแผงหลังบ้าน (ล็อกอินด้วย user/pass)  
ฟีเจอร์:
- ดาวน์โหลด MP3/MP4 โดยไม่ต้องล็อกอิน
- แสดง % ความคืบหน้าแบบเรียลไทม์
- ปุ่ม/โมชันสวยๆ + ยืนยันก่อนทำรายการสำคัญ
- หลังบ้าน: ปิด/เปิดดาวน์โหลด, ดูประวัติ, ปุ่มรีสตาร์ท (จำลอง)

## ติดตั้งบน VPS (Ubuntu 22.04/24.04)

```bash
sudo apt update -y
sudo apt install -y python3-venv ffmpeg git curl

# โครงสร้าง
mkdir -p /root/ytweb
cd /root/ytweb

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# ตั้งค่า
cp .env.example .env
nano .env   # เปลี่ยน PANEL_USER/PASS, PORT ถ้าต้องการ

# ทดสอบรัน
python3 app.py
# เปิด http://YOUR_IP:8090

# ทำเป็น service
sudo cp ytdl-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ytdl-web
sudo systemctl start ytdl-web
sudo systemctl status ytdl-web --no-pager
```

## ไฟล์สำคัญ
- `app.py` – แอป Flask
- `templates/` – หน้าเว็บ (index/admin)
- `static/` – CSS/JS
- `downloads/` – ไฟล์ที่โหลดเสร็จ
- `logs/history.json` – ประวัติ

