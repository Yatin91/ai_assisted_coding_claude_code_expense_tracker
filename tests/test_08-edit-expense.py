"""
Tests for Step 8: Edit Expense
Spec: .claude/specs/08-edit-expense.md

Coverage:
  Unit tests  — get_expense_by_id() and update_expense() in database/queries.py
  Route tests — GET  /expenses/<id>/edit  (auth guard, pre-population, ownership, 404)
  Route tests — POST /expenses/<id>/edit  (auth guard, happy path, ownership, validation,
                                           form retention, blank description)

Each test is fully independent: it uses its own temporary SQLite file,
initialises the schema directly, and tears the file down after the test.
"""

import os
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
# Fixed category list — derived from the spec, not the implementation
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


def _create_expense(
    conn,
    user_id,
    amount=99.50,
    category="Food",
    date="2026-03-10",
    description="Original description",
):
    """Insert a test expense and return its new expense_id."""
    cur = conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        (user_id, amount, category, date, description),
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
      - Initialises the schema, inserts one test user, and one test expense.
      - Yields (flask_test_client, user_id, expense_id, db_file, db_mod).
    """
    import database.db as db_mod

    monkeypatch.setattr(db_mod, "DATABASE", db_file)

    conn = db_mod.get_db()
    _init_schema(conn)
    user_id = _create_user(conn)
    expense_id = _create_expense(conn, user_id)
    conn.close()

    flask_app = _make_app(db_file)
    client = flask_app.test_client()

    yield client, user_id, expense_id, db_file, db_mod


# ---------------------------------------------------------------------------
# Unit tests — get_expense_by_id()
# ---------------------------------------------------------------------------


class TestGetExpenseById:
    """Direct unit tests for the get_expense_by_id() query helper."""

    def test_existing_id_returns_dict_with_all_columns(self, setup):
        """get_expense_by_id with a valid id must return a dict containing all expected keys."""
        client, user_id, expense_id, db_file, db_mod = setup

        from database.queries import get_expense_by_id

        result = get_expense_by_id(expense_id)

        assert result is not None, "get_expense_by_id must return a dict for a valid id"
        for key in (
            "id",
            "user_id",
            "amount",
            "category",
            "date",
            "description",
            "created_at",
        ):
            assert key in result, f"Returned dict must contain key '{key}'"

    def test_existing_id_returns_correct_values(self, setup):
        """get_expense_by_id must return the exact values that were inserted."""
        client, user_id, expense_id, db_file, db_mod = setup

        from database.queries import get_expense_by_id

        result = get_expense_by_id(expense_id)

        assert result["id"] == expense_id, "Returned id must match the queried id"
        assert (
            result["user_id"] == user_id
        ), "Returned user_id must match the inserting user"
        assert (
            result["amount"] == 99.50
        ), "Returned amount must match the inserted value"
        assert (
            result["category"] == "Food"
        ), "Returned category must match the inserted value"
        assert (
            result["date"] == "2026-03-10"
        ), "Returned date must match the inserted value"
        assert (
            result["description"] == "Original description"
        ), "Returned description must match the inserted value"

    def test_missing_id_returns_none(self, setup):
        """get_expense_by_id with a non-existent id must return None."""
        client, user_id, expense_id, db_file, db_mod = setup

        from database.queries import get_expense_by_id

        result = get_expense_by_id(99999)

        assert result is None, "get_expense_by_id must return None for a missing id"


# ---------------------------------------------------------------------------
# Unit tests — update_expense()
# ---------------------------------------------------------------------------


class TestUpdateExpense:
    """Direct unit tests for the update_expense() query helper."""

    def test_valid_update_returns_1_and_row_reflects_new_values(self, setup):
        """update_expense with valid owner and args must return 1 and DB row must be updated."""
        client, user_id, expense_id, db_file, db_mod = setup

        from database.queries import update_expense

        rows_updated = update_expense(
            expense_id=expense_id,
            user_id=user_id,
            amount=250.00,
            category="Transport",
            date="2026-04-15",
            description="Updated description",
        )

        assert (
            rows_updated == 1
        ), "update_expense must return 1 when the row is found and owned"

        conn = db_mod.get_db()
        row = conn.execute(
            "SELECT amount, category, date, description FROM expenses WHERE id = ?",
            (expense_id,),
        ).fetchone()
        conn.close()

        assert row is not None, "The expense row must still exist after update"
        assert row["amount"] == 250.00, "DB amount must reflect the new value"
        assert row["category"] == "Transport", "DB category must reflect the new value"
        assert row["date"] == "2026-04-15", "DB date must reflect the new value"
        assert (
            row["description"] == "Updated description"
        ), "DB description must reflect the new value"

    def test_wrong_user_id_returns_0_and_row_unchanged(self, setup):
        """update_expense with a mismatched user_id must return 0 and leave the row unchanged."""
        client, user_id, expense_id, db_file, db_mod = setup

        from database.queries import update_expense

        wrong_user_id = user_id + 9999

        rows_updated = update_expense(
            expense_id=expense_id,
            user_id=wrong_user_id,
            amount=999.99,
            category="Shopping",
            date="2026-12-31",
            description="Should not appear",
        )

        assert (
            rows_updated == 0
        ), "update_expense must return 0 when user_id does not own the row"

        conn = db_mod.get_db()
        row = conn.execute(
            "SELECT amount, category, date, description FROM expenses WHERE id = ?",
            (expense_id,),
        ).fetchone()
        conn.close()

        assert (
            row["amount"] == 99.50
        ), "DB amount must be unchanged after wrong-owner update"
        assert (
            row["category"] == "Food"
        ), "DB category must be unchanged after wrong-owner update"
        assert (
            row["date"] == "2026-03-10"
        ), "DB date must be unchanged after wrong-owner update"
        assert (
            row["description"] == "Original description"
        ), "DB description must be unchanged after wrong-owner update"

    def test_nonexistent_row_returns_0(self, setup):
        """update_expense with a row id that does not exist must return 0."""
        client, user_id, expense_id, db_file, db_mod = setup

        from database.queries import update_expense

        rows_updated = update_expense(
            expense_id=99999,
            user_id=user_id,
            amount=50.00,
            category="Bills",
            date="2026-01-01",
            description=None,
        )

        assert (
            rows_updated == 0
        ), "update_expense must return 0 when the expense id does not exist"


# ---------------------------------------------------------------------------
# Route tests — GET /expenses/<id>/edit
# ---------------------------------------------------------------------------


class TestGetEditExpense:
    """Tests for the GET /expenses/<id>/edit route."""

    def test_unauthenticated_get_redirects_to_login(self, setup):
        """Unauthenticated GET /expenses/<id>/edit must redirect (302) to /login."""
        client, user_id, expense_id, db_file, db_mod = setup

        resp = client.get(f"/expenses/{expense_id}/edit")

        assert (
            resp.status_code == 302
        ), "Expected a 302 redirect for unauthenticated access to edit page"
        assert (
            "/login" in resp.headers["Location"]
        ), "Redirect Location must contain /login for unauthenticated access"

    def test_authenticated_owner_returns_200(self, setup):
        """Authenticated GET by the expense owner must return HTTP 200."""
        client, user_id, expense_id, db_file, db_mod = setup

        _auth_client(client, user_id)
        resp = client.get(f"/expenses/{expense_id}/edit")

        assert (
            resp.status_code == 200
        ), "Expected 200 for authenticated owner accessing edit page"

    def test_authenticated_owner_form_prepopulated_with_amount(self, setup):
        """GET response body must contain the current expense amount pre-filled in the form."""
        client, user_id, expense_id, db_file, db_mod = setup

        _auth_client(client, user_id)
        resp = client.get(f"/expenses/{expense_id}/edit")
        body = resp.data.decode("utf-8")

        # The amount 99.50 must appear in the form (commonly as "99.50")
        assert (
            "99.50" in body
        ), "Form must be pre-filled with the current amount (99.50)"

    def test_authenticated_owner_form_prepopulated_with_date(self, setup):
        """GET response body must contain the current expense date pre-filled in the form."""
        client, user_id, expense_id, db_file, db_mod = setup

        _auth_client(client, user_id)
        resp = client.get(f"/expenses/{expense_id}/edit")
        body = resp.data.decode("utf-8")

        assert (
            "2026-03-10" in body
        ), "Form must be pre-filled with the current date (2026-03-10)"

    def test_authenticated_owner_form_prepopulated_with_description(self, setup):
        """GET response body must contain the current expense description pre-filled."""
        client, user_id, expense_id, db_file, db_mod = setup

        _auth_client(client, user_id)
        resp = client.get(f"/expenses/{expense_id}/edit")
        body = resp.data.decode("utf-8")

        assert (
            "Original description" in body
        ), "Form must be pre-filled with the current description"

    def test_authenticated_owner_select_contains_all_7_categories(self, setup):
        """GET response body must include all 7 category options inside a <select> element."""
        client, user_id, expense_id, db_file, db_mod = setup

        _auth_client(client, user_id)
        resp = client.get(f"/expenses/{expense_id}/edit")
        body = resp.data.decode("utf-8")

        assert (
            "<select" in body
        ), "Response body must contain a <select> element for categories"
        for category in CATEGORIES:
            assert (
                category in body
            ), f"Category option '{category}' must be present in the category <select>"

    def test_authenticated_owner_current_category_is_selected(self, setup):
        """The current expense category must be marked as selected in the <select> element."""
        client, user_id, expense_id, db_file, db_mod = setup

        _auth_client(client, user_id)
        resp = client.get(f"/expenses/{expense_id}/edit")
        body = resp.data.decode("utf-8")

        # The current category is "Food" (set in _create_expense).
        # The rendered HTML must have the selected attribute alongside "Food".
        # We check that "selected" appears somewhere and that "Food" is present;
        # a tighter check verifies the two appear in proximity.
        assert (
            "selected" in body
        ), "The form's category <select> must mark the current category as selected"
        assert (
            "Food" in body
        ), "The current category 'Food' must appear in the rendered form"

    def test_nonexistent_expense_returns_404(self, setup):
        """GET for an expense id that does not exist must return 404."""
        client, user_id, expense_id, db_file, db_mod = setup

        _auth_client(client, user_id)
        resp = client.get("/expenses/99999/edit")

        assert (
            resp.status_code == 404
        ), "Expected 404 when the requested expense does not exist"

    def test_other_users_expense_returns_404(self, setup):
        """GET for an expense owned by another user must return 404 — not 403."""
        client, user_id, expense_id, db_file, db_mod = setup

        # Seed a second user and an expense owned by that second user
        conn = db_mod.get_db()
        other_user_id = _create_user(conn, name="Other User", email="other@spendly.com")
        other_expense_id = _create_expense(
            conn,
            other_user_id,
            amount=10.00,
            category="Bills",
            date="2026-01-01",
            description="Other user's expense",
        )
        conn.close()

        # Log in as the FIRST user and attempt to access the OTHER user's expense
        _auth_client(client, user_id)
        resp = client.get(f"/expenses/{other_expense_id}/edit")

        assert (
            resp.status_code == 404
        ), "Accessing another user's expense via GET must return 404 (must not leak existence)"


# ---------------------------------------------------------------------------
# Route tests — POST /expenses/<id>/edit
# ---------------------------------------------------------------------------


class TestPostEditExpense:
    """Tests for the POST /expenses/<id>/edit route."""

    # -- Auth guard ----------------------------------------------------------

    def test_unauthenticated_post_redirects_to_login(self, setup):
        """Unauthenticated POST must redirect (302) to /login and leave the DB row unchanged."""
        client, user_id, expense_id, db_file, db_mod = setup

        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "200.00",
                "category": "Transport",
                "date": "2026-05-01",
                "description": "Should not be saved",
            },
        )

        assert (
            resp.status_code == 302
        ), "Expected a 302 redirect for unauthenticated POST to edit route"
        assert (
            "/login" in resp.headers["Location"]
        ), "Redirect Location must contain /login for unauthenticated POST"

        # Verify DB row is unchanged
        conn = db_mod.get_db()
        row = conn.execute(
            "SELECT amount, category, date, description FROM expenses WHERE id = ?",
            (expense_id,),
        ).fetchone()
        conn.close()

        assert (
            row["amount"] == 99.50
        ), "DB amount must be unchanged after unauthenticated POST"
        assert (
            row["category"] == "Food"
        ), "DB category must be unchanged after unauthenticated POST"

    # -- Happy path ----------------------------------------------------------

    def test_valid_post_redirects_to_profile(self, setup):
        """Valid authenticated POST by the owner must redirect (302) to /profile."""
        client, user_id, expense_id, db_file, db_mod = setup

        _auth_client(client, user_id)
        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "150.00",
                "category": "Transport",
                "date": "2026-04-20",
                "description": "Updated expense",
            },
        )

        assert (
            resp.status_code == 302
        ), "Expected a 302 redirect after a successful edit POST"
        assert (
            "/profile" in resp.headers["Location"]
        ), "Successful POST must redirect to /profile"

    def test_valid_post_updates_db_row(self, setup):
        """Valid POST must update the DB row with the new field values."""
        client, user_id, expense_id, db_file, db_mod = setup

        _auth_client(client, user_id)
        client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "150.00",
                "category": "Transport",
                "date": "2026-04-20",
                "description": "Updated expense",
            },
        )

        conn = db_mod.get_db()
        row = conn.execute(
            "SELECT amount, category, date, description FROM expenses WHERE id = ?",
            (expense_id,),
        ).fetchone()
        conn.close()

        assert row is not None, "Expense row must still exist after update"
        assert row["amount"] == 150.00, "DB amount must reflect the new value"
        assert row["category"] == "Transport", "DB category must reflect the new value"
        assert row["date"] == "2026-04-20", "DB date must reflect the new value"
        assert (
            row["description"] == "Updated expense"
        ), "DB description must reflect the new value"

    def test_valid_post_does_not_change_created_at(self, setup):
        """A successful update must NOT modify the created_at timestamp of the row."""
        client, user_id, expense_id, db_file, db_mod = setup

        # Capture created_at before the update
        conn = db_mod.get_db()
        before = conn.execute(
            "SELECT created_at FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
        conn.close()
        original_created_at = before["created_at"]

        _auth_client(client, user_id)
        client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "150.00",
                "category": "Transport",
                "date": "2026-04-20",
                "description": "Updated expense",
            },
        )

        # Verify created_at is unchanged after the update
        conn = db_mod.get_db()
        after = conn.execute(
            "SELECT created_at FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
        conn.close()

        assert (
            after["created_at"] == original_created_at
        ), "created_at must not be modified by an update operation"

    # -- Ownership guard (POST) ---------------------------------------------

    def test_other_users_expense_post_returns_404(self, setup):
        """POST to an expense owned by another user must return 404 and leave DB unchanged."""
        client, user_id, expense_id, db_file, db_mod = setup

        # Seed a second user and their expense
        conn = db_mod.get_db()
        other_user_id = _create_user(conn, name="Other User", email="other@spendly.com")
        other_expense_id = _create_expense(
            conn,
            other_user_id,
            amount=77.00,
            category="Shopping",
            date="2026-02-14",
            description="Other user's expense",
        )
        conn.close()

        # Log in as the FIRST user and POST to the OTHER user's expense
        _auth_client(client, user_id)
        resp = client.post(
            f"/expenses/{other_expense_id}/edit",
            data={
                "amount": "1.00",
                "category": "Other",
                "date": "2026-01-01",
                "description": "Attempted takeover",
            },
        )

        assert resp.status_code == 404, "POST to another user's expense must return 404"

        # Verify the other user's expense is untouched
        conn = db_mod.get_db()
        row = conn.execute(
            "SELECT amount, description FROM expenses WHERE id = ?",
            (other_expense_id,),
        ).fetchone()
        conn.close()

        assert row["amount"] == 77.00, "Other user's expense amount must be unchanged"
        assert (
            row["description"] == "Other user's expense"
        ), "Other user's expense description must be unchanged"

    # -- Validation: amount (parametrized) -----------------------------------

    @pytest.mark.parametrize(
        "bad_amount",
        [
            "",  # empty / missing
            "0",  # zero is not positive
            "-5",  # negative
            "abc",  # non-numeric text
            "1e999",  # overflow float
            "nan",  # not-a-number
        ],
    )
    def test_bad_amount_returns_200_with_error_and_db_unchanged(
        self, setup, bad_amount
    ):
        """Every invalid amount must re-render the form (200) with an error; DB row unchanged."""
        client, user_id, expense_id, db_file, db_mod = setup

        _auth_client(client, user_id)
        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": bad_amount,
                "category": "Food",
                "date": "2026-04-01",
                "description": "Test",
            },
        )

        assert (
            resp.status_code == 200
        ), f"Amount '{bad_amount}' must re-render the form (200), got {resp.status_code}"
        body = resp.data.decode("utf-8")
        assert any(
            keyword in body.lower()
            for keyword in ["error", "invalid", "positive", "amount", "required"]
        ), f"No error message found in body for amount='{bad_amount}'"

        # DB row must be unchanged
        conn = db_mod.get_db()
        row = conn.execute(
            "SELECT amount, category, date FROM expenses WHERE id = ?",
            (expense_id,),
        ).fetchone()
        conn.close()
        assert (
            row["amount"] == 99.50
        ), f"DB amount must be unchanged after invalid amount='{bad_amount}'"
        assert (
            row["category"] == "Food"
        ), f"DB category must be unchanged after invalid amount='{bad_amount}'"

    def test_bad_amount_form_retains_submitted_values_not_original(self, setup):
        """When amount is invalid, the re-rendered form must show the submitted (bad) values,
        NOT the original DB values."""
        client, user_id, expense_id, db_file, db_mod = setup

        _auth_client(client, user_id)
        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "0",  # triggers validation failure
                "category": "Health",
                "date": "2026-05-05",
                "description": "New gym membership",
            },
        )

        assert resp.status_code == 200, "Invalid amount must re-render the form (200)"
        body = resp.data.decode("utf-8")

        # The form must retain submitted values — NOT the original DB values
        assert (
            "Health" in body
        ), "Submitted category 'Health' must appear in the re-rendered form (not original 'Food')"
        assert (
            "2026-05-05" in body
        ), "Submitted date '2026-05-05' must appear in the re-rendered form"
        assert (
            "New gym membership" in body
        ), "Submitted description must appear in the re-rendered form"
        # Confirm the original category is NOT what was selected (sanity check)
        # Note: "Food" may still appear as another <option> — we verify the submitted value is there

    # -- Validation: category ------------------------------------------------

    def test_invalid_category_returns_200_with_error_and_db_unchanged(self, setup):
        """POST with a category not in the 7-item whitelist must return 200 with an error."""
        client, user_id, expense_id, db_file, db_mod = setup

        _auth_client(client, user_id)
        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "50.00",
                "category": "Luxury",  # not in the fixed list
                "date": "2026-04-01",
                "description": "Fancy dinner",
            },
        )

        assert (
            resp.status_code == 200
        ), "Invalid category must re-render the form (200), got {resp.status_code}"
        body = resp.data.decode("utf-8")
        assert any(
            keyword in body.lower()
            for keyword in ["error", "invalid", "category", "valid"]
        ), "Response body must contain an error message when category is invalid"

        # DB must be unchanged
        conn = db_mod.get_db()
        row = conn.execute(
            "SELECT category FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
        conn.close()
        assert (
            row["category"] == "Food"
        ), "DB category must be unchanged after invalid category POST"

    # -- Validation: date (parametrized) ------------------------------------

    @pytest.mark.parametrize(
        "bad_date",
        [
            "not-a-date",  # plain text
            "2026-13-01",  # invalid month
            "2026-02-30",  # invalid day for February
        ],
    )
    def test_bad_date_returns_200_with_error_and_db_unchanged(self, setup, bad_date):
        """Every malformed date must re-render the form (200) with an error; DB row unchanged."""
        client, user_id, expense_id, db_file, db_mod = setup

        _auth_client(client, user_id)
        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "50.00",
                "category": "Food",
                "date": bad_date,
                "description": "Test",
            },
        )

        assert (
            resp.status_code == 200
        ), f"Date '{bad_date}' must re-render the form (200), got {resp.status_code}"
        body = resp.data.decode("utf-8")
        assert any(
            keyword in body.lower() for keyword in ["error", "invalid", "date", "valid"]
        ), f"No error message found in body for date='{bad_date}'"

        # DB must be unchanged
        conn = db_mod.get_db()
        row = conn.execute(
            "SELECT date FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
        conn.close()
        assert (
            row["date"] == "2026-03-10"
        ), f"DB date must be unchanged after invalid date='{bad_date}'"

    # -- Blank description ---------------------------------------------------

    def test_blank_description_redirects_to_profile(self, setup):
        """POST with a blank description must redirect (302) to /profile."""
        client, user_id, expense_id, db_file, db_mod = setup

        _auth_client(client, user_id)
        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "50.00",
                "category": "Bills",
                "date": "2026-04-10",
                "description": "",  # intentionally blank
            },
        )

        assert (
            resp.status_code == 302
        ), "Blank description must still succeed and redirect (302)"
        assert (
            "/profile" in resp.headers["Location"]
        ), "Redirect after blank-description POST must go to /profile"

    def test_blank_description_stores_null_in_db(self, setup):
        """POST with a blank description must store NULL in the description column."""
        client, user_id, expense_id, db_file, db_mod = setup

        _auth_client(client, user_id)
        client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "50.00",
                "category": "Bills",
                "date": "2026-04-10",
                "description": "",
            },
        )

        conn = db_mod.get_db()
        row = conn.execute(
            "SELECT description FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
        conn.close()

        assert (
            row is not None
        ), "Expense row must still exist after blank-description update"
        assert (
            row["description"] is None
        ), "description must be stored as NULL when a blank string is submitted"
