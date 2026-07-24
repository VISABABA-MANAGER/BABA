
from flask import Flask, render_template, request, redirect, url_for, send_file, flash, session, abort
import sqlite3, io, os
from pathlib import Path
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

DB_PATH = Path(os.environ.get("DB_PATH", str(Path(__file__).with_name("visa_manager.db"))))
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", str(Path(__file__).with_name("uploads"))))
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}

CHECKLIST_RULES = {
    "Tourisme": [
        "Passeport",
        "Photo d'identité",
        "Assurance voyage",
        "Réservation de vol",
        "Justificatif d'hébergement",
        "Relevé bancaire",
        "Attestation de travail",
        "Itinéraire de voyage",
        "Cover Letter",
    ],
    "Affaires": [
        "Passeport",
        "Photo d'identité",
        "Assurance voyage",
        "Réservation de vol",
        "Justificatif d'hébergement",
        "Invitation professionnelle",
        "Lettre employeur",
        "Relevé bancaire",
        "Itinéraire de voyage",
    ],
    "Études": [
        "Passeport",
        "Photo d'identité",
        "Lettre d'admission",
        "Preuve de financement",
        "Assurance",
        "Justificatif d'hébergement",
        "Diplômes",
    ],
    "Visite familiale": [
        "Passeport",
        "Photo d'identité",
        "Assurance voyage",
        "Réservation de vol",
        "Lettre d'invitation",
        "Preuve de lien familial",
        "Justificatif d'hébergement",
        "Relevé bancaire",
    ],
}

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped

def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        if session.get("role") != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def log_action(action, details=""):
    conn = db()
    conn.execute(
        "INSERT INTO audit_logs(user_id, action, details) VALUES (?, ?, ?)",
        (session.get("user_id"), action, details),
    )
    conn.commit()
    conn.close()

