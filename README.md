# 🧶 Knitting Library

---

> ## ⚠️ BETA — UNDER ACTIVE DEVELOPMENT
>
> Things will change. Bugs are expected. Keep backups of your data.

---

Built for personal use — my wife needed somewhere to store her knitting patterns (PDFs, scanned magazine pages, photos) without paying a subscription or giving her data to someone else. It runs on your own machine and you own everything.

> **Runs with Docker — no coding required.**

---

## ⚠️ Local Use Only

**This app is not designed to be exposed to the internet.** See the security notice at the bottom of this page.

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
- Username/password login
- Admin can create and manage additional users
- Per-user settings: theme, colour theme, language (English/Norwegian), currency

### 💾 Backup & Export
- Everything lives in a single `data/` folder — copy it to back up
- Export as ZIP from **Settings → Data → Export Library**

---

## Backups

Copy the `data/` folder — that's it. The database, all recipe files, yarn images, annotations, session history, and settings are all in there.

To restore: copy it back and restart the container.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Blank page or won't load | Make sure Docker Desktop is running and the container is started |
| "Not logged in" error | Refresh the page — session may have expired |
| PDF thumbnail not showing | PDF processing can be slow for large files — give it a moment |
| Can't reach it on phone | Use the server's IP, not `localhost`. Phone must be on the same Wi-Fi |
| Header hidden under iPhone status bar | Remove and re-add the home screen shortcut after updating |
| Annotations not saving | Check that the `/data` volume is mounted correctly in your compose file |
| URL import didn't fill everything | Early beta — fill in missing fields manually |
| Old data missing after update | Migrations run automatically on startup — check container logs if something looks wrong |

---

## 🤖 About

Built for personal use. I used Claude (Anthropic) as a coding assistant throughout — the ideas and direction were mine, the AI helped me write and debug the code.

Open an issue if you find bugs or want to suggest something.

---

## ⚠️ Security

### Do not expose this app to the internet

- Passwords hashed with SHA-256 (not bcrypt/argon2) — fine for a home network, not for public exposure
- No rate limiting on login attempts
- No HTTPS
- No security audit has been done

✅ Safe to use on your home network, accessed by people you trust.  
❌ Not safe exposed via port forwarding or a public IP.

For remote access, use a VPN (Tailscale or WireGuard) — never open the port directly.

---

*Built with FastAPI · React · SQLite · nginx · Docker*
