"""
AI-Powered Product Review Analysis System
CS460 AI Transformation - Bangkok University

Backend: FastAPI + SQLite
AI: Google Gemini 1.5 Flash
Frontend: served from templates/dashboard.html (Tailwind + Chart.js via CDN)
"""

import csv
import io
import json
import os
import re
import sqlite3
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import google.generativeai as genai
import httpx
from dotenv import load_dotenv, set_key
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "reviews.db"
ENV_PATH = BASE_DIR / ".env"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


def _normalize_key(raw: str) -> str:
    """Clean a pasted API key.

    Removes whitespace, BOM, surrounding quotes, an accidental
    `GEMINI_API_KEY=` prefix, and any non-printable-ASCII characters
    (gRPC requires the auth metadata header to be plain ASCII).
    """
    if not raw:
        return ""
    key = raw.strip().lstrip("﻿")
    if (key.startswith('"') and key.endswith('"')) or (key.startswith("'") and key.endswith("'")):
        key = key[1:-1].strip()
    if "=" in key:
        prefix, _, rest = key.partition("=")
        if prefix.strip().upper() in ("GEMINI_API_KEY", "API_KEY", "GOOGLE_API_KEY"):
            key = rest.strip()
    return re.sub(r"[^\x21-\x7E]", "", key)


GEMINI_API_KEY = _normalize_key(os.getenv("GEMINI_API_KEY", ""))
GROQ_API_KEY = _normalize_key(os.getenv("GROQ_API_KEY", ""))
PROVIDER = (os.getenv("PROVIDER", "gemini").strip().lower() or "gemini")
if PROVIDER not in ("gemini", "groq"):
    PROVIDER = "gemini"

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


def _save_env() -> None:
    """Persist provider + both keys to .env, preserving other entries (e.g. model overrides)."""
    if not ENV_PATH.exists():
        ENV_PATH.touch()
    set_key(str(ENV_PATH), "PROVIDER", PROVIDER, quote_mode="never")
    set_key(str(ENV_PATH), "GEMINI_API_KEY", GEMINI_API_KEY, quote_mode="never")
    set_key(str(ENV_PATH), "GROQ_API_KEY", GROQ_API_KEY, quote_mode="never")


def set_gemini_key(raw: str) -> None:
    global GEMINI_API_KEY
    GEMINI_API_KEY = _normalize_key(raw)
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
    _save_env()
    print(f"[config] Gemini key set (length={len(GEMINI_API_KEY)})", flush=True)


def set_groq_key(raw: str) -> None:
    global GROQ_API_KEY
    GROQ_API_KEY = _normalize_key(raw)
    _save_env()
    print(f"[config] Groq key set (length={len(GROQ_API_KEY)})", flush=True)


def set_provider(p: str) -> None:
    global PROVIDER
    p = p.strip().lower()
    if p not in ("gemini", "groq"):
        raise HTTPException(400, f"Invalid provider: {p}")
    PROVIDER = p
    _save_env()
    print(f"[config] Active provider = {p}", flush=True)


def _active_key() -> str:
    return GEMINI_API_KEY if PROVIDER == "gemini" else GROQ_API_KEY


# ---------- Prompt (from project spec, with few-shot examples) ----------
ANALYSIS_PROMPT = """คุณคือ AI นักวิเคราะห์รีวิวสินค้าสำหรับธุรกิจออนไลน์ไทย
จากรีวิวต่อไปนี้ ให้วิเคราะห์และตอบเป็น JSON ตามรูปแบบที่กำหนด:
- sentiment: positive | negative | neutral | mixed
- score: คะแนนความพึงพอใจ 0-100
- issues: รายการปัญหาที่พบ (ถ้าไม่มีให้ใส่ array ว่าง)
- positives: รายการข้อดีที่พบ (ถ้าไม่มีให้ใส่ array ว่าง)
- recommendation: คำแนะนำสั้นๆ สำหรับเจ้าของร้าน

ตัวอย่าง:
Input: "รอของนานแต่เนื้อผ้าดีมาก"
Output: {"sentiment":"mixed","score":60,"issues":["ขนส่งช้า"],"positives":["คุณภาพผ้าดี"],"recommendation":"ปรับปรุงการจัดส่ง"}

Input: "ของดีมาก ส่งไว ราคาถูก ประทับใจ"
Output: {"sentiment":"positive","score":95,"issues":[],"positives":["คุณภาพดี","จัดส่งเร็ว","ราคาถูก"],"recommendation":"รักษามาตรฐานนี้ต่อไป"}

Input: "ของแตกตอนได้รับ ติดต่อร้านไม่ได้ ผิดหวังมาก"
Output: {"sentiment":"negative","score":10,"issues":["สินค้าเสียหาย","ติดต่อร้านไม่ได้"],"positives":[],"recommendation":"ปรับปรุงบรรจุภัณฑ์และช่องทางติดต่อลูกค้า"}

วิเคราะห์รีวิวต่อไปนี้:
Input: "<<REVIEW>>"
Output:"""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "sentiment": {"type": "string", "enum": ["positive", "negative", "neutral", "mixed"]},
        "score": {"type": "integer"},
        "issues": {"type": "array", "items": {"type": "string"}},
        "positives": {"type": "array", "items": {"type": "string"}},
        "recommendation": {"type": "string"},
    },
    "required": ["sentiment", "score", "issues", "positives", "recommendation"],
}


