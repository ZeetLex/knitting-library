# Knitting Library Deployment And Operations Guide

This guide collects the practical details that do not need to live in the project overview: deployment variants, first-run behavior, storage, backups, reverse proxy configuration, fail2ban, AI text recognition, and troubleshooting.

## Requirements

Use Docker Desktop, Docker Engine, or another Docker-compatible host.

Docker Desktop is available from `https://www.docker.com/products/docker-desktop/`.

## Running With Docker Compose

From the folder containing `docker-compose.yml`:

```bash
docker compose up -d
```

Open `http://localhost:3000`.

On first launch, Knitting Library shows a setup screen for creating the first admin account. There are no default credentials. The first admin password must be at least 12 characters.

Existing installs are not changed. If your database already contains users, the normal login screen appears.

## Docker Desktop

In Docker Desktop, open the Compose section, point it at `docker-compose.yml`, and start the stack.

## Unraid Or Home Server Example

```yaml
services:
  app:
    image: zeetlex/knitting-library:latest
    restart: unless-stopped
    ports:
      - "3000:8080"
    environment:
      - PUID=99
      - PGID=100
      - TRUSTED_PROXIES=
    volumes:
      - /path/to/your/data:/data
      - /path/to/your/logs:/logs
```

`PUID` and `PGID` control host ownership for files written to `/data` and `/logs`. Docker Desktop users can usually set these to `0` or omit them.

## Mobile Installation

Open `http://YOUR-SERVER-IP:3000` in Safari on iPhone, then use Share -> Add to Home Screen.

Knitting Library is designed primarily for mobile/PWA use while still supporting desktop browsers.

## Interface Overview

- **Home dashboard**: overview counters, active projects, finished projects, and a Discover shelf that favors unfinished or not-started recipes.
- **Mobile navigation**: bottom navigation for Home, Recipes, Add, Inventory, and Menu, with a collapsible mode for more reading space.
- **Desktop navigation**: left sidebar with primary navigation and secondary links.
- **Add menu**: one entry point for recipe uploads, folder imports, and yarn additions.
- **Inventory**: yarn and thread samples, yarn stock, needles, tools, and notions in one place.
- **Settings**: appearance, account, data, and admin tools grouped into focused sections.

## Recipe Library

The recipe library uses a visual grid with thumbnails and adjustable card size. Recipes can be searched by name or tag and filtered by category, tag, or project status.

Supported imports include PDFs, individual images, multiple images, and folders. The Bulk Import Wizard works through folder imports one file at a time and saves progress automatically.

The recipe viewer supports scrollable pages, zoom, fullscreen, mobile swipe gestures, desktop arrow-key navigation, and cover image selection.

Image recipes include tools for crop, rotate, reorder, cover selection, and persistent quality adjustments. Quality edits can tune brightness/exposure, contrast, gamma, saturation, warmth, and sharpness, with an original-image restore option.

## Text Recognition And Review

Recipe pages can have a shared editable text version generated from scanned recipe images. Open a recipe, switch from **Original** to **Text version**, then create, edit, save, or regenerate the transcription.

Text recognition is configured by an admin under **Settings -> Admin -> AI / Text recognition**. The beta workflow uses a vision-capable OpenAI-compatible model and sends each recipe image or PDF page directly to AI for plain text transcription, one page at a time. Results are stored beside the matching original image for review.

An optional second cleanup pass can send raw page text back to AI for Markdown cleanup after scanning completes. This cleanup step is disabled unless an admin enables it.

Admins can preview and edit scan and cleanup prompts, tune max output tokens, configure scan and cleanup temperatures, and fetch model names from the configured OpenAI-compatible endpoint. Model fetching only lists models; generation settings are sent with each chat completion request.

Compatible providers include:

- OpenAI GPT vision-capable models, for example `https://api.openai.com/v1` plus an API key.
- Ollama, for example `http://host.docker.internal:11434/v1`.
- LM Studio, for example `http://host.docker.internal:1234/v1`.
- Other OpenAI-compatible local or hosted providers.

