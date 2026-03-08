# 🧶 Knitting Library

My wife kept asking me for a cheap and configurable way to store all her knitting patterns — PDFs she'd bought, photos of magazine pages, scanned booklets, the works. Existing apps were either too expensive, too limited, or just not how she wanted to work. So I built this for her.

It runs on your own machine, costs nothing to operate, and you own all the data. Upload PDFs and photos of your patterns, browse them in a visual grid, annotate pages, track your active projects, and filter by any combination of category or tag.

> **Runs with Docker — no coding required to use it.**

---

## ⚠️ Important: Local Use Only

**This app is not designed to be exposed to the internet.** Please read the security notice at the bottom of this page before going any further.

---

## What You Need

Just **Docker Desktop** — nothing else.

- Download it at: https://www.docker.com/products/docker-desktop/
- Works on Windows, Mac, and Linux
- Make sure it's running before you start (look for the whale 🐳 icon in your taskbar)

---

## Getting Started

**Option A — Docker Desktop (GUI)**

1. Open Docker Desktop
2. Go to the **Compose** section and point it at the `docker-compose.yml` file from this repo
3. Hit **Start**
4. Open `http://localhost:3000` in your browser

**Option B — Terminal / Unraid Compose Stack**

Paste this into your compose stack manager (e.g. Unraid's Compose Manager):

```yaml
services:
  backend:
    image: zeetlex/knitting-library-backend:latest
    restart: unless-stopped
    volumes:
      - /path/to/your/data:/data

  frontend:
    image: zeetlex/knitting-library-frontend:latest
    restart: unless-stopped
    ports:
      - "3000:80"
    depends_on:
      - backend
```

Change `/path/to/your/data` to wherever you want your recipes stored (e.g. `/mnt/user/appdata/knitting-library/data` on Unraid).

Then start the stack and open `http://YOUR-SERVER-IP:3000`.

---

## First Login

Default credentials: **username:** `admin` **password:** `admin`

Change the password immediately after logging in — go to **Settings → My Account → Change Password**.

---

## Features

### Recipe Library
- Visual grid with thumbnail previews — small, medium, and large card sizes
- Upload PDFs, JPGs, PNGs, WebP images, or entire folders of scanned pages
- Multiple images uploaded together are automatically grouped as one recipe
- PDF pages are automatically converted to images for fast in-app browsing
- Thumbnails generated automatically on upload

### Viewing Recipes
- PDFs are displayed as scrollable page images — no iframe, no external viewer
- Image recipes support swipe navigation (mobile) and arrow navigation (desktop)
- Fullscreen mode for both PDFs and image recipes

### Drawing & Annotations
- Draw directly on any recipe page with a pencil or highlighter tool
- Adjustable brush size and opacity
- 8 colour presets plus a custom colour picker
- Undo last stroke, or clear all annotations for a page
- Annotations are saved to the database and survive container restarts
- Each page of a PDF has its own independent annotation layer

### Project Tracking
- Mark any recipe as **In Progress** or **Finished** with a single button
- Start and finish timestamps recorded automatically
- Full session history — every time you start and finish a project is logged
- Total knitting time calculated across all sessions
- Per-session duration shown with a proportional progress bar
- Start a finished project again — all previous session history is kept
- Clear all session data for a recipe if you want a fresh start
- Active projects are pinned to the top of the grid, finished projects second
- Cards show colour-coded status badges (blue = in progress, green = finished)

### Search & Filtering
- Search by recipe name, description, or tag
- Filter by category (e.g. Socks, Sweater, Hat)
- Filter by one or more tags (e.g. yarn weight, difficulty, designer)
- Filter by project status: All / In Progress / Finished
- Multiple filters work together — results update instantly

### Categories & Tags
- No pre-filled categories — you create your own
- Categories managed from a collapsible panel on the library page
- Tags are added freely during upload and are fully searchable
- Tags accumulate over time and appear as filter options automatically

### User Accounts & Settings
- Username and password login
- Admin can add and remove users, reset passwords
- Per-user settings: light or dark mode, English or Norwegian language
- All interface text is fully translated in both languages

### Mobile
- Fully responsive layout — works well on iPhone and Android browsers
- Touch-friendly buttons and navigation throughout
- Swipe left/right to navigate between pages in image recipes
- Annotations work on touchscreens

### Data & Backups
- All data lives in a single folder (`/data`) — easy to back up by just copying it
- SQLite database — no separate database server required
- Export your entire library (database + all files) as a ZIP from Settings → Data

---

## Using the App

- **Add a recipe** — click the + button, drop in a PDF or photos, fill in a name and tags
- **Browse** — scroll the grid, use the size buttons to make cards bigger or smaller
- **Filter** — use the search bar or click Filters to narrow by category, tag, or project status
- **View** — click any card to open it. Scroll through PDF pages, swipe between images
- **Annotate** — click the pencil button on any page to draw or highlight
- **Track progress** — use Start Project / Finish Project in the recipe sidebar
- **Mobile** — open `http://YOUR-SERVER-IP:3000` on your phone while on the same Wi-Fi

---

## Backups

Everything lives in your `data/` folder — the database and all recipe files. To back up, just copy that folder somewhere safe. To restore, copy it back and restart the container.

You can also export directly from the app: **Settings → Data → Export Library** downloads a ZIP of everything.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Blank page or won't load | Make sure Docker Desktop is running and the container is started |
| "Not logged in" error | Refresh the page — your session may have expired |
| PDF thumbnail not showing | Give it a moment after upload — PDF processing can be slow |
| PDF pages not showing | Open the recipe — conversion happens automatically on first view |
| Can't reach it on phone | Make sure your phone is on the same Wi-Fi, use the server's IP not `localhost` |
| Annotations not saving | Check that the `/data` volume is mounted correctly in your compose file |

---

## 🤖 About This Project

I built this for personal use and I'm not a professional software developer. I used AI (Claude by Anthropic) as a coding assistant throughout — helping me write and debug code, figure out architecture decisions, and work through problems I got stuck on. The ideas, requirements, and direction were mine; the AI helped me build it.

If you find bugs or want to suggest improvements, feel free to open an issue.

---

## ⚠️ Security Warning

### Do not expose this app to the internet

This app was built for trusted home network use. Specifically:

- **Passwords are hashed with SHA-256** — not a modern algorithm like bcrypt or argon2. Fine for a home network, not for internet exposure.
- **No rate limiting** on login attempts — no brute-force protection.
- **No HTTPS** — traffic is unencrypted. Acceptable locally, not over the internet.
- **The code has not been security audited.**

### What this means for you

✅ **Safe to use:** On your home network, behind your router, accessed only by people you trust.

❌ **Not safe to use:** Exposed via port forwarding, a public IP, or any service that makes it reachable from outside your home network.

If you want remote access, use a **VPN** (like Tailscale or WireGuard) to connect to your home network first — never open the port directly to the internet.

---

*Built with FastAPI · React · SQLite · Docker*
