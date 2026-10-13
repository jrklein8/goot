"""
Contractor estimating + scheduling app (rough draft).

Run:  python app.py        -> http://localhost:5000
Demo login: demo@example.com / demo1234
"""

import json
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, date
from functools import wraps

from flask import Flask, g, jsonify, request, session, send_from_directory, Response, abort
from werkzeug.security import generate_password_hash, check_password_hash

import pricing

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "data", "app.db")
SECRET_PATH = os.path.join(BASE, "data", "secret.key")

app = Flask(__name__, static_folder=os.path.join(BASE, "static"), static_url_path="/static")


def _secret():
    os.makedirs(os.path.dirname(SECRET_PATH), exist_ok=True)
    if not os.path.exists(SECRET_PATH):
        with open(SECRET_PATH, "w") as f:
            f.write(secrets.token_hex(32))
    with open(SECRET_PATH) as f:
        return f.read().strip()


app.secret_key = _secret()
app.json.sort_keys = False  # keep status / calculator order as defined
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0  # no stale CSS/JS while iterating
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  PERMANENT_SESSION_LIFETIME=timedelta(days=14))

JOB_STATUSES = ["lead", "estimating", "quoted", "approved", "in_progress", "complete", "lost"]
EVENT_TYPES = ["site_visit", "work", "inspection", "delivery", "meeting", "other"]

