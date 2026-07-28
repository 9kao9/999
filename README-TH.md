# ชุดทดลอง ScrapingAnt กับ ExpHuay ทั้ง 9 หน้า

โฟลเดอร์ในคอมพิวเตอร์:

`C:\00000\lottery-site\scrapingant-github-trial`

ชุดนี้แยกจากระบบเดิมและชุด ScrapingBee โดยสมบูรณ์ ไม่ใช้
`C:\actions-runner` และไม่ต้องเปิด `run.cmd`

## ระบบนี้ทำงานอย่างไร

1. คุณกด Run workflow บน GitHub
2. คอมพิวเตอร์ของ GitHub เปิด `scrape_with_scrapingant.py`
3. โปรแกรมส่ง URL ทั้ง 9 หน้าไปให้ ScrapingAnt
4. ScrapingAnt เปิดหน้า ExpHuay และส่ง HTML กลับมา
5. โปรแกรมอ่านตัวเลขแล้วบันทึกลง `results.json`
6. เว็บไซต์ GitHub Pages อ่านข้อมูลจาก Repository ใหม่นี้

## สองโหมดทดลอง

Workflow มีตัวเลือก `render_javascript`

### false — ทดลองก่อน

- ไม่เปิด JavaScript
- ประมาณ 1 เครดิตต่อหน้า
- 9 หน้าใช้ประมาณ 9 เครดิต
- เลือกโหมดนี้เป็นรอบแรก

### true — ใช้เมื่อ false ไม่ผ่าน

- เปิด Headless Chrome และ JavaScript
- ประมาณ 10 เครดิตต่อหน้า
- 9 หน้าใช้ประมาณ 90 เครดิต

อย่าเริ่มจาก `true` เพราะควรตรวจสอบโหมดประหยัดก่อน

## ขั้นที่ 1: สมัคร ScrapingAnt

1. เข้า https://scrapingant.com/
2. สมัครบัญชีฟรี
3. ยืนยันอีเมล
4. เข้า Dashboard แล้วคัดลอก API Key

API Key เปรียบเสมือนรหัสผ่าน ห้ามใส่ลงในไฟล์หรือโพสต์ใน Repository
และไม่ต้องส่ง API Key มาในแชต

## ขั้นที่ 2: สร้าง Repository แยกสำหรับการทดลอง

แนะนำให้สร้าง Repository ใหม่เพื่อไม่ให้ชนกับ ScrapingBee เช่น:

`lottery-scrapingant-trial`

อัปโหลดทุกไฟล์ภายในโฟลเดอร์นี้:

- `.github/workflows/scrapingant-test.yml`
- `.gitignore`
- `index.html`
- `README-TH.md`
- `requirements.txt`
- `results.json`
- `scrape_with_scrapingant.py`

ตำแหน่ง Workflow ต้องเป็น:

`.github/workflows/scrapingant-test.yml`

## ขั้นที่ 3: สร้าง GitHub Secret

1. เปิด Repository สำหรับ ScrapingAnt
2. กด `Settings`
3. กด `Secrets and variables`
4. กด `Actions`
5. กด `New repository secret`
6. ช่อง Name ใส่ `SCRAPINGANT_API_KEY`
7. ช่อง Secret วาง API Key จาก ScrapingAnt
8. กด `Add secret`

ชื่อ Secret ต้องตรงทุกตัว:

`SCRAPINGANT_API_KEY`

Secret ของ ScrapingBee และ ScrapingAnt เป็นคนละตัวและใช้แทนกันไม่ได้

## ขั้นที่ 4: ทดลองแบบประหยัด

1. เปิดแท็บ `Actions`
2. เลือก `Test ScrapingAnt on 9 ExpHuay pages`
3. กด `Run workflow`
4. ตรง `render_javascript` เลือก `false`
5. กดปุ่มสีเขียว `Run workflow`
6. รอประมาณ 1–5 นาที

ไม่ต้องเปิด `run.cmd`

## ขั้นที่ 5: อ่านผล

เปิดงานล่าสุด แล้วกด:

`Test all 9 pages with ScrapingAnt`

ถ้าผ่านครบจะเห็น:

`สรุป: สำเร็จ 9/9 หน้า`

หากโหมด `false` ผ่านครบ ให้หยุดทดสอบ ไม่ต้องรันแบบ `true`

หาก `false` ไม่ผ่าน ให้รันใหม่อีกหนึ่งครั้งโดยเลือก:

`render_javascript = true`

แล้วเปรียบเทียบจำนวนหน้าที่สำเร็จ

## ขั้นที่ 6: เปิด GitHub Pages

1. เข้า `Settings`
2. กด `Pages`
3. Source เลือก `Deploy from a branch`
4. Branch เลือก `main`
5. Folder เลือก `/(root)`
6. กด `Save`

เว็บไซต์จะมีรูปแบบ:

`https://ชื่อผู้ใช้.github.io/ชื่อ-repository/`

หน้าเว็บค้นหา `results.json` จาก Repository ของตัวเองโดยอัตโนมัติ

## ยังไม่ตั้งเวลาอัตโนมัติ

หลังยืนยันว่า `render_javascript=true` ผ่านครบแล้ว ชุดนี้มี Workflow
ใช้งานจริงเพิ่มอีกหนึ่งไฟล์:

`.github/workflows/scrapingant-production.yml`

Workflow ใช้งานจริงจะ:

- เปิด JavaScript เสมอ
- เรียกเฉพาะหวยที่เพิ่งถึงเวลาออก
- ตรวจซ้ำรายการเดิมอีกหนึ่งครั้งหลังประมาณ 15 นาที
- ไม่เรียกทั้ง 9 หน้าพร้อมกันในรอบอัตโนมัติ
- คาดว่าใช้ประมาณ 4,000–5,000 เครดิตต่อเดือน

ปุ่มทดสอบครบ 9 หน้ายังคงอยู่ใน Workflow เดิม ใช้เฉพาะเวลาตรวจสอบหรือ
แก้ปัญหาเท่านั้น

## การกดรัน Workflow ใช้งานจริงด้วยตัวเอง

เปิด `Update lottery results with ScrapingAnt` แล้วกด `Run workflow`

ช่อง `lottery_keys` สามารถใส่ชื่อรายการเดียว เช่น:

`hanoi_vip`

หรือหลายรายการโดยคั่นด้วย comma:

`lao,hanoi_vip`

ถ้าปล่อยว่าง ระบบจะดึงทั้ง 9 หน้าและใช้ประมาณ 90 เครดิต

## ไฟล์สำคัญ

- `scrape_with_scrapingant.py` ตัวดึงข้อมูลผ่าน ScrapingAnt
- `results.json` ผลรางวัลและประวัติ
- `index.html` หน้าเว็บไซต์
- `.github/workflows/scrapingant-test.yml` คำสั่งทดสอบบน GitHub
- `.github/workflows/scrapingant-production.yml` ตารางใช้งานจริงแบบประหยัดเครดิต
- `requirements.txt` ส่วนประกอบที่ GitHub ต้องติดตั้ง
