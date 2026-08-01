"""One-off maintenance script: shrink existing recipe thumbnails that were
generated full-resolution by the pre-fix PDF thumbnail path (see
app/recipes/files.py::_generate_thumbnail). Safe to re-run — recipes whose
thumbnail is already <=400px on both sides are left untouched.

Run from inside the container:
    docker exec -it knitting-library python fix_oversized_pdf_thumbnails.py
"""
from PIL import Image

from app.core.foundation import DATA_DIR, get_db

MAX_DIM = 400


def main():
    conn = get_db()
    try:
        rows = conn.execute("SELECT id, title FROM recipes").fetchall()
        fixed = skipped = missing = 0
        for row in rows:
            thumb = DATA_DIR / row["id"] / "thumbnail.jpg"
            if not thumb.is_file():
                missing += 1
                continue
            with Image.open(thumb) as img:
                if img.width <= MAX_DIM and img.height <= MAX_DIM:
                    skipped += 1
                    continue
                img = img.convert("RGB")
                img.thumbnail((MAX_DIM, MAX_DIM))
                img.save(str(thumb), "JPEG", quality=85)
            conn.execute(
                "UPDATE recipes SET thumbnail_version = thumbnail_version + 1 WHERE id = ?",
                (row["id"],),
            )
            conn.commit()
            fixed += 1
            print(f"resized: {row['title']} ({row['id']})")
        print(f"\nDone. fixed={fixed} already_ok={skipped} no_thumbnail={missing}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