# ------------------------------------------------------------------ database

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
  name TEXT, business_name TEXT, phone TEXT, license_no TEXT, address TEXT,
  markup_pct REAL DEFAULT 20, contingency_pct REAL DEFAULT 5, tax_pct REAL DEFAULT 7.0,
  price_overrides TEXT DEFAULT '{}', ics_token TEXT UNIQUE, created_at TEXT
);
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, job_no TEXT,
  title TEXT NOT NULL, client_name TEXT, client_phone TEXT, client_email TEXT,
  address TEXT, job_type TEXT, status TEXT DEFAULT 'lead', notes TEXT,
  markup_pct REAL, contingency_pct REAL, tax_pct REAL,
  conditions TEXT DEFAULT '[]', trips INTEGER DEFAULT 0,
  created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS line_items (
  id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL, source TEXT, group_label TEXT,
  description TEXT NOT NULL, category TEXT NOT NULL, qty REAL, unit TEXT,
  unit_cost REAL, total REAL, sort_order INTEGER DEFAULT 0, created_at TEXT
);
CREATE TABLE IF NOT EXISTS materials (
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, section TEXT, label TEXT NOT NULL,
  unit TEXT DEFAULT 'ea', cost REAL DEFAULT 0, category TEXT DEFAULT 'material', created_at TEXT
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, job_id INTEGER,
  title TEXT NOT NULL, type TEXT DEFAULT 'work', start TEXT NOT NULL, end TEXT,
  all_day INTEGER DEFAULT 0, location TEXT, notes TEXT, created_at TEXT
);
"""


def db():
    if "db" not in g:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    d = g.pop("db", None)
    if d is not None:
        d.close()


def now():
    return datetime.now().isoformat(timespec="seconds")


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    for col, ddl in (("conditions", "TEXT DEFAULT '[]'"), ("trips", "INTEGER DEFAULT 0")):
        if col not in [r[1] for r in conn.execute("PRAGMA table_info(jobs)")]:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {ddl}")
    conn.commit()
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        seed_demo(conn)
    conn.close()


# ------------------------------------------------------------------ auth helpers

def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not session.get("uid"):
            return jsonify(error="Not signed in"), 401
        return fn(*a, **kw)
    return wrapper


def current_user():
    return db().execute("SELECT * FROM users WHERE id=?", (session["uid"],)).fetchone()


def user_json(u):
    return {k: u[k] for k in ("id", "email", "name", "business_name", "phone", "license_no", "address",
                              "markup_pct", "contingency_pct", "tax_pct", "ics_token")} | \
           {"price_overrides": json.loads(u["price_overrides"] or "{}")}


def overrides_for(u):
    try:
        return json.loads(u["price_overrides"] or "{}")
    except json.JSONDecodeError:
        return {}


# ------------------------------------------------------------------ static

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


# ------------------------------------------------------------------ auth routes

@app.post("/api/auth/register")
def register():
    d = request.get_json(force=True) or {}
    email = (d.get("email") or "").strip().lower()
    pw = d.get("password") or ""
    if "@" not in email or len(pw) < 8:
        return jsonify(error="Valid email and a password of 8+ characters required"), 400
    try:
        cur = db().execute(
            "INSERT INTO users (email,password_hash,name,business_name,ics_token,created_at) VALUES (?,?,?,?,?,?)",
            (email, generate_password_hash(pw), d.get("name", ""), d.get("business_name", ""),
             secrets.token_urlsafe(24), now()))
        db().commit()
    except sqlite3.IntegrityError:
        return jsonify(error="That email is already registered"), 409
    session.permanent = True
    session["uid"] = cur.lastrowid
    return jsonify(user=user_json(current_user()))


@app.post("/api/auth/login")
def login():
    d = request.get_json(force=True) or {}
    u = db().execute("SELECT * FROM users WHERE email=?", ((d.get("email") or "").strip().lower(),)).fetchone()
    if not u or not check_password_hash(u["password_hash"], d.get("password") or ""):
        return jsonify(error="Wrong email or password"), 401
    session.permanent = True
    session["uid"] = u["id"]
    return jsonify(user=user_json(u))


@app.post("/api/auth/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@app.get("/api/auth/me")
def me():
    if not session.get("uid"):
        return jsonify(user=None)
    u = current_user()
    if not u:
        session.clear()
        return jsonify(user=None)
    return jsonify(user=user_json(u))


@app.put("/api/settings")
@login_required
def update_settings():
    d = request.get_json(force=True) or {}
    u = current_user()
    fields = {}
    for k in ("name", "business_name", "phone", "license_no", "address"):
        if k in d:
            fields[k] = str(d[k] or "")
    for k in ("markup_pct", "contingency_pct", "tax_pct"):
        if k in d:
            try:
                fields[k] = float(d[k])
            except (TypeError, ValueError):
                return jsonify(error=f"{k} must be a number"), 400
    if "price_overrides" in d and isinstance(d["price_overrides"], dict):
        fields["price_overrides"] = json.dumps(d["price_overrides"])
    if d.get("rotate_ics_token"):
        fields["ics_token"] = secrets.token_urlsafe(24)
    if d.get("new_password"):
        if len(d["new_password"]) < 8:
            return jsonify(error="Password must be 8+ characters"), 400
        fields["password_hash"] = generate_password_hash(d["new_password"])
    if fields:
        sets = ", ".join(f"{k}=?" for k in fields)
        db().execute(f"UPDATE users SET {sets} WHERE id=?", (*fields.values(), u["id"]))
        db().commit()
    return jsonify(user=user_json(current_user()))


# ------------------------------------------------------------------ pricing

def custom_materials(uid):
    rows = db().execute("SELECT * FROM materials WHERE user_id=? ORDER BY section, label", (uid,)).fetchall()
    return [{"id": f"custom.{r['id']}", "db_id": r["id"], "section": r["section"] or "My materials", "label": r["label"],
             "unit": r["unit"], "cost": r["cost"], "category": r["category"], "builtin": False} for r in rows]


@app.get("/api/pricing")
@login_required
def get_pricing():
    u = current_user()
    book = pricing.merged_prices(overrides_for(u))
    return jsonify(region=pricing.REGION, book=book, calculators=pricing.calculator_catalog(),
                   materials=pricing.material_catalog(book) + custom_materials(u["id"]),
                   conditions=pricing.conditions_catalog(book),
                   statuses=JOB_STATUSES, event_types=EVENT_TYPES)


# ------------------------------------------------------------------ custom materials

MATERIAL_CATEGORIES = ("material", "labor", "equipment", "disposal", "other")


def _material_fields(d):
    label = (d.get("label") or "").strip()
    if not label:
        return None, "Name required"
    try:
        cost = float(d.get("cost") or 0)
    except (TypeError, ValueError):
        return None, "Cost must be a number"
    cat = d.get("category") if d.get("category") in MATERIAL_CATEGORIES else "material"
    return {"section": (d.get("section") or "My materials").strip(), "label": label,
            "unit": (d.get("unit") or "ea").strip(), "cost": cost, "category": cat}, None


@app.post("/api/materials")
@login_required
def add_material():
    u = current_user()
    f, err = _material_fields(request.get_json(force=True) or {})
    if err:
        return jsonify(error=err), 400
    db().execute("INSERT INTO materials (user_id,section,label,unit,cost,category,created_at) VALUES (?,?,?,?,?,?,?)",
                 (u["id"], f["section"], f["label"], f["unit"], f["cost"], f["category"], now()))
    db().commit()
    return jsonify(materials=custom_materials(u["id"])), 201


@app.put("/api/materials/<int:mid>")
@login_required
def update_material(mid):
    u = current_user()
    if not db().execute("SELECT id FROM materials WHERE id=? AND user_id=?", (mid, u["id"])).fetchone():
        abort(404)
    f, err = _material_fields(request.get_json(force=True) or {})
    if err:
        return jsonify(error=err), 400
    db().execute("UPDATE materials SET section=?, label=?, unit=?, cost=?, category=? WHERE id=?",
                 (f["section"], f["label"], f["unit"], f["cost"], f["category"], mid))
    db().commit()
    return jsonify(materials=custom_materials(u["id"]))


@app.delete("/api/materials/<int:mid>")
@login_required
def delete_material(mid):
    u = current_user()
    db().execute("DELETE FROM materials WHERE id=? AND user_id=?", (mid, u["id"]))
    db().commit()
    return jsonify(materials=custom_materials(u["id"]))


@app.post("/api/calc/<name>")
@login_required
def run_calc(name):
    u = current_user()
    try:
        res = pricing.run_calculator(name, request.get_json(force=True) or {}, overrides_for(u))
    except KeyError:
        return jsonify(error="Unknown calculator"), 404
    book = pricing.merged_prices(overrides_for(u))
    res["summary"] = pricing.summarize(res["items"], book, u["markup_pct"], u["contingency_pct"], u["tax_pct"])
    res["competitors"] = pricing.competitor_quotes(res["items"], book, res["summary"])
    return jsonify(res)


# ------------------------------------------------------------------ jobs

def job_row_json(j, u, with_items=False):
    out = dict(j)
    items = db().execute("SELECT * FROM line_items WHERE job_id=? ORDER BY sort_order, id", (j["id"],)).fetchall()
    items = [dict(i) for i in items]
    mk = j["markup_pct"] if j["markup_pct"] is not None else u["markup_pct"]
    ct = j["contingency_pct"] if j["contingency_pct"] is not None else u["contingency_pct"]
    tx = j["tax_pct"] if j["tax_pct"] is not None else u["tax_pct"]
    try:
        conds = json.loads(j["conditions"] or "[]")
    except (json.JSONDecodeError, TypeError):
        conds = []
    out["conditions"] = conds
    book = pricing.merged_prices(overrides_for(u))
    out["summary"] = pricing.summarize(items, book, mk, ct, tx, conds, j["trips"] or 0)
    out["item_count"] = len(items)
    if with_items:
        out["items"] = items
        out["competitors"] = pricing.competitor_quotes(items, book, out["summary"])
        out["events"] = [dict(e) for e in db().execute(
            "SELECT * FROM events WHERE job_id=? ORDER BY start", (j["id"],)).fetchall()]
    return out


def next_job_no(uid):
    yr = date.today().year
    n = db().execute("SELECT COUNT(*) FROM jobs WHERE user_id=?", (uid,)).fetchone()[0] + 1
    return f"J{yr}-{n:03d}"


@app.get("/api/jobs")
@login_required
def list_jobs():
    u = current_user()
    rows = db().execute("SELECT * FROM jobs WHERE user_id=? ORDER BY updated_at DESC", (u["id"],)).fetchall()
    return jsonify(jobs=[job_row_json(j, u) for j in rows])


@app.post("/api/jobs")
@login_required
def create_job():
    u = current_user()
    d = request.get_json(force=True) or {}
    if not (d.get("title") or "").strip():
        return jsonify(error="Job title required"), 400
    status = d.get("status") if d.get("status") in JOB_STATUSES else "lead"
    conds = [c for c in (d.get("conditions") or []) if isinstance(c, str)]
    cur = db().execute(
        """INSERT INTO jobs (user_id,job_no,title,client_name,client_phone,client_email,address,job_type,status,notes,conditions,trips,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (u["id"], next_job_no(u["id"]), d["title"].strip(), d.get("client_name", ""), d.get("client_phone", ""),
         d.get("client_email", ""), d.get("address", ""), d.get("job_type", ""), status, d.get("notes", ""),
         json.dumps(conds), int(d.get("trips") or 0), now(), now()))
    db().commit()
    j = db().execute("SELECT * FROM jobs WHERE id=?", (cur.lastrowid,)).fetchone()
    return jsonify(job=job_row_json(j, u, True)), 201


