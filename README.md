# 🧶 Knitting Library

---

> ## ⚠️ BETA SOFTWARE — UNDER ACTIVE DEVELOPMENT
>
> **This project is in beta. It is being actively developed and things will change.**
>
> - Features may be added, removed, or significantly changed between versions
> - Bugs and rough edges are expected — please report them
> - Database migrations are included where possible, but large structural changes may occasionally require a clean install
> - Do not rely on this as your only copy of important patterns — keep backups

---

My wife kept asking for a cheap and configurable way to store all her knitting patterns — PDFs she'd bought, photos of magazine pages, scanned booklets, the works. Existing apps were either too expensive, too limited, or just not how she wanted to work. So I built this for her.

It runs on your own machine, costs nothing to operate, and you own all the data. Upload PDFs and photos of your patterns, browse them in a visual grid, annotate pages, track your active projects, and filter by any combination of category or tag. There's a full yarn database for keeping track of your stash, and a physical inventory system to track how many skeins you actually own.

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

### Option D — iPhone / iPad Home Screen

The app works as a home screen web app on iOS:

1. Open `http://YOUR-SERVER-IP:3000` in Safari
2. Tap the **Share** button → **Add to Home Screen**
3. The app will open fullscreen, without the browser toolbar

---

## First Login

Default credentials: **username:** `admin` **password:** `admin`

Change the password immediately after logging in — go to **Settings → My Account → Change Password**.

---

## Features

### 📖 Recipe Library
- Visual grid with thumbnail previews
- Adjustable grid size — small, medium, or large cards
- Search by name or tag; filter by category, tags, or project status
- Results update instantly without reloading the page

### 📥 Importing Recipes
- Upload PDFs or images — single files, multiple images, or an entire folder at once
- **Bulk Import Wizard** — select a folder of PDFs and work through them one by one, filling in name, categories, tags, and description for each
  - The full PDF is displayed in the wizard so you can read the pattern while filling in the details
  - Skip or discard individual recipes
  - Stop partway through and resume later — the queue is saved automatically
  - Add more files to the queue at any time without starting over
- Automatic thumbnail generation for every recipe
- PDF pages are pre-converted to images for fast, reliable viewing — no browser PDF plugin required

### 📄 Recipe Viewer
- Scrollable PDF pages with zoom
- Swipe (mobile) or arrow key (desktop) navigation between image pages
- Fullscreen mode
- Slide-up info panel on mobile for tags, categories, and project details

### ✏️ Annotations
- Draw or highlight directly on any recipe page
- Adjustable brush size, opacity, and colour
- Per-page undo
- Annotations saved to the database and persist across sessions

### 🧶 Project Tracking
- Mark recipes as **In Progress** or **Finished**
- Pick which yarn type and colour variant you're using when starting a project
- Optionally deduct skeins directly from your inventory when starting
- Full session history with start/finish timestamps and total knitting time per recipe

### 🧵 Yarn Database
- Catalogue of yarn types with full spec fields: wool type, yardage, needle size, tension, origin, seller, price per skein, product info
- Each yarn type supports multiple **colour variants**, each with its own name, price, and photo
- Colour swatch strip visible directly on yarn cards in the grid
- URL import — paste a yarn shop URL to auto-fill fields *(early beta — works best with Sandnes Garn)*
- Search by any field; filter by wool type or seller
- Access via **Inventory → Yarn Database**

### 📦 Inventory
- Track physical items you own: yarn skeins and tools, needles, and notions
- Yarn inventory entries link to your Yarn Database for photos and specs
- Add a new yarn to the database directly from the inventory entry form without leaving the page
- **+/−** buttons directly on each card for quick quantity adjustments
- Purchase info per entry: date, price, and receipt notes
- Full history log per item showing every addition and deduction with timestamps
- When starting a project, optionally select an inventory yarn and specify how many skeins to deduct — automatically logged

### 👤 User Accounts
- Login with username and password
- Admin can create and manage additional users
- Per-user settings: light/dark mode, English/Norwegian language

### 💾 Backups & Export
- Everything stored in a single `/data` folder — easy to copy for backup or migration
- Export as ZIP directly from **Settings → Data → Export Library**
- ZIP contains: full database, all recipe files, all yarn images and colour photos
- Inventory data is stored in the database — included automatically in every export

---

## Using the App

### Recipes