The current beta workflow is user-guided:

- AI vision sends each page image directly to the model, sequentially, and marks the job as ready for review.
- Optional AI cleanup can format raw page text before review.
- The Review view shows the original page beside editable draft text.
- Reviewers can accept pages, pause and resume, cancel the draft, insert a diagram crop, or crop a legend image.
- The diagram tool can move, resize, rotate and deskew the selected diagram crop, adjust the overlay grid, blur the background preview, and change overlay/generated grid line thickness.
- Completing review publishes one shared Markdown text version with reviewed text and saved diagram or legend image inserts.

The diagram editor saves diagram and legend inserts as images inside the reviewed Markdown text version. It does not parse knitting symbols into a final machine-readable chart or complete written instructions. Generation audit details, including provider tokens and estimated image input, are shown below the text version for review.

Generated text is persistent for the whole server, not private per user. AI output should always be checked against the original recipe, especially for old scans, Norwegian/English knitting abbreviations, stitch counts, unclear page photos, and diagram symbols.

## Annotations

Draw or highlight directly on recipe pages. Brush, opacity, and color are adjustable. Strokes are saved per page to the database and persist across sessions.

## Project Tracking

Recipes can be marked active or finished per user account. Other users can start and finish the same recipe separately without changing your own project state.

Starting a project can link a yarn and color variant, optionally deducting skeins from inventory. Finished projects can be rated for quality, difficulty, and result with optional notes.

The Home dashboard shows active and finished projects from every user, including who started or finished them. Opening someone else's active project opens the recipe with your own project state, so you can start it yourself. Admin users can view and manage all project sessions.

## Yarn And Inventory

The yarn catalogue stores material, yardage, needle size, tension, seller, price, and color variants. Each color can have a name, price, and photo. URL import is early beta and currently works best with Sandnes Garn.

Inventory tracks yarn/thread samples, yarn stock, needles, tools, and notions. Yarn/thread entries can be saved with quantity `0` as project-planning samples, or with stock quantity for physical skeins. Quantity changes have quick controls and a history log.

## Accounts, Appearance, And Admin Tools

User accounts use username/password login with bcrypt hashing, login rate limiting, optional TOTP two-factor authentication, and per-user settings.

Appearance options include light/dark mode, multiple color themes, and per-user background choices.

The interface is available in English, Norwegian, and Hungarian. Prices and inventory values can be shown in NOK, USD, GBP, HUF, or EUR.

The admin panel includes user management, API/container logs, SMTP mail configuration, AI text recognition settings, 2FA status management, update notes, and all-user project session inspection.

## Folder Structure

After first run, your directory will contain:

```text
your-folder/
  docker-compose.yml
  data/
    knitting.db       <- database
    recipes/          <- recipe files and thumbnails
    yarns/            <- yarn images
  logs/
    uvicorn.log       <- API requests and errors; also streamed to docker logs
    supervisord.log   <- container startup and watchdog events
    auth.log          <- failed logins, useful for fail2ban
```

Logs rotate automatically: 10 MB per file, 5 backups. Use `docker logs knitting-library` for startup, access, and crash output when the UI does not load. The Admin -> Logs screen reads the same persisted files from `./logs`.

## Backups And Restore

Copy the `data/` folder. It contains the database, recipe files, yarn images, annotations, session history, and settings.

To restore, copy `data/` back and restart the container.

Back up before updating, especially while the project is in beta.

## Security Details

