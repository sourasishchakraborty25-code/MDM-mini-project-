/*
 * Library Management System - frontend logic
 * All data is loaded and changed through the Flask REST API using fetch(),
 * so the page never reloads.
 */

const API = "/api";

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

/** Call the backend and return parsed JSON, or throw an Error with the server's message. */
async function api(path, options = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.error || `Request failed (${res.status})`);
    err.fields = data.fields || {};
    err.status = res.status;
    throw err;
  }
  return data;
}

/** Escape text before putting it into HTML (prevents XSS). */
function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

function formatDate(iso) {
  if (!iso) return "—";
  return new Date(iso + "T00:00:00").toLocaleDateString("en-IN", {
    day: "numeric", month: "short", year: "numeric",
  });
}

function toast(message, type = "") {
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = message;
  $("#toasts").appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

function debounce(fn, ms = 250) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

/** Show field-level errors returned by the server (or found on the client). */
function showFieldErrors(form, fields = {}) {
  $$(".field-error[data-for]", form).forEach((el) => {
    const msg = fields[el.dataset.for] || "";
    el.textContent = msg;
    const input = form.elements[el.dataset.for];
    if (input) input.classList.toggle("invalid", Boolean(msg));
  });
}

// ---------------------------------------------------------------------------
// Client-side validation (the server validates again - never trust the client)
// ---------------------------------------------------------------------------
const ISBN_RE = /^(\d{9}[\dX]|\d{13})$/;
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$/;
const PHONE_RE = /^[6-9]\d{9}$/;

function validateBookForm(data) {
  const errors = {};
  if (!data.title.trim()) errors.title = "Title is required.";
  if (!data.author.trim()) errors.author = "Author is required.";
  const isbn = data.isbn.replace(/[\s-]/g, "").toUpperCase();
  if (!isbn) errors.isbn = "ISBN is required.";
  else if (!ISBN_RE.test(isbn)) errors.isbn = "ISBN must be 10 or 13 digits (hyphens allowed).";
  if (!data.category.trim()) errors.category = "Category is required.";
  return errors;
}

function validateMemberForm(data) {
  const errors = {};
  if (!data.name.trim()) errors.name = "Name is required.";
  if (!EMAIL_RE.test(data.email.trim())) errors.email = "Enter a valid email address.";
  if (!PHONE_RE.test(data.phone.replace(/[\s-]/g, ""))) errors.phone = "Phone must be a valid 10-digit mobile number.";
  return errors;
}

// ---------------------------------------------------------------------------
// Dashboard stats
// ---------------------------------------------------------------------------
async function loadStats() {
  try {
    const s = await api("/stats");
    $("#stat-total").textContent = s.total_books;
    $("#stat-available").textContent = s.available;
    $("#stat-issued").textContent = s.issued;
    $("#stat-overdue").textContent = s.overdue;
    $("#stat-members").textContent = s.members;
  } catch (e) {
    toast("Could not load statistics: " + e.message, "error");
  }
}

async function loadCategories() {
  const cats = await api("/categories");
  const filter = $("#filter-category");
  const current = filter.value;
  filter.innerHTML = '<option value="">All categories</option>' +
    cats.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join("");
  filter.value = cats.includes(current) ? current : "";
  $("#category-list").innerHTML = cats.map((c) => `<option value="${esc(c)}">`).join("");
}

// ---------------------------------------------------------------------------
// Books
// ---------------------------------------------------------------------------
let books = [];

async function loadBooks(highlightId) {
  const params = new URLSearchParams({
    q: $("#book-search").value.trim(),
    by: $("#search-by").value,
    category: $("#filter-category").value,
    status: $("#filter-status").value,
  });
  try {
    books = await api("/books?" + params);
    renderBooks(highlightId);
  } catch (e) {
    toast("Could not load books: " + e.message, "error");
  }
}

function renderBooks(highlightId) {
  const tbody = $("#book-rows");
  const q = $("#book-search").value.trim();
  $("#book-count").textContent = q || $("#filter-category").value || $("#filter-status").value
    ? `${books.length} result${books.length === 1 ? "" : "s"}`
    : `${books.length} book${books.length === 1 ? "" : "s"} in catalogue`;

  if (!books.length) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty">${
      q ? `No book found matching “${esc(q)}”.` : "No books to show."
    }</td></tr>`;
    return;
  }

  tbody.innerHTML = books.map((b) => {
    let status;
    if (b.status === "Available") status = '<span class="badge available">Available</span>';
    else status = `<span class="badge ${b.overdue ? "overdue" : "issued"}">${b.overdue ? "Overdue" : "Issued"}</span>
      <div class="sub">${esc(b.issued_to)} · due ${formatDate(b.due_date)}</div>`;

    const action = b.status === "Available"
      ? `<button class="btn small issue" data-action="issue" data-id="${b.id}">Issue</button>`
      : `<button class="btn small return" data-action="return" data-id="${b.id}">Return</button>`;

    return `<tr data-id="${b.id}" class="${b.id === highlightId ? "flash" : ""}">
      <td><div class="book-title">${esc(b.title)}</div><div class="sub">${esc(b.author)}</div></td>
      <td class="mono">${esc(b.isbn)}</td>
      <td>${esc(b.category)}</td>
      <td>${status}</td>
      <td class="right">
        ${action}
        <button class="btn small ghost" data-action="edit" data-id="${b.id}">Edit</button>
        <button class="btn small danger" data-action="delete" data-id="${b.id}">Delete</button>
      </td>
    </tr>`;
  }).join("");
}

function resetBookForm() {
  const form = $("#book-form");
  form.reset();
  $("#book-id").value = "";
  $("#book-form-title").textContent = "Add a new book";
  $("#book-submit").textContent = "Add book";
  $("#book-cancel").classList.add("hidden");
  showFieldErrors(form);
}

function startEditBook(book) {
  $("#book-id").value = book.id;
  $("#book-title").value = book.title;
  $("#book-author").value = book.author;
  $("#book-isbn").value = book.isbn;
  $("#book-category").value = book.category;
  $("#book-form-title").textContent = "Edit book";
  $("#book-submit").textContent = "Save changes";
  $("#book-cancel").classList.remove("hidden");
  showFieldErrors($("#book-form"));
  $("#book-form").scrollIntoView({ behavior: "smooth", block: "start" });
  $("#book-title").focus();
}

$("#book-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  // Use form.elements[...] - form.title / form.name are built-in form properties.
  const f = form.elements;
  const data = {
    title: f["title"].value,
    author: f["author"].value,
    isbn: f["isbn"].value,
    category: f["category"].value,
  };
  const errors = validateBookForm(data);
  showFieldErrors(form, errors);
  if (Object.keys(errors).length) return;

  const id = $("#book-id").value;
  try {
    const saved = await api(id ? `/books/${id}` : "/books", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(data),
    });
    toast(id ? `Updated “${saved.title}”.` : `Added “${saved.title}” to the catalogue.`, "success");
    resetBookForm();
    await Promise.all([loadBooks(saved.id), loadStats(), loadCategories()]);
  } catch (err) {
    showFieldErrors(form, err.fields);
    toast(err.message, "error");
  }
});

$("#book-cancel").addEventListener("click", resetBookForm);

$("#book-rows").addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-action]");
  if (!btn) return;
  const id = Number(btn.dataset.id);
  const book = books.find((b) => b.id === id);
  if (!book) return;

  switch (btn.dataset.action) {
    case "edit":
      startEditBook(book);
      break;
    case "issue":
      openIssueDialog(book);
      break;
    case "return":
      if (!confirm(`Mark “${book.title}” as returned by ${book.issued_to}?`)) return;
      try {
        const res = await api(`/books/${id}/return`, { method: "POST" });
        toast(res.message, res.fine ? "error" : "success");
        refreshAll(id);
      } catch (err) { toast(err.message, "error"); }
      break;
    case "delete":
      if (!confirm(`Delete “${book.title}” permanently?`)) return;
      try {
        const res = await api(`/books/${id}`, { method: "DELETE" });
        toast(res.message, "success");
        if ($("#book-id").value == id) resetBookForm();
        await Promise.all([loadBooks(), loadStats(), loadCategories()]);
      } catch (err) { toast(err.message, "error"); }
      break;
  }
});

const reloadBooks = debounce(() => loadBooks(), 250);
$("#book-search").addEventListener("input", reloadBooks);
["#search-by", "#filter-category", "#filter-status"].forEach((s) =>
  $(s).addEventListener("change", () => loadBooks()));

// ---------------------------------------------------------------------------
// Issue dialog
// ---------------------------------------------------------------------------
let issuingBook = null;

async function openIssueDialog(book) {
  issuingBook = book;
  $("#issue-book-title").textContent = `“${book.title}” by ${book.author}`;
  $("#issue-error").textContent = "";
  $("#issue-days").value = 14;
  try {
    const members = await api("/members");
    if (!members.length) {
      toast("Register a member first (Members tab).", "error");
      return;
    }
    $("#issue-member").innerHTML = members.map((m) =>
      `<option value="${m.id}" ${m.books_held >= 3 ? "disabled" : ""}>
        ${esc(m.name)} (${m.books_held}/3 held)${m.books_held >= 3 ? " — limit reached" : ""}
      </option>`).join("");
    const firstEnabled = members.find((m) => m.books_held < 3);
    if (firstEnabled) $("#issue-member").value = firstEnabled.id;
    $("#issue-dialog").showModal();
  } catch (err) { toast(err.message, "error"); }
}

$("#issue-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const member_id = $("#issue-member").value;
  const days = Number($("#issue-days").value);
  if (!member_id) { $("#issue-error").textContent = "Select a member."; return; }
  if (!(days >= 1 && days <= 60)) { $("#issue-error").textContent = "Loan period must be 1–60 days."; return; }
  try {
    const res = await api(`/books/${issuingBook.id}/issue`, {
      method: "POST",
      body: JSON.stringify({ member_id: Number(member_id), days }),
    });
    $("#issue-dialog").close();
    toast(res.message, "success");
    refreshAll(issuingBook.id);
  } catch (err) {
    $("#issue-error").textContent = err.message;
  }
});
$("#issue-cancel").addEventListener("click", () => $("#issue-dialog").close());

// ---------------------------------------------------------------------------
// Members
// ---------------------------------------------------------------------------
async function loadMembers() {
  const q = $("#member-search").value.trim();
  try {
    const members = await api("/members?" + new URLSearchParams({ q }));
    const tbody = $("#member-rows");
    if (!members.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty">${
        q ? `No member found matching “${esc(q)}”.` : "No members registered yet."}</td></tr>`;
      return;
    }
    tbody.innerHTML = members.map((m) => `
      <tr>
        <td><div class="book-title">${esc(m.name)}</div><div class="sub">Joined ${formatDate(m.joined_on)}</div></td>
        <td>${esc(m.email)}</td>
        <td class="mono">${esc(m.phone)}</td>
        <td>${m.books_held} / 3</td>
        <td class="right"><button class="btn small danger" data-id="${m.id}" data-name="${esc(m.name)}">Remove</button></td>
      </tr>`).join("");
  } catch (err) { toast("Could not load members: " + err.message, "error"); }
}

