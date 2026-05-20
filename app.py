import math
import os
from datetime import date as date_cls, datetime, timedelta
from flask import (
    Flask,
    abort,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
)
from database.db import (
    get_db,
    init_db,
    seed_db,
    create_user,
    get_user_by_email,
    get_user_by_id,
    verify_password,
)
from database.queries import (
    get_user_profile,
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
    insert_expense,
    get_expense_by_id,
    update_expense,
    delete_expense_by_id,
)

EXPENSE_CATEGORIES = [
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
]

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24))


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #


@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        # Validation
        if not name or not email or not password:
            flash("All fields are required.", "error")
            return render_template("register.html")

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("register.html")

        # Check if email already exists
        existing_user = get_user_by_email(email)
        if existing_user:
            flash("An account with this email already exists.", "error")
            return render_template("register.html")

        # Create user
        try:
            create_user(name, email, password)
            flash("Account created successfully! Please sign in.", "success")
            return redirect(url_for("login"))
        except Exception as e:
            flash("An error occurred. Please try again.", "error")
            return render_template("register.html")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        # Validation
        if not email or not password:
            flash("Email and password are required.", "error")
            return render_template("login.html")

        # Check if user exists
        user = get_user_by_email(email)
        if not user:
            flash("Invalid email or password.", "error")
            return render_template("login.html")

        # Verify password
        if not verify_password(password, user["password_hash"]):
            flash("Invalid email or password.", "error")
            return render_template("login.html")

        # Create session
        session["user_id"] = user["id"]
        session["user_name"] = user["name"]
        flash("Welcome back, " + user["name"] + "!", "success")
        return redirect(url_for("profile"))

    return render_template("login.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("landing"))


@app.route("/profile")
def profile():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    # --- Date param validation ---
    raw_from = request.args.get("date_from", "").strip()
    raw_to = request.args.get("date_to", "").strip()

    date_from = date_to = None
    if raw_from:
        try:
            datetime.strptime(raw_from, "%Y-%m-%d")
            date_from = raw_from
        except ValueError:
            pass
    if raw_to:
        try:
            datetime.strptime(raw_to, "%Y-%m-%d")
            date_to = raw_to
        except ValueError:
            pass

    if (date_from is None) != (date_to is None):
        flash("Please provide both a start date and an end date.", "error")
        date_from = date_to = None
    elif date_from and date_to and date_from > date_to:
        flash("Start date must be before end date.", "error")
        date_from = date_to = None

    # --- Preset date ranges (computed here, not in template) ---
    today = date_cls.today()
    today_iso = today.isoformat()

    def _months_ago(n):
        month = today.month - n
        year = today.year + month // 12
        month = month % 12 or 12
        if month > today.month:
            year -= 1
        return date_cls(year, month, today.day).isoformat()

    presets = {
        "this_month": {
            "label": "This Month",
            "date_from": date_cls(today.year, today.month, 1).isoformat(),
            "date_to": today_iso,
        },
        "last_3_months": {
            "label": "Last 3 Months",
            "date_from": _months_ago(3),
            "date_to": today_iso,
        },
        "last_6_months": {
            "label": "Last 6 Months",
            "date_from": _months_ago(6),
            "date_to": today_iso,
        },
        "all_time": {
            "label": "All Time",
            "date_from": None,
            "date_to": None,
        },
    }

    active_preset = None
    if date_from is None and date_to is None:
        active_preset = "all_time"
    else:
        for key, p in presets.items():
            if p["date_from"] == date_from and p["date_to"] == date_to:
                active_preset = key
                break

    # --- Fetch real data ---
    user = get_user_profile(user_id)
    if not user:
        abort(404)

    stats = get_summary_stats(user_id, date_from, date_to)
    transactions = get_recent_transactions(
        user_id, limit=10, date_from=date_from, date_to=date_to
    )
    categories = get_category_breakdown(user_id, date_from, date_to)

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=transactions,
        categories=categories,
        presets=presets,
        active_preset=active_preset,
        date_from=date_from,
        date_to=date_to,
    )


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_id = session["user_id"]

    if request.method == "POST":
        amount_raw = request.form.get("amount", "").strip()
        category = request.form.get("category", "")
        date_str = request.form.get("date", "").strip()
        description_raw = request.form.get("description", "").strip()
        description = description_raw or None

        form_values = {
            "amount": amount_raw,
            "category": category,
            "date": date_str,
            "description": description_raw,
        }

        try:
            amount = float(amount_raw)
            if not math.isfinite(amount) or amount <= 0:
                raise ValueError
        except ValueError:
            flash("Amount must be a positive number.", "error")
            return render_template(
                "add_expense.html", categories=EXPENSE_CATEGORIES, form=form_values
            )

        if category not in EXPENSE_CATEGORIES:
            flash("Please select a valid category.", "error")
            return render_template(
                "add_expense.html", categories=EXPENSE_CATEGORIES, form=form_values
            )

        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            flash("Please provide a valid date (YYYY-MM-DD).", "error")
            return render_template(
                "add_expense.html", categories=EXPENSE_CATEGORIES, form=form_values
            )

        insert_expense(user_id, amount, category, date_str, description)
        flash("Expense added successfully.", "success")
        return redirect(url_for("profile"))

    form_values = {
        "amount": "",
        "category": "",
        "date": date_cls.today().isoformat(),
        "description": "",
    }
    return render_template(
        "add_expense.html", categories=EXPENSE_CATEGORIES, form=form_values
    )


