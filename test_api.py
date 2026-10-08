"""
Automated tests for the Library Management System API.
Run from the project folder:   python -m pytest -v
Each test uses a fresh temporary database, so your real data is never touched.
"""
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app import create_app  # noqa: E402

BOOK = {"title": "Test Driven Development", "author": "Kent Beck",
        "isbn": "978-0-321-14653-3", "category": "Computer Science"}
MEMBER = {"name": "Sneha Kulkarni", "email": "sneha@example.com", "phone": "9812345670"}


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def client(db_path):
    app = create_app(db_path=db_path, seed=False)
    app.config["TESTING"] = True
    return app.test_client()


def add_book(client, **overrides):
    return client.post("/api/books", json={**BOOK, **overrides})


def add_member(client, **overrides):
    return client.post("/api/members", json={**MEMBER, **overrides})


# ---------------------------------------------------------------- Books CRUD
def test_add_and_list_book(client):
    r = add_book(client)
    assert r.status_code == 201
    assert r.json["isbn"] == "9780321146533"          # hyphens removed
    assert r.json["status"] == "Available"
    assert len(client.get("/api/books").json) == 1


def test_required_fields_and_invalid_isbn(client):
    r = client.post("/api/books", json={"title": "", "author": "", "isbn": "123", "category": ""})
    assert r.status_code == 400
    assert set(r.json["fields"]) == {"title", "author", "isbn", "category"}


def test_duplicate_isbn_rejected(client):
    add_book(client)
    r = add_book(client, title="Another title")
    assert r.status_code == 409
    assert "isbn" in r.json["fields"]


def test_non_json_body_rejected(client):
    r = client.post("/api/books", data="not json", content_type="text/plain")
    assert r.status_code == 400


def test_search_by_title_author_isbn(client):
    add_book(client)
    add_book(client, title="Wings of Fire", author="A. P. J. Abdul Kalam", isbn="9788173711466", category="Biography")
    assert [b["title"] for b in client.get("/api/books?q=wings&by=title").json] == ["Wings of Fire"]
    assert [b["title"] for b in client.get("/api/books?q=beck&by=author").json] == ["Test Driven Development"]
    assert len(client.get("/api/books?q=978-81737&by=isbn").json) == 1
    assert len(client.get("/api/books?category=Biography").json) == 1


def test_search_non_existent_book_returns_empty_list(client):
    add_book(client)
    r = client.get("/api/books?q=harry potter")
    assert r.status_code == 200
    assert r.json == []


def test_update_book(client):
    book_id = add_book(client).json["id"]
    r = client.put(f"/api/books/{book_id}", json={**BOOK, "title": "TDD by Example"})
    assert r.status_code == 200 and r.json["title"] == "TDD by Example"


def test_update_non_existent_book(client):
    assert client.put("/api/books/999", json=BOOK).status_code == 404


def test_delete_book_and_non_existent(client):
    book_id = add_book(client).json["id"]
    assert client.delete(f"/api/books/{book_id}").status_code == 200
    assert client.delete(f"/api/books/{book_id}").status_code == 404


# ------------------------------------------------------------ Issue / Return
def test_issue_and_return_flow(client):
    book_id = add_book(client).json["id"]
    member_id = add_member(client).json["id"]

    r = client.post(f"/api/books/{book_id}/issue", json={"member_id": member_id, "days": 7})
    assert r.status_code == 200
    assert r.json["book"]["status"] == "Issued"
    assert r.json["book"]["issued_to"] == "Sneha Kulkarni"

    r = client.post(f"/api/books/{book_id}/return")
    assert r.status_code == 200
    assert r.json["book"]["status"] == "Available"
    assert r.json["fine"] == 0


def test_cannot_issue_unavailable_book(client):
    book_id = add_book(client).json["id"]
    m1 = add_member(client).json["id"]
    m2 = add_member(client, email="other@example.com").json["id"]
    client.post(f"/api/books/{book_id}/issue", json={"member_id": m1})
    r = client.post(f"/api/books/{book_id}/issue", json={"member_id": m2})
    assert r.status_code == 409
    assert "not available" in r.json["error"]


def test_return_book_not_issued(client):
    book_id = add_book(client).json["id"]
    r = client.post(f"/api/books/{book_id}/return")
    assert r.status_code == 409
    assert "not currently issued" in r.json["error"]


def test_issue_or_return_non_existent_book(client):
    member_id = add_member(client).json["id"]
    assert client.post("/api/books/999/issue", json={"member_id": member_id}).status_code == 404
    assert client.post("/api/books/999/return").status_code == 404


def test_issue_to_non_existent_member(client):
    book_id = add_book(client).json["id"]
    assert client.post(f"/api/books/{book_id}/issue", json={"member_id": 42}).status_code == 404


def test_invalid_loan_period(client):
    book_id = add_book(client).json["id"]
    member_id = add_member(client).json["id"]
    r = client.post(f"/api/books/{book_id}/issue", json={"member_id": member_id, "days": 100})
    assert r.status_code == 400


def test_member_borrow_limit(client):
    member_id = add_member(client).json["id"]
    isbns = ["9780000000001", "9780000000002", "9780000000003", "9780000000004"]
    ids = [add_book(client, isbn=i, title=f"Book {i}").json["id"] for i in isbns]
    for book_id in ids[:3]:
        assert client.post(f"/api/books/{book_id}/issue", json={"member_id": member_id}).status_code == 200
    r = client.post(f"/api/books/{ids[3]}/issue", json={"member_id": member_id})
    assert r.status_code == 409 and "limit" in r.json["error"]


def test_cannot_delete_issued_book(client):
    book_id = add_book(client).json["id"]
    member_id = add_member(client).json["id"]
    client.post(f"/api/books/{book_id}/issue", json={"member_id": member_id})
    assert client.delete(f"/api/books/{book_id}").status_code == 409


def test_late_return_fine(client, db_path):
    book_id = add_book(client).json["id"]
    member_id = add_member(client).json["id"]
    client.post(f"/api/books/{book_id}/issue", json={"member_id": member_id})
    # Pretend the book was due 4 days ago
    con = sqlite3.connect(db_path)
    con.execute("UPDATE issues SET due_date = date('now', '-4 day')")
    con.commit(); con.close()
    assert client.get("/api/stats").json["overdue"] == 1
    r = client.post(f"/api/books/{book_id}/return")
    assert r.json["days_late"] == 4 and r.json["fine"] == 20


# ------------------------------------------------------------------- Members
def test_member_validation(client):
    r = add_member(client, name="", email="not-an-email", phone="12345")
    assert r.status_code == 400
    assert set(r.json["fields"]) == {"name", "email", "phone"}


def test_duplicate_member_email(client):
    add_member(client)
    assert add_member(client, email="SNEHA@example.com").status_code == 409


def test_cannot_delete_member_holding_books(client):
    book_id = add_book(client).json["id"]
    member_id = add_member(client).json["id"]
    client.post(f"/api/books/{book_id}/issue", json={"member_id": member_id})
    assert client.delete(f"/api/members/{member_id}").status_code == 409
    client.post(f"/api/books/{book_id}/return")
    assert client.delete(f"/api/members/{member_id}").status_code == 200


def test_unknown_api_route_returns_json_404(client):
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404 and "error" in r.json