- **Add a single recipe** — click **+ Add Recipe**, drop in a PDF or photos, fill in a name and tags
- **Bulk import** — click **+ Add Recipe → Import folder**, select a folder of PDFs. The wizard walks you through each one: the full PDF is shown on the left so you can read it while filling in the name, categories, and tags on the right. Stop at any time — your progress is saved and you can resume later
- **Browse** — scroll the grid; use the size buttons to make cards bigger or smaller
- **Filter** — use the search bar or click Filters to narrow by category, tag, or project status
- **View** — click any card to open it. Scroll through PDF pages or swipe between images
- **Annotate** — click the pencil button on any page to draw or highlight
- **Track progress** — use Start Project / Finish Project in the recipe sidebar. You'll be prompted to pick a yarn, colour, and optionally deduct skeins from inventory

### Yarn Database

- **Add a yarn** — go to **Inventory → Yarn Database**, click **+ Add yarn**, fill in spec fields. Optionally paste a shop URL to auto-fill
- **Add colours** — open any yarn, scroll to the Colours section, click **Add colour**. Enter a name, price, and photo — you can paste an image from your clipboard
- **Browse & search** — grid view with swatch strip; use the field dropdown to search by name, material, etc.

### Inventory

- **Add yarn to inventory** — go to **Inventory**, click **+ Add yarn**. Search your Yarn Database to link the entry. If the yarn isn't in the database yet, click **+ Add yarn** from within the search results to add it on the spot. Set quantity and purchase details
- **Add tools / needles / notions** — click **+ Add item**, give it a name, pick a category, set quantity
- **Adjust quantity** — use the **+/−** buttons directly on the inventory card
- **View history** — click the clock icon on any card to see every change with dates and project links
- **Deduct when starting a project** — when clicking Start Project on a recipe, after choosing your yarn you'll be offered the option to select a matching inventory item and specify how many skeins to deduct

### General

- **Mobile** — open `http://YOUR-SERVER-IP:3000` on your phone while on the same Wi-Fi. Works in the browser, or add to your iPhone home screen via Safari → Share → Add to Home Screen for a fullscreen experience

---

## Backups

Everything lives in your `data/` folder — the database, all recipe files, and all yarn and colour images. Inventory items and their history are stored in the database and included automatically.

To back up: copy the `data/` folder somewhere safe.  
To restore: copy it back and restart the container.

You can also export from inside the app: **Settings → Data → Export Library** — downloads a ZIP containing everything.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Blank page or won't load | Make sure Docker Desktop is running and the container is started |
| "Not logged in" error | Refresh the page — your session may have expired |
| PDF thumbnail not showing | Give it a moment after upload — PDF processing can be slow for large files |
| PDF pages blank on first open | This is a known issue on the first import — stop and reopen the import wizard, or refresh the page |
| Can't reach it on phone | Make sure your phone is on the same Wi-Fi, use the server's IP not `localhost` |
| Header hidden under iPhone status bar | Make sure you're on a recent build. Remove and re-add the home screen shortcut after updating |
| Annotations not saving | Check that the `/data` volume is mounted correctly in your compose file |
| Yarn photo not showing | Supported formats: JPG, PNG, WebP |
| URL import didn't fill everything | The scraper is early beta — fill in missing fields manually before saving |
| Inventory quantity went negative | Quantity floors at 0 — it won't go below zero |
| Old data missing after update | All migrations run automatically on startup — check container logs if something seems wrong |

---

## 🤖 About This Project

I built this for personal use and I'm not a professional software developer. I used AI (Claude by Anthropic) as a coding assistant throughout — helping me write and debug code, figure out architecture decisions, and work through problems I got stuck on. The ideas, requirements, and direction were mine; the AI helped me build it.

If you find bugs or want to suggest improvements, feel free to open an issue.

---

## ⚠️ Security Warning

### Do not expose this app to the internet

This app was built for trusted home network use. Specifically:

- **Passwords are hashed with SHA-256** — not a modern algorithm like bcrypt or argon2. Fine for a home network, not for internet exposure
- **No rate limiting** on login attempts — no brute-force protection
- **No HTTPS** — traffic is unencrypted. Acceptable locally, not over the internet
- **The code has not been security audited**

### What this means for you

✅ **Safe to use:** On your home network, behind your router, accessed only by people you trust.

❌ **Not safe to use:** Exposed via port forwarding, a public IP, or any service that makes it reachable from outside your home network.

If you want remote access, use a **VPN** (like Tailscale or WireGuard) to connect to your home network first — never open the port directly to the internet.

---

*Built with FastAPI · React · SQLite · nginx · Docker*
