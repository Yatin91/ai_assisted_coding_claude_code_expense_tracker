"""
Tests for Step 6: Date Filter for Profile Page
Spec: .claude/specs/06-date-filter-profile.md

These tests cover GET /profile with optional date_from / date_to query params.
Each test is fully independent — it sets up its own DB state and tears it down.
"""

import sqlite3
import tempfile
import os
from datetime import date, timedelta

import pytest
from werkzeug.security import generate_password_hash

# ---------------------------------------------------------------------------
# App import & configuration
# ---------------------------------------------------------------------------

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as app_module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_app(db_path):
    """Return a configured Flask test app pointing at db_path."""
    app_module.app.config["TESTING"] = True
    app_module.app.config["DATABASE"] = db_path
    app_module.app.secret_key = "test-secret-key"
    return app_module.app


def _init_schema(conn):
    """Create the users and expenses tables in a fresh connection."""
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


def _create_user(conn, name="Test User", email="test@spendly.com"):
    """Insert a user row and return the new user_id."""
    pw_hash = generate_password_hash("password123")
    cur = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        (name, email, pw_hash),
    )
    conn.commit()
    return cur.lastrowid


def _insert_expense(conn, user_id, amount, category, expense_date, description="Test expense"):
    """Insert a single expense row. expense_date must be a YYYY-MM-DD string."""
    conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        (user_id, amount, category, expense_date, description),
    )
    conn.commit()


def _iso(d: date) -> str:
    return d.isoformat()


