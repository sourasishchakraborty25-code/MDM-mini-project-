"""
Library Management System - Flask backend
=========================================
REST API (JSON) for managing books, members and book issue/return,
with SQLite for persistent storage. Also serves the frontend files.

Run:  python backend/app.py   ->   http://127.0.0.1:5000
"""

import os
import re
import sqlite3
from datetime import date, timedelta

from flask import Flask, g, jsonify, request, send_from_directory

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "frontend"))
SCHEMA_FILE = os.path.join(BASE_DIR, "schema.sql")
DEFAULT_DB = os.path.join(BASE_DIR, "library.db")

MAX_BOOKS_PER_MEMBER = 3      # a member can hold at most 3 books at a time
DEFAULT_LOAN_DAYS = 14
FINE_PER_DAY = 5              # Rs. 5 per day late

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(r"^[6-9]\d{9}$")          # 10-digit Indian mobile number
ISBN_RE = re.compile(r"^(\d{9}[\dX]|\d{13})$")  # ISBN-10 or ISBN-13 (hyphens removed)


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def error(message, status=400, fields=None):
    body = {"error": message}
    if fields:
        body["fields"] = fields
    return jsonify(body), status


def normalize_isbn(value):
    return re.sub(r"[\s-]", "", str(value or "")).upper()


def get_json_body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def validate_book(data):
    """Return (clean_data, field_errors)."""
    clean = {
        "title": str(data.get("title") or "").strip(),
        "author": str(data.get("author") or "").strip(),
        "isbn": normalize_isbn(data.get("isbn")),
        "category": str(data.get("category") or "").strip(),
    }
    errors = {}
    if not clean["title"]:
        errors["title"] = "Title is required."
    elif len(clean["title"]) > 200:
        errors["title"] = "Title must be at most 200 characters."
    if not clean["author"]:
        errors["author"] = "Author is required."
    elif len(clean["author"]) > 120:
        errors["author"] = "Author must be at most 120 characters."
    if not clean["isbn"]:
        errors["isbn"] = "ISBN is required."
    elif not ISBN_RE.match(clean["isbn"]):
        errors["isbn"] = "ISBN must be 10 or 13 digits (hyphens allowed)."
    if not clean["category"]:
        errors["category"] = "Category is required."
    return clean, errors


def validate_member(data):
    clean = {
        "name": str(data.get("name") or "").strip(),
        "email": str(data.get("email") or "").strip().lower(),
        "phone": re.sub(r"[\s-]", "", str(data.get("phone") or "")),
    }
    errors = {}
    if not clean["name"]:
        errors["name"] = "Name is required."
    if not EMAIL_RE.match(clean["email"]):
        errors["email"] = "Enter a valid email address."
    if not PHONE_RE.match(clean["phone"]):
        errors["phone"] = "Phone must be a valid 10-digit mobile number."
    return clean, errors


def book_row_to_dict(row):
    return {
        "id": row["id"],
        "title": row["title"],
        "author": row["author"],
        "isbn": row["isbn"],
        "category": row["category"],
        "status": row["status"],
        "issued_to": row["member_name"],
        "member_id": row["member_id"],
        "due_date": row["due_date"],
        "overdue": bool(row["due_date"] and row["due_date"] < date.today().isoformat()),
    }


BOOK_SELECT = """
    SELECT b.*, m.name AS member_name, m.id AS member_id, i.due_date
    FROM books b
    LEFT JOIN issues  i ON i.book_id = b.id AND i.return_date IS NULL
    LEFT JOIN members m ON m.id = i.member_id
"""


