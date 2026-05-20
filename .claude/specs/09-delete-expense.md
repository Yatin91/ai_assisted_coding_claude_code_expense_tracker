# Spec: Delete Expense

## Overview
Step 9 lets a logged-in user permanently delete one of their own expenses
directly from the profile page. The route currently exists as a stub
(`GET /expenses/<id>/delete` returning a placeholder string); this step
upgrades it to a **`POST`-only** handler that deletes the row and redirects
back to `/profile` on success. A small inline form (styled as a "Delete" link
next to the existing "Edit" link in the Actions column) is added to each row
of the Recent Transactions table, with a JavaScript `confirm()` prompt so a
single misclick can't destroy data. As with edit-expense, ownership is
enforced — attempts to delete another user's row return 404.

## Depends on
- Step 1: Database setup (`expenses` table exists)
- Step 3: Login / Logout (`session["user_id"]` is set and checked)
- Step 4 / 5: Profile page exists and is the natural redirect target after deletion
- Step 7: Add Expense (the per-row layout in the transactions table is from this work)
- Step 8: Edit Expense (Actions column and the `id` field on each transaction were introduced here — we extend the same column)

## Routes
- `POST /expenses/<int:id>/delete` — delete the expense and redirect to `/profile` — logged-in only

Note: the existing stub at `GET /expenses/<int:id>/delete` is **replaced** by the POST handler. Deletes must not be reachable via GET — GET links are followed by browser prefetch / link-preview crawlers / accidental clicks, any of which would silently destroy data.

## Database changes
No database changes. The `expenses` table already has all required columns.

## Templates
- **Create**: none
- **Modify**: `templates/profile.html`
  - Inside the Actions cell of each transaction row, add a small `<form method="POST" action="{{ url_for('delete_expense', id=txn.id) }}">` containing a single `<button type="submit">Delete</button>` styled as a link (same look as the existing `.txn-action` Edit link, but in a "danger" colour)
  - The form has `onsubmit="return confirm('Delete this expense? This cannot be undone.');"` so a misclick is recoverable
  - Edit and Delete should sit side-by-side in the same cell (small flex/inline gap, no extra column)

## Files to change
- `app.py` — replace the `GET /expenses/<int:id>/delete` stub with a `methods=["POST"]` handler:
  - If not authenticated → redirect to `/login`
  - Load the expense via `get_expense_by_id`; if missing OR `user_id` doesn't match the session → `abort(404)`
  - Call `delete_expense_by_id(id, user_id)` (parameterised, defence-in-depth WHERE clause)
  - Flash a success message and redirect to `/profile`
  - Import the new helper from `database/queries`
- `database/queries.py` — add `delete_expense_by_id(expense_id, user_id)`:
  - `DELETE FROM expenses WHERE id = ? AND user_id = ?` (parameterised; the `user_id` predicate is defence-in-depth even though the route already checks ownership)
  - Returns the number of rows deleted (so the caller can detect not-yours / not-found cases)
- `templates/profile.html` — add the Delete form/button to the Actions column (see Templates)
- `static/css/style.css` — add a `.txn-action--danger` (or similar) modifier styling the Delete button as a link in `var(--danger)` / a red-leaning CSS variable; if no danger variable exists yet, add one (e.g. `--danger: #c0392b`) in the same `:root` block where `--accent` lives

## Files to create
- `tests/test_09-delete-expense.py` — pytest suite (see Tests to write below)

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never string-format values into SQL
- Foreign keys PRAGMA must be enabled on every connection (already done in `get_db()`)
- Passwords hashed with werkzeug (no change here — listed for project-wide compliance)
- **The delete route must be POST-only.** A `GET` request to `/expenses/<id>/delete` must NOT delete the row (Flask returns 405 automatically when the route only declares POST — leave that default behaviour in place; do not implement a GET handler at all)
- Unauthenticated `POST` must redirect to `/login` (302) and **must not** touch the database
- Ownership check (same pattern as Step 8):
  - Expense doesn't exist → 404
  - Expense exists but `expense.user_id != session["user_id"]` → 404 (do NOT use 403 — would leak existence)
  - Run the ownership check **before** the DELETE
- The DELETE statement must include `WHERE id = ? AND user_id = ?` as defence-in-depth even though the route already checks ownership
- After a successful delete, redirect to `url_for("profile")` with a success flash — do NOT render a page directly
- Use a JavaScript `confirm()` prompt on the Delete form's `onsubmit` so a misclick is recoverable. If the user cancels the confirm, the form must NOT submit
- Use CSS variables for the danger colour — never hardcode hex values in the rule body
- All templates extend `base.html`; no inline `<style>` tags

## Tests to write
File: `tests/test_09-delete-expense.py`

### Unit tests
| Function | Input | Expected output |
|---|---|---|
| `delete_expense_by_id` | valid id owned by `user_id` | returns `1`; row is gone from the DB |
| `delete_expense_by_id` | id exists but `user_id` doesn't match | returns `0`; row is still in the DB |
| `delete_expense_by_id` | id does not exist | returns `0` |

### Route tests
`POST /expenses/<id>/delete` — unauthenticated:
- Returns 302 to `/login`
- DB row unchanged

`GET /expenses/<id>/delete` — authenticated, owner:
- Returns 405 (method not allowed) — verifies the route is POST-only
- DB row unchanged

`POST /expenses/<id>/delete` — authenticated, owner, expense exists:
- Returns 302 to `/profile`
- DB row is gone

`POST /expenses/<id>/delete` — authenticated, expense does not exist:
- Returns 404
- (Nothing to delete; nothing to assert about DB state beyond "no rows deleted")

`POST /expenses/<id>/delete` — authenticated, expense belongs to another user:
- Returns 404 (must NOT leak existence with 403)
- The other user's DB row is still present

`POST /expenses/<id>/delete` — authenticated, deleting one of many own expenses:
- The target row is gone; the user's other rows are untouched

### Profile page assertions (regression check)
- `GET /profile` for an authenticated user with at least one transaction returns 200 and the response body contains a `<form>` whose `action` is `/expenses/<id>/delete` and method is `POST` for the seeded expense's id

## Definition of done
- [ ] `GET /expenses/<id>/delete` returns 405 (route is POST-only — no destructive GET)
- [ ] Posting to `/expenses/<id>/delete` while logged out redirects to `/login` and does not delete the row
- [ ] Posting to `/expenses/<id>/delete` for an expense you own deletes the row and redirects to `/profile`
- [ ] After a successful delete, the row no longer appears in the profile transaction list
- [ ] Other expenses owned by the same user are untouched
- [ ] Posting to `/expenses/<id>/delete` for an expense that does not exist returns 404
- [ ] Posting to `/expenses/<id>/delete` for another user's expense returns 404 (no information leak) and does not delete the row
- [ ] Each row in the profile transactions table has a Delete button next to the Edit link
- [ ] Clicking Delete shows a JavaScript confirmation; cancelling the confirmation does NOT submit the form
- [ ] All tests in `tests/test_09-delete-expense.py` pass
- [ ] Full test suite remains green
