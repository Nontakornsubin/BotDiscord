FROM python:3.11-slim

# บังคับติดตั้ง ffmpeg ในระดับระบบปฏิบัติการ
RUN apt-get update && apt-get install -y ffmpeg

# ตั้งค่าพื้นที่ทำงาน
WORKDIR /app

# คัดลอกและติดตั้ง Library ต่างๆ
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# คัดลอกโค้ดทั้งหมดลงเซิร์ฟเวอร์
COPY . .

# สั่งรันบอท
CMD ["python", "main.py"]