# Spec: Edit Expense

## Overview
Step 8 lets a logged-in user update an existing expense through a dedicated form
page at `/expenses/<id>/edit`. The route already exists as a stub; this step
upgrades it to a full GET + POST handler that loads the existing row, renders
the form pre-populated with current values, validates a submission, persists
the change, and redirects back to the profile page on success. A user may only
edit expenses they own — attempts to edit another user's expense return 404.
Reusable `get_expense_by_id` and `update_expense` helpers are added to
`database/queries.py`, and an "Edit" link is added to each row of the recent
transactions table on the profile page so users can reach the form.

## Depends on
- Step 1: Database setup (`expenses` table exists with all required columns)
- Step 3: Login / Logout (`session["user_id"]` is set and checked)
- Step 4 / 5: Profile page exists and is the natural redirect target after saving
- Step 7: Add Expense (validation rules and the 7-category whitelist are reused here)

## Routes
- `GET /expenses/<int:id>/edit` — render the edit-expense form pre-populated with the existing row — logged-in only
- `POST /expenses/<int:id>/edit` — validate the submission and update the row — logged-in only

## Database changes
No database changes. The `expenses` table already has all required columns:
`id`, `user_id`, `amount`, `category`, `date`, `description`, `created_at`.

## Templates
- **Create**: `templates/edit_expense.html`
  - Extends `base.html`
  - Form with `method="POST"` and `action="{{ url_for('edit_expense', id=expense.id) }}"`
  - Fields are the same as `add_expense.html`, pre-filled from `form` (a dict identical in shape to add-expense):
    - `amount` — number input, `step="0.01"`, `min="0.01"`, required
    - `category` — `<select>` with the 7 fixed categories, current value selected
    - `date` — `<input type="date">`, required
    - `description` — text input, optional, `maxlength="200"`
  - Submit button labelled "Save Changes"
  - Cancel link back to `/profile`
  - Display flash error message when validation fails, re-populating previous values

- **Modify**: `templates/profile.html`
  - Add an "Actions" column (or compact icon link) to the Recent Transactions table
  - For each row, render a link to `{{ url_for('edit_expense', id=txn.id) }}` (requires `id` to be present on each transaction dict — see Files to change)

## Files to change
- `app.py` — replace the GET-only placeholder at `/expenses/<int:id>/edit` with a GET+POST handler:
  - Both verbs: redirect to `/login` if not authenticated
  - GET: load the expense via `get_expense_by_id`; if missing OR `user_id` doesn't match the session, return 404; render `edit_expense.html` with values pre-filled
  - POST: read form fields, validate (same rules as add-expense), call `update_expense`, redirect to `/profile` on success
- `database/queries.py`:
  - Add `get_expense_by_id(expense_id)` returning the row as a dict (or `None`)
  - Add `update_expense(expense_id, user_id, amount, category, date, description)` returning the number of rows updated (so the route can detect "not yours / not found" cases atomically)
  - Modify `get_recent_transactions` to include `id` in each returned dict (so the profile page can link to the edit route)
- `templates/profile.html` — render the per-row Edit link (see Templates)

## Files to create
- `templates/edit_expense.html` — the edit-expense form template
- `tests/test_08_edit_expense.py` — pytest suite (see Tests to write)

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never string-format values into SQL
- Foreign keys PRAGMA must be enabled on every connection (already done in `get_db()`)
- Passwords hashed with werkzeug (no change here — listed for project-wide compliance)
- Unauthenticated access to GET and POST `/expenses/<id>/edit` must redirect to `/login`
- **Ownership check** — a user may only edit their own expense:
  - If the expense does not exist → 404
  - If the expense exists but `expense.user_id != session["user_id"]` → 404 (do not leak existence with 403)
  - The ownership check must run on BOTH GET and POST, BEFORE any DB write
