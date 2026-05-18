# สรุปสิ่งที่ต้องแก้ในเอกสาร AI_01.pdf

จากการเทียบเอกสาร `AI_01.pdf` กับโค้ดและฟีเจอร์จริงในแอป

---

## 🔴 ส่วนที่ต้องลบหรือแก้ทันที (defend ไม่ได้ถ้าโดนถาม)

### 1. Section 4.2 — Accuracy Metrics (ลบทิ้งหรือทำใหม่)

**ปัญหา:** ตัวเลข Precision/Recall/F1 ทั้งหมดเป็นตัวเลขลอย — แอปไม่มีโค้ดที่:
- เก็บ Ground Truth label
- เปรียบเทียบ AI output กับ label
- คำนวณ Precision/Recall/F1

**ทางเลือก:**

**A) ลบ section 4.2 ทิ้ง** แล้วเขียนแทนเป็น "ทดสอบเชิงคุณภาพ" — ทดลองอัปโหลด `review_shopping.csv` ดูผลด้วยตา

**B) วัดจริง** — ใช้ไฟล์ `review_shopping.csv` (มี label `pos`/`neg` 128 รายการเป็น Ground Truth) เขียนสคริปต์เปรียบเทียบ แล้วใส่ตัวเลขจริง

> 💡 ถ้าเลือก A ให้ลบ 4.5 บรรทัด "ระบบสามารถวิเคราะห์รีวิวได้ถูกต้อง 92.5%" ออกด้วย

---

### 2. Section 4.3 — Performance Metrics (แก้ตัวเลข)

| รายการ | เอกสารบอก | ของจริง (sequential, ในแอป) | แก้เป็น |
|---|---|---|---|
| 100 รีวิว / Gemini **paid** (ไม่ throttle) | ~52 วินาที | ~200-300 วินาที | **~3-5 นาที** |
| 100 รีวิว / Gemini **free** (throttle 4.5s/req) | — | ~450 วินาที (15 RPM cap) | **~7-8 นาที** |
| 500 รีวิว / Gemini **paid** | ~4 นาที | ~15-25 นาที | **~20 นาที** |
| 500 รีวิว / Gemini **free** | — | ~2,250 วินาที | **~40 นาที** |
| ต้นทุน Gemini 1.5 Flash | 0.002 บาท | ✅ (แต่ 1.5 ถูก deprecate แล้ว) | — |
| ต้นทุน Gemini **2.5 Flash paid** | — | ~0.012 บาท/รีวิว | **~0.01 บาท** |
| ต้นทุน Gemini **2.5 Flash free** | — | **0 บาท** | **0 บาท** |
| Human baseline 78% | 78% | ไม่มีแหล่งที่มา | **ลบบรรทัดนี้ทิ้ง** |
| Time Saved 99.2% | 99.2% | derivative ของตัวเลขเดิมที่ผิด | **คำนวณใหม่ตามเวลาที่แก้** |

**ตัวอย่างตาราง 4.3 หลังแก้ (Gemini 2.5 Flash):**

```
การทดสอบ                       ระบบเดิม (Manual)    ระบบใหม่ (Free tier)    ระบบใหม่ (Paid tier)
เวลาวิเคราะห์ 100 รีวิว         ~3.5 ชั่วโมง          ~7-8 นาที                ~3-5 นาที
เวลาวิเคราะห์ 500 รีวิว         ~17 ชั่วโมง           ~40 นาที                 ~20 นาที
ต้นทุนต่อรีวิว                  ~2.5 บาท (ค่าแรง)    0 บาท                    ~0.01 บาท
การลดเวลา (100 รีวิว)           —                     ลดลง ~96.5%              ลดลง ~98%
```

> หมายเหตุ: Free tier ของ Gemini 2.5 Flash จำกัด **15 คำขอ/นาที** ระบบจึงหน่วง 4.5 วินาทีระหว่างคำขอเพื่อไม่ให้เกิน limit · Paid tier ไม่มีการหน่วง

---

### 3. Section 4.4 — User Feedback (ตรวจสอบ)

ถ้า**ไม่ได้ทำสำรวจ 10 คนจริง** → ลบทั้ง section ทิ้ง หรือเขียนเป็น "ผลตอบรับเบื้องต้นจากทีมผู้พัฒนา"

ถ้า**ทำจริง** → เก็บไว้แต่ระบุชื่อ/ตำแหน่งของผู้ให้คะแนน (รุ่นพี่/อาจารย์/เพื่อน)

---

## 🟡 ความไม่ตรงกับแอปจริง (ต้องแก้ให้สอดคล้อง)

### หน้า 1 (หน้าปก)

| ในเอกสาร | แก้เป็น |
|---|---|
| CS460 **Artificial Intelligence** | **เลือกอย่างใดอย่างหนึ่ง** — ในหน้าอื่นใช้ "AI Transformation" |

### บทนำ + Section 3.1, 3.2 (ทุกที่ที่พูดถึง AI Engine)

| ในเอกสาร | แก้เป็น |
|---|---|
| Google Gemini **1.5** Flash | Google Gemini **2.5** Flash (Gemini 1.5 ถูก deprecate ตั้งแต่ Sep 2025) |
| ใช้ provider เดียว | ใช้ได้ **2 providers**: Gemini 2.5 Flash **หรือ** Groq Llama 3.3 70B (สลับได้ใน UI) |

### Section 2 (Workflow) และ Section 3.2 (Tech Stack)

