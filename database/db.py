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
