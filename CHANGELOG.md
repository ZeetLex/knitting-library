# Changelog

## Unreleased

### Localization
- Added Hungarian (`hu`) as a selectable interface language.
- Added Hungarian Forint (`HUF`) and Euro (`EUR`) as selectable currencies.

### Security
- Removed the default `admin/admin` first-run account. New installs now create the first admin through the setup screen.
- Added HttpOnly SameSite session cookies, CSRF protection for cookie-authenticated write requests, and retained legacy `X-Session-Token` support for compatibility.
- Removed session tokens from frontend media and download URLs.
- Added trusted proxy handling through `TRUSTED_PROXIES`; forwarded client IP and HTTPS headers are ignored unless the sender is trusted.
- Hardened the yarn URL scraper against SSRF by validating schemes, DNS results, blocked IP ranges, redirects, response sizes, and content types.
- Redacted sensitive token query values from request/admin log output.
- Moved the runtime Docker base to the current `python:3.12-alpine` image and refreshed base layers to pick up Alpine security fixes.

### Dependencies
- Upgraded the PDF viewer stack to `react-pdf` 10.4.1 / `pdfjs-dist` 5.4.296.
- Upgraded python-multipart to 0.0.31 for multipart upload resource-handling fixes.
- Upgraded Pillow to 12.2.0 for image-processing security fixes.
- Replaced Create React App / `react-scripts` with Vite to remove the remaining frontend audit vulnerability cluster.
- Added and enforced `app/frontend/package-lock.json`; Docker frontend builds now use `npm ci`.

### Documentation
- Updated self-hosting documentation for first-run setup, backups, reverse proxy usage, `TRUSTED_PROXIES`, HTTPS, Nginx Proxy Manager, Caddy, and safer pinned-image upgrades.
- Updated feature documentation to reflect Hungarian language support and the expanded currency list.
- Added `.env.example` with proxy and origin configuration examples.
