# Spec: Logout

## Overview

Implement the logout functionality to allow authenticated users to sign out of their session. This is a simple but essential feature that completes the authentication flow started in Step 2 (Registration and Login). The logout feature clears the user's session data and redirects them to the landing page with a confirmation message.

## Depends on

- Step 2: Registration and Login (session management must exist)

## Routes

- `GET /logout` — Destroys session and redirects to landing page — logged-in users only

## Database changes

No database changes.

## Templates

No new templates to create.

No existing templates to modify.

## Files to change

- `app.py` — Replace stub route with session destruction and redirect logic

## Files to create

None.

## New dependencies

No new dependencies.

## Rules for implementation

- No SQLAlchemy or ORMs
- Use Flask's `session.clear()` to destroy all session data
- Use `flash()` to show "You have been logged out" message on redirect
- Redirect to landing page (`/`) after logout
- All templates extend `base.html`
- Use `url_for()` for internal redirects, never hardcoded URLs
- Keep route in `app.py` — no blueprints

## Definition of done

- [ ] `GET /logout` destroys the user session
- [ ] User is redirected to the landing page after logout
- [ ] A success flash message is displayed: "You have been logged out"
- [ ] Navbar updates after logout (shows "Sign in" / "Get started" instead of user menu)
- [ ] Calling `/logout` when not logged in does not cause errors
- [ ] No new files created
- [ ] No new pip packages installed
