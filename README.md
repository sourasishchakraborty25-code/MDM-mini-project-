# Library Management System

**Mini Project — Aim 4**

A full-stack web application to **add, search, issue, return, update and delete** book records and manage library members.

| Layer    | Technology                                                                 |
|----------|----------------------------------------------------------------------------|
| Frontend | HTML5, CSS3, JavaScript (Fetch API). Node.js (npm) for tooling: Prettier formatting and npm scripts |
| Backend  | Python 3 + Flask (REST API, JSON)                                          |
| Database | SQLite (file `backend/library.db`, created automatically)                  |

---

## 1. How to run

**Requirements:** Python 3.9 or newer. Node.js is optional; it's only needed for the `npm` scripts.

```bash
# 1. Open a terminal inside the project folder
cd library-management-system

# 2. (Optional but recommended) create a virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start the server
python backend/app.py
```

Open **http://127.0.0.1:5000** in your browser.

On first run the database is created and filled with 10 sample books and 3 members, with one book overdue so every feature can be demonstrated. To start fresh, stop the server, delete `backend/library.db`, and run it again.

**With Node.js (optional):**

```bash
npm install          # installs Prettier
npm start            # same as: python backend/app.py
npm test             # runs the automated tests
npm run format       # auto-formats the frontend code
```

> On macOS/Linux use `python3` instead of `python` if needed.

---

## 2. Features

- **Add / edit / delete books** (Title, Author, ISBN, Category, Availability Status)
- **Search** by title, author or ISBN (or all at once), filter by category and status. Results update as you type, with no page reload.
- **Register / remove members** (Name, Email, Phone)
- **Issue a book** to a member with a loan period (1–60 days)
- **Return a book**, with an automatic late fine (Rs. 5 per day overdue)
- **Dashboard**: total, available, issued and overdue books, plus member count
- **Issue history** of all past and current loans
- Validation on **both frontend and backend**
- Responsive layout (works on mobile)

---

## 3. Project structure

```
library-management-system/
├── backend/
│   ├── app.py            # Flask app: REST API, validation, business rules
│   ├── schema.sql        # SQLite tables, constraints and indexes
│   └── library.db        # created automatically on first run
├── frontend/
│   ├── index.html        # page layout (tabs, forms, tables, issue dialog)
│   ├── style.css         # styling + responsive design
│   └── app.js            # Fetch API calls, rendering, client-side validation
├── tests/
│   └── test_api.py       # 22 automated tests (pytest)
├── requirements.txt      # Python dependencies
├── package.json          # Node.js tooling (npm scripts, Prettier)
└── README.md
```

---

## 4. Database schema (SQLite)

```
books                     members                   issues
─────────────────         ─────────────────         ──────────────────────────
id (PK)                   id (PK)                   id (PK)
title                     name                      book_id   (FK → books.id)
author                    email (UNIQUE)            member_id (FK → members.id)
isbn (UNIQUE)             phone                     issue_date
category                  joined_on                 due_date
status (Available/Issued)                           return_date (NULL = not returned)
created_at
```

- **books ↔ issues ↔ members**: one book can have many issue records over time, and one member can borrow many books. `issues` is the linking table.
- A **partial unique index** (`one_active_issue_per_book`) guarantees at the database level that a book can never have two active issues at the same time.
- `status` has a `CHECK` constraint so only `Available` or `Issued` can be stored.

---

## 5. REST API

All requests and responses use **JSON**. Errors return `{"error": "...", "fields": {...}}` with a proper HTTP status code.

| Method | Endpoint                       | Purpose                                                        |
|--------|--------------------------------|----------------------------------------------------------------|
| GET    | `/api/books`                   | List books. Query: `q`, `by` (all/title/author/isbn), `category`, `status` |
| GET    | `/api/books/<id>`              | Get one book                                                   |
| POST   | `/api/books`                   | Add a book                                                     |
| PUT    | `/api/books/<id>`              | Update a book                                                  |
| DELETE | `/api/books/<id>`              | Delete a book (blocked if issued)                              |
| POST   | `/api/books/<id>/issue`        | Issue a book. Body: `{"member_id": 1, "days": 14}`             |
| POST   | `/api/books/<id>/return`       | Return a book (calculates fine if late)                        |
| GET    | `/api/issues?status=active/all`| Current loans, or full history                                 |
| GET    | `/api/members?q=`              | List / search members                                          |
| POST   | `/api/members`                 | Register a member                                              |
| DELETE | `/api/members/<id>`            | Remove a member (blocked if holding books)                     |
| GET    | `/api/categories`              | Distinct categories (for filters)                              |
| GET    | `/api/stats`                   | Dashboard counts                                               |

**HTTP status codes used:** `200` OK · `201` Created · `400` Validation error · `404` Not found · `409` Conflict (rule broken, e.g. book already issued).

---

## 6. Validation rules

| Rule                                                   | Where checked                 |
|--------------------------------------------------------|-------------------------------|
| All book fields required                               | Frontend + Backend            |
| ISBN must be 10 or 13 digits (hyphens allowed)         | Frontend + Backend            |
| ISBN must be unique                                    | Backend + DB `UNIQUE`         |
| Valid email; email unique                              | Frontend + Backend + DB       |
| Phone must be a 10-digit mobile number                 | Frontend + Backend            |
| **Cannot issue a book that is already issued**         | Backend + DB partial index    |
| Member can hold at most 3 books                        | Backend (+ disabled in UI)    |
| Loan period 1–60 days                                  | Frontend + Backend            |
| Cannot return a book that isn't issued                 | Backend                       |
| Cannot delete an issued book / member holding books    | Backend                       |

---

## 7. Testing

Run `python -m pytest -v` (or `npm test`). There are 22 tests and all of them pass, including these edge cases:

| Test case                                    | Expected result                          |
|----------------------------------------------|------------------------------------------|
| Search for a non-existent book               | `200`, empty list, "No book found…" in UI|
| Issue a book that is already issued          | `409` "not available"                    |
| Return a book that was never issued          | `409` "not currently issued"             |
| Issue / return a non-existent book           | `404`                                    |
| Issue to a non-existent member               | `404`                                    |
| Add a book with a duplicate ISBN             | `409`                                    |
| Invalid ISBN / missing fields                | `400` with field errors                  |
| Member tries to borrow a 4th book            | `409` limit reached                      |
| Delete an issued book                        | `409`                                    |
| Return 4 days late                           | Fine = Rs. 20                            |
| Duplicate member email (case-insensitive)    | `409`                                    |
| Delete a member who still holds books        | `409`                                    |

Tests use a temporary database, so they never change your real data.

---

## 8. How it works (request flow)

1. The user clicks **Issue** in the browser. `app.js` sends `fetch("/api/books/3/issue", {method: "POST", body: JSON})`.
2. **Flask** routes the request to `issue_book()` and validates the input.
3. It checks the business rules (book exists, is available, and the member is under the limit) using **SQLite** queries.
4. In one transaction it sets the book's status to `Issued` and inserts an `issues` row, then commits.
5. Flask returns JSON. `app.js` shows a toast and re-renders the table and stats **without reloading the page**.