# ---------- Database ----------
def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS stores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            review_text TEXT NOT NULL,
            sentiment TEXT NOT NULL,
            score INTEGER NOT NULL,
            issues TEXT NOT NULL,
            positives TEXT NOT NULL,
            recommendation TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Migrate: add store_id column to reviews if missing
    cols = [row[1] for row in conn.execute("PRAGMA table_info(reviews)").fetchall()]
    if "store_id" not in cols:
        conn.execute("ALTER TABLE reviews ADD COLUMN store_id INTEGER")

    # Ensure at least one store exists
    first = conn.execute("SELECT id FROM stores ORDER BY id LIMIT 1").fetchone()
    if first is None:
        conn.execute("INSERT INTO stores (name) VALUES (?)", ("ร้านค้าหลัก",))
        first = conn.execute("SELECT id FROM stores ORDER BY id LIMIT 1").fetchone()
    default_store_id = first[0]

    # Backfill any reviews that don't have a store yet
    conn.execute(
        "UPDATE reviews SET store_id = ? WHERE store_id IS NULL",
        (default_store_id,),
    )

    conn.commit()
    conn.close()


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---------- Preprocessing ----------
def clean_text(text: str) -> str:
    return " ".join(text.split()).strip()


# ---------- AI Analyzer ----------
def _parse_json_response(raw: str) -> dict:
    """Strip code fences, parse JSON, coerce/clamp expected fields."""
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        result = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(500, f"AI response was not valid JSON: {raw[:300]}")

    result["score"] = max(0, min(100, int(result.get("score", 0))))
    result["issues"] = [str(x) for x in result.get("issues", [])]
    result["positives"] = [str(x) for x in result.get("positives", [])]
    result["recommendation"] = str(result.get("recommendation", ""))
    if result.get("sentiment") not in ("positive", "negative", "neutral", "mixed"):
        result["sentiment"] = "neutral"
    return result


def _analyze_gemini(review_text: str) -> dict:
    if not GEMINI_API_KEY:
        raise HTTPException(500, "Gemini API key not configured")

    model = genai.GenerativeModel(
        GEMINI_MODEL,
        generation_config={
            "response_mime_type": "application/json",
            "temperature": 0.2,
        },
    )
    prompt = ANALYSIS_PROMPT.replace("<<REVIEW>>", review_text.replace('"', "'"))

    try:
        response = model.generate_content(prompt)
        raw = (response.text or "").strip()
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(502, f"Gemini API error ({GEMINI_MODEL}): {type(e).__name__}: {e}")

    print(f"[analyze] gemini ok, {len(raw)} chars", flush=True)
    return _parse_json_response(raw)


