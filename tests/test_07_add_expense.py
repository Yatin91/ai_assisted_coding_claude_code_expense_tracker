"""
Tests for Step 7: Add Expense
Spec: .claude/specs/07-add-expense.md

Coverage:
  Unit tests  — insert_expense() in database/queries.py
  Route tests — GET  /expenses/add  (auth guard + form rendering)
  Route tests — POST /expenses/add  (auth guard, validation, DB side effects)

Each test is fully independent: it uses its own temporary SQLite file,
initialises the schema directly, and tears the file down after the test.
"""

import os
import sqlite3
import sys
import tempfile

import pytest
from werkzeug.security import generate_password_hash

# ---------------------------------------------------------------------------
# Make the project root importable regardless of cwd
# ---------------------------------------------------------------------------

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as app_module

# ---------------------------------------------------------------------------
# Fixed category list (from the spec — never derived from implementation)
# ---------------------------------------------------------------------------

CATEGORIES = [
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
]

# ---------------------------------------------------------------------------
# Shared low-level helpers
# ---------------------------------------------------------------------------


def _make_app(db_path):
    """Return the Flask app configured to use db_path as its database."""
    app_module.app.config["TESTING"] = True
    app_module.app.config["DATABASE"] = db_path
    app_module.app.secret_key = "test-secret-key"
    return app_module.app


def _init_schema(conn):
    """Create users and expenses tables in an existing connection."""
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            date TEXT NOT NULL,
            description TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.commit()


def _create_user(conn, name="Test User", email="tester@spendly.com"):
    """Insert a test user and return its new user_id."""
    pw_hash = generate_password_hash("password123")
    cur = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        (name, email, pw_hash),
    )
    conn.commit()
    return cur.lastrowid


