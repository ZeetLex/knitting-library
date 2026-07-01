"""Yarn catalogue, colour variants, yarn images, and URL scraping workflows."""
from app.core.foundation import *
from app.auth.service import get_current_user, require_admin, _verify_token_param

def _yarn_to_dict(row, conn) -> dict:
    d = dict(row)
    d["colours"] = [dict(c) for c in conn.execute(
        "SELECT id, name, image_path, price FROM yarn_colours WHERE yarn_id=? ORDER BY created_date ASC",
        (d["id"],)
    ).fetchall()]
    return d


def list_yarns(
    search:           Optional[str] = None,
    field:            Optional[str] = None,
    filter_colour:    Optional[str] = None,
    filter_wool_type: Optional[str] = None,
    filter_seller:    Optional[str] = None,
    current_user:     dict = Depends(get_current_user)
):
    conn   = get_db()
    query  = "SELECT * FROM yarns WHERE 1=1"
    params = []
    if search:
        like = f"%{search}%"
        if field == "name":
            query += " AND name LIKE ?"; params.append(like)
        elif field == "colour":
            query += " AND colour LIKE ?"; params.append(like)
        elif field == "material":
            query += " AND (wool_type LIKE ? OR origin LIKE ?)"; params.extend([like, like])
        else:
            query += " AND (name LIKE ? OR colour LIKE ? OR wool_type LIKE ? OR origin LIKE ? OR product_info LIKE ? OR seller LIKE ?)"
            params.extend([like] * 6)
    if filter_colour:
        query += " AND colour=?"; params.append(filter_colour)
    if filter_wool_type:
        query += " AND wool_type=?"; params.append(filter_wool_type)
    if filter_seller:
        query += " AND seller=?"; params.append(filter_seller)
    query += " ORDER BY created_date DESC"
    result = [_yarn_to_dict(r, conn) for r in conn.execute(query, params).fetchall()]
    conn.close()
    return result


def yarn_autocomplete(field: str, current_user: dict = Depends(get_current_user)):
    allowed = {"name", "colour", "wool_type", "origin", "seller"}
    if field not in allowed:
        raise HTTPException(status_code=400, detail="Invalid field")
    conn = get_db()
    rows = conn.execute(
        f"SELECT DISTINCT {field} FROM yarns WHERE {field} != '' ORDER BY {field}"
    ).fetchall()
    conn.close()
    return {"values": [r[field] for r in rows]}