def get_job_or_404(job_id, uid):
    j = db().execute("SELECT * FROM jobs WHERE id=? AND user_id=?", (job_id, uid)).fetchone()
    if not j:
        abort(404)
    return j


@app.get("/api/jobs/<int:job_id>")
@login_required
def get_job(job_id):
    u = current_user()
    return jsonify(job=job_row_json(get_job_or_404(job_id, u["id"]), u, True))


@app.put("/api/jobs/<int:job_id>")
@login_required
def update_job(job_id):
    u = current_user()
    get_job_or_404(job_id, u["id"])
    d = request.get_json(force=True) or {}
    fields = {}
    for k in ("title", "client_name", "client_phone", "client_email", "address", "job_type", "notes"):
        if k in d:
            fields[k] = str(d[k] or "")
    if "status" in d and d["status"] in JOB_STATUSES:
        fields["status"] = d["status"]
    for k in ("markup_pct", "contingency_pct", "tax_pct"):
        if k in d:
            fields[k] = None if d[k] in (None, "") else float(d[k])
    if "conditions" in d and isinstance(d["conditions"], list):
        fields["conditions"] = json.dumps([c for c in d["conditions"] if isinstance(c, str)])
    if "trips" in d:
        try:
            fields["trips"] = max(0, int(d["trips"] or 0))
        except (TypeError, ValueError):
            return jsonify(error="trips must be a whole number"), 400
    fields["updated_at"] = now()
    sets = ", ".join(f"{k}=?" for k in fields)
    db().execute(f"UPDATE jobs SET {sets} WHERE id=?", (*fields.values(), job_id))
    db().commit()
    return jsonify(job=job_row_json(get_job_or_404(job_id, u["id"]), u, True))


