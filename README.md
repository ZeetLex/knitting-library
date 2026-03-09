# 🧶 Knitting Library

My wife kept asking me for a cheap and configurable way to store all her knitting patterns — PDFs she'd bought, photos of magazine pages, scanned booklets, the works. Existing apps were either too expensive, too limited, or just not how she wanted to work. So I built this for her.

It runs on your own machine, costs nothing to operate, and you own all the data. Upload PDFs and photos of your patterns, browse them in a visual grid, annotate pages, track your active projects, and filter by any combination of category or tag. There's also a full yarn database for keeping track of your stash.

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

### Option A — Docker Desktop (GUI)

1. Open Docker Desktop
2. Go to the **Compose** section and point it at the `docker-compose.yml` file from this repo
3. Hit **Start**
4. Open `http://localhost:3000` in your browser

### Option B — Terminal

```bash
docker-compose up -d
```

Then open `http://localhost:3000`.

### Option C — Unraid / Home Server (Compose Stack)

Paste this into your compose stack manager (e.g. Unraid's Compose Manager):

```yaml
services:
  app:
    image: zeetlex/knitting-library:latest
    restart: unless-stopped
    ports:
      - "3000:80"
    volumes:
      - /path/to/your/data:/data
```

Change `/path/to/your/data` to wherever you want your data stored (e.g. `/mnt/user/appdata/knitting-library/data` on Unraid).

Then start the stack and open `http://YOUR-SERVER-IP:3000`.

---

## First Login

Default credentials: **username:** `admin` **password:** `admin`

Change the password immediately after logging in — go to **Settings → My Account → Change Password**.

---

## Features

- **Recipe library** — visual grid with thumbnail previews, upload PDFs or images (single files, multi-page scans, or whole folders), automatic thumbnail and PDF-to-image conversion
- **Recipe viewer** — scrollable PDF pages, swipe/arrow image navigation, fullscreen mode
- **Annotations** — draw or highlight directly on any page, adjustable brush size/opacity/colour, per-page undo, saved to database
- **Project tracking** — mark recipes In Progress or Finished, pick which yarn and colour you're using, full session history with timestamps and total knitting time
- **Recipe search & filters** — search by name/tag, filter by category, tags, or project status, results update instantly
- **Yarn database** — dedicated Yarns tab; each yarn type can have multiple colour variants, each with its own photo and price per skein. Stores wool type, yardage, needles, tension, origin, seller, and product info
- **Yarn URL import** — paste a yarn shop URL to auto-fill fields (early beta — works best with Sandnes Garn, limited support for other stores)
- **Yarn search & filters** — field-specific search with autofill, filter by wool type and seller
- **Categories & tags** — fully custom, no presets, managed directly from the library page
- **User accounts** — login with username/password, admin can manage users, per-user light/dark mode and English/Norwegian language
- **Mobile friendly** — responsive layout, touch navigation, swipe between recipe pages, recipe info accessible via a slide-up panel
- **Backups** — everything in one `/data` folder, export as ZIP from Settings → Data (includes recipes, yarn images, and database)

---

## Using the App

### Recipes
- **Add a recipe** — click **+ Add recipe**, drop in a PDF or photos, fill in a name and tags
- **Browse** — scroll the grid, use the size buttons to make cards bigger or smaller
- **Filter** — use the search bar or click Filters to narrow by category, tag, or project status
- **View** — click any card to open it. Scroll through PDF pages, swipe between images
- **Annotate** — click the pencil button on any page to draw or highlight
- **Track progress** — use Start Project / Finish Project in the recipe sidebar. You'll be prompted to pick a yarn and colour when starting
- **On mobile** — tap **Recipe info ▲** at the bottom of the screen to see tags, categories, and project status

### Yarns
- **Add a yarn** — click **+ Add yarn**, fill in the spec fields. Optionally paste a shop URL to auto-fill
- **Add colours** — open any yarn, scroll to the Colours section, click **Add colour**. Enter a name/number, price, and photo. You can paste an image directly from your clipboard
- **Browse** — grid view with a colour swatch strip at the bottom of each card
- **Search** — use the field dropdown to search by name or material
- **Filter** — click Filters to narrow by wool type or seller
- **View details** — click any yarn card to see the full spec table, product info, and colour gallery

### General
- **Mobile** — open `http://YOUR-SERVER-IP:3000` on your phone while on the same Wi-Fi

---

## Backups

Everything lives in your `data/` folder — the database, all recipe files, and all yarn photos and colour images. To back up, just copy that folder somewhere safe. To restore, copy it back and restart the container.

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
| Yarn photo not showing | Supported formats are JPG, PNG, and WebP only |
| URL import didn't fill everything | The scraper is in early beta — fill in missing fields manually before saving |

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

*Built with FastAPI · React · SQLite · nginx · Docker*