def get_yarn(yarn_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    row  = conn.execute("SELECT * FROM yarns WHERE id=?", (yarn_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Yarn not found")
    result = _yarn_to_dict(row, conn)
    conn.close()
    return result


async def create_yarn(
    name:            str            = Form(...),
    colour:          str            = Form(""),
    wool_type:       str            = Form(""),
    yardage:         str            = Form(""),
    needles:         str            = Form(""),
    tension:         str            = Form(""),
    origin:          str            = Form(""),
    seller:          str            = Form(""),
    price_per_skein: str            = Form(""),
    product_info:    str            = Form(""),
    image:           Optional[UploadFile] = File(None),
    current_user:    dict           = Depends(get_current_user)
):
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    yarn_id  = str(uuid.uuid4())
    img_path = ""
    if image and image.filename:
        ext = Path(image.filename).suffix.lower()
        if ext not in IMAGE_EXTS:
            raise HTTPException(status_code=400, detail="Only jpg, png, webp images are accepted")
        file_data = await image.read()
        if len(file_data) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail="Image file too large (max 20 MB)")
        if not _validate_file_magic(file_data, ext):
            raise HTTPException(status_code=400, detail="File content does not match its extension")
        yarn_dir = YARN_DIR / yarn_id
        yarn_dir.mkdir(parents=True, exist_ok=True)
        dest = yarn_dir / f"yarn{ext}"
        with open(dest, "wb") as fh:
            fh.write(file_data)
        img_path = f"{yarn_id}/yarn{ext}"
    conn = get_db()
    conn.execute(
        "INSERT INTO yarns (id,name,colour,wool_type,yardage,needles,tension,origin,seller,price_per_skein,product_info,image_path,created_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (yarn_id, name, colour, wool_type, yardage, needles, tension, origin,
         seller, price_per_skein, product_info, img_path, datetime.utcnow().isoformat())
    )
    conn.commit()
    result = _yarn_to_dict(conn.execute("SELECT * FROM yarns WHERE id=?", (yarn_id,)).fetchone(), conn)
    conn.close()
    return result


async def update_yarn(
    yarn_id:         str,
    name:            str            = Form(""),
    colour:          str            = Form(""),
    wool_type:       str            = Form(""),
    yardage:         str            = Form(""),
    needles:         str            = Form(""),
    tension:         str            = Form(""),
    origin:          str            = Form(""),
    seller:          str            = Form(""),
    price_per_skein: str            = Form(""),
    product_info:    str            = Form(""),
    image:           Optional[UploadFile] = File(None),
    current_user:    dict           = Depends(get_current_user)
):
    conn = get_db()
    if not conn.execute("SELECT id FROM yarns WHERE id=?", (yarn_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Yarn not found")
    if image and image.filename:
        ext = Path(image.filename).suffix.lower()
        if ext not in IMAGE_EXTS:
            conn.close()
            raise HTTPException(status_code=400, detail="Only jpg, png, webp images are accepted")
        file_data = await image.read()
        if len(file_data) > MAX_IMAGE_BYTES:
            conn.close()
            raise HTTPException(status_code=413, detail="Image file too large (max 20 MB)")
        if not _validate_file_magic(file_data, ext):
            conn.close()
            raise HTTPException(status_code=400, detail="File content does not match its extension")
        yarn_dir = YARN_DIR / yarn_id
        yarn_dir.mkdir(parents=True, exist_ok=True)
        dest = yarn_dir / f"yarn{ext}"
        with open(dest, "wb") as fh:
            fh.write(file_data)
        img_path = f"{yarn_id}/yarn{ext}"
        conn.execute(
            "UPDATE yarns SET name=?,colour=?,wool_type=?,yardage=?,needles=?,tension=?,origin=?,seller=?,price_per_skein=?,product_info=?,image_path=? WHERE id=?",
            (name, colour, wool_type, yardage, needles, tension, origin, seller,
             price_per_skein, product_info, img_path, yarn_id)
        )
    else:
        conn.execute(
            "UPDATE yarns SET name=?,colour=?,wool_type=?,yardage=?,needles=?,tension=?,origin=?,seller=?,price_per_skein=?,product_info=? WHERE id=?",
            (name, colour, wool_type, yardage, needles, tension, origin, seller,
             price_per_skein, product_info, yarn_id)
        )
    conn.commit()
    result = _yarn_to_dict(conn.execute("SELECT * FROM yarns WHERE id=?", (yarn_id,)).fetchone(), conn)
    conn.close()
    return result


def delete_yarn(yarn_id: str, current_user: dict = Depends(get_current_user)):
    conn     = get_db()
    yarn_dir = YARN_DIR / yarn_id
    conn.execute("DELETE FROM yarn_colours WHERE yarn_id=?", (yarn_id,))
    conn.execute("DELETE FROM yarns        WHERE id=?",      (yarn_id,))
    conn.commit()
    conn.close()
    if yarn_dir.exists():
        shutil.rmtree(yarn_dir)
    return {"message": "Yarn deleted"}


def get_yarn_image(yarn_id: str, request: Request, token: Optional[str] = None):
    _verify_token_param(request, token)
    yarn_dir = YARN_DIR / yarn_id
    for name in ("thumbnail.jpg", "yarn.jpg", "yarn.jpeg", "yarn.png", "yarn.webp"):
        p = yarn_dir / name
        if p.exists():
            mt = "image/jpeg" if name.endswith((".jpg",".jpeg")) else "image/png" if name.endswith(".png") else "image/webp"
            return FileResponse(str(p), media_type=mt)
    raise HTTPException(status_code=404, detail="No image")

# ── Yarn colours ──────────────────────────────────────────────────────────────

def list_yarn_colours(yarn_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute("SELECT * FROM yarn_colours WHERE yarn_id=? ORDER BY created_date ASC", (yarn_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_yarn_colour(yarn_id: str, body: dict = Body(...), current_user: dict = Depends(get_current_user)):
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    colour_id = str(uuid.uuid4())
    conn      = get_db()
    conn.execute(
        "INSERT INTO yarn_colours (id,yarn_id,name,image_path,price,created_date) VALUES (?,?,?,?,?,?)",
        (colour_id, yarn_id, name, body.get("image_path",""), body.get("price",""), datetime.utcnow().isoformat())
    )
    conn.commit()
    result = dict(conn.execute("SELECT * FROM yarn_colours WHERE id=?", (colour_id,)).fetchone())
    conn.close()
    return result


def update_yarn_colour(yarn_id: str, colour_id: str, body: dict = Body(...), current_user: dict = Depends(get_current_user)):
    conn = get_db()
    if not conn.execute("SELECT id FROM yarn_colours WHERE id=? AND yarn_id=?", (colour_id, yarn_id)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Colour not found")
    conn.execute(
        "UPDATE yarn_colours SET name=?, image_path=?, price=? WHERE id=?",
        (body.get("name",""), body.get("image_path",""), body.get("price",""), colour_id)
    )
    conn.commit()
    result = dict(conn.execute("SELECT * FROM yarn_colours WHERE id=?", (colour_id,)).fetchone())
    conn.close()
    return result


def delete_yarn_colour(yarn_id: str, colour_id: str, current_user: dict = Depends(get_current_user)):
    conn   = get_db()
    colour = conn.execute("SELECT image_path FROM yarn_colours WHERE id=? AND yarn_id=?", (colour_id, yarn_id)).fetchone()
    if not colour:
        conn.close()
        raise HTTPException(status_code=404, detail="Colour not found")
    image_path = colour["image_path"]
    conn.execute("DELETE FROM yarn_colours WHERE id=?", (colour_id,))
    conn.commit()
    conn.close()
    if image_path:
        p = Path(image_path) if Path(image_path).is_absolute() else YARN_DIR / image_path
        p.unlink(missing_ok=True)
    return {"message": "Colour deleted"}


async def upload_colour_image(
    yarn_id:   str,
    colour_id: str,
    file:      UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    conn = get_db()
    if not conn.execute("SELECT id FROM yarn_colours WHERE id=? AND yarn_id=?", (colour_id, yarn_id)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Colour not found")
    colour_dir = YARN_DIR / yarn_id / "colours" / colour_id
    colour_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename).suffix.lower()
    if ext not in IMAGE_EXTS:
        raise HTTPException(status_code=400, detail="Only jpg, png, webp images are accepted")
    file_data = await file.read()
    if len(file_data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image file too large (max 20 MB)")
    if not _validate_file_magic(file_data, ext):
        raise HTTPException(status_code=400, detail="File content does not match its extension")
    dest = colour_dir / f"colour{ext}"
    with open(dest, "wb") as f:
        f.write(file_data)
    rel_path = str(dest.relative_to(YARN_DIR))
    conn.execute("UPDATE yarn_colours SET image_path=? WHERE id=?", (rel_path, colour_id))
    conn.commit()
    conn.close()
    return {"image_path": rel_path}


def get_colour_image(yarn_id: str, colour_id: str, request: Request, token: Optional[str] = None):
    _verify_token_param(request, token)
    conn   = get_db()
    colour = conn.execute("SELECT image_path FROM yarn_colours WHERE id=? AND yarn_id=?", (colour_id, yarn_id)).fetchone()
    conn.close()
    if not colour or not colour["image_path"]:
        raise HTTPException(status_code=404, detail="No image")
    path = YARN_DIR / colour["image_path"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image file not found")
    ext = path.suffix.lower()
    mt  = "image/jpeg" if ext in (".jpg",".jpeg") else "image/png" if ext == ".png" else "image/webp"
    return FileResponse(str(path), media_type=mt)


async def upload_yarn_image(
    yarn_id: str,
    file:    UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    conn = get_db()
    if not conn.execute("SELECT id FROM yarns WHERE id=?", (yarn_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Yarn not found")
    yarn_dir = YARN_DIR / yarn_id
    yarn_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename).suffix.lower()
    if ext not in IMAGE_EXTS:
        raise HTTPException(status_code=400, detail="Only jpg, png, webp images are accepted")
    file_data = await file.read()
    if len(file_data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image file too large (max 20 MB)")
    if not _validate_file_magic(file_data, ext):
        raise HTTPException(status_code=400, detail="File content does not match its extension")
    dest = yarn_dir / f"yarn{ext}"
    with open(dest, "wb") as f:
        f.write(file_data)
    rel_path = f"{yarn_id}/yarn{ext}"
    conn.execute("UPDATE yarns SET image_path=? WHERE id=?", (rel_path, yarn_id))
    conn.commit()
    conn.close()
    return {"image_path": rel_path}

# ── Inventory ─────────────────────────────────────────────────────────────────


async def scrape_yarn_url(body: dict = Body(...), current_user: dict = Depends(get_current_user)):
    """Fetch a yarn product page and extract key fields.
    Strategy 1: Shopify JSON API  (fast, structured).
    Strategy 2: HTML scraping fallback."""
    url = (body.get("url") or "").strip()
    url = _validate_public_url(url)
    parsed = urlparse(url)

    headers = {
        "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Accept-Language": "nb-NO,nb;q=0.9,no;q=0.8,en;q=0.7",
    }

    label_map = {
        "løpelengde": "yardage",  "run length": "yardage",  "meterage": "yardage",  "yardage": "yardage",
        "veiledende pinner": "needles", "anbefalt pinnestørrelse": "needles",
        "needle size": "needles", "pinner": "needles",
        "strikkefasthet": "tension", "gauge": "tension", "tension": "tension",
        "råvare kommer fra": "origin", "raw material": "origin", "opprinnelse": "origin",
        "sammensetning": "wool_type", "composition": "wool_type",
        "fiber content": "wool_type", "material": "wool_type",
    }

    def _clean(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip() if s else ""

    def _parse_specs(soup, result: dict):
        for el in soup.find_all(["li", "dt", "dd", "p", "span", "td", "th"]):
            text = _clean(el.get_text())
            if ":" in text:
                k, _, v = text.partition(":")
                for label, field in label_map.items():
                    if label in k.strip().lower() and field not in result and v.strip():
                        result[field] = v.strip()
                        break

    async def _safe_get(client: httpx.AsyncClient, start_url: str, expected: tuple[str, ...]):
        current = _validate_public_url(start_url)
        for _ in range(4):
            resp = await client.get(current, headers=headers)
            if resp.is_redirect:
                location = resp.headers.get("location", "")
                if not location:
                    raise HTTPException(status_code=502, detail="Redirect missing location")
                current = _validate_public_url(urljoin(current, location))
                continue
            ctype = resp.headers.get("content-type", "").lower()
            if expected and not any(kind in ctype for kind in expected):
                raise HTTPException(status_code=415, detail="Unsupported response type")
            if len(resp.content) > MAX_SCRAPE_BYTES:
                raise HTTPException(status_code=413, detail="Response too large")
            return resp
        raise HTTPException(status_code=400, detail="Too many redirects")

    handle      = parsed.path.strip("/").split("/")[-1].split("?")[0]
    shopify_url = f"{parsed.scheme}://{parsed.netloc}/products/{handle}.json"

    # Strategy 1: Shopify JSON API
    try:
        async with httpx.AsyncClient(follow_redirects=False, timeout=10) as client:
            sj = await _safe_get(client, shopify_url, ("application/json", "text/json"))
        if sj.status_code == 200:
            product = sj.json().get("product", {})
            if product.get("title"):
                result: dict = {"name": product["title"]}
                if product.get("vendor"):
                    result["seller"] = product["vendor"]
                if product.get("body_html"):
                    soup = BeautifulSoup(product["body_html"], "html.parser")
                    _parse_specs(soup, result)
                    plain = _clean(soup.get_text(" "))
                    if plain:
                        result["product_info"] = plain[:1000]
                images = product.get("images", [])
                if images:
                    src = re.sub(r"_\d+x\d+(\.[a-z]+)$", r"\1", images[0].get("src", ""))
                    if src:
                        result["scraped_image_url"] = src
                        result["image_url"] = src
                return result
    except Exception:
        pass

    # Strategy 2: HTML scraping
    try:
        async with httpx.AsyncClient(follow_redirects=False, timeout=10) as client:
            resp = await _safe_get(client, url, ("text/html", "application/xhtml+xml"))
        soup   = BeautifulSoup(resp.text, "html.parser")
        result = {}
        h1     = soup.find("h1")
        if h1:
            result["name"] = _clean(h1.get_text())
        _parse_specs(soup, result)
        meta = soup.find("meta", {"property": "og:image"}) or soup.find("meta", {"name": "og:image"})
        if meta and meta.get("content"):
            result["scraped_image_url"] = meta["content"]
            result["image_url"] = meta["content"]
        if not result.get("name"):
            raise HTTPException(status_code=422, detail="Could not extract product name from page")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch URL: {e}")

# ── Admin: live logs ──────────────────────────────────────────────────────────


__all__ = [name for name in globals() if not name.startswith("__")]
