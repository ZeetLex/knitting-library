# 🧶 Knitting Library

A personal knitting pattern library that runs on your own machine. Upload PDFs and photos of your patterns, browse them in a visual grid, and filter by category or tag. Built for home use on a local network.

> **Built with Docker — no coding required to run it.**

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

## Using the App

- **Add a recipe** — click the + button, drop in a PDF or photos, fill in a name and tags
- **Browse** — scroll the grid, use the size buttons to make cards bigger or smaller
- **Filter** — use the search bar or click Filters to narrow by category or tag
- **View** — click any card to open it. PDFs have a built-in viewer, images support swipe and zoom
- **Mobile** — open `http://YOUR-SERVER-IP:3000` on your phone's browser while on the same Wi-Fi

---

## Backups

Everything lives in your `data/` folder — the database and all recipe files. To back up, just copy that folder somewhere safe. To restore, copy it back and restart the container.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Blank page or won't load | Make sure Docker Desktop is running and the container is started |
| "Not logged in" error | Refresh the page — your session may have expired |
| PDF thumbnail not showing | Give it a moment after upload — PDF processing can be slow |
| Can't reach it on phone | Make sure your phone is on the same Wi-Fi, use the server's IP not `localhost` |

---

---

## 🤖 AI Notice & Security Warning

This application was built almost entirely with the assistance of AI (Claude by Anthropic). While it works well for personal home use, there are important things to understand before using it:

### Do not expose this app to the internet

This app was not built with public-facing security in mind. Specifically:

- **Passwords are hashed with a simple SHA-256 scheme** — not a modern password hashing algorithm like bcrypt or argon2. This is fine for a trusted home network, but not for internet exposure.
- **Session tokens are stored in browser localStorage** — acceptable locally, but a known security trade-off.
- **No rate limiting** on login attempts — meaning there is no protection against brute-force password attacks.
- **No HTTPS** — traffic between your browser and the server is unencrypted. On a local network this is generally fine; over the internet it is not.
- **The code has not been audited** — AI-generated code can contain subtle bugs or security flaws that haven't been caught.

### What this means for you

✅ **Safe to use:** On your home network, behind your router, accessed only by people you trust.

❌ **Not safe to use:** Exposed via port forwarding, a public IP, or any service that makes it reachable from outside your home network.

If you want to access this remotely, use a **VPN** (like Tailscale or Wireguard) to connect to your home network first — never open the port directly to the internet.

---

*Built with FastAPI · React · SQLite · Docker*
