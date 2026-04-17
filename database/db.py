import sqlite3
from werkzeug.security import generate_password_hash

DATABASE = "expense_tracker.db"


def get_db():
    """
    Opens a connection to the SQLite database.
    Sets row_factory for dict-like access and enables foreign keys.
    """
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """
    Creates the users and expenses tables if they don't exist.
    Safe to call multiple times.
    """
    conn = get_db()
    cursor = conn.cursor()

    # Create users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create expenses table
    cursor.execute("""
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
    conn.close()


def seed_db():
    """
    Inserts demo user and sample expenses if they don't already exist.
    Safe to call multiple times without duplicating data.
    """
    conn = get_db()
    cursor = conn.cursor()

    # Check if users table already has data
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] > 0:
        conn.close()
        return

    # Insert demo user
    demo_password_hash = generate_password_hash("demo123")
    cursor.execute("""
        INSERT INTO users (name, email, password_hash)
        VALUES (?, ?, ?)
    """, ("Demo User", "demo@spendly.com", demo_password_hash))

    # Get the demo user's ID
    cursor.execute("SELECT id FROM users WHERE email = ?", ("demo@spendly.com",))
    user_id = cursor.fetchone()[0]

    # Insert 8 sample expenses across different categories
    sample_expenses = [
        (150.50, "Food", "2026-04-01", "Grocery shopping at Walmart"),
        (45.00, "Transport", "2026-04-02", "Uber rides to work"),
        (120.00, "Bills", "2026-04-03", "Electric bill"),
        (35.99, "Health", "2026-04-04", "Pharmacy - vitamins"),
        (65.00, "Entertainment", "2026-04-05", "Movie tickets and popcorn"),
        (200.00, "Shopping", "2026-04-06", "New shoes"),
        (80.75, "Food", "2026-04-07", "Dinner at restaurant"),
        (50.00, "Other", "2026-04-08", "Miscellaneous expenses"),
    ]

    cursor.executemany("""
        INSERT INTO expenses (user_id, amount, category, date, description)
        VALUES (?, ?, ?, ?, ?)
    """, [(user_id, *expense) for expense in sample_expenses])

    conn.commit()
    conn.close()


def create_user(name, email, password):
    """
    Creates a new user with the given name, email, and password.
    Returns the user ID on success.
    Raises sqlite3.IntegrityError if email already exists.
    """
    conn = get_db()
    cursor = conn.cursor()

    password_hash = generate_password_hash(password)
    cursor.execute("""
        INSERT INTO users (name, email, password_hash)
        VALUES (?, ?, ?)
    """, (name, email, password_hash))

    conn.commit()
    user_id = cursor.lastrowid
    conn.close()
    return user_id


def get_user_by_email(email):
    """
    Fetches a user by email address.
    Returns a dict-like Row object or None if not found.
    """
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, name, email, password_hash, created_at
        FROM users
        WHERE email = ?
    """, (email,))

    user = cursor.fetchone()
    conn.close()
    return user


def get_user_by_id(user_id):
    """
    Fetches a user by ID.
    Returns a dict-like Row object or None if not found.
    """
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, name, email, created_at
        FROM users
        WHERE id = ?
    """, (user_id,))

    user = cursor.fetchone()
    conn.close()
    return user


def verify_password(password, password_hash):
    """
    Verifies a password against a stored hash.
    Returns True if valid, False otherwise.
    """
    from werkzeug.security import check_password_hash
    return check_password_hash(password_hash, password)


def get_expense_stats(user_id):
    """
    Fetches expense statistics for a user: total expenses, transaction count.
    Returns a dict with total_expenses and transaction_count.
    """
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            COALESCE(SUM(amount), 0) as total_expenses,
            COUNT(*) as transaction_count
        FROM expenses
        WHERE user_id = ?
    """, (user_id,))

    row = cursor.fetchone()
    conn.close()

    return {
        "total_expenses": row["total_expenses"],
        "transaction_count": row["transaction_count"]
    }


def get_top_category(user_id):
    """
    Fetches the top spending category for a user.
    Returns a dict with category name and amount.
    """
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT category, SUM(amount) as amount
        FROM expenses
        WHERE user_id = ?
        GROUP BY category
        ORDER BY amount DESC
        LIMIT 1
    """, (user_id,))

    row = cursor.fetchone()
    conn.close()

    if row:
        return {"name": row["category"], "amount": row["amount"]}
    return None


def get_recent_transactions(user_id, limit=5):
    """
    Fetches the most recent transactions for a user.
    Returns a list of dicts with date, description, category, and amount.
    """
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT date, description, category, amount
        FROM expenses
        WHERE user_id = ?
        ORDER BY date DESC, id DESC
        LIMIT ?
    """, (user_id, limit))

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "date": row["date"],
            "description": row["description"],
            "category": row["category"],
            "amount": row["amount"]
        }
        for row in rows
    ]


def get_category_breakdown(user_id):
    """
    Fetches spending breakdown by category for a user.
    Returns a list of dicts with name, amount, percentage, and color.
    """
    conn = get_db()
    cursor = conn.cursor()

    # Get total expenses
    cursor.execute("""
        SELECT COALESCE(SUM(amount), 0) as total
        FROM expenses
        WHERE user_id = ?
    """, (user_id,))
    total = cursor.fetchone()["total"]

    if total == 0:
        conn.close()
        return []

    # Get category breakdown
    cursor.execute("""
        SELECT category, SUM(amount) as amount
        FROM expenses
        WHERE user_id = ?
        GROUP BY category
        ORDER BY amount DESC
    """, (user_id,))

    rows = cursor.fetchall()
    conn.close()

    # Category colors matching the CSS badges
    category_colors = {
        "Food": "#f59e0b",
        "Transport": "#3b82f6",
        "Bills": "#ef4444",
        "Health": "#10b981",
        "Entertainment": "#8b5cf6",
        "Shopping": "#ec4899",
        "Other": "#6b7280"
    }

    return [
        {
            "name": row["category"],
            "amount": row["amount"],
            "percentage": round((row["amount"] / total) * 100, 1),
            "color": category_colors.get(row["category"], "#6b7280")
        }
        for row in rows
    ]
