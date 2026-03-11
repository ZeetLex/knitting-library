# 🧶 Knitting Library

---

> ## ⚠️ BETA — UNDER ACTIVE DEVELOPMENT
>
> Things will change. Bugs are expected. Keep backups of your data.

---

> ## 🔒 SECURITY DISCLAIMER — PLEASE READ
>
> This application was built by a hobbyist, not a professional software developer or security engineer. The code was written with AI assistance (Claude by Anthropic) and has **not** been reviewed or audited by a qualified security professional.
>
> Security measures have been implemented in good faith, but **no guarantees can be made about the security of this application.**
>
> **You run this software entirely at your own risk.**
>
> - ✅ Recommended: run on a local home network, accessed only by people you trust
> - ✅ Acceptable: remote access via a private VPN tunnel (Tailscale, WireGuard)
> - ❌ Not recommended: exposed to the public internet via port forwarding or a public domain
>
> If you choose to expose this app publicly, you do so at your own risk. The author takes no responsibility for data loss, unauthorised access, or any other issues that may result.

---

Built for personal use — my wife needed somewhere to store her knitting patterns (PDFs, scanned magazine pages, photos) without paying a subscription or giving her data to someone else. It runs on your own machine and you own everything.

> **Runs with Docker — no coding required.**

---

## Requirements

Just **Docker Desktop** — nothing else.  
Download at: https://www.docker.com/products/docker-desktop/  
Works on Windows, Mac, and Linux.

---

## Getting Started

**Terminal:**
```bash
docker-compose up -d
```
Then open `http://localhost:3000`.

**Docker Desktop GUI:**  
Open the Compose section, point it at `docker-compose.yml`, hit Start.

**Unraid / home server:**
```yaml
services:
  app:
    image: zeetlex/knitting-library:latest
    restart: unless-stopped
    ports:
      - "3000:8080"
    volumes:
      - /path/to/your/data:/data
      - /path/to/your/logs:/logs
```

**iPhone home screen:**  
Open `http://YOUR-SERVER-IP:3000` in Safari → Share → Add to Home Screen.

---

## First Login

Default credentials: `admin` / `admin`  
Change your password immediately — **Settings → My Account → Change Password**.

---

## Features

### 📖 Recipe Library
- Visual grid with thumbnails — adjustable card size
- Search by name or tag; filter by category, tag, or project status
- Instant filtering without page reload

### 📥 Importing
- Upload PDFs or images — single file, multiple images, or a whole folder
- **Bulk Import Wizard** — work through a folder of PDFs one by one, adding metadata as you go. Saves progress automatically so you can stop and resume
- Automatic thumbnail generation
- PDFs pre-converted to images for reliable viewing on all devices

### 📄 Recipe Viewer
- Scrollable pages with zoom and fullscreen
- Swipe (mobile) or arrow keys (desktop) between pages
- Slide-up info panel on mobile

### ✏️ Annotations
- Draw or highlight directly on any recipe page
- Adjustable brush, opacity, and colour; per-page undo
- Saved to the database and persist across sessions

### 🧶 Project Tracking
- Mark recipes as In Progress or Finished
- Link a yarn and colour variant when starting a project
- Optionally deduct skeins from inventory on start
- Full session history with timestamps and total time per recipe
- **Feedback** — rate finished projects on quality, difficulty, and result (1–6 scale) with optional notes. Average score shown as a ★ badge on the recipe card

### 🎨 Themes
- Light and dark mode
- 5 colour themes: Terracotta, Rose Garden, Lavender Mist, Sage & Linen, Berry Bloom
- Per-user setting, saved to your profile

### 🧵 Yarn Database
- Catalogue yarn types with full specs: material, yardage, needle size, tension, seller, price
- Multiple colour variants per yarn, each with name, price, and photo
- Colour swatch strip on yarn cards
- URL import to auto-fill fields *(early beta — works best with Sandnes Garn)*

### 📦 Inventory
- Track yarn skeins, needles, tools, and notions
- Yarn entries link to your Yarn Database for specs and photos
- +/− buttons on each card for quick quantity adjustments
- Full history log per item with timestamps

### 💱 Currency
- Choose NOK (kr), USD ($), or GBP (£) — all price fields update throughout the app
- Per-user setting

### 👤 User Accounts
- Username/password login with bcrypt password hashing
- Login rate limiting — accounts lock out after repeated failed attempts
- Two-factor authentication (TOTP) — optional per user, set up in Settings
- Admin can create, manage, and reset 2FA for any user
- Per-user settings: theme, colour theme, language (English/Norwegian), currency
- Sessions expire after 30 days

### 🔐 Admin Panel
Accessible to admin users under **Settings → Admin**.

