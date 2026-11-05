# Security release — 5 November 2026

Promote the existing beta fixes and features to `main`, and publish the same
linux/amd64 image to Docker Hub `zeetlex/knitting-library:beta` and `:latest`.
The clean local beta checkout was fetched and verified against origin first.

## GitHub alerts

All 54 open Dependabot alerts concern versions on the older default branch.
Beta already contains every required patch; promote these fixes rather than
unnecessarily changing the tested dependency resolution.

| Package | Alerts | Required fixed version | Release version |
| --- | ---: | --- | --- |
| Pillow | 41 | 13.0.0 | 13.0.0 |
| fast-uri | 7 | up to 3.1.9 | 3.1.9 |
| Vite | 5 | 6.4.4 | 6.4.5 |
| source-map-js | 1 | 1.2.2 | 1.2.2 |

No open code-scanning or secret-scanning alerts were returned by GitHub.
Dependabot must re-evaluate the promoted default branch before its UI clears.

## Image rebuild and scan

Rebuilt without cache so `apk upgrade` installs current Alpine 3.24 packages,
including musl 1.2.6-r3, zlib 1.3.2-r1 and current CA certificates.
Python constraints and the npm lockfile remain unchanged.

Docker Scout reports four findings (0 critical, 1 high, 1 medium, 1 low,
1 unspecified). Preserve scanner visibility; no findings are suppressed.

| Advisory | Package | Assessment |
| --- | --- | --- |
| CVE-2026-119586 | sqlite 3.53.4-r0 | High; no fix in the configured Alpine repository. The advisory concerns CLI `.recover` output. The image contains sqlite-libs for Python, but no sqlite3 CLI; the application does not use the affected recovery workflow. |
| CVE-2006-5201 | nss 3.124-r0 | Medium; PDF-toolchain dependency, no fix offered by the current Alpine repository/Scout feed. |
| CVE-2025-50422 | cairo 1.18.4-r1 | Low; PDF-toolchain dependency, no fix offered by the current Alpine repository/Scout feed. |
| CVE-2026-107891 | musl 1.2.6-r3 | Scout uses the edge fixed version 1.2.6-r6. Alpine explicitly marks 1.2.6-r3 fixed on branch 3.24; this is a branch-version mismatch in the scan. |

Sources: [Alpine musl security status](https://security.alpinelinux.org/vuln/CVE-2026-107891),
[SQLite advisory](https://explore.alas.aws.amazon.com/CVE-2026-119586.html).

## Validation

- npm audit: zero findings across production and development dependencies.
- 18 frontend policy/viewer tests and the actual JSX renderer check pass.
- All six locales validate; the Vite production build succeeds.
- 71 backend tests pass inside the rebuilt Linux image.
- Normal entrypoint starts successfully; frontend returns HTTP 200, protected
  auth endpoint returns HTTP 401, and the initialized database passes SQLite
  integrity_check. Smoke testing uses isolated container data.
- No paid AI requests or production data are used for release verification.

## Previous published digests for rollback

- latest: `sha256:c29e50efd266d0813e7a7a8702ff01ad1f679d8c845aa431e0dc560f86a72ff3`
- beta: `sha256:535418e986e32c6fb4dbf935f75afcbf8c64132e0ca554a4ec57d942afee62f2`

Before promotion, main was `ac3ce9f82bc57598de463ba9f6fab6280bc045a7`
and beta was `6695f64e04539c59d010a6d9965cc3041ca285e9`.