$("#member-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const f = form.elements;
  const data = { name: f["name"].value, email: f["email"].value, phone: f["phone"].value };
  const errors = validateMemberForm(data);
  showFieldErrors(form, errors);
  if (Object.keys(errors).length) return;
  try {
    const m = await api("/members", { method: "POST", body: JSON.stringify(data) });
    toast(`Registered ${m.name}.`, "success");
    form.reset();
    loadMembers(); loadStats();
  } catch (err) {
    showFieldErrors(form, err.fields);
    toast(err.message, "error");
  }
});

$("#member-rows").addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-id]");
  if (!btn) return;
  if (!confirm(`Remove member ${btn.dataset.name}?`)) return;
  try {
    const res = await api(`/members/${btn.dataset.id}`, { method: "DELETE" });
    toast(res.message, "success");
    loadMembers(); loadStats();
  } catch (err) { toast(err.message, "error"); }
});

$("#member-search").addEventListener("input", debounce(loadMembers, 250));

// ---------------------------------------------------------------------------
// Issued books / history
// ---------------------------------------------------------------------------
async function loadIssues() {
  const all = $("#show-history").checked;
  try {
    const issues = await api("/issues?status=" + (all ? "all" : "active"));
    const tbody = $("#issue-rows");
    if (!issues.length) {
      tbody.innerHTML = `<tr><td colspan="6" class="empty">${all ? "No issue records yet." : "No books are currently issued."}</td></tr>`;
      return;
    }
    tbody.innerHTML = issues.map((i) => {
      let badge;
      if (i.return_date) badge = `<span class="badge returned">Returned ${formatDate(i.return_date)}</span>`;
      else if (i.overdue) badge = '<span class="badge overdue">Overdue</span>';
      else badge = '<span class="badge issued">With member</span>';
      return `<tr>
        <td><div class="book-title">${esc(i.title)}</div><div class="sub mono">${esc(i.isbn)}</div></td>
        <td>${esc(i.member_name)}</td>
        <td>${formatDate(i.issue_date)}</td>
        <td>${formatDate(i.due_date)}</td>
        <td>${badge}</td>
        <td class="right">${i.return_date ? "" :
          `<button class="btn small return" data-book="${i.book_id}" data-title="${esc(i.title)}">Return</button>`}</td>
      </tr>`;
    }).join("");
  } catch (err) { toast("Could not load issue records: " + err.message, "error"); }
}

$("#issue-rows").addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-book]");
  if (!btn) return;
  if (!confirm(`Mark “${btn.dataset.title}” as returned?`)) return;
  try {
    const res = await api(`/books/${btn.dataset.book}/return`, { method: "POST" });
    toast(res.message, res.fine ? "error" : "success");
    refreshAll();
  } catch (err) { toast(err.message, "error"); }
});
$("#show-history").addEventListener("change", loadIssues);

// ---------------------------------------------------------------------------
// Tabs + startup
// ---------------------------------------------------------------------------
$$(".tab").forEach((tab) => tab.addEventListener("click", () => {
  $$(".tab").forEach((t) => t.classList.toggle("active", t === tab));
  $$(".panel").forEach((p) => p.classList.toggle("active", p.id === "panel-" + tab.dataset.tab));
  if (tab.dataset.tab === "members") loadMembers();
  if (tab.dataset.tab === "issues") loadIssues();
}));

function refreshAll(highlightId) {
  return Promise.all([loadBooks(highlightId), loadStats(), loadMembers(), loadIssues()]);
}

loadCategories().catch(() => {});
refreshAll();
