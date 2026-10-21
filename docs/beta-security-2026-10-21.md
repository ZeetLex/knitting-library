# Beta security verification — 21 October 2026

Release scope: GitHub `beta` and Docker Hub `zeetlex/knitting-library:beta` only.
`main` and `latest` are not promoted by this change.

## Baseline

- Image index: `sha256:c29e50efd266d0813e7a7a8702ff01ad1f679d8c845aa431e0dc560f86a72ff3`
- Runtime platform: `linux/amd64` (the other manifest is a provenance attestation).
- Runtime manifest: `sha256:da7b61b8d009b42822954e1b29dbe763dae9fb4a38eba79385c3c0205e6e1896`
- Docker Scout found 23 vulnerabilities across 10 packages.

Keep the previous index digest available for rollback.

## Changes

- Pillow 13.0.0 and Certifi 2026.10.19 address the reported Python findings.
- Refresh Alpine 3.24 packages, including Expat, LibXrender, LibX11, zlib,
  OpenJPEG and libpng. Preserve PDF conversion and image-processing libraries.
- Pin Python 3.12 and Node 24 base images by digest; constrain Python runtime
  dependencies to the tested resolution and update the npm lockfile.
- Remove compiler and packaging tools after installation. Do not strip scanner
  metadata or suppress installation/cleanup failures.
- Patch Vite, fast-uri and source-map-js. The frontend npm audit reports zero
  vulnerabilities.
- The standalone ChatGPT diagnostic uses patched PyJWT 2.15.1.

## Remaining findings

The rebuilt candidate has 2 vulnerabilities, with no critical or high findings.
Neither remaining finding has a fixed version in the Alpine 3.24 Scout feed:

| Advisory | Package | Severity | Fixed version |
| --- | --- | --- | --- |
| CVE-2025-50422 | cairo 1.18.4-r1 | Low | Not available |
| CVE-2006-5201 | nss 3.124-r0 | Medium | Not available |

These libraries are dependencies of the supported PDF toolchain. They remain
visible in scans; no scanner exclusions or package-metadata edits are used.

## Validation

- 71 backend tests pass in the candidate Linux image, including 15 isolated
  subscription integration scenarios, JPEG/image and
  PDF conversion, SMTP certificate verification, deployment paths, saved-text
  visibility, and standalone OAuth protocol tests.
- 14 frontend viewer tests pass.
- Six locales validate and the Vite production build succeeds.
- Live Windows OpenAI sign-in, encrypted Docker import, token refresh, two-page
  subscription OCR, review/publication and container restart pass. A physical NAS
  was unavailable for a separate device-specific check.
- Approval bypasses, changed sources/settings, usage-limit recovery, stream
  cancellation/incomplete output, redaction, serialized refresh, revocation and
  credential path isolation are covered by tests.
- Repeat the scan and container smoke check on the exact revision-labeled image
  before moving the public beta tag. Capture its published digest in the release
  handoff.

## ChatGPT setup

The beta includes an administrator-only Windows-to-server connection wizard and
packaged Windows helper. See [setup and recovery](../tools/CHATGPT-SETUP.md).
Household jobs require the connection owner's approval; there is no automatic
paid-API fallback. Runtime credentials are encrypted outside static/export data.

## Reproduce

```sh
docker scout cves registry://zeetlex/knitting-library:beta --platform linux/amd64
docker run --rm --entrypoint python zeetlex/knitting-library:beta -m unittest discover -s tests
```
