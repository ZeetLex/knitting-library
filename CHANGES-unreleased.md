# Unreleased Changes

> Changes made this session — not yet pushed to Docker Hub or tagged as a release.
> Delete or archive this file after the next release.

---

## New Features

### Mail / SMTP system (full implementation)
- **Forgot password flow** — "Forgot password?" button on login page. User enters username or email; a 12-character temporary password is generated, emailed, and only committed to the database if the send succeeds. Always returns a generic response to avoid leaking whether an account exists.
- **Welcome email** — when an admin creates a user with an email address, a prompt appears offering to send a welcome email. The plaintext password from the creation form is sent once and never stored again.
- **Announcement emails** — new toggle in Mail settings: "Email Update Notes to users". When enabled, pushing an Update Note emails all users who have an email address on file (non-blocking via BackgroundTasks).
- **Email template editor** — both the Forgot Password and Welcome email templates are editable in Settings → Mail. The editor shows subject + body fields, colour-coded token chips (`{USERNAME}`, `{PASSWORD}`, `{APP_URL}`), required-token validation, and an optional test-send that substitutes mock values.
- **Pre-filled default templates** — both templates ship with polished, ready-to-use defaults so no setup is required. Shown in the editor even before the user has saved anything.
- **`mail_enabled` master switch** — added the missing "Enable email" toggle at the top of the Mail settings section. This was tracked in the backend but was never exposed in the UI, causing "Mail is not enabled" errors for all users.
- **User email field** — users now have an optional email address. Admins can set/clear it via an edit button (@ icon) in the Users section, or supply it during user creation.

### Import help modal
- **"How does import work?" button** added to the import drop zone (dotted underline link with a `?` icon).
- Opens a full tutorial modal explaining the folder structure with three rule cards (loose PDFs, image folders, mix freely), an annotated visual file tree showing a real example resulting in 4 detected recipes, and a mobile tip explaining that folder selection isn't available on mobile but individual files still work.
- On mobile the modal slides up as a bottom sheet; "Got it!" button stretches full width.

---

## Fixes

### Settings panel auto-closes on navigation
- Previously, opening Settings and then clicking a tab (Recipes, Inventory, Yarn Database) or the Statistics button left the settings panel open while the content underneath changed.
- Fixed: `handleTabChange` and the stats click handler in `App.js` now call `setShowSettings(false)` before switching view.

### Import wizard JSX syntax error (build failure)
- The `{showHelp && <ImportHelpModal />}` render was placed as a sibling of the drop zone `<div>` inside a `{!groups && (...)}` expression, which only accepts a single root element.
- Fixed by wrapping both in a `<>...</>` fragment.

---

## Backend changes (`main.py`, ~3017 lines)
- Added `email TEXT NOT NULL DEFAULT ''` column to `users` table; migration runs automatically via `get_db()` on first start.
- Added `_send_app_mail(to, subject, body)` — central SMTP helper used by all mail flows.
- Added `_render_template(text, tokens)` — `{TOKEN}` substitution helper.
- Added default template constants: `_DEFAULT_FORGOT_SUBJECT/BODY`, `_DEFAULT_WELCOME_SUBJECT/BODY` (polished plain-text with section dividers).
- New endpoints:
  - `POST /api/auth/forgot-password` (public)
  - `PUT /api/admin/users/{id}/email`
  - `POST /api/admin/users/{id}/welcome-mail`
  - `POST /api/admin/mail/templates/test`
- `POST /api/admin/mail` allowlist expanded to include template keys and `mail_announcements_enabled`.
- `POST /api/admin/announcements` — now accepts `BackgroundTasks`; emails users when `mail_announcements_enabled = true`.

## Frontend changes

### `app/frontend/src/pages/LoginPage.js` + `LoginPage.css`
- Added forgot-password view (third state alongside login and 2FA).
- "Forgot password?" text button below Sign In.
- Generic success message shown after submit regardless of outcome.

### `app/frontend/src/pages/SettingsPage.js` + `SettingsPage.css`
- **Mail section**: `mail_enabled` toggle (master switch), template editor rows for Forgot Password and Welcome emails, announcement email toggle, `DEFAULT_*` template constants as pre-fill fallbacks.
- **New components**: `TemplateEditorModal`, `WelcomeMailModal`, `EditEmailModal`.
- **Users section**: email shown under username in user rows, @ icon button to edit email, optional email field in Add User modal, `WelcomeMailModal` prompt after user creation.
- **CSS additions**: `.settings-divider`, `.section-subheading`, `.btn-icon-label`, `.form-textarea`, `.template-tokens`, `.token-chip`, `.token-chip--required`, `.settings-modal--wide`.

### `app/frontend/src/components/ImportWizard.js` + `ImportWizard.css`
- `ImportHelpModal` component with rule cards, visual file tree, and mobile tip.
- `iw-help-btn` trigger inside the drop zone.
- Full CSS for the help overlay, modal, rule cards, tree diagram, and mobile sheet layout.

### `app/frontend/src/utils/api.js`
- `forgotPassword(usernameOrEmail)`
- `updateUserEmail(userId, email)`
- `sendWelcomeMail(userId, password)`
- `testMailTemplate(to, subject, body)`

### `app/frontend/src/utils/translations.js`
- Added `forgotPassword`, `forgotPasswordBack`, `forgotPasswordDesc`, `forgotPasswordSent`, `forgotPasswordSubmit` (English + Norwegian).

### `app/frontend/src/App.js`
- `handleTabChange` now calls `setShowSettings(false)`.
- Stats click handler now calls `setShowSettings(false)` before opening stats.