def _analyze_groq(review_text: str) -> dict:
    if not GROQ_API_KEY:
        raise HTTPException(500, "Groq API key not configured")

    prompt = ANALYSIS_PROMPT.replace("<<REVIEW>>", review_text.replace('"', "'"))
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(
                GROQ_API_URL,
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                json={
                    "model": GROQ_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.2,
                },
            )
        r.raise_for_status()
        raw = r.json()["choices"][0]["message"]["content"].strip()
    except httpx.HTTPStatusError as e:
        try:
            detail = e.response.json().get("error", {}).get("message") or e.response.text[:300]
        except Exception:
            detail = e.response.text[:300]
        raise HTTPException(e.response.status_code, f"Groq error ({GROQ_MODEL}): {detail}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(502, f"Groq API error: {type(e).__name__}: {e}")

    print(f"[analyze] groq ok, {len(raw)} chars", flush=True)
    return _parse_json_response(raw)


def analyze_review(review_text: str) -> dict:
    print(f"[analyze] provider={PROVIDER} review={review_text[:80]!r}", flush=True)
    if PROVIDER == "groq":
        return _analyze_groq(review_text)
    return _analyze_gemini(review_text)


def save_analysis(review_text: str, analysis: dict, store_id: int) -> int:
    with get_db() as conn:
        cursor = conn.execute(
            """INSERT INTO reviews
               (store_id, review_text, sentiment, score, issues, positives, recommendation)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                store_id,
                review_text,
                analysis["sentiment"],
                analysis["score"],
                json.dumps(analysis["issues"], ensure_ascii=False),
                json.dumps(analysis["positives"], ensure_ascii=False),
                analysis["recommendation"],
            ),
        )
        return cursor.lastrowid


# ---------- FastAPI App ----------
app = FastAPI(title="AI-Powered Product Review Analysis System")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


class ReviewRequest(BaseModel):
    text: str
    store_id: int


class ConfigUpdate(BaseModel):
    provider: str
    key: str = ""


class StoreCreate(BaseModel):
    name: str


def _assert_store_exists(store_id: int) -> None:
    with get_db() as conn:
        row = conn.execute("SELECT id FROM stores WHERE id = ?", (store_id,)).fetchone()
    if row is None:
        raise HTTPException(404, f"Store {store_id} not found")


@app.get("/api/stores")
def list_stores():
    with get_db() as conn:
        rows = conn.execute(
            """SELECT s.id, s.name,
                      (SELECT COUNT(*) FROM reviews r WHERE r.store_id = s.id) AS review_count
               FROM stores s ORDER BY s.id"""
        ).fetchall()
    return [{"id": r["id"], "name": r["name"], "review_count": r["review_count"]} for r in rows]


@app.post("/api/stores")
def create_store(req: StoreCreate):
    name = req.name.strip()
    if not name:
        raise HTTPException(400, "Store name is required")
    if len(name) > 80:
        raise HTTPException(400, "Store name is too long (max 80 chars)")
    try:
        with get_db() as conn:
            cur = conn.execute("INSERT INTO stores (name) VALUES (?)", (name,))
        return {"id": cur.lastrowid, "name": name}
    except sqlite3.IntegrityError:
        raise HTTPException(400, f"Store '{name}' already exists")


@app.delete("/api/stores/{store_id}")
def delete_store(store_id: int):
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM stores").fetchone()[0]
        if total <= 1:
            raise HTTPException(400, "Cannot delete the only remaining store")
        _ = _assert_store_exists  # keep symbol used
        exists = conn.execute("SELECT id FROM stores WHERE id = ?", (store_id,)).fetchone()
        if not exists:
            raise HTTPException(404, f"Store {store_id} not found")
        conn.execute("DELETE FROM reviews WHERE store_id = ?", (store_id,))
        conn.execute("DELETE FROM stores WHERE id = ?", (store_id,))
    return {"deleted": store_id}


def _provider_status(name: str) -> dict:
    if name == "gemini":
        k, model = GEMINI_API_KEY, GEMINI_MODEL
    else:
        k, model = GROQ_API_KEY, GROQ_MODEL
    return {
        "configured": bool(k),
        "last4": k[-4:] if len(k) >= 4 else None,
        "length": len(k),
        "model": model,
    }


@app.get("/api/config/status")
def config_status():
    active = _provider_status(PROVIDER)
    return {
        "provider": PROVIDER,
        "configured": active["configured"],
        "last4": active["last4"],
        "length": active["length"],
        "providers": {
            "gemini": _provider_status("gemini"),
            "groq": _provider_status("groq"),
        },
    }


def _test_provider(provider: str) -> None:
    if provider == "gemini":
        if not GEMINI_API_KEY:
            raise HTTPException(400, "Gemini key not configured yet")
        m = genai.GenerativeModel(GEMINI_MODEL)
        m.generate_content("ok", generation_config={"max_output_tokens": 5})
    else:
        if not GROQ_API_KEY:
            raise HTTPException(400, "Groq key not configured yet")
        with httpx.Client(timeout=15.0) as client:
            r = client.post(
                GROQ_API_URL,
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                json={
                    "model": GROQ_MODEL,
                    "messages": [{"role": "user", "content": "say ok"}],
                    "max_tokens": 5,
                },
            )
        r.raise_for_status()


@app.post("/api/config")
def update_config(req: ConfigUpdate):
    provider = req.provider.strip().lower()
    if provider not in ("gemini", "groq"):
        raise HTTPException(400, "Provider must be 'gemini' or 'groq'")

    new_key_provided = bool(req.key.strip())

    if new_key_provided:
        normalized = _normalize_key(req.key)
        if not normalized:
            raise HTTPException(400, "API key is empty after cleanup")
        if len(normalized) < 20:
            raise HTTPException(400, f"Key looks too short ({len(normalized)} chars after cleanup)")
        if provider == "gemini":
            set_gemini_key(req.key)
        else:
            set_groq_key(req.key)
    else:
        # No new key — must already have one for the target provider
        target_key = GEMINI_API_KEY if provider == "gemini" else GROQ_API_KEY
        if not target_key:
            raise HTTPException(400, f"No saved key for {provider}. Please paste one.")

    set_provider(provider)

    # Only verify with a live call when the user just pasted a brand-new key.
    # Switching back to a previously-saved key skips the test so rate limits
    # don't block you from switching.
    if new_key_provided:
        try:
            _test_provider(provider)
        except HTTPException:
            raise
        except httpx.HTTPStatusError as e:
            try:
                detail = e.response.json().get("error", {}).get("message") or e.response.text[:300]
            except Exception:
                detail = e.response.text[:300]
            raise HTTPException(502, f"{provider} rejected key: {detail}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise HTTPException(502, f"{provider} test failed: {type(e).__name__}: {e}")

    return {"configured": True, "provider": provider}


@app.post("/api/analyze")
def api_analyze(req: ReviewRequest):
    text = clean_text(req.text)
    if not text:
        raise HTTPException(400, "Review text is required")
    _assert_store_exists(req.store_id)
    analysis = analyze_review(text)
    rid = save_analysis(text, analysis, req.store_id)
    return {"id": rid, "review": text, **analysis}


@app.post("/api/analyze/csv")
async def api_analyze_csv(file: UploadFile = File(...), store_id: int = Form(...)):
    _assert_store_exists(store_id)
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "CSV file required")

    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp874", errors="replace")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(400, "Empty or invalid CSV")

    review_col = None
    for name in reader.fieldnames:
        if name.strip().lower() in ("review", "text", "comment", "รีวิว", "ความคิดเห็น"):
            review_col = name
            break
    if review_col is None:
        review_col = reader.fieldnames[0]

    results, errors = [], []
    for row in reader:
        review = clean_text(row.get(review_col) or "")
        if not review:
            continue
        try:
            analysis = analyze_review(review)
            rid = save_analysis(review, analysis, store_id)
            results.append({"id": rid, "review": review, **analysis})
        except HTTPException as e:
            errors.append({"review": review, "error": e.detail})
        except Exception as e:
            errors.append({"review": review, "error": str(e)})

    return {"processed": len(results), "errors": errors, "results": results}


def _range_to_cutoff(range_key: str) -> str | None:
    """Convert a range preset to a SQLite-format UTC cutoff datetime, or None for 'all'."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if range_key == "today":
        cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif range_key == "1h":
        cutoff = now - timedelta(hours=1)
    elif range_key == "24h":
        cutoff = now - timedelta(hours=24)
    elif range_key == "7d":
        cutoff = now - timedelta(days=7)
    elif range_key == "30d":
        cutoff = now - timedelta(days=30)
    else:
        return None
    return cutoff.strftime("%Y-%m-%d %H:%M:%S")


@app.get("/api/stats")
def api_stats(store_id: int, range: str = "all", sort: str = "desc"):
    _assert_store_exists(store_id)
    order = "ASC" if sort == "asc" else "DESC"
    cutoff = _range_to_cutoff(range)

    where = ["store_id = ?"]
    params: list = [store_id]
    if cutoff:
        where.append("created_at >= ?")
        params.append(cutoff)
    where_sql = "WHERE " + " AND ".join(where)

    with get_db() as conn:
        rows = conn.execute(
            f"SELECT * FROM reviews {where_sql} ORDER BY created_at {order}",
            params,
        ).fetchall()

    total = len(rows)
    if total == 0:
        return {
            "total": 0,
            "sentiment_counts": {"positive": 0, "negative": 0, "neutral": 0, "mixed": 0},
            "avg_score": 0,
            "top_issues": [],
            "top_positives": [],
            "recent": [],
        }

    sentiment_counts = Counter(r["sentiment"] for r in rows)
    avg_score = sum(r["score"] for r in rows) / total

    issue_counter: Counter = Counter()
    positive_counter: Counter = Counter()
    for r in rows:
        for issue in json.loads(r["issues"]):
            issue_counter[issue] += 1
        for pos in json.loads(r["positives"]):
            positive_counter[pos] += 1

    recent = [
        {
            "id": r["id"],
            "review_text": r["review_text"],
            "sentiment": r["sentiment"],
            "score": r["score"],
            "issues": json.loads(r["issues"]),
            "positives": json.loads(r["positives"]),
            "recommendation": r["recommendation"],
            "created_at": r["created_at"],
        }
        for r in rows[:50]
    ]

    return {
        "total": total,
        "sentiment_counts": {
            "positive": sentiment_counts.get("positive", 0),
            "negative": sentiment_counts.get("negative", 0),
            "neutral": sentiment_counts.get("neutral", 0),
            "mixed": sentiment_counts.get("mixed", 0),
        },
        "avg_score": round(avg_score, 1),
        "top_issues": issue_counter.most_common(10),
        "top_positives": positive_counter.most_common(10),
        "recent": recent,
    }


@app.delete("/api/reviews")
def clear_reviews(store_id: int):
    _assert_store_exists(store_id)
    with get_db() as conn:
        conn.execute("DELETE FROM reviews WHERE store_id = ?", (store_id,))
    return {"status": "cleared", "store_id": store_id}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