- The `UPDATE` statement must include `WHERE id = ? AND user_id = ?` as a defence-in-depth guard, even though the route already checks ownership
- Validation rules for POST (identical to Step 7 — reuse the same constants and helpers where reasonable):
  - `amount`: required, must be a positive finite number greater than 0 (parse with `float()`; reject `nan`/`inf`)
  - `category`: required, must be one of the 7 fixed categories (reuse `EXPENSE_CATEGORIES` from `app.py`)
  - `date`: required, must be a valid `YYYY-MM-DD` date (parse with `datetime.strptime`)
  - `description`: optional; strip whitespace; store `None` if blank
  - On any validation error, re-render the form with the error message AND the previously submitted values pre-filled (NOT the original DB values)
- After a successful update, redirect to `url_for("profile")` — do NOT render the form again
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline styles
- Currency must always display as ₹ — never £ or $
- Do not change the `expenses.created_at` value when updating a row

## Tests to write
File: `tests/test_08_edit_expense.py`

### Unit tests
| Function | Input | Expected output |
|---|---|---|
| `get_expense_by_id` | id of an existing expense | dict with all columns including `id`, `user_id`, `amount`, `category`, `date`, `description` |
| `get_expense_by_id` | id that does not exist | `None` |
| `update_expense` | valid args for an existing row owned by `user_id` | returns `1`; DB row reflects new values |
| `update_expense` | row exists but `user_id` doesn't match | returns `0`; DB row unchanged |
| `update_expense` | row does not exist | returns `0` |

### Route tests
`GET /expenses/<id>/edit` — unauthenticated:
- Redirects to `/login` (302)

`GET /expenses/<id>/edit` — authenticated, expense exists and belongs to user:
- Returns 200
- Response body contains form pre-filled with the existing amount, category, date, description
- Response body contains the category `<select>` with all 7 options, current category selected

`GET /expenses/<id>/edit` — authenticated, expense does not exist:
- Returns 404

`GET /expenses/<id>/edit` — authenticated, expense exists but belongs to another user:
- Returns 404 (must not leak that the expense exists)

`POST /expenses/<id>/edit` — unauthenticated:
- Redirects to `/login` (302)
- DB row unchanged

`POST /expenses/<id>/edit` — authenticated, valid data, owns the row:
- Redirects to `/profile` (302)
- DB row reflects the new values
- `created_at` is unchanged

`POST /expenses/<id>/edit` — authenticated, expense belongs to another user:
- Returns 404
- DB row unchanged

`POST /expenses/<id>/edit` — authenticated, missing/zero/non-numeric/overflow amount:
- Returns 200 (re-renders form)
- Response body contains an error message
- DB row unchanged
- Form retains the previously submitted (invalid) values, not the original DB values

`POST /expenses/<id>/edit` — authenticated, invalid category (not in fixed list):
- Returns 200 (re-renders form)
- Response body contains an error message
- DB row unchanged

`POST /expenses/<id>/edit` — authenticated, invalid date string:
- Returns 200 (re-renders form)
- Response body contains an error message
- DB row unchanged

`POST /expenses/<id>/edit` — authenticated, blank description:
- Redirects to `/profile` (302)
- DB row updated with `description = NULL`

## Definition of done
- [ ] Visiting `/expenses/<id>/edit` while logged out redirects to `/login`
- [ ] Visiting `/expenses/<id>/edit` for an expense you own shows a form pre-filled with the current values
- [ ] Visiting `/expenses/<id>/edit` for an expense that doesn't exist returns 404
- [ ] Visiting `/expenses/<id>/edit` for another user's expense returns 404 (no information leak)
- [ ] Submitting valid changes redirects to `/profile` and the updated values appear in the transaction list
- [ ] `created_at` of the edited row is unchanged after a successful update
- [ ] Submitting with a missing, zero, non-numeric, or overflow amount re-renders the form with an error and the submitted (invalid) values retained
- [ ] Submitting with an invalid category re-renders the form with an error
- [ ] Submitting with an invalid date re-renders the form with an error
- [ ] Submitting with a blank description saves the expense with `description = NULL`
- [ ] Each row in the profile transaction table has an Edit link pointing to the correct expense
- [ ] Attempting to POST to another user's expense returns 404 and does not modify the database
- [ ] All tests in `tests/test_08_edit_expense.py` pass