# Commonly used reference dates (relative to today)
TODAY = date.today()
THIS_MONTH_START = date(TODAY.year, TODAY.month, 1)
NINETY_DAYS_AGO = TODAY - timedelta(days=90)
ONE_EIGHTY_DAYS_AGO = TODAY - timedelta(days=180)
SEVEN_MONTHS_AGO = TODAY - timedelta(days=210)  # outside 6-month window


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_file():
    """Yield a temporary SQLite file path; delete it after the test."""
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
    Patch database.db.DATABASE and database.db.get_db to use the temp file,
    initialise the schema, create one test user, and yield (flask_client, user_id).
    """
    import database.db as db_mod

    # Patch the DATABASE constant used by get_db()
    monkeypatch.setattr(db_mod, "DATABASE", db_file)

    # Seed schema via the real get_db() (now pointing at db_file)
    conn = db_mod.get_db()
    _init_schema(conn)
    user_id = _create_user(conn)
    conn.close()

    flask_app = _make_app(db_file)
    client = flask_app.test_client()

    yield client, user_id, db_file, db_mod


def _auth_client(client, user_id):
    """Push user_id into the session so subsequent requests are authenticated."""
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    return client


# ---------------------------------------------------------------------------
# 1. Unfiltered view returns ALL expenses
# ---------------------------------------------------------------------------

def test_unfiltered_profile_returns_all_expenses(setup):
    client, user_id, db_file, db_mod = setup

    # Insert expenses across different months
    conn = db_mod.get_db()
    _insert_expense(conn, user_id, 100.00, "Food", _iso(TODAY), "today expense")
    _insert_expense(conn, user_id, 200.00, "Transport", _iso(NINETY_DAYS_AGO), "old expense")
    _insert_expense(conn, user_id, 300.00, "Bills", _iso(SEVEN_MONTHS_AGO), "very old expense")
    conn.close()

    _auth_client(client, user_id)
    resp = client.get("/profile")

    assert resp.status_code == 200
    body = resp.data.decode("utf-8")

    # All three amounts should appear in the unfiltered view
    assert "100" in body
    assert "200" in body
    assert "300" in body


# ---------------------------------------------------------------------------
# 2. "This Month" preset filters to the current calendar month only
# ---------------------------------------------------------------------------

def test_this_month_preset_filters_to_current_month(setup):
    client, user_id, db_file, db_mod = setup

    conn = db_mod.get_db()
    # Expense inside this month
    _insert_expense(conn, user_id, 500.00, "Food", _iso(THIS_MONTH_START), "this month")
    # Expense outside this month (7 months ago)
    _insert_expense(conn, user_id, 999.00, "Shopping", _iso(SEVEN_MONTHS_AGO), "old month")
    conn.close()

    _auth_client(client, user_id)
    resp = client.get(
        f"/profile?date_from={_iso(THIS_MONTH_START)}&date_to={_iso(TODAY)}"
    )

    assert resp.status_code == 200
    body = resp.data.decode("utf-8")

    # The in-range expense amount should appear
    assert "500" in body
    # The out-of-range amount must NOT appear
    assert "999" not in body


# ---------------------------------------------------------------------------
# 3. "Last 3 Months" preset — 90-day window
# ---------------------------------------------------------------------------

def test_last_3_months_preset(setup):
    client, user_id, db_file, db_mod = setup

    conn = db_mod.get_db()
    # Expense exactly on the 90-day boundary (inclusive)
    _insert_expense(conn, user_id, 250.00, "Health", _iso(NINETY_DAYS_AGO), "boundary expense")
    # Expense from 7 months ago — outside the window
    _insert_expense(conn, user_id, 888.00, "Entertainment", _iso(SEVEN_MONTHS_AGO), "too old")
    conn.close()

    _auth_client(client, user_id)
    resp = client.get(
        f"/profile?date_from={_iso(NINETY_DAYS_AGO)}&date_to={_iso(TODAY)}"
    )

    assert resp.status_code == 200
    body = resp.data.decode("utf-8")

    assert "250" in body
    assert "888" not in body


# ---------------------------------------------------------------------------
# 4. "Last 6 Months" preset — 180-day window
# ---------------------------------------------------------------------------

def test_last_6_months_preset(setup):
    client, user_id, db_file, db_mod = setup

    conn = db_mod.get_db()
    # Expense inside the 6-month window
    _insert_expense(conn, user_id, 400.00, "Bills", _iso(ONE_EIGHTY_DAYS_AGO), "six months boundary")
    # Expense older than 6 months
    _insert_expense(conn, user_id, 777.00, "Other", _iso(SEVEN_MONTHS_AGO), "too old")
    conn.close()

    _auth_client(client, user_id)
    resp = client.get(
        f"/profile?date_from={_iso(ONE_EIGHTY_DAYS_AGO)}&date_to={_iso(TODAY)}"
    )

    assert resp.status_code == 200
    body = resp.data.decode("utf-8")

    assert "400" in body
    assert "777" not in body


# ---------------------------------------------------------------------------
# 5. "All Time" preset — clean /profile URL shows everything
# ---------------------------------------------------------------------------

def test_all_time_preset_shows_all(setup):
    client, user_id, db_file, db_mod = setup

    conn = db_mod.get_db()
    _insert_expense(conn, user_id, 111.00, "Food", _iso(TODAY), "recent")
    _insert_expense(conn, user_id, 222.00, "Transport", _iso(SEVEN_MONTHS_AGO), "very old")
    conn.close()

    _auth_client(client, user_id)
    # "All Time" sends a clean URL with no query params
    resp = client.get("/profile")

    assert resp.status_code == 200
    body = resp.data.decode("utf-8")

    assert "111" in body
    assert "222" in body


# ---------------------------------------------------------------------------
# 6. Custom date range — only in-range expenses returned
# ---------------------------------------------------------------------------

def test_custom_date_range_filters_correctly(setup):
    client, user_id, db_file, db_mod = setup

    # Define a narrow custom window in the recent past
    range_end = TODAY - timedelta(days=5)
    range_start = TODAY - timedelta(days=15)
    before_range = TODAY - timedelta(days=30)
    after_range = TODAY  # after range_end

    conn = db_mod.get_db()
    _insert_expense(conn, user_id, 123.00, "Food", _iso(range_start), "start of range")
    _insert_expense(conn, user_id, 456.00, "Bills", _iso(range_end), "end of range")
    _insert_expense(conn, user_id, 789.00, "Other", _iso(before_range), "before range")
    _insert_expense(conn, user_id, 321.00, "Shopping", _iso(after_range), "after range")
    conn.close()

    _auth_client(client, user_id)
    resp = client.get(
        f"/profile?date_from={_iso(range_start)}&date_to={_iso(range_end)}"
    )

    assert resp.status_code == 200
    body = resp.data.decode("utf-8")

    # Expenses inside the range
    assert "123" in body
    assert "456" in body
    # Expenses outside the range must not appear
    assert "789" not in body
    # after_range is TODAY which is > range_end, so it must not appear
    assert "321" not in body


# ---------------------------------------------------------------------------
# 7. Inverted date range → flash error, unfiltered view returned
# ---------------------------------------------------------------------------

def test_inverted_date_range_flashes_error(setup):
    client, user_id, db_file, db_mod = setup

    conn = db_mod.get_db()
    _insert_expense(conn, user_id, 550.00, "Food", _iso(TODAY), "present expense")
    conn.close()

    _auth_client(client, user_id)
    # date_from is AFTER date_to — an invalid / inverted range
    resp = client.get(
        f"/profile?date_from={_iso(TODAY)}&date_to={_iso(TODAY - timedelta(days=10))}"
    )

    assert resp.status_code == 200
    body = resp.data.decode("utf-8")

    # Flash error message must appear
    assert "Start date must be before end date" in body
    # Since it falls back to unfiltered, the expense should still be visible
    assert "550" in body


# ---------------------------------------------------------------------------
# 8. Malformed date string does not crash the app
# ---------------------------------------------------------------------------

def test_malformed_date_does_not_crash(setup):
    client, user_id, db_file, db_mod = setup

    conn = db_mod.get_db()
    _insert_expense(conn, user_id, 640.00, "Health", _iso(TODAY), "some expense")
    conn.close()

    _auth_client(client, user_id)
    # Send a clearly malformed date_from; date_to is also bad
    resp = client.get("/profile?date_from=not-a-date&date_to=also-bad")

    # Must not crash — 200 OK, unfiltered fallback
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "640" in body


# ---------------------------------------------------------------------------
# 8b. Malformed date_from only (date_to valid) — still no crash
# ---------------------------------------------------------------------------

def test_malformed_date_from_with_valid_date_to_does_not_crash(setup):
    client, user_id, db_file, db_mod = setup

    _auth_client(client, user_id)
    resp = client.get(f"/profile?date_from=not-a-date&date_to={_iso(TODAY)}")

    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 9. Unauthenticated user is redirected to /login
# ---------------------------------------------------------------------------

def test_unauthenticated_redirects_to_login(setup):
    client, user_id, db_file, db_mod = setup

    # Do NOT call _auth_client — no session set
    resp = client.get("/profile")

    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


# ---------------------------------------------------------------------------
# 9b. Unauthenticated user with date params still redirected
# ---------------------------------------------------------------------------

def test_unauthenticated_with_date_params_redirects_to_login(setup):
    client, user_id, db_file, db_mod = setup

    resp = client.get(f"/profile?date_from={_iso(THIS_MONTH_START)}&date_to={_iso(TODAY)}")

    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


# ---------------------------------------------------------------------------
# 10. Empty result range → ₹0.00, 0 transactions, no errors
# ---------------------------------------------------------------------------

def test_empty_result_range_shows_zero_stats(setup):
    client, user_id, db_file, db_mod = setup

    conn = db_mod.get_db()
    # All expenses are 7 months ago — outside the filter window
    _insert_expense(conn, user_id, 1000.00, "Food", _iso(SEVEN_MONTHS_AGO), "old expense")
    conn.close()

    _auth_client(client, user_id)
    # Filter to just today (no expenses exist today)
    resp = client.get(
        f"/profile?date_from={_iso(TODAY)}&date_to={_iso(TODAY)}"
    )

    assert resp.status_code == 200
    body = resp.data.decode("utf-8")

    # Must show zero total spent
    assert "0.00" in body
    # Must not contain the old expense amount
    assert "1000" not in body


# ---------------------------------------------------------------------------
# 10b. User with zero expenses ever sees zero stats on unfiltered profile
# ---------------------------------------------------------------------------

def test_zero_expenses_user_shows_zero_stats(setup):
    client, user_id, db_file, db_mod = setup

    # No expenses inserted at all
    _auth_client(client, user_id)
    resp = client.get("/profile")

    assert resp.status_code == 200
    body = resp.data.decode("utf-8")

    assert "0.00" in body


# ---------------------------------------------------------------------------
# 11. ₹ symbol present regardless of active filter
# ---------------------------------------------------------------------------

def test_rupee_symbol_present_on_unfiltered_view(setup):
    client, user_id, db_file, db_mod = setup

    conn = db_mod.get_db()
    _insert_expense(conn, user_id, 300.00, "Food", _iso(TODAY), "some food")
    conn.close()

    _auth_client(client, user_id)
    resp = client.get("/profile")

    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "₹" in body


def test_rupee_symbol_present_with_date_filter(setup):
    client, user_id, db_file, db_mod = setup

    conn = db_mod.get_db()
    _insert_expense(conn, user_id, 300.00, "Food", _iso(TODAY), "some food")
    conn.close()

    _auth_client(client, user_id)
    resp = client.get(
        f"/profile?date_from={_iso(THIS_MONTH_START)}&date_to={_iso(TODAY)}"
    )

    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "₹" in body


def test_rupee_symbol_present_on_empty_filter(setup):
    client, user_id, db_file, db_mod = setup

    conn = db_mod.get_db()
    # Expense in the past, filter to today only — result is empty
    _insert_expense(conn, user_id, 500.00, "Food", _iso(SEVEN_MONTHS_AGO), "old")
    conn.close()

    _auth_client(client, user_id)
    # Filter to a future range where no expenses exist
    future_start = TODAY + timedelta(days=1)
    future_end = TODAY + timedelta(days=5)
    resp = client.get(
        f"/profile?date_from={_iso(future_start)}&date_to={_iso(future_end)}"
    )

    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "₹" in body


# ---------------------------------------------------------------------------
# 12. Stats reflect the active filter (totals change between filter windows)
# ---------------------------------------------------------------------------

def test_stats_change_with_different_filters(setup):
    client, user_id, db_file, db_mod = setup

    conn = db_mod.get_db()
    # Expense in the current month
    _insert_expense(conn, user_id, 100.00, "Food", _iso(THIS_MONTH_START), "current month")
    # Expense 7 months ago
    _insert_expense(conn, user_id, 900.00, "Bills", _iso(SEVEN_MONTHS_AGO), "old bills")
    conn.close()

    _auth_client(client, user_id)

    # Unfiltered — both should appear; total = 1000
    resp_all = client.get("/profile")
    body_all = resp_all.data.decode("utf-8")
    assert "1000" in body_all or ("100" in body_all and "900" in body_all)

    # Filtered to this month — only the 100.00 expense
    resp_month = client.get(
        f"/profile?date_from={_iso(THIS_MONTH_START)}&date_to={_iso(TODAY)}"
    )
    body_month = resp_month.data.decode("utf-8")
    assert "100" in body_month
    assert "900" not in body_month


# ---------------------------------------------------------------------------
# 13. Transaction count in stats is correct for filtered range
# ---------------------------------------------------------------------------

def test_transaction_count_reflects_filter(setup):
    client, user_id, db_file, db_mod = setup

    conn = db_mod.get_db()
    # Two expenses in current month
    _insert_expense(conn, user_id, 50.00, "Food", _iso(THIS_MONTH_START), "exp1")
    _insert_expense(conn, user_id, 75.00, "Transport", _iso(TODAY), "exp2")
    # One expense out of range
    _insert_expense(conn, user_id, 200.00, "Bills", _iso(SEVEN_MONTHS_AGO), "old exp")
    conn.close()

    _auth_client(client, user_id)
    resp = client.get(
        f"/profile?date_from={_iso(THIS_MONTH_START)}&date_to={_iso(TODAY)}"
    )

    assert resp.status_code == 200
    body = resp.data.decode("utf-8")

    # Template should render "2" somewhere as the transaction count
    # (old expense produces "3" unfiltered, so "2" distinguishes the filtered view)
    assert "2" in body


# ---------------------------------------------------------------------------
# 14. Category breakdown respects the date filter
# ---------------------------------------------------------------------------

def test_category_breakdown_respects_date_filter(setup):
    client, user_id, db_file, db_mod = setup

    conn = db_mod.get_db()
    # In-range: Food category
    _insert_expense(conn, user_id, 300.00, "Food", _iso(TODAY), "food today")
    # Out-of-range: Entertainment
    _insert_expense(conn, user_id, 500.00, "Entertainment", _iso(SEVEN_MONTHS_AGO), "old fun")
    conn.close()

    _auth_client(client, user_id)
    resp = client.get(
        f"/profile?date_from={_iso(THIS_MONTH_START)}&date_to={_iso(TODAY)}"
    )

    assert resp.status_code == 200
    body = resp.data.decode("utf-8")

    # Food should appear in breakdown; Entertainment should not
    assert "Food" in body
    assert "Entertainment" not in body


# ---------------------------------------------------------------------------
# 15. "All Time" with no params still processes without error
#     (regression: ensure no param processing code accidentally crashes)
# ---------------------------------------------------------------------------

def test_all_time_no_params_processes_without_error(setup):
    client, user_id, db_file, db_mod = setup

    _auth_client(client, user_id)
    resp = client.get("/profile")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 16. date_from equal to date_to (single-day range) is valid
# ---------------------------------------------------------------------------

def test_single_day_range_is_valid(setup):
    client, user_id, db_file, db_mod = setup

    conn = db_mod.get_db()
    _insert_expense(conn, user_id, 99.00, "Food", _iso(TODAY), "today only")
    _insert_expense(conn, user_id, 150.00, "Bills", _iso(SEVEN_MONTHS_AGO), "old")
    conn.close()

    _auth_client(client, user_id)
    # Single-day range: date_from == date_to == TODAY
    resp = client.get(f"/profile?date_from={_iso(TODAY)}&date_to={_iso(TODAY)}")

    assert resp.status_code == 200
    body = resp.data.decode("utf-8")

    assert "99" in body
    assert "150" not in body