# ----------------------------------------------------------------------------
# App factory
# ----------------------------------------------------------------------------
def create_app(db_path=None, seed=True):
    app = Flask(__name__, static_folder=None)
    app.config["DATABASE"] = db_path or os.environ.get("LIBRARY_DB", DEFAULT_DB)
    app.json.sort_keys = False

    # ---------------- database connection (one per request) ----------------
    def get_db():
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DATABASE"])
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db

    @app.teardown_appcontext
    def close_db(_exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    def init_db():
        with app.app_context():
            db = get_db()
            with open(SCHEMA_FILE, encoding="utf-8") as f:
                db.executescript(f.read())
            if seed and db.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 0:
                seed_data(db)
            db.commit()

    def fetch_book(book_id):
        return get_db().execute(BOOK_SELECT + " WHERE b.id = ?", (book_id,)).fetchone()

    # ------------------------------------------------------------------------
    # Frontend
    # ------------------------------------------------------------------------
    @app.get("/")
    def index():
        return send_from_directory(FRONTEND_DIR, "index.html")

    @app.get("/<path:filename>")
    def static_files(filename):
        if filename.startswith("api/"):
            return error("API endpoint not found.", 404)
        return send_from_directory(FRONTEND_DIR, filename)

    # ------------------------------------------------------------------------
    # Books
    # ------------------------------------------------------------------------
    @app.get("/api/books")
    def list_books():
        """List / search books.
        Query params: q (text), by (all|title|author|isbn), category, status."""
        q = (request.args.get("q") or "").strip()
        by = request.args.get("by", "all")
        category = (request.args.get("category") or "").strip()
        status = (request.args.get("status") or "").strip()

        where, params = [], []
        if q:
            like = f"%{q}%"
            isbn_like = f"%{normalize_isbn(q)}%"
            if by == "title":
                where.append("b.title LIKE ?"); params.append(like)
            elif by == "author":
                where.append("b.author LIKE ?"); params.append(like)
            elif by == "isbn":
                where.append("b.isbn LIKE ?"); params.append(isbn_like)
            else:
                where.append("(b.title LIKE ? OR b.author LIKE ? OR b.isbn LIKE ?)")
                params += [like, like, isbn_like]
        if category:
            where.append("b.category = ?"); params.append(category)
        if status in ("Available", "Issued"):
            where.append("b.status = ?"); params.append(status)

        sql = BOOK_SELECT + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY b.title COLLATE NOCASE"
        rows = get_db().execute(sql, params).fetchall()
        return jsonify([book_row_to_dict(r) for r in rows])

    @app.get("/api/books/<int:book_id>")
    def get_book(book_id):
        row = fetch_book(book_id)
        if not row:
            return error("Book not found.", 404)
        return jsonify(book_row_to_dict(row))

    @app.post("/api/books")
    def add_book():
        data = get_json_body()
        if data is None:
            return error("Request body must be JSON.")
        clean, errors = validate_book(data)
        if errors:
            return error("Please fix the highlighted fields.", 400, errors)
        db = get_db()
        try:
            cur = db.execute(
                "INSERT INTO books (title, author, isbn, category) VALUES (?, ?, ?, ?)",
                (clean["title"], clean["author"], clean["isbn"], clean["category"]),
            )
            db.commit()
        except sqlite3.IntegrityError:
            return error(f"A book with ISBN {clean['isbn']} already exists.", 409,
                         {"isbn": "This ISBN is already in the catalogue."})
        return jsonify(book_row_to_dict(fetch_book(cur.lastrowid))), 201

    @app.put("/api/books/<int:book_id>")
    def update_book(book_id):
        data = get_json_body()
        if data is None:
            return error("Request body must be JSON.")
        if not fetch_book(book_id):
            return error("Book not found.", 404)
        clean, errors = validate_book(data)
        if errors:
            return error("Please fix the highlighted fields.", 400, errors)
        db = get_db()
        try:
            db.execute(
                "UPDATE books SET title = ?, author = ?, isbn = ?, category = ? WHERE id = ?",
                (clean["title"], clean["author"], clean["isbn"], clean["category"], book_id),
            )
            db.commit()
        except sqlite3.IntegrityError:
            return error(f"Another book already uses ISBN {clean['isbn']}.", 409,
                         {"isbn": "This ISBN is already in the catalogue."})
        return jsonify(book_row_to_dict(fetch_book(book_id)))

    @app.delete("/api/books/<int:book_id>")
    def delete_book(book_id):
        row = fetch_book(book_id)
        if not row:
            return error("Book not found.", 404)
        if row["status"] == "Issued":
            return error(f"'{row['title']}' is currently issued to {row['member_name']}. "
                         "It must be returned before it can be deleted.", 409)
        db = get_db()
        db.execute("DELETE FROM books WHERE id = ?", (book_id,))
        db.commit()
        return jsonify({"message": f"'{row['title']}' was deleted."})

    @app.get("/api/categories")
    def list_categories():
        rows = get_db().execute(
            "SELECT DISTINCT category FROM books ORDER BY category COLLATE NOCASE"
        ).fetchall()
        return jsonify([r["category"] for r in rows])

    # ------------------------------------------------------------------------
    # Issue / Return
    # ------------------------------------------------------------------------
    @app.post("/api/books/<int:book_id>/issue")
    def issue_book(book_id):
        data = get_json_body()
        if data is None:
            return error("Request body must be JSON.")
        try:
            member_id = int(data.get("member_id"))
        except (TypeError, ValueError):
            return error("Select a member to issue the book to.", 400, {"member_id": "Member is required."})
        try:
            days = int(data.get("days", DEFAULT_LOAN_DAYS))
        except (TypeError, ValueError):
            days = -1
        if not 1 <= days <= 60:
            return error("Loan period must be between 1 and 60 days.", 400, {"days": "1 to 60 days."})

        db = get_db()
        book = fetch_book(book_id)
        if not book:
            return error("Book not found.", 404)
        member = db.execute("SELECT * FROM members WHERE id = ?", (member_id,)).fetchone()
        if not member:
            return error("Member not found.", 404)
        if book["status"] != "Available":
            return error(f"'{book['title']}' is not available - it is already issued to "
                         f"{book['member_name']} (due {book['due_date']}).", 409)
        active = db.execute(
            "SELECT COUNT(*) FROM issues WHERE member_id = ? AND return_date IS NULL", (member_id,)
        ).fetchone()[0]
        if active >= MAX_BOOKS_PER_MEMBER:
            return error(f"{member['name']} already has {active} books issued "
                         f"(limit is {MAX_BOOKS_PER_MEMBER}).", 409)

        today = date.today()
        due = today + timedelta(days=days)
        try:
            # Conditional update guards against two simultaneous issue requests.
            cur = db.execute(
                "UPDATE books SET status = 'Issued' WHERE id = ? AND status = 'Available'", (book_id,)
            )
            if cur.rowcount != 1:
                db.rollback()
                return error("This book was just issued by someone else.", 409)
            db.execute(
                "INSERT INTO issues (book_id, member_id, issue_date, due_date) VALUES (?, ?, ?, ?)",
                (book_id, member_id, today.isoformat(), due.isoformat()),
            )
            db.commit()
        except sqlite3.IntegrityError:
            db.rollback()
            return error("This book already has an active issue record.", 409)

        return jsonify({
            "message": f"'{book['title']}' issued to {member['name']}. Due on {due.isoformat()}.",
            "book": book_row_to_dict(fetch_book(book_id)),
        })

    @app.post("/api/books/<int:book_id>/return")
    def return_book(book_id):
        db = get_db()
        book = fetch_book(book_id)
        if not book:
            return error("Book not found.", 404)
        issue = db.execute(
            "SELECT * FROM issues WHERE book_id = ? AND return_date IS NULL", (book_id,)
        ).fetchone()
        if not issue:
            return error(f"'{book['title']}' is not currently issued, so it cannot be returned.", 409)

        today = date.today()
        days_late = max(0, (today - date.fromisoformat(issue["due_date"])).days)
        fine = days_late * FINE_PER_DAY
        db.execute("UPDATE issues SET return_date = ? WHERE id = ?", (today.isoformat(), issue["id"]))
        db.execute("UPDATE books SET status = 'Available' WHERE id = ?", (book_id,))
        db.commit()

        msg = f"'{book['title']}' returned by {book['member_name']}."
        if days_late:
            msg += f" Returned {days_late} day(s) late - fine Rs. {fine}."
        return jsonify({"message": msg, "days_late": days_late, "fine": fine,
                        "book": book_row_to_dict(fetch_book(book_id))})

    @app.get("/api/issues")
    def list_issues():
        """?status=active (default) or ?status=all for full history."""
        status = request.args.get("status", "active")
        sql = """
            SELECT i.*, b.title, b.isbn, m.name AS member_name
            FROM issues i
            JOIN books b   ON b.id = i.book_id
            JOIN members m ON m.id = i.member_id
        """
        if status != "all":
            sql += " WHERE i.return_date IS NULL"
        sql += " ORDER BY i.return_date IS NOT NULL, i.due_date, i.id DESC"
        today = date.today().isoformat()
        rows = get_db().execute(sql).fetchall()
        return jsonify([{
            "id": r["id"], "book_id": r["book_id"], "title": r["title"], "isbn": r["isbn"],
            "member_id": r["member_id"], "member_name": r["member_name"],
            "issue_date": r["issue_date"], "due_date": r["due_date"], "return_date": r["return_date"],
            "overdue": r["return_date"] is None and r["due_date"] < today,
        } for r in rows])

    # ------------------------------------------------------------------------
    # Members
    # ------------------------------------------------------------------------
    @app.get("/api/members")
    def list_members():
        q = (request.args.get("q") or "").strip()
        sql = """
            SELECT m.*, (SELECT COUNT(*) FROM issues i
                         WHERE i.member_id = m.id AND i.return_date IS NULL) AS books_held
            FROM members m
        """
        params = []
        if q:
            sql += " WHERE m.name LIKE ? OR m.email LIKE ? OR m.phone LIKE ?"
            params = [f"%{q}%"] * 3
        sql += " ORDER BY m.name COLLATE NOCASE"
        rows = get_db().execute(sql, params).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.post("/api/members")
    def add_member():
        data = get_json_body()
        if data is None:
            return error("Request body must be JSON.")
        clean, errors = validate_member(data)
        if errors:
            return error("Please fix the highlighted fields.", 400, errors)
        db = get_db()
        try:
            cur = db.execute("INSERT INTO members (name, email, phone) VALUES (?, ?, ?)",
                             (clean["name"], clean["email"], clean["phone"]))
            db.commit()
        except sqlite3.IntegrityError:
            return error("A member with this email already exists.", 409,
                         {"email": "This email is already registered."})
        row = db.execute("SELECT *, 0 AS books_held FROM members WHERE id = ?", (cur.lastrowid,)).fetchone()
        return jsonify(dict(row)), 201

    @app.delete("/api/members/<int:member_id>")
    def delete_member(member_id):
        db = get_db()
        member = db.execute("SELECT * FROM members WHERE id = ?", (member_id,)).fetchone()
        if not member:
            return error("Member not found.", 404)
        held = db.execute("SELECT COUNT(*) FROM issues WHERE member_id = ? AND return_date IS NULL",
                          (member_id,)).fetchone()[0]
        if held:
            return error(f"{member['name']} still has {held} book(s) issued. "
                         "They must be returned first.", 409)
        db.execute("DELETE FROM members WHERE id = ?", (member_id,))
        db.commit()
        return jsonify({"message": f"Member {member['name']} was removed."})

    # ------------------------------------------------------------------------
    # Dashboard stats
    # ------------------------------------------------------------------------
    @app.get("/api/stats")
    def stats():
        db = get_db()
        one = lambda sql, *p: db.execute(sql, p).fetchone()[0]
        return jsonify({
            "total_books": one("SELECT COUNT(*) FROM books"),
            "available": one("SELECT COUNT(*) FROM books WHERE status = 'Available'"),
            "issued": one("SELECT COUNT(*) FROM books WHERE status = 'Issued'"),
            "members": one("SELECT COUNT(*) FROM members"),
            "overdue": one("SELECT COUNT(*) FROM issues WHERE return_date IS NULL AND due_date < ?",
                           date.today().isoformat()),
        })

    @app.errorhandler(404)
    def not_found(_e):
        if request.path.startswith("/api/"):
            return error("API endpoint not found.", 404)
        return error("Page not found.", 404)

    @app.errorhandler(405)
    def method_not_allowed(_e):
        return error("Method not allowed for this endpoint.", 405)

    init_db()
    return app


# ----------------------------------------------------------------------------
# Sample data so the app isn't empty on first run
# ----------------------------------------------------------------------------
def seed_data(db):
    books = [
        ("Wings of Fire", "A. P. J. Abdul Kalam", "9788173711466", "Biography"),
        ("The Discovery of India", "Jawaharlal Nehru", "9780143031031", "History"),
        ("Clean Code", "Robert C. Martin", "9780132350884", "Computer Science"),
        ("Introduction to Algorithms", "Cormen, Leiserson, Rivest, Stein", "9780262033848", "Computer Science"),
        ("Database System Concepts", "Silberschatz, Korth, Sudarshan", "9780073523323", "Computer Science"),
        ("The Guide", "R. K. Narayan", "9780143039648", "Fiction"),
        ("Godaan", "Munshi Premchand", "9788171880966", "Fiction"),
        ("A Brief History of Time", "Stephen Hawking", "9780553380163", "Science"),
        ("Higher Engineering Mathematics", "B. S. Grewal", "9788174091956", "Mathematics"),
        ("Python Crash Course", "Eric Matthes", "9781593279288", "Computer Science"),
    ]
    db.executemany("INSERT INTO books (title, author, isbn, category) VALUES (?, ?, ?, ?)", books)
    members = [
        ("Aarav Sharma", "aarav.sharma@example.com", "9876543210"),
        ("Priya Deshmukh", "priya.d@example.com", "9823456781"),
        ("Rohan Patil", "rohan.patil@example.com", "9765432109"),
    ]
    db.executemany("INSERT INTO members (name, email, phone) VALUES (?, ?, ?)", members)

    today = date.today()
    sample_issues = [  # (book_id, member_id, issued_days_ago, loan_days)
        (3, 1, 5, 14),    # Clean Code -> Aarav, due in 9 days
        (6, 2, 20, 14),   # The Guide  -> Priya, 6 days overdue
    ]
    for book_id, member_id, ago, loan in sample_issues:
        issued = today - timedelta(days=ago)
        db.execute("INSERT INTO issues (book_id, member_id, issue_date, due_date) VALUES (?, ?, ?, ?)",
                   (book_id, member_id, issued.isoformat(), (issued + timedelta(days=loan)).isoformat()))
        db.execute("UPDATE books SET status = 'Issued' WHERE id = ?", (book_id,))


if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("PORT", 5000))
    print(f"\n  Library Management System running at  http://127.0.0.1:{port}\n")
    app.run(debug=True, port=port)