def _auth_client(client, user_id):
    """Push user_id into the Flask session (no real login request needed)."""
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    return client


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_file():
    """Yield a temporary SQLite file path; clean it up after the test."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture()
def setup(db_file, monkeypatch):
    """
    Full test harness:
      - Patches database.db.DATABASE to the temp file.
      - Initialises the schema and inserts one test user.
      - Yields (flask_test_client, user_id, db_file, db_mod).
    """
    import database.db as db_mod

    monkeypatch.setattr(db_mod, "DATABASE", db_file)

    conn = db_mod.get_db()
    _init_schema(conn)
    user_id = _create_user(conn)
    conn.close()

    flask_app = _make_app(db_file)
    client = flask_app.test_client()

    yield client, user_id, db_file, db_mod


# ---------------------------------------------------------------------------
# Unit tests — insert_expense()
# ---------------------------------------------------------------------------


class TestInsertExpense:
    """Direct unit tests for the insert_expense() query helper."""

    def test_valid_insert_stores_row_in_db(self, setup):
        """insert_expense with all fields → row exists in DB with correct values."""
        client, user_id, db_file, db_mod = setup

        from database.queries import insert_expense

        expense_id = insert_expense(
            user_id=user_id,
            amount=50.0,
            category="Food",
            date="2026-03-20",
            description="Lunch",
        )

        assert expense_id is not None, "insert_expense must return the new row id"

        conn = db_mod.get_db()
        row = conn.execute(
            "SELECT * FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
        conn.close()

        assert row is not None, "A row with the returned id must exist in the DB"
        assert row["user_id"] == user_id, "Stored user_id must match"
        assert row["amount"] == 50.0, "Stored amount must match"
        assert row["category"] == "Food", "Stored category must match"
        assert row["date"] == "2026-03-20", "Stored date must match"
        assert row["description"] == "Lunch", "Stored description must match"

    def test_insert_with_none_description_stores_null(self, setup):
        """insert_expense with description=None → description column is NULL in DB."""
        client, user_id, db_file, db_mod = setup

        from database.queries import insert_expense

        expense_id = insert_expense(
            user_id=user_id,
            amount=25.0,
            category="Transport",
            date="2026-03-21",
            description=None,
        )

        assert expense_id is not None, "insert_expense must return the new row id"

        conn = db_mod.get_db()
        row = conn.execute(
            "SELECT description FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
        conn.close()

        assert row is not None, "Row must exist in the DB"
        assert (
            row["description"] is None
        ), "description must be stored as NULL when None is passed"


# ---------------------------------------------------------------------------
# Route tests — GET /expenses/add
# ---------------------------------------------------------------------------


class TestGetAddExpense:
    """Tests for the GET /expenses/add route."""

    def test_unauthenticated_get_redirects_to_login(self, setup):
        """Unauthenticated GET /expenses/add must redirect (302) to /login."""
        client, user_id, db_file, db_mod = setup

        resp = client.get("/expenses/add")

        assert (
            resp.status_code == 302
        ), "Expected a 302 redirect for unauthenticated access"
        assert (
            "/login" in resp.headers["Location"]
        ), "Redirect Location must contain /login"

    def test_authenticated_get_returns_200(self, setup):
        """Authenticated GET /expenses/add must return HTTP 200."""
        client, user_id, db_file, db_mod = setup

        _auth_client(client, user_id)
        resp = client.get("/expenses/add")

        assert (
            resp.status_code == 200
        ), "Expected 200 for authenticated GET /expenses/add"

    def test_authenticated_get_contains_all_7_category_options(self, setup):
        """Response body must include all 7 fixed categories inside a <select> element."""
        client, user_id, db_file, db_mod = setup

        _auth_client(client, user_id)
        resp = client.get("/expenses/add")
        body = resp.data.decode("utf-8")

        assert (
            "<select" in body
        ), "Response body must contain a <select> element for categories"

        for category in CATEGORIES:
            assert (
                category in body
            ), f"Category option '{category}' must be present in the form"

    def test_authenticated_get_contains_post_form(self, setup):
        """Response body must contain a <form element with method POST."""
        client, user_id, db_file, db_mod = setup

        _auth_client(client, user_id)
        resp = client.get("/expenses/add")
        body = resp.data.decode("utf-8").lower()

        assert "<form" in body, "Response body must contain a <form> element"
        assert (
            "post" in body
        ), "The form must declare method POST (case-insensitive check)"


# ---------------------------------------------------------------------------
# Route tests — POST /expenses/add
# ---------------------------------------------------------------------------


class TestPostAddExpense:
    """Tests for the POST /expenses/add route."""

    # -- Auth guard ----------------------------------------------------------

    def test_unauthenticated_post_redirects_to_login(self, setup):
        """Unauthenticated POST /expenses/add must redirect (302) to /login."""
        client, user_id, db_file, db_mod = setup

        resp = client.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )

        assert (
            resp.status_code == 302
        ), "Expected a 302 redirect for unauthenticated POST"
        assert (
            "/login" in resp.headers["Location"]
        ), "Redirect Location must contain /login"

    # -- Happy path ----------------------------------------------------------

    def test_valid_post_redirects_to_profile(self, setup):
        """Valid authenticated POST must redirect (302) to /profile."""
        client, user_id, db_file, db_mod = setup

        _auth_client(client, user_id)
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )

        assert (
            resp.status_code == 302
        ), "Expected a 302 redirect after successful insert"
        assert (
            "/profile" in resp.headers["Location"]
        ), "Successful POST must redirect to /profile"

    def test_valid_post_inserts_row_in_db(self, setup):
        """Valid authenticated POST must create a matching row in the expenses table."""
        client, user_id, db_file, db_mod = setup

        _auth_client(client, user_id)
        client.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )

        conn = db_mod.get_db()
        row = conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? AND date = ? AND category = ?",
            (user_id, "2026-03-20", "Food"),
        ).fetchone()
        conn.close()

        assert (
            row is not None
        ), "A new expense row must exist in the DB after a valid POST"
        assert row["amount"] == 50.0, "Stored amount must be 50.0"
        assert (
            row["description"] == "Lunch"
        ), "Stored description must match submitted value"

    # -- Validation: amount --------------------------------------------------

    def test_missing_amount_returns_200_with_error(self, setup):
        """POST with missing amount must return 200 and display an error message."""
        client, user_id, db_file, db_mod = setup

        _auth_client(client, user_id)
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "",
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )

        assert resp.status_code == 200, "Missing amount must re-render the form (200)"
        body = resp.data.decode("utf-8")
        # An error message must be present; we check for common error-related terms
        # rather than exact wording to stay spec-driven
        assert any(
            keyword in body.lower()
            for keyword in ["error", "invalid", "required", "positive", "amount"]
        ), "Response body must contain an error message when amount is missing"

    def test_zero_amount_returns_200_with_error(self, setup):
        """POST with amount=0 must return 200 and display an error message."""
        client, user_id, db_file, db_mod = setup

        _auth_client(client, user_id)
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "0",
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )

        assert resp.status_code == 200, "Amount=0 must re-render the form (200)"
        body = resp.data.decode("utf-8")
        assert any(
            keyword in body.lower()
            for keyword in ["error", "invalid", "positive", "amount"]
        ), "Response body must contain an error message when amount is 0"

    def test_non_numeric_amount_returns_200_with_error(self, setup):
        """POST with a non-numeric amount must return 200 and display an error message."""
        client, user_id, db_file, db_mod = setup

        _auth_client(client, user_id)
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "abc",
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )

        assert (
            resp.status_code == 200
        ), "Non-numeric amount must re-render the form (200)"
        body = resp.data.decode("utf-8")
        assert any(
            keyword in body.lower()
            for keyword in ["error", "invalid", "positive", "amount"]
        ), "Response body must contain an error message when amount is non-numeric"

    # -- Validation: category ------------------------------------------------

    def test_invalid_category_returns_200_with_error(self, setup):
        """POST with a category not in the fixed 7 must return 200 and display an error."""
        client, user_id, db_file, db_mod = setup

        _auth_client(client, user_id)
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "Luxury",  # not in the fixed list
                "date": "2026-03-20",
                "description": "Fancy dinner",
            },
        )

        assert resp.status_code == 200, "Invalid category must re-render the form (200)"
        body = resp.data.decode("utf-8")
        assert any(
            keyword in body.lower()
            for keyword in ["error", "invalid", "category", "valid"]
        ), "Response body must contain an error message when category is invalid"

    # -- Validation: date ----------------------------------------------------

    def test_invalid_date_string_returns_200_with_error(self, setup):
        """POST with a malformed date must return 200 and display an error message."""
        client, user_id, db_file, db_mod = setup

        _auth_client(client, user_id)
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "Food",
                "date": "not-a-date",
                "description": "Lunch",
            },
        )

        assert resp.status_code == 200, "Invalid date must re-render the form (200)"
        body = resp.data.decode("utf-8")
        assert any(
            keyword in body.lower() for keyword in ["error", "invalid", "date", "valid"]
        ), "Response body must contain an error message when date is malformed"

    # -- Optional description ------------------------------------------------

    def test_no_description_redirects_to_profile(self, setup):
        """POST without description (optional field) must redirect (302) to /profile."""
        client, user_id, db_file, db_mod = setup

        _auth_client(client, user_id)
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "75.0",
                "category": "Bills",
                "date": "2026-03-22",
                "description": "",  # intentionally empty
            },
        )

        assert (
            resp.status_code == 302
        ), "Missing description must still succeed and redirect to /profile"
        assert (
            "/profile" in resp.headers["Location"]
        ), "Redirect must go to /profile when description is absent"

    def test_no_description_stores_null_in_db(self, setup):
        """POST without description must insert the row with description = NULL."""
        client, user_id, db_file, db_mod = setup

        _auth_client(client, user_id)
        client.post(
            "/expenses/add",
            data={
                "amount": "75.0",
                "category": "Bills",
                "date": "2026-03-22",
                "description": "",
            },
        )

        conn = db_mod.get_db()
        row = conn.execute(
            "SELECT description FROM expenses WHERE user_id = ? AND date = ? AND category = ?",
            (user_id, "2026-03-22", "Bills"),
        ).fetchone()
        conn.close()

        assert row is not None, "Expense row must exist when description is omitted"
        assert (
            row["description"] is None
        ), "description column must be NULL when an empty string is submitted"

    # -- Parametrized edge cases for amount validation -----------------------

    @pytest.mark.parametrize(
        "bad_amount",
        [
            "",  # empty / missing
            "0",  # zero
            "0.00",  # zero as float string
            "-10",  # negative
            "abc",  # non-numeric text
            "1e999",  # would overflow float in some parsers
            " ",  # whitespace only
        ],
    )
    def test_bad_amounts_return_200_with_error(self, setup, bad_amount):
        """Every invalid amount value must re-render the form (200) with an error."""
        client, user_id, db_file, db_mod = setup

        _auth_client(client, user_id)
        resp = client.post(
            "/expenses/add",
            data={
                "amount": bad_amount,
                "category": "Food",
                "date": "2026-03-20",
                "description": "Test",
            },
        )

        assert (
            resp.status_code == 200
        ), f"Amount '{bad_amount}' must re-render the form, got {resp.status_code}"
        body = resp.data.decode("utf-8")
        assert any(
            keyword in body.lower()
            for keyword in ["error", "invalid", "positive", "amount", "required"]
        ), f"No error message found in body for amount='{bad_amount}'"

    # -- Parametrized edge cases for category validation ---------------------

    @pytest.mark.parametrize(
        "bad_category",
        [
            "",  # empty string
            "food",  # wrong case
            "FOOD",  # all caps
            "Groceries",  # plausible but not in list
            "Other ",  # trailing space
            "<script>alert(1)</script>",  # injection attempt
        ],
    )
    def test_bad_categories_return_200_with_error(self, setup, bad_category):
        """Every category value not in the fixed 7 must re-render the form with an error."""
        client, user_id, db_file, db_mod = setup

        _auth_client(client, user_id)
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": bad_category,
                "date": "2026-03-20",
                "description": "Test",
            },
        )

        assert (
            resp.status_code == 200
        ), f"Category '{bad_category}' must re-render the form, got {resp.status_code}"
        body = resp.data.decode("utf-8")
        assert any(
            keyword in body.lower()
            for keyword in ["error", "invalid", "category", "valid"]
        ), f"No error message found for category='{bad_category}'"

    # -- Parametrized edge cases for date validation -------------------------

    @pytest.mark.parametrize(
        "bad_date",
        [
            "",  # empty
            "20260320",  # no separators
            "03-20-2026",  # MM-DD-YYYY order
            "2026/03/20",  # wrong separator
            "not-a-date",  # plain text
            "2026-13-01",  # invalid month
            "2026-02-30",  # invalid day for February
        ],
    )
    def test_bad_dates_return_200_with_error(self, setup, bad_date):
        """Every malformed date value must re-render the form (200) with an error."""
        client, user_id, db_file, db_mod = setup

        _auth_client(client, user_id)
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "Food",
                "date": bad_date,
                "description": "Test",
            },
        )

        assert (
            resp.status_code == 200
        ), f"Date '{bad_date}' must re-render the form, got {resp.status_code}"
        body = resp.data.decode("utf-8")
        assert any(
            keyword in body.lower() for keyword in ["error", "invalid", "date", "valid"]
        ), f"No error message found for date='{bad_date}'"

    # -- Form re-population on validation error ------------------------------

    def test_submitted_values_are_repopulated_after_error(self, setup):
        """When validation fails, previously submitted values must appear in the re-rendered form."""
        client, user_id, db_file, db_mod = setup

        _auth_client(client, user_id)
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "0",  # triggers validation failure
                "category": "Health",
                "date": "2026-04-15",
                "description": "Gym membership",
            },
        )

        assert resp.status_code == 200
        body = resp.data.decode("utf-8")

        # The previously entered values should be retained in the form
        assert "Health" in body, "Category value must be re-populated after error"
        assert "2026-04-15" in body, "Date value must be re-populated after error"
        assert (
            "Gym membership" in body
        ), "Description value must be re-populated after error"
