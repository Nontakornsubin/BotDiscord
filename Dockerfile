FROM python:3.11-slim

# เพิ่ม git เข้าไปในคำสั่งติดตั้งระดับระบบปฏิบัติการ
RUN apt-get update && apt-get install -y ffmpeg git

# ตั้งค่าพื้นที่ทำงาน
WORKDIR /app

# คัดลอกและติดตั้ง Library ต่างๆ
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# คัดลอกโค้ดทั้งหมดลงเซิร์ฟเวอร์
COPY . .

# สั่งรันบอท
CMD ["python", "main.py"]
