import sqlite3
from database.db import get_db


def insert_expense(user_id, amount, category, date, description):
    """
    Inserts a new expense for a user.
    Returns the id of the newly inserted row.
    `description` may be None (stored as NULL).
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO expenses (user_id, amount, category, date, description)
        VALUES (?, ?, ?, ?, ?)
    """,
        (user_id, amount, category, date, description),
    )
    conn.commit()
    expense_id = cursor.lastrowid
    conn.close()
    return expense_id


def get_expense_by_id(expense_id):
    """
    Fetch a single expense row by id.
    Returns a dict with id, user_id, amount, category, date, description, created_at,
    or None if no row exists.
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, user_id, amount, category, date, description, created_at
        FROM expenses
        WHERE id = ?
    """,
        (expense_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "amount": row["amount"],
        "category": row["category"],
        "date": row["date"],
        "description": row["description"],
        "created_at": row["created_at"],
    }


def update_expense(expense_id, user_id, amount, category, date, description):
    """
    Update an existing expense owned by `user_id`.
    The user_id guard in the WHERE clause is defence-in-depth — the route also
    performs an ownership check before calling this.
    `description` may be None (stored as NULL).
    Returns the number of rows updated (0 if the row doesn't exist or isn't owned).
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE expenses
           SET amount = ?, category = ?, date = ?, description = ?
         WHERE id = ? AND user_id = ?
    """,
        (amount, category, date, description, expense_id, user_id),
    )
    conn.commit()
    rowcount = cursor.rowcount
    conn.close()
    return rowcount


def delete_expense_by_id(expense_id, user_id):
    """
    Delete an expense owned by `user_id`.
    The user_id guard in the WHERE clause is defence-in-depth — the route also
    performs an ownership check before calling this.
    Returns the number of rows deleted (0 if the row doesn't exist or isn't owned).
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        DELETE FROM expenses
         WHERE id = ? AND user_id = ?
    """,
        (expense_id, user_id),
    )
    conn.commit()
    rowcount = cursor.rowcount
    conn.close()
    return rowcount


def get_user_profile(user_id):
    """
    Fetch user profile data by ID.
    Returns dict with name, email, member_since (formatted as "Month YYYY") or None if not found.
    """
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, name, email, created_at
        FROM users
        WHERE id = ?
    """,
        (user_id,),
    )

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    # Format created_at as "Month YYYY"
    member_since = "Unknown"
    if row["created_at"]:
        # created_at is like "2026-04-01 12:34:56"
        date_part = row["created_at"].split()[0]  # "2026-04-01"
        try:
            from datetime import datetime

            dt = datetime.strptime(date_part, "%Y-%m-%d")
            member_since = dt.strftime("%B %Y")  # "April 2026"
        except (ValueError, IndexError):
            member_since = "Unknown"

    return {"name": row["name"], "email": row["email"], "member_since": member_since}


def get_summary_stats(user_id, date_from=None, date_to=None):
    """
    Fetch summary statistics for a user.
    Returns dict with total_spent, transaction_count, top_category.
    Returns zeros/empty if user has no expenses.
    """
    conn = get_db()
    cursor = conn.cursor()

    # date_filter is a hard-coded literal, not user input; values flow through params_base
    date_filter = ""
    params_base = [user_id]
    if date_from and date_to:
        date_filter = "AND date BETWEEN ? AND ?"
        params_base = [user_id, date_from, date_to]

    # Get total spent and transaction count
    cursor.execute(
        f"""
        SELECT
            COALESCE(SUM(amount), 0) as total_spent,
            COUNT(*) as transaction_count
        FROM expenses
        WHERE user_id = ? {date_filter}
    """,
        params_base,
    )

    row = cursor.fetchone()
    total_spent = row["total_spent"]
    transaction_count = row["transaction_count"]

    # Get top category (category with highest total amount)
    cursor.execute(
        f"""
        SELECT category
        FROM expenses
        WHERE user_id = ? {date_filter}
        GROUP BY category
        ORDER BY SUM(amount) DESC
        LIMIT 1
    """,
        params_base,
    )

    top_row = cursor.fetchone()
    top_category = top_row["category"] if top_row else "—"

    conn.close()

    return {
        "total_spent": total_spent,
        "transaction_count": transaction_count,
        "top_category": top_category,
    }


def get_recent_transactions(user_id, limit=10, date_from=None, date_to=None):
    """
    Fetch recent transactions for a user, ordered newest-first.
    Returns list of dicts with date, description, category, amount.
    Returns empty list if user has no expenses.
    """
    conn = get_db()
    cursor = conn.cursor()

    # date_filter is a hard-coded literal, not user input; values flow through params
    date_filter = ""
    params = [user_id]
    if date_from and date_to:
        date_filter = "AND date BETWEEN ? AND ?"
        params = [user_id, date_from, date_to]
    params.append(limit)

    cursor.execute(
        f"""
        SELECT id, date, description, category, amount
        FROM expenses
        WHERE user_id = ? {date_filter}
        ORDER BY date DESC, created_at DESC
        LIMIT ?
    """,
        params,
    )

    transactions = []
    for row in cursor.fetchall():
        transactions.append(
            {
                "id": row["id"],
                "date": row["date"],
                "description": row["description"],
                "category": row["category"],
                "amount": row["amount"],
            }
        )

    conn.close()
    return transactions


def get_category_breakdown(user_id, date_from=None, date_to=None):
    """
    Fetch category breakdown for a user.
    Returns list of dicts with name, amount, pct (percentage, integer).
    Percentages sum to 100; largest category absorbs rounding remainder.
    Returns empty list if user has no expenses.
    """
    conn = get_db()
    cursor = conn.cursor()

    # date_filter is a hard-coded literal, not user input; values flow through params_base
    date_filter = ""
    params_base = [user_id]
    if date_from and date_to:
        date_filter = "AND date BETWEEN ? AND ?"
        params_base = [user_id, date_from, date_to]

    # Single query: CTE computes the overall total; main SELECT does per-category breakdown
    cursor.execute(
        f"""
        WITH totals AS (
            SELECT COALESCE(SUM(amount), 0) as grand_total
            FROM expenses
            WHERE user_id = ? {date_filter}
        )
        SELECT
            category,
            SUM(amount) as amount,
            (SELECT grand_total FROM totals) as grand_total
        FROM expenses
        WHERE user_id = ? {date_filter}
        GROUP BY category
        ORDER BY amount DESC
    """,
        params_base + params_base,
    )

    rows = cursor.fetchall()
    conn.close()

    if not rows or rows[0]["grand_total"] == 0:
        return []

    total = rows[0]["grand_total"]
    categories = []
    raw_percentages = []

    for row in rows:
        categories.append({"name": row["category"], "amount": row["amount"]})
        raw_pct = (row["amount"] / total) * 100
        raw_percentages.append((raw_pct, len(categories) - 1))

    # Calculate integer percentages, largest absorbs remainder
    rounded_pcts = [int(raw_pct) for raw_pct, _ in raw_percentages]
    remainder = 100 - sum(rounded_pcts)

    # Add remainder to the largest category (first one, since ordered by amount DESC)
    if remainder != 0 and categories:
        rounded_pcts[0] += remainder

    # Add percentage to each category
    for i, cat in enumerate(categories):
        cat["pct"] = rounded_pcts[i]

    return categories