@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
def edit_expense(id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_id = session["user_id"]

    expense = get_expense_by_id(id)
    if not expense or expense["user_id"] != user_id:
        abort(404)

    if request.method == "POST":
        amount_raw = request.form.get("amount", "").strip()
        category = request.form.get("category", "")
        date_str = request.form.get("date", "").strip()
        description_raw = request.form.get("description", "").strip()
        description = description_raw or None

        form_values = {
            "amount": amount_raw,
            "category": category,
            "date": date_str,
            "description": description_raw,
        }

        try:
            amount = float(amount_raw)
            if not math.isfinite(amount) or amount <= 0:
                raise ValueError
        except ValueError:
            flash("Amount must be a positive number.", "error")
            return render_template(
                "edit_expense.html",
                categories=EXPENSE_CATEGORIES,
                form=form_values,
                expense=expense,
            )

        if category not in EXPENSE_CATEGORIES:
            flash("Please select a valid category.", "error")
            return render_template(
                "edit_expense.html",
                categories=EXPENSE_CATEGORIES,
                form=form_values,
                expense=expense,
            )

        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            flash("Please provide a valid date (YYYY-MM-DD).", "error")
            return render_template(
                "edit_expense.html",
                categories=EXPENSE_CATEGORIES,
                form=form_values,
                expense=expense,
            )

        update_expense(id, user_id, amount, category, date_str, description)
        flash("Expense updated successfully.", "success")
        return redirect(url_for("profile"))

    form_values = {
        "amount": f"{expense['amount']:.2f}",
        "category": expense["category"],
        "date": expense["date"],
        "description": expense["description"] or "",
    }
    return render_template(
        "edit_expense.html",
        categories=EXPENSE_CATEGORIES,
        form=form_values,
        expense=expense,
    )


@app.route("/expenses/<int:id>/delete", methods=["POST"])
def delete_expense(id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_id = session["user_id"]

    expense = get_expense_by_id(id)
    if not expense or expense["user_id"] != user_id:
        abort(404)

    delete_expense_by_id(id, user_id)
    flash("Expense deleted.", "success")
    return redirect(url_for("profile"))


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


if __name__ == "__main__":
    with app.app_context():
        init_db()
        seed_db()
    app.run(debug=True, port=5001)
