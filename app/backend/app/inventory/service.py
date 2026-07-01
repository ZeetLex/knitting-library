"""Inventory CRUD and stock adjustment workflows."""
from app.core.foundation import *
from app.auth.service import get_current_user, require_admin, _verify_token_param

def _inventory_to_dict(row, conn) -> dict:
    d = dict(row)
    if d.get("type") == "yarn":
        yarn   = conn.execute("SELECT name FROM yarns WHERE id=?", (d["yarn_id"],)).fetchone() if d.get("yarn_id") else None
        colour = conn.execute("SELECT name, image_path FROM yarn_colours WHERE id=?", (d["yarn_colour_id"],)).fetchone() if d.get("yarn_colour_id") else None
        d["yarn_name"]         = yarn["name"]         if yarn   else ""
        d["colour_name"]       = colour["name"]       if colour else ""
        d["colour_image_path"] = colour["image_path"] if colour else ""
    return d


def list_inventory(
    type:   Optional[str] = None,
    search: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    conn   = get_db()
    query  = "SELECT * FROM inventory_items WHERE 1=1"
    params = []
    if type:
        query += " AND type=?"; params.append(type)
    if search:
        like   = f"%{search}%"
        query += " AND (name LIKE ? OR notes LIKE ?)"; params.extend([like, like])
    query += " ORDER BY created_date DESC"
    result = [_inventory_to_dict(r, conn) for r in conn.execute(query, params).fetchall()]
    conn.close()
    return result


def get_inventory_item(item_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    row  = conn.execute("SELECT * FROM inventory_items WHERE id=?", (item_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Item not found")
    result = _inventory_to_dict(row, conn)
    conn.close()
    return result


def get_inventory_log(item_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute(
        "SELECT l.*, r.title as recipe_title FROM inventory_log l LEFT JOIN recipes r ON l.recipe_id=r.id WHERE l.item_id=? ORDER BY l.created_at DESC",
        (item_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_inventory_item(body: dict = Body(...), current_user: dict = Depends(get_current_user)):
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    item_id = str(uuid.uuid4())
    qty     = int(body.get("quantity", 0))
    now     = datetime.utcnow().isoformat()
    conn    = get_db()
    conn.execute(
        "INSERT INTO inventory_items (id,type,yarn_id,yarn_colour_id,category,name,quantity,purchase_date,purchase_price,purchase_note,notes,created_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (item_id, body.get("type","yarn"), body.get("yarn_id") or None, body.get("yarn_colour_id") or None,
         body.get("category",""), name, qty, body.get("purchase_date",""), body.get("purchase_price",""),
         body.get("purchase_note",""), body.get("notes",""), now)
    )
    if qty > 0:
        conn.execute(
            "INSERT INTO inventory_log (id,item_id,change,reason,note,created_at) VALUES (?,?,?,?,?,?)",
            (str(uuid.uuid4()), item_id, qty, "added", "Initial stock", now)
        )
    conn.commit()
    result = _inventory_to_dict(conn.execute("SELECT * FROM inventory_items WHERE id=?", (item_id,)).fetchone(), conn)
    conn.close()
    return result


def update_inventory_item(item_id: str, body: dict = Body(...), current_user: dict = Depends(get_current_user)):
    conn = get_db()
    row  = conn.execute("SELECT * FROM inventory_items WHERE id=?", (item_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Item not found")
    conn.execute(
        "UPDATE inventory_items SET category=?,name=?,purchase_date=?,purchase_price=?,purchase_note=?,notes=?,yarn_id=?,yarn_colour_id=? WHERE id=?",
        (body.get("category",       row["category"]),
         (body.get("name",          row["name"]) or "").strip() or row["name"],
         body.get("purchase_date",  row["purchase_date"]),
         body.get("purchase_price", row["purchase_price"]),
         body.get("purchase_note",  row["purchase_note"]),
         body.get("notes",          row["notes"]),
         body.get("yarn_id")        or row["yarn_id"],
         body.get("yarn_colour_id") or row["yarn_colour_id"],
         item_id)
    )
    conn.commit()
    result = _inventory_to_dict(conn.execute("SELECT * FROM inventory_items WHERE id=?", (item_id,)).fetchone(), conn)
    conn.close()
    return result


def adjust_inventory(item_id: str, body: dict = Body(...), current_user: dict = Depends(get_current_user)):
    conn   = get_db()
    row    = conn.execute("SELECT * FROM inventory_items WHERE id=?", (item_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Item not found")
    change = int(body.get("change", 0))
    if change == 0:
        conn.close()
        raise HTTPException(status_code=400, detail="change cannot be 0")
    now = datetime.utcnow().isoformat()
    conn.execute("UPDATE inventory_items SET quantity=? WHERE id=?", (max(0, row["quantity"] + change), item_id))
    conn.execute(
        "INSERT INTO inventory_log (id,item_id,change,reason,recipe_id,session_id,note,created_at) VALUES (?,?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), item_id, change, body.get("reason","manual"),
         body.get("recipe_id") or None, body.get("session_id") or None, body.get("note",""), now)
    )
    conn.commit()
    result = _inventory_to_dict(conn.execute("SELECT * FROM inventory_items WHERE id=?", (item_id,)).fetchone(), conn)
    conn.close()
    return result


def delete_inventory_item(item_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    if not conn.execute("SELECT id FROM inventory_items WHERE id=?", (item_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Item not found")
    conn.execute("DELETE FROM inventory_log   WHERE item_id=?", (item_id,))
    conn.execute("DELETE FROM inventory_items WHERE id=?",      (item_id,))
    conn.commit()
    conn.close()
    return {"message": "Deleted"}

# ── Yarn URL scraper ──────────────────────────────────────────────────────────


__all__ = [name for name in globals() if not name.startswith("__")]