- **Users** — create and manage user accounts, reset 2FA
- **Live Logs** — real-time view of API and nginx logs, filterable by source (API / nginx / system). Auto-refreshes every 3 seconds
- **Mail Server** — configure SMTP for outgoing email, with a test-send button
- **Two-Factor Auth** — view and reset 2FA status for all users

### 💾 Backup & Export
- Recipe files and database live in `data/` — copy it to back up
- Logs live in `logs/` — separate folder so log growth never affects your data volume
- Export as ZIP from **Settings → Data → Export Library**

---

## Folder Structure

After first run, your appdata directory will contain:

```
your-appdata-folder/
  docker-compose.yml
  data/
    knitting.db       ← database
    recipes/          ← recipe files and thumbnails
    yarns/            ← yarn images
  logs/
    uvicorn.log       ← API requests and errors
    nginx.log         ← web server traffic
    supervisord.log   ← container startup and process events
```

Logs rotate automatically at 10 MB with 5 backups. The `logs/` folder will never exceed ~120 MB.

---

## Backups

Copy the `data/` folder — that's it. The database, all recipe files, yarn images, annotations, session history, and settings are all in there.

Logs are in `logs/` — these are optional to back up.

To restore: copy `data/` back and restart the container.

---

## Fail2ban (optional, Unraid + Nginx Proxy Manager)

If you expose this app through a reverse proxy, fail2ban can automatically block IPs that repeatedly fail to log in.

**Filter** (`/mnt/user/appdata/fail2ban/filter.d/knitting-library.conf`):
```ini
[Definition]
failregex = ^<HOST> .+ "(POST|GET) /api/auth/login.* (401|429)
            ^<HOST> .+ "POST /api/auth/2fa/challenge.* (401|429)
ignoreregex =
```

**Jail** (`/mnt/user/appdata/fail2ban/jail.d/knitting-library.conf`):
```ini
[knitting-library]
enabled  = true
filter   = knitting-library
logpath  = /mnt/user/appdata/knitting-library/logs/nginx.log
maxretry = 10
findtime = 900
bantime  = 3600
action   = iptables-multiport[name=knitting, port="http,https,3000", protocol=tcp]
```

Make sure Nginx Proxy Manager is forwarding the real client IP — add this to the **Advanced** tab of your proxy host:
```nginx
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Real-IP $remote_addr;
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Blank page or won't load | Make sure Docker Desktop is running and the container is started |
| "Not logged in" error | Refresh the page — session may have expired after 30 days |
| PDF thumbnail not showing | PDF processing can be slow for large files — give it a moment |
| Can't reach it on phone | Use the server's IP, not `localhost`. Phone must be on the same Wi-Fi |
| Header hidden under iPhone status bar | Remove and re-add the home screen shortcut after updating |
| Annotations not saving | Check that the `/data` volume is mounted correctly in your compose file |
| URL import didn't fill everything | Early beta — fill in missing fields manually |
| Live Logs shows nothing | Check that `./logs:/logs` is mounted in your compose file |
| All requests show same IP in logs | Set `X-Forwarded-For` header in your reverse proxy (see Fail2ban section) |
| Old data missing after update | Data persists in the `./data` volume and is not affected by container updates. If something looks wrong, check Live Logs for errors on startup |

---

## ⚠️ Security

Security measures in place:

| Area | Status |
|---|---|
| Password hashing | ✅ bcrypt (rounds=12) |
| Login rate limiting | ✅ 10 attempts per 15 min per IP |
| Two-factor authentication | ✅ TOTP (Google Authenticator etc.) |
| Session expiry | ✅ 30 days; 2FA challenges expire in 5 min |
| File upload validation | ✅ Magic-byte checks + size limits (50 MB PDF, 20 MB image) |
| CORS | ✅ Same-origin only (set `ALLOWED_ORIGINS` env var if needed) |
| Security headers | ✅ CSP, X-Frame-Options, HSTS (via nginx) |
| API documentation | ✅ Disabled in production |
| SQL injection | ✅ Parameterised queries throughout |
| Path traversal | ✅ Filename sanitisation on all uploads |
| SSRF | ✅ Private IP blocking on yarn URL scraper |
| HTTPS | ⚠️ Not built in — use a reverse proxy (Nginx Proxy Manager) |

**For remote access:** use a VPN (Tailscale or WireGuard) or a reverse proxy with HTTPS. Never forward the port directly.

---

## 🤖 About

Built for personal use. I used Claude (Anthropic) as a coding assistant throughout — the ideas and direction were mine, the AI helped me write and debug the code.

Open an issue if you find bugs or want to suggest something.

---

*Built with FastAPI · React · SQLite · nginx · Docker*