| Area | Status |
|---|---|
| Password hashing | bcrypt, rounds=12 |
| Login rate limiting | 10 attempts per 15 min per IP, plus fail2ban support |
| Two-factor authentication | TOTP |
| Session expiry | 30 days; 2FA challenges expire in 5 minutes |
| Session storage | HttpOnly SameSite cookies; legacy `X-Session-Token` still accepted for compatibility |
| CSRF | CSRF token required for cookie-authenticated write requests |
| File upload validation | Magic-byte checks plus size limits: 50 MB PDF, 20 MB image |
| CORS | Same-origin only, set `ALLOWED_ORIGINS` if needed |
| Security headers | CSP, X-Frame-Options, Referrer-Policy, Permissions-Policy |
| API documentation | Disabled in production |
| SQL injection | Parameterised queries throughout |
| Path traversal | Filename sanitisation on uploads |
| SSRF | Yarn URL scraper validates DNS/IPs and redirect hops |
| Frontend dependencies | Vite build with committed npm lockfile |
| HTTPS | Not built in; use a reverse proxy |

Recommended deployment options, in order of preference:

- Home network only.
- VPN access, such as Tailscale or WireGuard.
- Reverse proxy with HTTPS.

Direct port forwarding to the internet is not recommended.

The author takes no responsibility for data loss, unauthorised access, or issues arising from how you deploy this application.

## Reverse Proxy

If the app runs behind a reverse proxy, configure `TRUSTED_PROXIES` so the app only trusts `X-Forwarded-For` and `X-Forwarded-Proto` from your proxy. Use the proxy container IP or Docker network CIDR:

```yaml
environment:
  - TRUSTED_PROXIES=172.16.0.0/12
```

For Nginx Proxy Manager, add this in the proxy host Advanced tab:

```nginx
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Real-IP $remote_addr;
```

For Caddy:

```caddyfile
knitting.example.com {
  reverse_proxy knitting-library:8080 {
    header_up X-Forwarded-For {remote_host}
    header_up X-Forwarded-Proto {scheme}
  }
}
```

Pin image versions for production when possible. `latest` is convenient for testing, but a version tag plus a backup before updating is safer.

## Fail2ban Optional Setup

If the app is exposed through a reverse proxy, fail2ban can block IPs that repeatedly fail to log in.

The app writes failed login and bad 2FA attempts to `logs/auth.log`. When using a proxy, set `TRUSTED_PROXIES` as described above.

Example log line:

```text
2025-01-15 14:23:45 AUTH_FAIL ip=1.2.3.4 user=admin reason=bad_password
```

Filter, `filter.d/knitting-library.conf`:

```ini
[Definition]
failregex = ^%Y-%m-%d %H:%M:%S AUTH_FAIL ip=<HOST>\b
ignoreregex =
datepattern = ^%%Y-%%m-%%d %%H:%%M:%%S
```

Jail, `jail.d/knitting-library.conf`:

```ini
[knitting-library]
enabled  = true
filter   = knitting-library
logpath  = /path/to/your/logs/auth.log
maxretry = 5
findtime = 600
bantime  = 3600
action   = iptables-multiport[name=knitting-library, port="80,443,3000", protocol=tcp]
```

Reload fail2ban after placing the files:

```bash
fail2ban-client reload
fail2ban-client status knitting-library
```

## Troubleshooting

| Problem | Fix |
|---|---|
| Blank page or app will not load | Make sure Docker is running and the container is started. |
| Not logged in error | Refresh the page; the session may have expired. |
| PDF thumbnail not showing | Large PDFs can take time to process. |
| Cannot reach it on phone | Use the server IP, not `localhost`, and make sure the phone is on the same network. |
| Annotations not saving | Check that the `./data` volume is mounted correctly. |
| URL import did not fill everything | URL import is early beta; fill missing fields manually. |
| Live logs show nothing | Check `docker logs knitting-library` first, then confirm `./logs:/logs` is mounted. |
| Requests show the same IP | Configure forwarded headers and `TRUSTED_PROXIES`. |
| Port 8080 shows nothing | Check container logs with `docker logs knitting-library`. |

## Updating

Before updating, back up `data/`.

With Compose:

```bash
docker compose pull
docker compose up -d
```

If you maintain a pinned image tag, update the tag in `docker-compose.yml`, then pull and restart.
