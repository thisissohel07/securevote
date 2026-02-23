# app.py  — SecureVote (Face + OTP) FULL UPDATED VERSION
# Features:
# - Auto-import eligible voters from students.xlsx on startup
# - Eligible-only registration (OTP + Face)
# - No duplicate face allowed (cosine distance threshold)
# - Voter Login (OTP + Face) anytime
# - Voting requires OTP + Face every time
# - Admin: login, dashboard, create election, manage/toggle, results, (optional) upload import page too

import os
from datetime import datetime
import pandas as pd
from dotenv import load_dotenv
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, abort
)

from pyngrok import ngrok
from db import init_db, get_db
from otp_utils import generate_otp, otp_expiry, utc_now, send_email_otp
from face_utils import (
    b64_to_bgr, get_embedding_from_bgr,
    cosine_distance, emb_to_text, text_to_emb
)

load_dotenv()
from zoneinfo import ZoneInfo
IST = ZoneInfo("Asia/Kolkata")
APP_SECRET = os.getenv("FLASK_SECRET", "dev-secret")
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "admin123")

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = os.getenv("SMTP_PORT", "587")
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
FROM_EMAIL = os.getenv("FROM_EMAIL")

FACE_MODEL = os.getenv("FACE_MODEL", "Facenet512")
DUP_FACE_THRESHOLD = float(os.getenv("DUP_FACE_THRESHOLD", "0.35"))

# Ensure static path works (prevents /static 404 in some setups)
app = Flask(__name__, static_folder="static", static_url_path="/static")
app.secret_key = APP_SECRET


# ---------------------------
# Auto-import students.xlsx on startup
# ---------------------------
def auto_import_students_xlsx(path="students.xlsx"):
    if not os.path.exists(path):
        print(f"[AUTO-IMPORT] Excel not found: {path} (skipping)")
        return

    try:
        df = pd.read_excel(path)
    except Exception as e:
        print(f"[AUTO-IMPORT] Failed to read Excel: {e}")
        return

    # required columns: voter_id, name, email (phone optional)
    cols = {c.lower().strip(): c for c in df.columns}
    if "voter_id" not in cols or "name" not in cols or "email" not in cols:
        print("[AUTO-IMPORT] Missing columns. Need: voter_id, name, email (phone optional)")
        return

    conn = get_db()
    added, updated = 0, 0

    for _, r in df.iterrows():
        voter_id = str(r[cols["voter_id"]]).strip()
        name = str(r[cols["name"]]).strip()
        email = str(r[cols["email"]]).strip()
        phone = ""
        if "phone" in cols and pd.notna(r[cols["phone"]]):
            phone = str(r[cols["phone"]]).strip()

        if not voter_id or voter_id.lower() == "nan":
            continue

        existing = conn.execute("SELECT voter_id, is_registered FROM eligible_voters WHERE voter_id=?", (voter_id,)).fetchone()
        if existing:
            # don't reset is_registered
            conn.execute("""
                UPDATE eligible_voters SET name=?, email=?, phone=?
                WHERE voter_id=?
            """, (name, email, phone, voter_id))
            updated += 1
        else:
            conn.execute("""
                INSERT INTO eligible_voters(voter_id, name, email, phone, is_registered)
                VALUES (?, ?, ?, ?, 0)
            """, (voter_id, name, email, phone))
            added += 1

    conn.commit()
    conn.close()
    print(f"[AUTO-IMPORT] Done. Added={added}, Updated={updated}")


# ---------------------------
# Helpers
# ---------------------------
def admin_required():
    if not session.get("admin"):
        abort(403)

def voter_logged_in():
    return session.get("voter_id") is not None