@app.delete("/api/jobs/<int:job_id>")
@login_required
def delete_job(job_id):
    u = current_user()
    get_job_or_404(job_id, u["id"])
    db().execute("DELETE FROM line_items WHERE job_id=?", (job_id,))
    db().execute("UPDATE events SET job_id=NULL WHERE job_id=?", (job_id,))
    db().execute("DELETE FROM jobs WHERE id=?", (job_id,))
    db().commit()
    return jsonify(ok=True)


# ------------------------------------------------------------------ line items

@app.post("/api/jobs/<int:job_id>/items")
@login_required
def add_items(job_id):
    """Body: {items: [...], group_label: 'Deck 16x12'}  or a single item."""
    u = current_user()
    get_job_or_404(job_id, u["id"])
    d = request.get_json(force=True) or {}
    items = d.get("items") if isinstance(d.get("items"), list) else [d]
    group = d.get("group_label", "")
    maxo = db().execute("SELECT COALESCE(MAX(sort_order),0) FROM line_items WHERE job_id=?", (job_id,)).fetchone()[0]
    for i, it in enumerate(items, 1):
        if not it.get("description"):
            continue
        qty = float(it.get("qty") or 0)
        uc = float(it.get("unit_cost") or 0)
        cat = it.get("category") if it.get("category") in ("material", "labor", "permit", "equipment", "disposal", "other") else "other"
        db().execute(
            """INSERT INTO line_items (job_id,source,group_label,description,category,qty,unit,unit_cost,total,sort_order,created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (job_id, it.get("source", "custom"), it.get("group_label", group), it["description"], cat, qty,
             it.get("unit", "ea"), uc, round(qty * uc, 2), maxo + i, now()))
    db().execute("UPDATE jobs SET updated_at=? WHERE id=?", (now(), job_id))
    if d.get("status_bump") and db().execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()[0] == "lead":
        db().execute("UPDATE jobs SET status='estimating' WHERE id=?", (job_id,))
    db().commit()
    return jsonify(job=job_row_json(get_job_or_404(job_id, u["id"]), u, True))


@app.put("/api/jobs/<int:job_id>/items/<int:item_id>")
@login_required
def update_item(job_id, item_id):
    u = current_user()
    get_job_or_404(job_id, u["id"])
    d = request.get_json(force=True) or {}
    it = db().execute("SELECT * FROM line_items WHERE id=? AND job_id=?", (item_id, job_id)).fetchone()
    if not it:
        abort(404)
    qty = float(d.get("qty", it["qty"]) or 0)
    uc = float(d.get("unit_cost", it["unit_cost"]) or 0)
    db().execute("UPDATE line_items SET description=?, category=?, qty=?, unit=?, unit_cost=?, total=? WHERE id=?",
                 (d.get("description", it["description"]), d.get("category", it["category"]), qty,
                  d.get("unit", it["unit"]), uc, round(qty * uc, 2), item_id))
    db().execute("UPDATE jobs SET updated_at=? WHERE id=?", (now(), job_id))
    db().commit()
    return jsonify(job=job_row_json(get_job_or_404(job_id, u["id"]), u, True))


@app.delete("/api/jobs/<int:job_id>/items/<int:item_id>")
@login_required
def delete_item(job_id, item_id):
    u = current_user()
    get_job_or_404(job_id, u["id"])
    db().execute("DELETE FROM line_items WHERE id=? AND job_id=?", (item_id, job_id))
    db().commit()
    return jsonify(job=job_row_json(get_job_or_404(job_id, u["id"]), u, True))


@app.delete("/api/jobs/<int:job_id>/groups")
@login_required
def delete_group(job_id):
    u = current_user()
    get_job_or_404(job_id, u["id"])
    label = request.args.get("label", "")
    db().execute("DELETE FROM line_items WHERE job_id=? AND group_label=?", (job_id, label))
    db().commit()
    return jsonify(job=job_row_json(get_job_or_404(job_id, u["id"]), u, True))


# ------------------------------------------------------------------ schedule

@app.get("/api/events")
@login_required
def list_events():
    u = current_user()
    start = request.args.get("start")
    end = request.args.get("end")
    q = "SELECT e.*, j.title AS job_title, j.job_no FROM events e LEFT JOIN jobs j ON j.id=e.job_id WHERE e.user_id=?"
    args = [u["id"]]
    if start:
        q += " AND e.start >= ?"
        args.append(start)
    if end:
        q += " AND e.start < ?"
        args.append(end)
    q += " ORDER BY e.start"
    return jsonify(events=[dict(r) for r in db().execute(q, args).fetchall()])


@app.post("/api/events")
@login_required
def create_event():
    u = current_user()
    d = request.get_json(force=True) or {}
    if not d.get("title") or not d.get("start"):
        return jsonify(error="Title and start required"), 400
    job_id = d.get("job_id") or None
    if job_id:
        get_job_or_404(int(job_id), u["id"])
    et = d.get("type") if d.get("type") in EVENT_TYPES else "work"
    cur = db().execute(
        "INSERT INTO events (user_id,job_id,title,type,start,end,all_day,location,notes,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (u["id"], job_id, d["title"], et, d["start"], d.get("end") or None, 1 if d.get("all_day") else 0,
         d.get("location", ""), d.get("notes", ""), now()))
    db().commit()
    r = db().execute("SELECT e.*, j.title AS job_title, j.job_no FROM events e LEFT JOIN jobs j ON j.id=e.job_id WHERE e.id=?",
                     (cur.lastrowid,)).fetchone()
    return jsonify(event=dict(r)), 201


@app.put("/api/events/<int:eid>")
@login_required
def update_event(eid):
    u = current_user()
    e = db().execute("SELECT * FROM events WHERE id=? AND user_id=?", (eid, u["id"])).fetchone()
    if not e:
        abort(404)
    d = request.get_json(force=True) or {}
    fields = {}
    for k in ("title", "start", "end", "location", "notes"):
        if k in d:
            fields[k] = d[k]
    if "type" in d and d["type"] in EVENT_TYPES:
        fields["type"] = d["type"]
    if "all_day" in d:
        fields["all_day"] = 1 if d["all_day"] else 0
    if "job_id" in d:
        fields["job_id"] = d["job_id"] or None
    if fields:
        sets = ", ".join(f"{k}=?" for k in fields)
        db().execute(f"UPDATE events SET {sets} WHERE id=?", (*fields.values(), eid))
        db().commit()
    r = db().execute("SELECT e.*, j.title AS job_title, j.job_no FROM events e LEFT JOIN jobs j ON j.id=e.job_id WHERE e.id=?",
                     (eid,)).fetchone()
    return jsonify(event=dict(r))


@app.delete("/api/events/<int:eid>")
@login_required
def delete_event(eid):
    u = current_user()
    db().execute("DELETE FROM events WHERE id=? AND user_id=?", (eid, u["id"]))
    db().commit()
    return jsonify(ok=True)


def _ics_dt(s, all_day):
    dt = datetime.fromisoformat(s)
    if all_day:
        return f";VALUE=DATE:{dt.strftime('%Y%m%d')}"
    return f":{dt.strftime('%Y%m%dT%H%M%S')}"


def _ics_escape(s):
    return (s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


@app.get("/calendar/<token>.ics")
def ics_feed(token):
    """Subscribe-able feed: paste the URL into Google Calendar (Other calendars > From URL),
    Apple Calendar, or Outlook, and the schedule shows up in his own calendar."""
    u = db().execute("SELECT * FROM users WHERE ics_token=?", (token,)).fetchone()
    if not u:
        abort(404)
    rows = db().execute(
        "SELECT e.*, j.title AS job_title, j.job_no, j.address AS job_address FROM events e LEFT JOIN jobs j ON j.id=e.job_id WHERE e.user_id=? ORDER BY e.start",
        (u["id"],)).fetchall()
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Contractor App//EN", "CALSCALE:GREGORIAN",
             f"X-WR-CALNAME:{_ics_escape(u['business_name'] or 'Job Schedule')}", "X-WR-TIMEZONE:America/New_York"]
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    for e in rows:
        start = e["start"]
        end = e["end"]
        if not end:
            end = (datetime.fromisoformat(start) + (timedelta(days=1) if e["all_day"] else timedelta(hours=2))).isoformat()
        title = e["title"]
        if e["job_no"]:
            title = f"[{e['job_no']}] {title}"
        desc = e["notes"] or ""
        if e["job_title"]:
            desc = f"Job: {e['job_title']}\n{desc}"
        lines += ["BEGIN:VEVENT", f"UID:evt-{e['id']}@contractor-app", f"DTSTAMP:{stamp}",
                  f"DTSTART{_ics_dt(start, e['all_day'])}", f"DTEND{_ics_dt(end, e['all_day'])}",
                  f"SUMMARY:{_ics_escape(title)}", f"DESCRIPTION:{_ics_escape(desc)}",
                  f"LOCATION:{_ics_escape(e['location'] or e['job_address'] or '')}",
                  f"CATEGORIES:{(e['type'] or 'work').upper()}", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    body = "\r\n".join(lines) + "\r\n"
    return Response(body, mimetype="text/calendar",
                    headers={"Content-Disposition": "inline; filename=schedule.ics"})


# ------------------------------------------------------------------ dashboard

@app.get("/api/dashboard")
@login_required
def dashboard():
    u = current_user()
    jobs = [job_row_json(j, u) for j in db().execute("SELECT * FROM jobs WHERE user_id=?", (u["id"],)).fetchall()]
    by_status = {s: {"count": 0, "value": 0.0} for s in JOB_STATUSES}
    for j in jobs:
        by_status[j["status"]]["count"] += 1
        by_status[j["status"]]["value"] = round(by_status[j["status"]]["value"] + j["summary"]["total"], 2)
    today = date.today().isoformat()
    upcoming = db().execute(
        "SELECT e.*, j.title AS job_title, j.job_no FROM events e LEFT JOIN jobs j ON j.id=e.job_id WHERE e.user_id=? AND e.start >= ? ORDER BY e.start LIMIT 8",
        (u["id"], today)).fetchall()
    pipeline = sum(j["summary"]["total"] for j in jobs if j["status"] in ("estimating", "quoted"))
    booked = sum(j["summary"]["total"] for j in jobs if j["status"] in ("approved", "in_progress"))
    return jsonify(by_status=by_status, pipeline_value=round(pipeline, 2), booked_value=round(booked, 2),
                   job_count=len(jobs), upcoming=[dict(e) for e in upcoming],
                   recent_jobs=sorted(jobs, key=lambda j: j["updated_at"], reverse=True)[:5])


# ------------------------------------------------------------------ seed

def seed_demo(conn):
    uid = conn.execute(
        "INSERT INTO users (email,password_hash,name,business_name,phone,license_no,address,ics_token,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        ("demo@example.com", generate_password_hash("demo1234"), "Demo Owner", "Demo Contracting Co.",
         "(910) 555-0142", "NC GC #00000 (limited)", "Wilmington, NC 28401", secrets.token_urlsafe(24), now())).lastrowid

    for sec, label, unit, cost in [
        ("Lumber", "Cedar 1x6 tongue-and-groove porch ceiling, per lf", "lf", 2.95),
        ("Hardware", "Black exterior lag screw, 3/8 x 6 in", "ea", 1.35),
        ("Drywall", "Moisture-resistant 1/2 in greenboard, per sq ft", "sqft", 0.78),
        ("Misc", "Rosin paper + floor protection, per room", "ea", 24.0),
    ]:
        conn.execute("INSERT INTO materials (user_id,section,label,unit,cost,category,created_at) VALUES (?,?,?,?,?,?,?)",
                     (uid, sec, label, unit, cost, "material", now()))

    def job(title, client, phone, addr, jtype, status, notes="", conditions=(), trips=0):
        n = conn.execute("SELECT COUNT(*) FROM jobs WHERE user_id=?", (uid,)).fetchone()[0] + 1
        return conn.execute(
            "INSERT INTO jobs (user_id,job_no,title,client_name,client_phone,client_email,address,job_type,status,notes,conditions,trips,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (uid, f"J{date.today().year}-{n:03d}", title, client, phone, "", addr, jtype, status, notes, json.dumps(list(conditions)), trips, now(), now())).lastrowid

    book = pricing.merged_prices()

    def add_mat(job_id, sec, key, qty, label, group):
        it = pricing._mat(book, sec, key, qty)
        conn.execute(
            "INSERT INTO line_items (job_id,source,group_label,description,category,qty,unit,unit_cost,total,sort_order,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (job_id, "pricebook", group, label or it["description"], it["category"], it["qty"], it["unit"], it["unit_cost"], it["total"], 50, now()))

    def add_calc(job_id, name, params, label):
        res = pricing.run_calculator(name, params)
        for i, it in enumerate(res["items"], 1):
            conn.execute(
                "INSERT INTO line_items (job_id,source,group_label,description,category,qty,unit,unit_cost,total,sort_order,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (job_id, name, label, it["description"], it["category"], it["qty"], it["unit"], it["unit_cost"], it["total"], i, now()))

    j0 = job("Close in half hall + add door", "Justin K.", "(910) 555-0120", "Wilmington, NC 28405",
             "Interior", "quoted",
             "16 ft total length including a new door. Existing half wall is 44.5 in tall, ceiling 8 ft. Right side wall is offset 3 in, "
             "so build out 3 in on that side. Opening between wall and half wall is 44 in. Back side is over the stairs: scaffold/plank "
             "needed for drywall and paint on that face.\n\nQuoted at $4,150.",
             conditions=("stairs_scaffold", "occupied"), trips=5)
    add_calc(j0, "framing", {"wall_lf": 16, "height_ft": 8, "openings": 1, "corners": 2, "furring_lf": 8}, "Frame upper wall + door, build out 3 in")
    add_calc(j0, "drywall", {"wall_sqft": 200, "corner_lf": 20}, "Drywall both faces")
    add_calc(j0, "trim", {"baseboard_lf": 0, "doors": 1, "cased_openings": 1}, "Prehung door + casing")
    add_calc(j0, "paint", {"wall_sqft": 200, "trim_lf": 17, "doors": 1, "coats": 2, "primer": 1}, "Prime + paint, door")
    add_mat(j0, "equipment", "stair_scaffold_setup", 1, None, "Stairway scaffolding")
    add_mat(j0, "equipment", "dust_wall_kit", 1, None, "Stairway scaffolding")

    j1 = job("Backyard composite deck", "Sarah Mitchell", "(910) 555-0199", "412 Pine Grove Dr, Wilmington, NC 28403",
             "Deck", "quoted", "Wants Trex Enhance in Coastal Bluff. HOA approval needed. Access from side yard gate.", trips=6)
    add_calc(j1, "deck", {"length_ft": 18, "width_ft": 14, "height_ft": 4, "material": "composite", "stairs": 1, "permit": 1}, "Deck 18x14 composite")
    add_calc(j1, "hourly", {"trade": "electrician", "hours": 5, "materials": 420, "materials_desc": "Low-voltage deck lighting kit"}, "Deck lighting")

    j2 = job("Bonus room finish-out over garage", "Marcus Lee", "(910) 555-0133", "2207 Oleander Dr, Wilmington, NC 28403",
             "Interior", "estimating", "Currently open studs. Wants a closet and a door to the hall. Electrical by his cousin.",
             conditions=("occupied",), trips=7)
    add_calc(j2, "framing", {"wall_lf": 22, "height_ft": 8, "stud_size": "2x4", "openings": 2, "corners": 3}, "Closet + hall wall framing")
    add_calc(j2, "drywall", {"wall_sqft": 1040, "ceiling_sqft": 380, "corner_lf": 32, "thickness": "half"}, "Drywall 1,040 wall / 380 ceiling")
    add_calc(j2, "trim", {"baseboard_lf": 128, "base_type": "mdf", "doors": 2, "door_type": "hollow", "shoe": 0}, "Trim + 2 doors")
    add_calc(j2, "paint", {"wall_sqft": 1040, "ceiling_sqft": 380, "trim_lf": 128, "doors": 2, "coats": 2, "primer": 1}, "Paint bonus room")

    j3 = job("Garage partition wall + storage room", "Tom and Ana Reyes", "(910) 555-0177", "815 Carolina Beach Rd, Wilmington, NC 28412",
             "Framing", "approved", "Wall on slab, PT bottom plate. 5/8 Type X on the house side. Owner supplies the door.", trips=4)
    add_calc(j3, "framing", {"wall_lf": 28, "height_ft": 9, "stud_size": "2x4", "openings": 1, "corners": 1, "pt_bottom_plate": 1}, "Partition wall 28 lf")
    add_calc(j3, "drywall", {"wall_sqft": 504, "ceiling_sqft": 0, "corner_lf": 18, "thickness": "58"}, "Drywall 5/8 both sides")
    add_calc(j3, "trim", {"baseboard_lf": 0, "doors": 0, "cased_openings": 1}, "Case the door opening")

    j4 = job("Screened porch deck rebuild", "Denise Carter", "(910) 555-0161", "1308 Market St, Wilmington, NC 28401",
             "Deck", "lead", "Existing PT deck is rotted at the ledger. Keep the screen frame if possible. Wants estimate before Thanksgiving.",
             conditions=("tight_access",), trips=5)
    add_calc(j4, "deck", {"length_ft": 14, "width_ft": 12, "height_ft": 2, "material": "pt", "stairs": 1, "demo": 1, "permit": 1}, "Deck 14x12 PT rebuild")

    j5 = job("Closet + laundry room build-out", "Kyle Brandt", "(910) 555-0108", "5 Shipyard Blvd, Wilmington, NC 28412",
             "Interior", "complete", "Done 2 weeks ago. Ask for Google review.", conditions=("occupied",), trips=6)
    add_calc(j5, "framing", {"wall_lf": 18, "height_ft": 8, "openings": 2, "corners": 2}, "Framing 18 lf")
    add_calc(j5, "drywall", {"wall_sqft": 560, "ceiling_sqft": 90, "corner_lf": 24}, "Drywall")
    add_calc(j5, "trim", {"baseboard_lf": 64, "doors": 2, "door_type": "solid"}, "Trim + 2 solid doors")
    add_calc(j5, "paint", {"wall_sqft": 560, "ceiling_sqft": 90, "trim_lf": 64, "doors": 2, "primer": 1}, "Paint")

    today = date.today()
    def ev(job_id, title, etype, day_offset, hour, dur_h, loc="", notes="", all_day=0):
        start = datetime.combine(today + timedelta(days=day_offset), datetime.min.time()).replace(hour=hour)
        end = start + timedelta(hours=dur_h)
        conn.execute("INSERT INTO events (user_id,job_id,title,type,start,end,all_day,location,notes,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (uid, job_id, title, etype, start.isoformat(timespec="minutes"), end.isoformat(timespec="minutes"), all_day, loc, notes, now()))

    ev(j0, "Half hall: frame + hang drywall", "work", 1, 8, 8, "Justin's place", "Set stair plank first. ZipWall at hall.")
    ev(j0, "Half hall: tape + 2nd coat", "work", 2, 8, 3, "Justin's place")
    ev(j0, "Half hall: 3rd coat, sand, hang door", "work", 3, 8, 4, "Justin's place")
    ev(j0, "Half hall: prime + paint", "work", 4, 8, 5, "Justin's place")
    ev(j4, "Site visit + measure porch", "site_visit", 1, 9, 1, "1308 Market St", "Bring moisture meter, check ledger + joists")
    ev(j3, "Frame garage partition wall", "work", 2, 7, 8, "815 Carolina Beach Rd", "PT plate, Tapcons, 5/8 board on house side")
    ev(j3, "Lumber + drywall delivery (84 Lumber)", "delivery", 2, 7, 1, "815 Carolina Beach Rd")
    ev(j3, "Hang + tape drywall", "work", 3, 7, 8, "815 Carolina Beach Rd")
    ev(j3, "Second coat + sand", "work", 4, 8, 4, "815 Carolina Beach Rd")
    ev(j1, "Deck proposal walkthrough with Sarah", "meeting", 3, 17, 1, "412 Pine Grove Dr")
    ev(j2, "Measure bonus room, confirm door swing", "site_visit", 5, 10, 1, "2207 Oleander Dr")
    ev(None, "Shop day: sharpen blades, truck oil change", "other", 8, 8, 4, "Shop")
    ev(j1, "Deck footing inspection", "inspection", 12, 13, 1, "412 Pine Grove Dr", "COAST inspection window 1-3pm")
    ev(j1, "Deck build week", "work", 12, 7, 9, "412 Pine Grove Dr", "Pending client approval", all_day=1)
    conn.commit()


init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n  Contractor app running at http://localhost:{port}\n  Demo login: demo@example.com / demo1234\n")
    app.run(host="127.0.0.1", port=port, debug=False)