| ในเอกสาร | แก้เป็น |
|---|---|
| Database: **PostgreSQL** | Database: **SQLite** (file `reviews.db` ในเครื่อง) |
| Frontend: **React.js** + Tailwind | Frontend: **HTML + Tailwind CSS + Chart.js** (ผ่าน CDN, ไม่ใช้ React) |

> ❗ ถ้าจะคงคำว่า React/PostgreSQL ไว้ ต้องเปลี่ยนแอปให้ใช้จริง — ซึ่งไม่จำเป็น Tailwind+Chart.js+SQLite ทำได้ครบเหมือนกัน

---

## 🟢 ฟีเจอร์ที่มีในแอปจริงแต่ไม่ได้ระบุในเอกสาร (ควรเพิ่ม)

ฟีเจอร์เหล่านี้ทำให้คะแนนดีขึ้น — แนะนำเพิ่มใน Section 3 หรือ 5.3

1. **Multi-provider support** — เลือกระหว่าง Gemini และ Groq พร้อมระบบ test key อัตโนมัติ
2. **Multi-store management** — สร้าง/ลบ/สลับร้านได้ แต่ละร้านมี dashboard แยก
3. **Free/Paid tier toggle** — ปรับ rate limit อัตโนมัติตาม tier ที่ผู้ใช้เลือก
4. **Auto-throttling สำหรับ CSV upload** — หน่วงระหว่างคำขอเพื่อไม่ให้เกิน rate limit + แสดงเวลาที่เหลือแบบ real-time
5. **กรองตามช่วงเวลา** — All / 1h / Today / 24h / 7d / 30d + sort เก่า↔ใหม่
6. **Export เป็น PDF** — print-optimized layout (stats + sentiment chart หน้า 1, top issues + positives หน้า 2)
7. **Export เป็น CSV** — ดาวน์โหลดข้อมูลทั้งหมดของร้านที่เลือก พร้อม BOM (เปิดใน Excel ได้)
8. **API Key setup ใน UI** — popup ตั้งค่าครั้งแรก, แสดง 4 หลักท้ายของ key ที่บันทึก
9. **CSV batch upload** — รองรับ encoding UTF-8, UTF-8 BOM, CP874

---

## 📝 ช่องว่างในเอกสารที่ต้องเติม

| หน้า | ตำแหน่ง | สิ่งที่ต้องใส่ |
|---|---|---|
| 6 | `[ แทรก Workflow Diagram ]` | วาด flowchart 5 ขั้นตอน (Input → Preprocessing → AI → Storage → Output) |
| 8 | `ลิงก์ Web App Demo: ____` | https://github.com/delmoonkarn/CS460 |
| 9 | `[ แทรก Screenshot ]` | แคปหน้าจอ Dashboard, popup ตั้งค่า API, ตัวอย่างผลวิเคราะห์ |

---

## 📚 เอกสารอ้างอิง (แก้)

อ้างอิงที่ 2 (React.js) และ 4 (PostgreSQL) ไม่จำเป็นแล้วถ้าแก้ Tech Stack ตามข้อ 🟡

**แทนด้วย:**

```
2) Tailwind Labs. (2024). Tailwind CSS Documentation. https://tailwindcss.com/docs
3) Chart.js Contributors. (2024). Chart.js Documentation. https://www.chartjs.org/docs/
4) SQLite Consortium. (2024). SQLite Documentation. https://www.sqlite.org/docs.html
6) Groq Inc. (2024). Groq Console API Reference. https://console.groq.com/docs
```

---

## ✅ Checklist สรุปก่อนส่ง

- [ ] แก้ Gemini 1.5 → 2.5 ทุกที่ในเอกสาร
- [ ] เพิ่ม Groq Llama 3.3 70B เป็น provider ทางเลือก
- [ ] แก้ PostgreSQL → SQLite
- [ ] แก้ React.js → HTML + Tailwind + Chart.js
- [ ] เลือกชื่อวิชาเดียว (AI Transformation หรือ Artificial Intelligence)
- [ ] ลบหรือทำใหม่ Section 4.2 (Precision/Recall/F1)
- [ ] แก้ตัวเลขใน 4.3 ให้สมจริง (เวลา + ราคา)
- [ ] ตัดสินใจ 4.4 (มีสำรวจจริงไหม?)
- [ ] ใส่ลิงก์ GitHub ในหน้า 8
- [ ] วาด Workflow Diagram หน้า 6
- [ ] แคป screenshot หน้า 9
- [ ] เพิ่มฟีเจอร์ใหม่ในเอกสาร (multi-store, export, filter, throttle)
- [ ] อัปเดต References list

---

## 🚀 ถ้ามีเวลา — ทำให้ 4.2 legit ภายใน 10 นาที

ไฟล์ `reviews samples/review_shopping.csv` มี 128 รีวิวพร้อม label `pos`/`neg` ในคอลัมน์ที่ 2 อยู่แล้ว — เป็น Ground Truth สำเร็จรูป

เขียนสคริปต์เล็กๆ:
1. อ่าน CSV → ดึง (review_text, label)
2. รันผ่าน Gemini/Groq → เก็บ predicted sentiment
3. Map: `pos` ↔ `positive`, `neg` ↔ `negative`
4. คำนวณ confusion matrix → Precision/Recall/F1

ใช้เวลาเขียน ~5 นาที + รัน ~5 นาที (Groq free tier 30 RPM) = **10 นาที**

ได้ตัวเลขจริง defend ได้ทุกคำถาม

ขอแค่บอกว่าให้ทำ ผมจะเขียนให้
