# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Spendly - A Flask-based expense tracking web application with SQLite database, built as part of an AI-assisted coding educational project.

## Commands

```bash
# Run the application
python app.py

# Run tests
pytest

# Run a specific test
pytest -k test_name

# Install dependencies
pip install -r requirements.txt
```

## Architecture

- **Framework**: Flask 3.1.3 with Werkzeug 3.1.6
- **Database**: SQLite with foreign key support (via `database/db.py`)
- **Testing**: pytest with pytest-flask plugin
- **Frontend**: Vanilla JavaScript, custom CSS with Google Fonts (DM Serif Display, DM Sans)

### File Structure

```
expense-tracker/
├── app.py              # Flask application entry point
├── database/
│   ├── __init__.py
│   └── db.py           # Database utilities: get_db(), init_db(), seed_db()
├── static/
│   ├── css/style.css   # Application styles
│   └── js/main.js      # Client-side JavaScript
├── templates/
│   ├── base.html       # Base template with navbar/footer
│   ├── landing.html    # Landing page
│   ├── login.html      # Login form
│   ├── register.html   # Registration form
│   ├── terms.html      # Terms and conditions
│   └── privacy.html    # Privacy policy
└── tests/              # Test suite
```

### Key Patterns

- **Database**: `db.py` provides `get_db()` (SQLite connection with row_factory + foreign keys), `init_db()` (CREATE TABLE IF NOT EXISTS), and `seed_db()` (sample data)
- **Templates**: Jinja2 templating with `base.html` as the parent; auth pages extend it with `{% block content %}`
- **Routes**: Defined in `app.py`; placeholder routes marked with comments for future implementation steps

## Development Notes

- Application runs on port 5001 in debug mode
- The project is structured as a step-by-step learning exercise - many routes and `db.py` are stubs awaiting implementation
- Check `requirements.txt` for current dependencies before adding new packages
