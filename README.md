# Knitting Library

Knitting Library is a self-hosted pattern, project, and yarn inventory manager for people who want their knitting archive under their own control. It runs as a single Docker container, stores data locally, and provides a mobile-friendly interface for daily use.

The project started as a practical home tool: a private place to keep knitting patterns, notes, project status, and yarn inventory without a subscription or third-party data lock-in.

> **Built with AI assistance.** This project was developed with AI coding assistants. Architecture, feature decisions, and direction remain human-owned; AI helped write and debug code. The codebase has not been formally reviewed by a professional developer or security auditor. See [Security](#security) for the current posture and limits.

## What It Does

- Stores PDF patterns and scanned image recipes with generated thumbnails.
- Provides searchable recipe browsing, categories, tags, and project status filters.
- Supports page annotations, recipe text versions, image cleanup tools, and per-recipe knitting tools for counters, increase/decrease calculations, and notes.
- Tracks active and finished projects per user, with shared household visibility.
- Manages yarn and thread references, color variants, stock, needles, tools, and notions.
- Includes user accounts, optional TOTP two-factor authentication, per-user appearance settings, and admin tools.
- Runs locally with SQLite-backed storage in mounted `data/` and `logs/` folders.

## Status

Knitting Library is active beta software. It is used in real workflows, but interfaces and data workflows may still change. Keep regular backups of the `data/` folder, especially before updating.

AI-assisted text recognition and diagram review are early beta features. Treat generated text as a draft and check it against the original pattern before relying on it.

## Quick Start

Requirements: Docker Desktop, Docker Engine, or another Docker-compatible host.

From the folder containing `docker-compose.yml`:

```bash
docker compose up -d
```

Open `http://localhost:3000` and create the first admin account. There are no default credentials.

For Unraid, reverse proxy, fail2ban, backups, AI setup, and troubleshooting, see the [deployment and operations guide](GUIDE.md).

## Storage

Runtime data is kept outside the container:

```text
data/
  knitting.db
  recipes/
  yarns/
logs/
  uvicorn.log
  supervisord.log
  auth.log
```

Backups are straightforward: stop the container if possible, copy `data/`, then restart. Restoring means putting `data/` back and starting the container again.

## Security

Implemented measures include bcrypt password hashing, login rate limiting, optional TOTP two-factor authentication, HttpOnly SameSite session cookies, CSRF protection for cookie-authenticated writes, upload validation, same-origin CORS by default, security headers, disabled production API docs, parameterised database queries, upload filename sanitisation, and SSRF checks for yarn URL imports.

HTTPS is not built into the container. Use a reverse proxy if the app is reachable beyond a trusted private network. A home network or VPN-only deployment is strongly preferred; direct public port forwarding is not recommended.

These measures were implemented in good faith, but the project has not had a professional security audit. You run this software at your own risk.

## Screenshots

| Desktop | Mobile |
|---|---|
| ![Desktop home dashboard](screenshots/1_desktop_home.png) | ![Mobile home dashboard](screenshots/1_mobile_home.png) |
| ![Desktop recipe library](screenshots/2_desktop_recipelibrary.png) | ![Mobile recipe library](screenshots/2_mobile_recipelibrary.png) |
| ![Desktop statistics dashboard](screenshots/3_desktop_statistics.png) | ![Mobile settings](screenshots/3_mobile_settings.png) |

![Desktop settings](screenshots/4_desktop_settings.png)

## Documentation

- [Deployment and operations guide](GUIDE.md)
- [Changelog](CHANGELOG.md)
- [Code of conduct](CODE_OF_CONDUCT.md)

## Tech Stack

FastAPI, React, Vite, SQLite, and Docker.