def init_db():
    conn = db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'employee'
    );

    CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        passport_number TEXT,
        nationality TEXT,
        email TEXT,
        phone TEXT
    );

    CREATE TABLE IF NOT EXISTS visa_cases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER NOT NULL,
        destination_country TEXT NOT NULL,
        visa_type TEXT,
        departure_date TEXT,
        return_date TEXT,
        appointment_date TEXT,
        status TEXT DEFAULT 'Brouillon',
        FOREIGN KEY(client_id) REFERENCES clients(id)
    );

    CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id INTEGER NOT NULL,
        document_type TEXT NOT NULL,
        original_name TEXT NOT NULL,
        stored_name TEXT NOT NULL,
        uploaded_by INTEGER,
        FOREIGN KEY(case_id) REFERENCES visa_cases(id),
        FOREIGN KEY(uploaded_by) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS checklist_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id INTEGER NOT NULL,
        item_name TEXT NOT NULL,
        status TEXT DEFAULT 'Manquant',
        FOREIGN KEY(case_id) REFERENCES visa_cases(id)
    );

    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action TEXT NOT NULL,
        details TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY CHECK (id=1),
        agency_name TEXT DEFAULT 'Visa Manager Pro',
        agency_email TEXT,
        agency_phone TEXT,
        agency_address TEXT
    );
    INSERT OR IGNORE INTO settings(id, agency_name) VALUES(1, 'Visa Manager Pro');
    """)
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        conn.execute(
            "INSERT INTO users(full_name,email,password_hash,role) VALUES(?,?,?,?)",
            ("Administrateur", "admin@visamanager.local", generate_password_hash("Admin123!"), "admin")
        )
    conn.commit()
    conn.close()

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        conn = db()
        user = conn.execute("SELECT * FROM users WHERE email=?", (request.form["email"].strip().lower(),)).fetchone()
        conn.close()
        if user and check_password_hash(user["password_hash"], request.form["password"]):
            session.clear()
            session["user_id"], session["full_name"], session["role"] = user["id"], user["full_name"], user["role"]
            return redirect(url_for("dashboard"))
        flash("Identifiants incorrects.")
    return render_template("login.html")
@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}

    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return {
            "success": False,
            "message": "Email et mot de passe requis"
        }, 400

    conn = db()
    user = conn.execute(
        "SELECT * FROM users WHERE email = ?",
        (email,)
    ).fetchone()
    conn.close()

    if not user or not check_password_hash(
        user["password_hash"], password
    ):
        return {
            "success": False,
            "message": "Identifiants incorrects"
        }, 401

    return {
        "success": True,
        "message": "Connexion réussie",
        "user": {
            "id": user["id"],
            "full_name": user["full_name"],
            "email": user["email"],
            "role": user["role"]
        }
    },200

@app.route("/api/countries", methods=["GET"])
def api_countries():
    countries = [
        "France",
        "Allemagne",
        "Belgique",
        "Espagne",
        "Italie",
        "Lituanie",
        "Pays-Bas",
        "Portugal",
        "Pologne",
        "Canada",
        "États-Unis",
        "Royaume-Uni"
    ]

    return {
        "success": True,
        "countries": countries
    }, 200

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def dashboard():
    conn = db()
    stats = {
        "clients": conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0],
        "cases": conn.execute("SELECT COUNT(*) FROM visa_cases").fetchone()[0],
        "docs": conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
        "complete": conn.execute("SELECT COUNT(*) FROM visa_cases WHERE status='Complet'").fetchone()[0],
    }
    recent = conn.execute("""
        SELECT visa_cases.*, clients.full_name FROM visa_cases
        JOIN clients ON clients.id=visa_cases.client_id
        ORDER BY visa_cases.id DESC LIMIT 8
    """).fetchall()
    conn.close()
    return render_template("dashboard.html", stats=stats, recent=recent)

@app.route("/clients", methods=["GET", "POST"])
@login_required
def clients():
    conn = db()
    if request.method == "POST":
        conn.execute("""INSERT INTO clients(full_name,passport_number,nationality,email,phone)
                        VALUES(?,?,?,?,?)""",
                     (request.form["full_name"], request.form.get("passport_number",""),
                      request.form.get("nationality",""), request.form.get("email",""),
                      request.form.get("phone","")))
        conn.commit()
        conn.close()
        log_action("Création client", request.form["full_name"])
        flash("Client ajouté.")
        return redirect(url_for("clients"))
    rows = conn.execute("SELECT * FROM clients ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("clients.html", clients=rows)

@app.route("/cases", methods=["GET", "POST"])
@login_required
def cases():
    conn = db()
    if request.method == "POST":
        cur = conn.execute("""INSERT INTO visa_cases(client_id,destination_country,visa_type,
                    departure_date,return_date,appointment_date,status)
                    VALUES(?,?,?,?,?,?,?)""",
                    (request.form["client_id"], request.form["destination_country"], request.form["visa_type"],
                     request.form.get("departure_date",""), request.form.get("return_date",""),
                     request.form.get("appointment_date",""), request.form.get("status","Brouillon")))
        case_id = cur.lastrowid
        for item in CHECKLIST_RULES.get(request.form["visa_type"], []):
            conn.execute("INSERT INTO checklist_items(case_id,item_name,status) VALUES(?,?,?)",
                         (case_id, item, "Manquant"))
        conn.commit()
        conn.close()
        log_action("Création dossier", f"Dossier #{case_id}")
        flash("Dossier créé avec checklist automatique.")
        return redirect(url_for("case_detail", case_id=case_id))
    clients_rows = conn.execute("SELECT * FROM clients ORDER BY full_name").fetchall()
    case_rows = conn.execute("""SELECT visa_cases.*,clients.full_name FROM visa_cases
                               JOIN clients ON clients.id=visa_cases.client_id
                               ORDER BY visa_cases.id DESC""").fetchall()
    conn.close()
    return render_template("cases.html", clients=clients_rows, cases=case_rows)

@app.route("/case/<int:case_id>")
@login_required
def case_detail(case_id):
    conn = db()
    case = conn.execute("""SELECT visa_cases.*,clients.full_name,clients.passport_number
                           FROM visa_cases JOIN clients ON clients.id=visa_cases.client_id
                           WHERE visa_cases.id=?""", (case_id,)).fetchone()
    if not case:
        conn.close(); abort(404)
    docs = conn.execute("SELECT * FROM documents WHERE case_id=? ORDER BY id DESC", (case_id,)).fetchall()
    checklist = conn.execute("SELECT * FROM checklist_items WHERE case_id=? ORDER BY id", (case_id,)).fetchall()
    conn.close()
    return render_template("case_detail.html", case=case, documents=docs, checklist=checklist)

@app.route("/case/<int:case_id>/upload", methods=["POST"])
@login_required
def upload_document(case_id):
    file = request.files.get("file")
    if not file or not file.filename:
        flash("Aucun fichier sélectionné."); return redirect(url_for("case_detail", case_id=case_id))
    if not allowed_file(file.filename):
        flash("Format non autorisé."); return redirect(url_for("case_detail", case_id=case_id))
    original = secure_filename(file.filename)
    folder = UPLOAD_DIR / str(case_id)
    folder.mkdir(exist_ok=True)
    stored = f"{len(list(folder.iterdir()))+1}_{original}"
    file.save(folder / stored)
    conn = db()
    conn.execute("""INSERT INTO documents(case_id,document_type,original_name,stored_name,uploaded_by)
                    VALUES(?,?,?,?,?)""",
                 (case_id, request.form["document_type"], original, stored, session["user_id"]))
    conn.commit(); conn.close()
    log_action("Ajout document", f"{request.form['document_type']} - dossier #{case_id}")
    flash("Document ajouté.")
    return redirect(url_for("case_detail", case_id=case_id))

@app.route("/document/<int:doc_id>/delete", methods=["POST"])
@login_required
def delete_document(doc_id):
    conn = db()
    doc = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    if not doc:
        conn.close(); abort(404)
    path = UPLOAD_DIR / str(doc["case_id"]) / doc["stored_name"]
    if path.exists():
        path.unlink()
    conn.execute("DELETE FROM documents WHERE id=?", (doc_id,))
    conn.commit(); conn.close()
    log_action("Suppression document", doc["original_name"])
    flash("Document supprimé.")
    return redirect(url_for("case_detail", case_id=doc["case_id"]))

@app.route("/document/<int:doc_id>")
@login_required
def download_document(doc_id):
    conn = db()
    doc = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    conn.close()
    if not doc: abort(404)
    path = UPLOAD_DIR / str(doc["case_id"]) / doc["stored_name"]
    return send_file(path, as_attachment=True, download_name=doc["original_name"])

@app.route("/checklist/<int:item_id>", methods=["POST"])
@login_required
def update_checklist(item_id):
    conn = db()
    row = conn.execute("SELECT case_id FROM checklist_items WHERE id=?", (item_id,)).fetchone()
    if not row:
        conn.close(); abort(404)
    conn.execute("UPDATE checklist_items SET status=? WHERE id=?", (request.form["status"], item_id))
    conn.commit(); conn.close()
    return redirect(url_for("case_detail", case_id=row["case_id"]))

@app.route("/case/<int:case_id>/status", methods=["POST"])
@login_required
def update_status(case_id):
    conn = db()
    conn.execute("UPDATE visa_cases SET status=? WHERE id=?", (request.form["status"], case_id))
    conn.commit(); conn.close()
    log_action("Changement statut", f"Dossier #{case_id}: {request.form['status']}")
    return redirect(url_for("cases"))

@app.route("/users", methods=["GET","POST"])
@admin_required
def users():
    conn = db()
    if request.method == "POST":
        try:
            conn.execute("INSERT INTO users(full_name,email,password_hash,role) VALUES(?,?,?,?)",
                         (request.form["full_name"], request.form["email"].lower(),
                          generate_password_hash(request.form["password"]), request.form["role"]))
            conn.commit(); flash("Utilisateur créé.")
        except sqlite3.IntegrityError:
            flash("Email déjà utilisé.")
        conn.close(); return redirect(url_for("users"))
    rows = conn.execute("SELECT id,full_name,email,role FROM users ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("users.html", users=rows)
@app.route("/users/<int:user_id>/reset-password", methods=["POST"])
@admin_required
def reset_user_password(user_id):
    new_password = request.form.get("new_password", "")

    if len(new_password) < 8:
        flash("Le nouveau mot de passe doit contenir au moins 8 caractères.")
        return redirect(url_for("users"))

    conn = db()
    user = conn.execute(
        "SELECT id FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()

    if not user:
        conn.close()
        flash("Utilisateur introuvable.")
        return redirect(url_for("users"))

    conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (generate_password_hash(new_password), user_id)
    )
    conn.commit()
    conn.close()

    flash("Mot de passe réinitialisé avec succès.")
    return redirect(url_for("users"))


@app.route("/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def delete_user(user_id):
    if user_id == session.get("user_id"):
        flash("Vous ne pouvez pas supprimer votre propre compte.")
        return redirect(url_for("users"))

    conn = db()
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

    flash("Utilisateur supprimé.")
    return redirect(url_for("users"))  
@app.route("/change-password", methods=["POST"])
@admin_required
def change_password():
    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")

    if new_password != confirm_password:
        flash("Les nouveaux mots de passe ne correspondent pas.")
        return redirect(url_for("settings"))

    if len(new_password) < 8:
        flash("Le nouveau mot de passe doit contenir au moins 8 caractères.")
        return redirect(url_for("settings"))

    conn = db()
    user = conn.execute(
        "SELECT id, password_hash FROM users WHERE id = ?",
        (session["user_id"],)
    ).fetchone()

    if not user or not check_password_hash(user["password_hash"], current_password):
        conn.close()
        flash("Mot de passe actuel incorrect.")
        return redirect(url_for("settings"))

    conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (generate_password_hash(new_password), session["user_id"])
    )
    conn.commit()
    conn.close()

    flash("Mot de passe modifié avec succès.")
    return redirect(url_for("settings"))
@app.route("/settings", methods=["GET","POST"])
@admin_required
def settings():
    conn = db()
    if request.method == "POST":
        conn.execute("""UPDATE settings SET agency_name=?,agency_email=?,agency_phone=?,agency_address=? WHERE id=1""",
                     (request.form["agency_name"], request.form.get("agency_email",""),
                      request.form.get("agency_phone",""), request.form.get("agency_address","")))
        conn.commit(); conn.close(); flash("Paramètres enregistrés."); return redirect(url_for("settings"))
    row = conn.execute("SELECT * FROM settings WHERE id=1").fetchone()
    conn.close()
    return render_template("settings.html", settings=row)

@app.route("/audit")
@admin_required
def audit():
    conn = db()
    logs = conn.execute("""SELECT audit_logs.*,users.full_name FROM audit_logs
                           LEFT JOIN users ON users.id=audit_logs.user_id
                           ORDER BY audit_logs.id DESC LIMIT 100""").fetchall()
    conn.close()
    return render_template("audit.html", logs=logs)

@app.route("/case/<int:case_id>/pdf")
@login_required
def case_pdf(case_id):
    conn = db()
    row = conn.execute("""SELECT visa_cases.*,clients.full_name,clients.passport_number,
                          clients.nationality,clients.email,clients.phone
                          FROM visa_cases JOIN clients ON clients.id=visa_cases.client_id
                          WHERE visa_cases.id=?""", (case_id,)).fetchone()
    settings = conn.execute("SELECT * FROM settings WHERE id=1").fetchone()
    checklist = conn.execute("SELECT * FROM checklist_items WHERE case_id=?", (case_id,)).fetchall()
    conn.close()
    if not row: abort(404)

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(2*cm, height-2*cm, settings["agency_name"] or "Visa Manager Pro")
    pdf.setFont("Helvetica", 9)
    pdf.drawString(2*cm, height-2.6*cm, settings["agency_address"] or "")
    pdf.drawString(2*cm, height-3.0*cm, f"{settings['agency_email'] or ''}  {settings['agency_phone'] or ''}")
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(2*cm, height-4.2*cm, "Fiche récapitulative du dossier visa")

    y = height - 5.2*cm
    fields = [
        ("Client", row["full_name"]), ("Passeport", row["passport_number"]),
        ("Nationalité", row["nationality"]), ("Destination", row["destination_country"]),
        ("Type de visa", row["visa_type"]), ("Départ", row["departure_date"]),
        ("Retour", row["return_date"]), ("Rendez-vous", row["appointment_date"]),
        ("Statut", row["status"])
    ]
    for label, value in fields:
        pdf.setFont("Helvetica-Bold", 10); pdf.drawString(2*cm, y, f"{label} :")
        pdf.setFont("Helvetica", 10); pdf.drawString(6*cm, y, str(value or "-")); y -= .55*cm

    y -= .3*cm
    pdf.setFont("Helvetica-Bold", 12); pdf.drawString(2*cm, y, "Checklist")
    y -= .6*cm
    for item in checklist:
        pdf.setFont("Helvetica", 9)
        pdf.drawString(2.2*cm, y, f"- {item['item_name']}: {item['status']}")
        y -= .45*cm
        if y < 2*cm:
            pdf.showPage(); y = height - 2*cm

    pdf.save(); buffer.seek(0)
    safe = "".join(c for c in row["full_name"] if c.isalnum() or c in " _-").strip()
    return send_file(buffer, as_attachment=True, download_name=f"dossier_{safe or case_id}.pdf", mimetype="application/pdf")

init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
