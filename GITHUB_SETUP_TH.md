# ขึ้น HitRun V3 บน GitHub (รันเองทุกวัน + เว็บแดชบอร์ด + Telegram)

หลังตั้งค่าเสร็จ GitHub จะรันระบบให้ **จันทร์–ศุกร์ 18:00 น. (เวลาไทย)** โดยไม่ต้องเปิดคอม
(GitHub อาจช้ากว่าเวลาที่ตั้ง 5–30 นาที)

## 1. สร้าง repo สาธารณะ
1. เข้า https://github.com/new
2. Repository name: `hitrun3` (ตั้งชื่ออื่นได้ ลิงก์เว็บจะเปลี่ยนตาม)
3. เลือก **Public** และ**ไม่ต้อง**ติ๊ก Add README / .gitignore
4. กด **Create repository**

## 2. อัปโหลดโค้ด (เลือกวิธีใดวิธีหนึ่ง)
**วิธี A: GitHub Desktop (ง่ายสุด)**
1. ติดตั้ง https://desktop.github.com แล้วล็อกอิน
2. File → Add local repository → เลือกโฟลเดอร์ `D:\APP เขียนเอง\hitrun_th V3` → ถ้าถาม ให้กด *create a repository* (อย่าเลือก .gitignore เพราะมีอยู่แล้ว)
3. เช็กรายการไฟล์ทางซ้าย: **ต้องไม่มี** `.venv`, `out`, `data/backup`
4. ใส่ข้อความ เช่น `first upload` → Commit → **Publish repository** → *เอาติ๊ก Keep this code private ออก* → ชื่อ `hitrun3`

**วิธี B: คำสั่ง git** (ต้องติดตั้ง git ก่อน)
```bash
cd "D:\APP เขียนเอง\hitrun_th V3"
git init -b main
git add .
git status          # ตรวจว่าไม่มี .venv / out / data/backup
git commit -m "first upload"
git remote add origin https://github.com/<ชื่อคุณ>/hitrun3.git
git push -u origin main
```

## 3. ใส่ความลับ Telegram
repo → **Settings → Secrets and variables → Actions → New repository secret** เพิ่ม 2 ตัว:
- `TELEGRAM_BOT_TOKEN` = token บอท
- `TELEGRAM_CHAT_ID` = chat_id (วิธีหาดูใน `TELEGRAM_SETUP_TH.md`)

ความลับนี้คนอื่นมองไม่เห็นแม้ repo จะเป็นสาธารณะ

## 4. เปิดเว็บ (GitHub Pages)
repo → **Settings → Pages → Build and deployment → Source: เลือก "GitHub Actions"**

## 5. อนุญาตให้ระบบบันทึกข้อมูลกลับ
repo → **Settings → Actions → General → Workflow permissions → เลือก "Read and write permissions" → Save**

## 6. รันครั้งแรกด้วยมือ
repo → แท็บ **Actions** → (ถ้ามีปุ่มเปิดใช้ workflow ให้กดก่อน) → **HitRun daily** → **Run workflow**
- ใช้เวลาประมาณ 3–6 นาที ถ้าขึ้นเครื่องหมายถูกสีเขียวคือเรียบร้อย
- Telegram จะได้รับรายการพอร์ตของเดือนล่าสุด + สรุปพอร์ตจำลอง

## 7. เปิดแดชบอร์ด
`https://<ชื่อคุณ>.github.io/hitrun3/`
ไฟล์ให้ AI อ่านต่อ: `https://<ชื่อคุณ>.github.io/hitrun3/ai_report.md` และ `ai_report.json`

## ข้อควรรู้
- repo สาธารณะ: คนอื่นเห็นโค้ด ผลทดสอบ และ**พอร์ตจำลอง (ตัวเลขสมมติ)** — ห้ามใส่ข้อมูลพอร์ตจริง/บัญชีโบรกเกอร์
- ทุกวัน GitHub จะ commit ราคาใหม่ (`data/prices`, `data/paper_state.json`, `data/alert_state.json`) กลับเข้า repo เอง
  ถ้าจะแก้ไฟล์บนคอมแล้วอัปขึ้นอีก ให้กด **Pull/Fetch origin** ใน GitHub Desktop ก่อน ไม่งั้นจะชนกัน
- ถ้า workflow ล้มเหลว จะมีข้อความ ❌ เข้า Telegram พร้อมลิงก์ log
- บนคอมยังใช้ `HITRUN.bat` ได้เหมือนเดิม