def eligible_row(voter_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM eligible_voters WHERE voter_id=?", (voter_id,)).fetchone()
    conn.close()
    return row

def voter_row(voter_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM voters WHERE voter_id=?", (voter_id,)).fetchone()
    conn.close()
    return row

def is_election_active(e):
    # Parse stored start/end
    start = datetime.fromisoformat(e["start_at"])
    end = datetime.fromisoformat(e["end_at"])

    # If saved without timezone, assume IST
    if start.tzinfo is None:
        start = start.replace(tzinfo=IST)
    if end.tzinfo is None:
        end = end.replace(tzinfo=IST)

    now = datetime.now(IST)
    return e["is_active"] == 1 and start <= now <= end

def get_active_elections():
    conn = get_db()
    rows = conn.execute("SELECT * FROM elections WHERE is_active=1 ORDER BY id DESC").fetchall()
    conn.close()
    return rows

def verify_latest_otp(voter_id, purpose, code):
    conn = get_db()
    row = conn.execute("""
        SELECT * FROM otp_codes
        WHERE voter_id=? AND purpose=?
        ORDER BY id DESC LIMIT 1
    """, (voter_id, purpose)).fetchone()

    if not row:
        conn.close()
        return False, "OTP not found. Please request again."

    expires_at = datetime.fromisoformat(row["expires_at"])
    if datetime.utcnow() > expires_at:
        conn.close()
        return False, "OTP expired. Please request again."

    if row["code"] != code:
        conn.close()
        return False, "Invalid OTP."

    conn.close()
    return True, "OTP verified."

def check_duplicate_face(new_emb):
    """
    Returns (is_duplicate, matched_voter_id, best_distance)
    """
    conn = get_db()
    all_voters = conn.execute("SELECT voter_id, face_embedding FROM voters").fetchall()
    conn.close()

    best_voter, best_d = None, 999.0
    for v in all_voters:
        old_emb = text_to_emb(v["face_embedding"])
        d = cosine_distance(new_emb, old_emb)
        if d < best_d:
            best_d = d
            best_voter = v["voter_id"]

    if best_voter is not None and best_d <= DUP_FACE_THRESHOLD:
        return True, best_voter, best_d

    return False, None, None

def smtp_ready():
    return all([SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, FROM_EMAIL])


# ---------------------------
# Public routes
# ---------------------------
@app.route("/")
def index():
    elections = get_active_elections()
    return render_template("index.html", elections=elections, voter_id=session.get("voter_id"))

@app.route("/logout")
def logout():
    session.pop("voter_id", None)
    flash("Logged out.", "info")
    return redirect(url_for("index"))


# ---------------------------
# Voter Registration (OTP + Face)
# ---------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    voter_id = request.form.get("voter_id", "").strip()
    email = request.form.get("email", "").strip()

    if not voter_id or not email:
        flash("Please enter Voter ID and Email.", "danger")
        return redirect(url_for("register"))

    erow = eligible_row(voter_id)
    if not erow:
        flash("You are not in the eligible voter list.", "danger")
        return redirect(url_for("register"))

    if erow["is_registered"] == 1:
        flash("This Voter ID is already registered. Please login.", "warning")
        return redirect(url_for("login"))

    if erow["email"].lower() != email.lower():
        flash("Email does not match eligible voter list.", "danger")
        return redirect(url_for("register"))

    if not smtp_ready():
        flash("SMTP is not configured. Fill SMTP settings in .env", "danger")
        return redirect(url_for("register"))

    code = generate_otp()
    try:
        send_email_otp(SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, FROM_EMAIL, email, code, "register")
    except Exception as e:
        flash(f"Failed to send OTP email: {e}", "danger")
        return redirect(url_for("register"))

    conn = get_db()
    conn.execute("""
        INSERT INTO otp_codes(voter_id, purpose, code, expires_at, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (voter_id, "register", code, otp_expiry(5), utc_now()))
    conn.commit()
    conn.close()

    session["pending_voter_id"] = voter_id
    session["pending_email"] = email
    flash("OTP sent to your email. Verify to continue.", "success")
    return redirect(url_for("verify_otp", purpose="register"))


# ---------------------------
# Voter Login (OTP + Face)
# ---------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    voter_id = request.form.get("voter_id", "").strip()
    if not voter_id:
        flash("Enter Voter ID.", "warning")
        return redirect(url_for("login"))

    erow = eligible_row(voter_id)
    if not erow:
        flash("You are not in the eligible voter list.", "danger")
        return redirect(url_for("login"))

    if erow["is_registered"] != 1:
        flash("You are not registered yet. Please register first.", "warning")
        return redirect(url_for("register"))

    if not smtp_ready():
        flash("SMTP is not configured. Fill SMTP settings in .env", "danger")
        return redirect(url_for("login"))

    code = generate_otp()
    try:
        send_email_otp(SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, FROM_EMAIL, erow["email"], code, "login")
    except Exception as e:
        flash(f"Failed to send OTP email: {e}", "danger")
        return redirect(url_for("login"))

    conn = get_db()
    conn.execute("""
        INSERT INTO otp_codes(voter_id, purpose, code, expires_at, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (voter_id, "login", code, otp_expiry(5), utc_now()))
    conn.commit()
    conn.close()

    session["pending_voter_id"] = voter_id
    session["pending_email"] = erow["email"]

    flash("OTP sent. Verify OTP to continue.", "success")
    return redirect(url_for("verify_otp", purpose="login"))


# ---------------------------
# OTP verify (register/vote/login)
# ---------------------------
@app.route("/verify-otp/<purpose>", methods=["GET", "POST"])
def verify_otp(purpose):
    voter_id = session.get("pending_voter_id")
    email = session.get("pending_email")

    if purpose not in ("register", "vote", "login"):
        abort(404)

    if not voter_id or not email:
        flash("Session expired. Start again.", "warning")
        return redirect(url_for("index"))

    if request.method == "GET":
        return render_template("verify_otp.html", purpose=purpose, voter_id=voter_id, email=email)

    code = request.form.get("otp", "").strip()
    ok, msg = verify_latest_otp(voter_id, purpose, code)

    if not ok:
        flash(msg, "danger")
        return redirect(url_for("verify_otp", purpose=purpose))

    if purpose == "register":
        session["otp_verified_register"] = True
        flash("OTP verified. Now capture your face.", "success")
        return redirect(url_for("register_face"))

    if purpose == "vote":
        session["otp_verified_vote"] = True
        flash("OTP verified. Now verify face to vote.", "success")
        return redirect(url_for("vote_face"))

    if purpose == "login":
        session["otp_verified_login"] = True
        flash("OTP verified. Now verify face to login.", "success")
        return redirect(url_for("login_face"))

    flash("Unknown OTP purpose.", "danger")
    return redirect(url_for("index"))


# ---------------------------
# Face Capture Pages (reuse elections.html with modes)
# ---------------------------
@app.route("/register-face", methods=["GET"])
def register_face():
    voter_id = session.get("pending_voter_id")
    if not voter_id or not session.get("otp_verified_register"):
        flash("Please verify OTP first.", "warning")
        return redirect(url_for("register"))
    return render_template("elections.html", mode="register_face", voter_id=voter_id)

@app.route("/login-face", methods=["GET"])
def login_face():
    voter_id = session.get("pending_voter_id")
    if not voter_id or not session.get("otp_verified_login"):
        flash("Please verify login OTP first.", "warning")
        return redirect(url_for("login"))
    return render_template("elections.html", mode="login_face", voter_id=voter_id)

@app.route("/vote-face", methods=["GET"])
def vote_face():
    voter_id = session.get("pending_voter_id")
    election_id = session.get("pending_election_id")
    if not voter_id or not election_id or not session.get("otp_verified_vote"):
        flash("Please verify vote OTP first.", "warning")
        return redirect(url_for("elections"))
    return render_template("elections.html", mode="vote_face", voter_id=voter_id, election_id=election_id)


# ---------------------------
# Face APIs
# ---------------------------
@app.route("/api/register-face", methods=["POST"])
def api_register_face():
    voter_id = session.get("pending_voter_id")
    if not voter_id or not session.get("otp_verified_register"):
        return jsonify({"ok": False, "error": "OTP not verified"}), 403

    erow = eligible_row(voter_id)
    if not erow:
        return jsonify({"ok": False, "error": "Not eligible"}), 403

    if erow["is_registered"] == 1:
        return jsonify({"ok": False, "error": "Already registered"}), 409

    data = request.get_json(silent=True) or {}
    img_b64 = data.get("image")
    if not img_b64:
        return jsonify({"ok": False, "error": "No image received"}), 400

    try:
        bgr = b64_to_bgr(img_b64)
        emb = get_embedding_from_bgr(bgr, model_name=FACE_MODEL)
    except Exception as e:
        return jsonify({"ok": False, "error": f"Face not detected clearly. Try again. ({e})"}), 400

    dup, matched_voter_id, dist = check_duplicate_face(emb)
    if dup:
        return jsonify({
            "ok": False,
            "error": f"Duplicate face detected (matches voter: {matched_voter_id}, distance={dist:.3f}). Registration blocked."
        }), 409

    conn = get_db()
    conn.execute("""
        INSERT INTO voters(voter_id, face_embedding, registered_at)
        VALUES (?, ?, ?)
    """, (voter_id, emb_to_text(emb), utc_now()))
    conn.execute("UPDATE eligible_voters SET is_registered=1 WHERE voter_id=?", (voter_id,))
    conn.commit()
    conn.close()

    # login voter
    session["voter_id"] = voter_id

    # clear pending
    session.pop("pending_voter_id", None)
    session.pop("pending_email", None)
    session.pop("otp_verified_register", None)

    return jsonify({"ok": True, "message": "Registration successful!"})

@app.route("/api/login-face-verify", methods=["POST"])
def api_login_face_verify():
    voter_id = session.get("pending_voter_id")
    if not voter_id or not session.get("otp_verified_login"):
        return jsonify({"ok": False, "error": "OTP not verified"}), 403

    vrow = voter_row(voter_id)
    if not vrow:
        return jsonify({"ok": False, "error": "Not registered"}), 403

    data = request.get_json(silent=True) or {}
    img_b64 = data.get("image")
    if not img_b64:
        return jsonify({"ok": False, "error": "No image received"}), 400

    try:
        bgr = b64_to_bgr(img_b64)
        emb_now = get_embedding_from_bgr(bgr, model_name=FACE_MODEL)
    except Exception as e:
        return jsonify({"ok": False, "error": f"Face not detected. Try again. ({e})"}), 400

    emb_saved = text_to_emb(vrow["face_embedding"])
    d = cosine_distance(emb_now, emb_saved)

    if d > DUP_FACE_THRESHOLD:
        return jsonify({"ok": False, "error": f"Face mismatch (distance={d:.3f})."}), 401

    session["voter_id"] = voter_id

    # clear pending
    session.pop("pending_voter_id", None)
    session.pop("pending_email", None)
    session.pop("otp_verified_login", None)

    return jsonify({"ok": True, "message": "Login successful!"})

@app.route("/api/vote-face-verify", methods=["POST"])
def api_vote_face_verify():
    voter_id = session.get("pending_voter_id")
    election_id = session.get("pending_election_id")

    if not voter_id or not election_id or not session.get("otp_verified_vote"):
        return jsonify({"ok": False, "error": "OTP not verified"}), 403

    vrow = voter_row(voter_id)
    if not vrow:
        return jsonify({"ok": False, "error": "Voter not registered"}), 403

    data = request.get_json(silent=True) or {}
    img_b64 = data.get("image")
    if not img_b64:
        return jsonify({"ok": False, "error": "No image received"}), 400

    try:
        bgr = b64_to_bgr(img_b64)
        emb_now = get_embedding_from_bgr(bgr, model_name=FACE_MODEL)
    except Exception as e:
        return jsonify({"ok": False, "error": f"Face not detected clearly. Try again. ({e})"}), 400

    emb_saved = text_to_emb(vrow["face_embedding"])
    d = cosine_distance(emb_now, emb_saved)

    if d > DUP_FACE_THRESHOLD:
        return jsonify({"ok": False, "error": f"Face verification failed (distance={d:.3f})."}), 401

    session["face_verified_vote"] = True
    return jsonify({"ok": True, "message": "Face verified. You can submit vote now."})


# ---------------------------
# Elections + Voting
# ---------------------------
@app.route("/elections")
def elections():
    if not voter_logged_in():
        flash("Please login/register first.", "warning")
        return redirect(url_for("login"))
    elections_list = get_active_elections()
    return render_template("elections.html", mode="list", elections=elections_list, voter_id=session.get("voter_id"))

@app.route("/vote/<int:election_id>", methods=["GET"])
def vote(election_id):
    if not voter_logged_in():
        flash("Please login first.", "warning")
        return redirect(url_for("login"))

    voter_id = session["voter_id"]
    conn = get_db()
    election = conn.execute("SELECT * FROM elections WHERE id=?", (election_id,)).fetchone()
    if not election:
        conn.close()
        abort(404)

    if not is_election_active(election):
        conn.close()
        flash("Election is not active right now.", "warning")
        return redirect(url_for("elections"))

    already = conn.execute(
        "SELECT 1 FROM votes WHERE election_id=? AND voter_id=?",
        (election_id, voter_id)
    ).fetchone()
    if already:
        conn.close()
        flash("You already voted in this election.", "info")
        return redirect(url_for("elections"))

    candidates = conn.execute(
        "SELECT * FROM candidates WHERE election_id=? ORDER BY id ASC",
        (election_id,)
    ).fetchall()
    conn.close()

    if not candidates:
        flash("No candidates in this election yet.", "warning")
        return redirect(url_for("elections"))

    return render_template("vote.html", election=election, candidates=candidates, voter_id=voter_id)

@app.route("/vote-request-otp/<int:election_id>", methods=["POST"])
def vote_request_otp(election_id):
    if not voter_logged_in():
        abort(403)

    voter_id = session["voter_id"]
    erow = eligible_row(voter_id)
    if not erow:
        abort(403)

    if not smtp_ready():
        flash("SMTP is not configured. Fill SMTP settings in .env", "danger")
        return redirect(url_for("vote", election_id=election_id))

    code = generate_otp()
    try:
        send_email_otp(SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, FROM_EMAIL, erow["email"], code, "vote")
    except Exception as e:
        flash(f"Failed to send OTP email: {e}", "danger")
        return redirect(url_for("vote", election_id=election_id))

    conn = get_db()
    conn.execute("""
        INSERT INTO otp_codes(voter_id, purpose, code, expires_at, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (voter_id, "vote", code, otp_expiry(5), utc_now()))
    conn.commit()
    conn.close()

    session["pending_voter_id"] = voter_id
    session["pending_email"] = erow["email"]
    session["pending_election_id"] = election_id

    flash("OTP sent. Verify OTP to proceed.", "success")
    return redirect(url_for("verify_otp", purpose="vote"))

@app.route("/submit-vote/<int:election_id>", methods=["POST"])
def submit_vote(election_id):
    if not voter_logged_in():
        abort(403)

    voter_id = session["voter_id"]

    if not session.get("otp_verified_vote") or not session.get("face_verified_vote"):
        flash("Complete OTP + Face verification first.", "danger")
        return redirect(url_for("vote", election_id=election_id))

    candidate_id = request.form.get("candidate_id")
    if not candidate_id:
        flash("Select a candidate.", "warning")
        return redirect(url_for("vote", election_id=election_id))

    conn = get_db()
    election = conn.execute("SELECT * FROM elections WHERE id=?", (election_id,)).fetchone()
    if not election or not is_election_active(election):
        conn.close()
        flash("Election not active.", "warning")
        return redirect(url_for("elections"))

    already = conn.execute(
        "SELECT 1 FROM votes WHERE election_id=? AND voter_id=?",
        (election_id, voter_id)
    ).fetchone()
    if already:
        conn.close()
        flash("You already voted.", "info")
        return redirect(url_for("elections"))

    c = conn.execute(
        "SELECT * FROM candidates WHERE id=? AND election_id=?",
        (candidate_id, election_id)
    ).fetchone()
    if not c:
        conn.close()
        flash("Invalid candidate.", "danger")
        return redirect(url_for("vote", election_id=election_id))

    try:
        conn.execute("""
            INSERT INTO votes(election_id, voter_id, candidate_id, voted_at)
            VALUES (?, ?, ?, ?)
        """, (election_id, voter_id, candidate_id, utc_now()))
        conn.commit()
    except Exception as e:
        conn.close()
        flash(f"Vote failed: {e}", "danger")
        return redirect(url_for("vote", election_id=election_id))

    conn.close()

    # clear vote verification session
    session.pop("otp_verified_vote", None)
    session.pop("face_verified_vote", None)
    session.pop("pending_election_id", None)
    session.pop("pending_voter_id", None)
    session.pop("pending_email", None)

    flash("✅ Vote submitted successfully!", "success")
    return redirect(url_for("elections"))


# ---------------------------
# Admin
# ---------------------------
@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "GET":
        return render_template("admin_login.html")

    user = request.form.get("username", "")
    pw = request.form.get("password", "")

    if user == ADMIN_USER and pw == ADMIN_PASS:
        session["admin"] = True
        flash("Admin logged in.", "success")
        return redirect(url_for("admin_dashboard"))

    flash("Invalid admin credentials.", "danger")
    return redirect(url_for("admin_login"))

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    flash("Admin logged out.", "info")
    return redirect(url_for("index"))

@app.route("/admin/dashboard")
def admin_dashboard():
    admin_required()
    conn = get_db()
    elections_list = conn.execute("SELECT * FROM elections ORDER BY id DESC").fetchall()
    total_eligible = conn.execute("SELECT COUNT(*) c FROM eligible_voters").fetchone()["c"]
    total_registered = conn.execute("SELECT COUNT(*) c FROM voters").fetchone()["c"]
    total_votes = conn.execute("SELECT COUNT(*) c FROM votes").fetchone()["c"]
    elections_list = conn.execute("SELECT * FROM elections ORDER BY id DESC").fetchall()

    conn.close()
    return render_template(
        "admin_dashboard.html",
        total_eligible=total_eligible,
        total_registered=total_registered,
        total_votes=total_votes,
        elections=elections_list
    )

# Optional admin upload import (you can keep or remove)
@app.route("/admin/import", methods=["GET", "POST"])
def admin_import():
    admin_required()
    if request.method == "GET":
        return render_template("admin_import.html")

    f = request.files.get("file")
    if not f:
        flash("Please upload an Excel file.", "warning")
        return redirect(url_for("admin_import"))

    try:
        df = pd.read_excel(f)
    except Exception as e:
        flash(f"Invalid Excel: {e}", "danger")
        return redirect(url_for("admin_import"))

    cols = {c.lower().strip(): c for c in df.columns}
    if "voter_id" not in cols or "name" not in cols or "email" not in cols:
        flash("Excel must contain columns: voter_id, name, email (phone optional).", "danger")
        return redirect(url_for("admin_import"))

    conn = get_db()
    added = 0
    updated = 0

    for _, r in df.iterrows():
        voter_id = str(r[cols["voter_id"]]).strip()
        name = str(r[cols["name"]]).strip()
        email = str(r[cols["email"]]).strip()
        phone = str(r[cols["phone"]]).strip() if "phone" in cols and pd.notna(r[cols["phone"]]) else ""

        if not voter_id or voter_id.lower() == "nan":
            continue

        existing = conn.execute("SELECT * FROM eligible_voters WHERE voter_id=?", (voter_id,)).fetchone()
        if existing:
            conn.execute("""
                UPDATE eligible_voters
                SET name=?, email=?, phone=?
                WHERE voter_id=?
            """, (name, email, phone, voter_id))
            updated += 1
        else:
            conn.execute("""
                INSERT INTO eligible_voters(voter_id, name, email, phone, is_registered)
                VALUES (?, ?, ?, ?, 0)
            """, (voter_id, name, email, phone))
            added += 1

    conn.commit()
    conn.close()

    flash(f"Imported successfully. Added: {added}, Updated: {updated}", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/election/create", methods=["GET", "POST"])
def admin_create_election():
    admin_required()
    if request.method == "GET":
        return render_template("admin_create_election.html")

    title = request.form.get("title", "").strip()
    start_at = request.form.get("start_at", "").strip()
    end_at = request.form.get("end_at", "").strip()
    candidates_raw = request.form.get("candidates", "").strip()

    if not title or not start_at or not end_at or not candidates_raw:
        flash("All fields are required.", "danger")
        return redirect(url_for("admin_create_election"))

    try:
        start_iso = datetime.fromisoformat(start_at).replace(tzinfo=IST).isoformat()
        end_iso = datetime.fromisoformat(end_at).replace(tzinfo=IST).isoformat()
    except Exception:
        flash("Invalid date format.", "danger")
        return redirect(url_for("admin_create_election"))

    candidates = [c.strip() for c in candidates_raw.split("\n") if c.strip()]
    if len(candidates) < 2:
        flash("Add at least 2 candidates (one per line).", "warning")
        return redirect(url_for("admin_create_election"))

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO elections(title, start_at, end_at, is_active, created_at)
        VALUES (?, ?, ?, 1, ?)
    """, (title, start_iso, end_iso, utc_now()))
    election_id = cur.lastrowid

    for c in candidates:
        conn.execute("INSERT INTO candidates(election_id, name) VALUES (?, ?)", (election_id, c))

    conn.commit()
    conn.close()

    flash("Election created.", "success")
    return redirect(url_for("admin_election_manage", election_id=election_id))

@app.route("/admin/election/<int:election_id>")
def admin_election_manage(election_id):
    admin_required()
    conn = get_db()
    election = conn.execute("SELECT * FROM elections WHERE id=?", (election_id,)).fetchone()
    if not election:
        conn.close()
        abort(404)

    candidates = conn.execute("SELECT * FROM candidates WHERE election_id=? ORDER BY id", (election_id,)).fetchall()
    total_votes = conn.execute("SELECT COUNT(*) c FROM votes WHERE election_id=?", (election_id,)).fetchone()["c"]
    eligible_total = conn.execute("SELECT COUNT(*) c FROM eligible_voters").fetchone()["c"]
    turnout = (total_votes / eligible_total * 100.0) if eligible_total else 0.0

    conn.close()
    return render_template(
        "admin_election_manage.html",
        election=election,
        candidates=candidates,
        total_votes=total_votes,
        eligible_total=eligible_total,
        turnout=turnout
    )

@app.route("/admin/election/<int:election_id>/toggle", methods=["POST"])
def admin_toggle_election(election_id):
    admin_required()
    conn = get_db()
    e = conn.execute("SELECT * FROM elections WHERE id=?", (election_id,)).fetchone()
    if not e:
        conn.close()
        abort(404)
    new_state = 0 if e["is_active"] == 1 else 1
    conn.execute("UPDATE elections SET is_active=? WHERE id=?", (new_state, election_id))
    conn.commit()
    conn.close()
    flash("Election status updated.", "success")
    return redirect(url_for("admin_election_manage", election_id=election_id))

@app.route("/admin/results/<int:election_id>")
def admin_results(election_id):
    admin_required()
    conn = get_db()
    election = conn.execute("SELECT * FROM elections WHERE id=?", (election_id,)).fetchone()
    if not election:
        conn.close()
        abort(404)

    eligible_total = conn.execute("SELECT COUNT(*) c FROM eligible_voters").fetchone()["c"]
    total_votes = conn.execute("SELECT COUNT(*) c FROM votes WHERE election_id=?", (election_id,)).fetchone()["c"]
    turnout = (total_votes / eligible_total * 100.0) if eligible_total else 0.0

    rows = conn.execute("""
        SELECT c.id, c.name,
               COUNT(v.id) as votes
        FROM candidates c
        LEFT JOIN votes v ON v.candidate_id = c.id AND v.election_id = c.election_id
        WHERE c.election_id=?
        GROUP BY c.id, c.name
        ORDER BY votes DESC, c.name ASC
    """, (election_id,)).fetchall()

    winner = rows[0] if rows else None
    conn.close()

    return render_template(
        "admin_results.html",
        election=election,
        rows=rows,
        winner=winner,
        eligible_total=eligible_total,
        total_votes=total_votes,
        turnout=turnout
    )


# ---------------------------
# Start
# ---------------------------
if __name__ == "__main__":
    init_db()
    auto_import_students_xlsx("students.xlsx")

    # Run Flask for LAN (mobile & desktop in same WiFi)
    host = "0.0.0.0"
    port = 5000

    # OPTIONAL: create HTTPS public link for mobile camera using ngrok
    try:
        from pyngrok import ngrok
        public_url = ngrok.connect(port, "http")
        print("\n✅ SecureVote Public HTTPS URL (Mobile Camera Works):", public_url)
    except Exception as e:
        print("\n⚠ Ngrok not started:", e)
        print("Install: pip install pyngrok")

    print(f"✅ Local Desktop URL: http://127.0.0.1:{port}")
    print(f"✅ LAN URL (Same WiFi): http://<your-ip>:{port}\n")

    app.run(host=host, port=port, debug=True)