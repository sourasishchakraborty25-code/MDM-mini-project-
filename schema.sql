-- Library Management System - SQLite schema
-- Three related tables: books, members, issues (issue/return history)

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS books (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,
    author      TEXT    NOT NULL,
    isbn        TEXT    NOT NULL UNIQUE,
    category    TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'Available'
                CHECK (status IN ('Available', 'Issued')),
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS members (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    email       TEXT    NOT NULL UNIQUE,
    phone       TEXT    NOT NULL,
    joined_on   TEXT    NOT NULL DEFAULT (date('now'))
);

CREATE TABLE IF NOT EXISTS issues (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id     INTEGER NOT NULL REFERENCES books(id)   ON DELETE CASCADE,
    member_id   INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    issue_date  TEXT    NOT NULL,
    due_date    TEXT    NOT NULL,
    return_date TEXT    -- NULL while the book is still with the member
);

-- Database-level guarantee: a book can have at most ONE active (unreturned) issue.
CREATE UNIQUE INDEX IF NOT EXISTS one_active_issue_per_book
    ON issues(book_id) WHERE return_date IS NULL;

CREATE INDEX IF NOT EXISTS idx_issues_member ON issues(member_id);
CREATE INDEX IF NOT EXISTS idx_books_title   ON books(title);
CREATE INDEX IF NOT EXISTS idx_books_author  ON books(author);
