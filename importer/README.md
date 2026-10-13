# Knit Import

A small web app that adds DROPS Design patterns to Knitting Library. For personal use.

Mary pastes a pattern link. The importer fetches the pattern, makes a PDF, reads the instructions, tags and videos, and adds the lot to Knitting Library. She checks the details first.

## The three stages

1. **Get pattern.** Paste a link from garnstudio.com. The importer fetches the pattern page and the print view, one request at a time, and makes the PDF itself.
   If DROPS refuses the request, the screen switches to a guided route. It tells Mary how to save the PDF and the page herself, accepts both files, and checks each one (is it a PDF, is it from DROPS, is it the same pattern, are tags and videos present).
2. **Check details.** Title, description, categories, tags and the cover picture. Everything the importer found is listed, with anything doubtful marked.
3. **Add to library.** The PDF, the instructions as text, the tags, categories and cover picture go into Knitting Library. The yarns are added to its yarn list. A duplicate is flagged first. If a step fails, trying again carries on from where it stopped.

## What it needs

* Knitting Library, with the patched image built from this fork (see `FORK.md` at the top of the repository). Two changes matter:
  * Tags are only saved with the one-line fix in the first patch commit. Without it, imported tags are silently dropped.
  * Video and yarn links in the text version are only clickable with the second patch commit.
* A normal (non-admin) Knitting Library user for the importer, for example `importer`.
* Protection in front of it. The importer has **no sign-in of its own**. Put it behind Pangolin with SSO, as with Knitting Library. Anyone who can open it can add patterns to the library.

## Where it lives

Mary can reach the importer from inside Knitting Library. The library has an **Import from DROPS** link in its sidebar and in its Add menu. Both go to `/import/` on the same address, for example `https://knit.wighttrash.uk/import/`. The importer has a **Back to library** link in return.

That needs one extra target on the existing Pangolin resource. In Pangolin, open the resource for the library and add a target:

| Field | Value |
| --- | --- |
| Site | the same site (Newt) as the library |
| Method, host, port | `http`, the NAS address, `31952` (the importer's published port in `deploy/docker-compose.yml`). If Newt shares the `knit` Docker network, use `knit-import` and `8080` instead |
| Path | `/import` |
| Path match | `prefix` |
| Rewrite | none |

Leave the library's own target as it is. The Pangolin docs say a path match ranks above the plain `/` target, so `/import/...` goes to the importer and everything else goes to the library. Source: https://docs.pangolin.net/manage/resources/public/targets.md

Notes:

* Do not add a rewrite. The importer accepts requests with or without `/import` in front, so it does not need one. With `stripPrefix` the page still loads from `/import/`, but `/import` without the slash would not redirect.
* The importer has no sign-in of its own, so Pangolin's sign-in has to cover `/import/`. The Pangolin docs describe authentication as a resource setting but do not say outright that it covers every path. Check it: open `/import/` in a private window. You should land on the SSO sign-in page. If you do not, stop and fix that before using it.
* The importer reaches the library over the Docker network (`KL_URL`), not through Pangolin, so the two apps sharing an address changes nothing there.
* Own hostname instead: create a second resource, for example `knit-import.wighttrash.uk`, pointing at the same importer address and port. It works with no changes. The link in the library goes to `/import/` on the library's address, so it only helps if the path target above exists too.
* The importer and the library share an origin when served this way. The importer writes page text with `textContent` and sends a strict Content-Security-Policy, so pattern text cannot run as script.

## Settings

Environment variables.

| Variable | Default | What it does |
| --- | --- | --- |
| `KL_URL` | `http://knitting-library:8080` | Where Knitting Library is, on the private network |
| `KL_PUBLIC_URL` | same as `KL_URL` | Address for the "Open Knitting Library" button |
| `BASE_PATH` | `/import` | Prefix it also answers on. Leave as is for the same-address route. Use an empty value to switch it off |
| `KL_USERNAME` / `KL_PASSWORD` | `importer` / none | The importer's Knitting Library account |
| `DATA_DIR` | `/data` | Drafts and a 24 hour page cache |
| `DRAFT_TTL_HOURS` | `24` | How long unfinished patterns are kept |
| `DROPS_FETCH_ENABLED` | `true` | Set to `false` to always use the guided manual route |
| `DROPS_MIN_INTERVAL` | `3` | Seconds between requests to DROPS |
| `DROPS_CONTACT` | none | Optional email address, added to the User-Agent |
| `DROPS_DEFAULT_CID` | `19` | Catalogue used when a link has none (19 is English, UK, cm and grams) |
| `MAX_UPLOAD_MB` | `50` | Knitting Library refuses PDFs above 50 MB |
| `CHROMIUM_PATH` | `/usr/bin/chromium` | The browser that makes the PDF |

## How it behaves towards DROPS

* One pattern per click. One request at a time, with a pause between requests. Pages are cached for 24 hours.
* An honest User-Agent. No cookie tricks, and no headless browser is pointed at the DROPS site.
* Chromium only prints a local copy of the page with the network switched off. It never talks to DROPS.
* If DROPS answers with a refusal, a rate limit or a human check, the importer stops and uses the guided manual route. It never tries to get round it.
* The DROPS copyright notice allows printing but not reproducing a complete pattern digitally. A private library goes beyond that notice. That was a decision for the owner of this setup, and it is the reason the app is for personal use only.

## Running it

```
docker compose -f docker-compose.example.yml up -d --build
```

Or for development, with a pretend DROPS and a pretend Knitting Library, to look at the screens:

```
pip install -r requirements-dev.txt
python dev/devserver.py          # http://127.0.0.1:8099
pytest
```

`dev/e2e_real_kl.py` runs the whole flow against a real Knitting Library on 127.0.0.1:8089.

## Layout

```
app/main.py            web API and page
app/pipeline.py        the three stages
app/drops/             link checks, polite fetcher, page readers, PDF maker, upload checks
app/kl/                Knitting Library client, text version builder
app/static/            the screens
tests/                 fixtures are one saved DROPS pattern, for private testing only
```

## Known limits

* The DROPS site structure was learned from one saved pattern (Sage Leaf Sweater). Other pattern types (crochet, accessories, charts only) are untested. Each pattern gets checks, so odd ones should show warnings, not wrong data.
* Live fetching from garnstudio.com has not been tested from the NAS. The test server stands in for it.
* The Docker image has not been built yet.
* Yarn matching adds the yarns and colours to the yarn list. Matching against stock is not built, because Knitting Library counts skeins and DROPS patterns give grams.
* Ravelry is not included.
