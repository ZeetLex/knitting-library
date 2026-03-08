"""
Knitting Recipe Library - Backend API
Built with FastAPI (Python)

This file is the main entry point for the backend server.
It handles all API routes: uploading recipes, searching, and serving files.
"""

import os
import uuid
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import sqlite3

# ─── App Setup ───────────────────────────────────────────────────────────────

app = FastAPI(title="Knitting Recipe Library", version="1.0.0")

# Allow the frontend (running on a different port) to talk to the backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Where all recipe files are stored (this folder is a Docker volume)
DATA_DIR = Path("/data/recipes")
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = Path("/data/recipes.db")


# ─── Database Setup ───────────────────────────────────────────────────────────

def get_db():
    """Open a connection to the SQLite database."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row  # Makes rows behave like dictionaries
    return conn


def init_db():
    """Create the database tables if they don't already exist."""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS recipes (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            file_type TEXT NOT NULL,
            thumbnail_path TEXT DEFAULT '',
            created_date TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );

        CREATE TABLE IF NOT EXISTS recipe_categories (
            recipe_id TEXT,
            category_id INTEGER,
            PRIMARY KEY (recipe_id, category_id),
            FOREIGN KEY (recipe_id) REFERENCES recipes(id),
            FOREIGN KEY (category_id) REFERENCES categories(id)
        );

        CREATE TABLE IF NOT EXISTS recipe_tags (
            recipe_id TEXT,
            tag_id INTEGER,
            PRIMARY KEY (recipe_id, tag_id),
            FOREIGN KEY (recipe_id) REFERENCES recipes(id),
            FOREIGN KEY (tag_id) REFERENCES tags(id)
        );

        -- Insert default categories if they don't exist
        INSERT OR IGNORE INTO categories (name) VALUES
            ('Socks'), ('Sweater'), ('Hat'), ('Mittens'), ('Scarf'),
            ('Shawl'), ('Blanket'), ('Cardigan'), ('Cowl'), ('Other');
    """)
    conn.commit()
    conn.close()


# Run database setup when the server starts
init_db()


# ─── Helper Functions ─────────────────────────────────────────────────────────

def generate_thumbnail(recipe_dir: Path, file_type: str, files: list) -> str:
    """
    Generate a thumbnail for the recipe card grid.
    - For PDFs: converts first page to an image using pdf2image
    - For images: copies the first image as the thumbnail
    Returns the relative path to the thumbnail.
    """
    thumb_path = recipe_dir / "thumbnail.jpg"

    if file_type == "pdf":
        try:
            from pdf2image import convert_from_path
            pdf_file = next(recipe_dir.glob("*.pdf"), None)
            if pdf_file:
                pages = convert_from_path(str(pdf_file), first_page=1, last_page=1, dpi=150)
                if pages:
                    pages[0].save(str(thumb_path), "JPEG", quality=85)
                    return "thumbnail.jpg"
        except Exception as e:
            print(f"PDF thumbnail generation failed: {e}")

    elif file_type == "images":
        # Use the first image file as the thumbnail
        image_extensions = [".jpg", ".jpeg", ".png", ".webp"]
        for ext in image_extensions:
            image_files = sorted(recipe_dir.glob(f"*{ext}"))
            if image_files:
                try:
                    from PIL import Image
                    img = Image.open(image_files[0])
                    img.thumbnail((400, 400))
                    img.save(str(thumb_path), "JPEG", quality=85)
                    return "thumbnail.jpg"
                except Exception as e:
                    print(f"Image thumbnail generation failed: {e}")

    return ""


def get_recipe_full(recipe_id: str, conn) -> dict:
    """Load a complete recipe record including its categories and tags."""
    recipe = conn.execute(
        "SELECT * FROM recipes WHERE id = ?", (recipe_id,)
    ).fetchone()

    if not recipe:
        return None

    recipe = dict(recipe)

    # Get categories for this recipe
    categories = conn.execute("""
        SELECT c.name FROM categories c
        JOIN recipe_categories rc ON c.id = rc.category_id
        WHERE rc.recipe_id = ?
    """, (recipe_id,)).fetchall()

    # Get tags for this recipe
    tags = conn.execute("""
        SELECT t.name FROM tags t
        JOIN recipe_tags rt ON t.id = rt.tag_id
        WHERE rt.recipe_id = ?
    """, (recipe_id,)).fetchall()

    recipe["categories"] = [r["name"] for r in categories]
    recipe["tags"] = [r["name"] for r in tags]

    # Get the list of image files if this is an image recipe
    if recipe["file_type"] == "images":
        recipe_dir = DATA_DIR / recipe_id
        image_extensions = [".jpg", ".jpeg", ".png", ".webp"]
        images = []
        for ext in image_extensions:
            images.extend(sorted(recipe_dir.glob(f"*{ext}")))
        # Filter out the thumbnail
        images = [f.name for f in images if f.name != "thumbnail.jpg"]
        recipe["images"] = sorted(images)
    else:
        recipe["images"] = []

    return recipe


# ─── API Routes ───────────────────────────────────────────────────────────────

@app.get("/api/recipes")
def list_recipes(
    search: Optional[str] = None,
    category: Optional[str] = None,
    tags: Optional[str] = None,
):
    """
    Returns a list of all recipes.
    Supports optional filtering by search text, category, and tags.
    Tags can be a comma-separated list, e.g. tags=wool,fingering
    """
    conn = get_db()

    query = """
        SELECT DISTINCT r.id, r.title, r.description, r.file_type,
               r.thumbnail_path, r.created_date
        FROM recipes r
        LEFT JOIN recipe_categories rc ON r.id = rc.recipe_id
        LEFT JOIN categories c ON rc.category_id = c.id
        LEFT JOIN recipe_tags rt ON r.id = rt.recipe_id
        LEFT JOIN tags t ON rt.tag_id = t.id
        WHERE 1=1
    """
    params = []

    if search:
        query += " AND (r.title LIKE ? OR r.description LIKE ? OR t.name LIKE ?)"
        like = f"%{search}%"
        params.extend([like, like, like])

    if category:
        query += " AND c.name = ?"
        params.append(category)

    if tags:
        tag_list = [t.strip() for t in tags.split(",")]
        placeholders = ",".join("?" * len(tag_list))
        query += f" AND t.name IN ({placeholders})"
        params.extend(tag_list)

    query += " ORDER BY r.created_date DESC"

    recipes = conn.execute(query, params).fetchall()
    result = []

    for r in recipes:
        recipe = dict(r)
        # Get categories and tags for each recipe
        cats = conn.execute("""
            SELECT c.name FROM categories c
            JOIN recipe_categories rc ON c.id = rc.category_id
            WHERE rc.recipe_id = ?
        """, (recipe["id"],)).fetchall()

        tgs = conn.execute("""
            SELECT t.name FROM tags t
            JOIN recipe_tags rt ON t.id = rt.tag_id
            WHERE rt.recipe_id = ?
        """, (recipe["id"],)).fetchall()

        recipe["categories"] = [c["name"] for c in cats]
        recipe["tags"] = [t["name"] for t in tgs]
        result.append(recipe)

    conn.close()
    return result


@app.get("/api/recipes/{recipe_id}")
def get_recipe(recipe_id: str):
    """Returns full details for a single recipe."""
    conn = get_db()
    recipe = get_recipe_full(recipe_id, conn)
    conn.close()

    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    return recipe


@app.post("/api/recipes")
async def create_recipe(
    title: str = Form(...),
    description: str = Form(""),
    categories: str = Form(""),      # Comma-separated list
    tags: str = Form(""),            # Comma-separated list
    files: List[UploadFile] = File(...),
):
    """
    Upload a new recipe.
    Accepts one PDF or one/many images.
    Automatically generates a thumbnail.
    """
    recipe_id = str(uuid.uuid4())
    recipe_dir = DATA_DIR / recipe_id
    recipe_dir.mkdir(parents=True)

    saved_files = []
    file_type = "images"

    for upload in files:
        filename = upload.filename.lower()
        ext = Path(filename).suffix

        # Determine if this is a PDF or image upload
        if ext == ".pdf":
            file_type = "pdf"
            save_name = "recipe.pdf"
        elif ext in [".jpg", ".jpeg", ".png", ".webp"]:
            save_name = upload.filename
        else:
            continue  # Skip unsupported file types

        dest = recipe_dir / save_name
        with open(dest, "wb") as f:
            content = await upload.read()
            f.write(content)
        saved_files.append(save_name)

    if not saved_files:
        shutil.rmtree(recipe_dir)
        raise HTTPException(status_code=400, detail="No valid files uploaded")

    # Generate the thumbnail image for the grid
    thumb = generate_thumbnail(recipe_dir, file_type, saved_files)

    # Save recipe to the database
    conn = get_db()
    conn.execute("""
        INSERT INTO recipes (id, title, description, file_type, thumbnail_path, created_date)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (recipe_id, title, description, file_type, thumb, datetime.utcnow().isoformat()))

    # Save categories
    category_list = [c.strip() for c in categories.split(",") if c.strip()]
    for cat_name in category_list:
        conn.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat_name,))
        cat_row = conn.execute("SELECT id FROM categories WHERE name = ?", (cat_name,)).fetchone()
        if cat_row:
            conn.execute(
                "INSERT OR IGNORE INTO recipe_categories (recipe_id, category_id) VALUES (?, ?)",
                (recipe_id, cat_row["id"])
            )

    # Save tags
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    for tag_name in tag_list:
        conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag_name,))
        tag_row = conn.execute("SELECT id FROM tags WHERE name = ?", (tag_name,)).fetchone()
        if tag_row:
            conn.execute(
                "INSERT OR IGNORE INTO recipe_tags (recipe_id, tag_id) VALUES (?, ?)",
                (recipe_id, tag_row["id"])
            )

    conn.commit()
    recipe = get_recipe_full(recipe_id, conn)
    conn.close()

    return recipe


@app.put("/api/recipes/{recipe_id}")
async def update_recipe(
    recipe_id: str,
    title: str = Form(...),
    description: str = Form(""),
    categories: str = Form(""),
    tags: str = Form(""),
):
    """Update the metadata (title, description, categories, tags) of an existing recipe."""
    conn = get_db()

    existing = conn.execute("SELECT id FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")

    conn.execute(
        "UPDATE recipes SET title = ?, description = ? WHERE id = ?",
        (title, description, recipe_id)
    )

    # Replace categories
    conn.execute("DELETE FROM recipe_categories WHERE recipe_id = ?", (recipe_id,))
    for cat_name in [c.strip() for c in categories.split(",") if c.strip()]:
        conn.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat_name,))
        cat_row = conn.execute("SELECT id FROM categories WHERE name = ?", (cat_name,)).fetchone()
        if cat_row:
            conn.execute(
                "INSERT OR IGNORE INTO recipe_categories (recipe_id, category_id) VALUES (?, ?)",
                (recipe_id, cat_row["id"])
            )

    # Replace tags
    conn.execute("DELETE FROM recipe_tags WHERE recipe_id = ?", (recipe_id,))
    for tag_name in [t.strip() for t in tags.split(",") if t.strip()]:
        conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag_name,))
        tag_row = conn.execute("SELECT id FROM tags WHERE name = ?", (tag_name,)).fetchone()
        if tag_row:
            conn.execute(
                "INSERT OR IGNORE INTO recipe_tags (recipe_id, tag_id) VALUES (?, ?)",
                (recipe_id, tag_row["id"])
            )

    conn.commit()
    recipe = get_recipe_full(recipe_id, conn)
    conn.close()

    return recipe


@app.delete("/api/recipes/{recipe_id}")
def delete_recipe(recipe_id: str):
    """Delete a recipe and all its files."""
    conn = get_db()
    existing = conn.execute("SELECT id FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Recipe not found")

    # Remove from database
    conn.execute("DELETE FROM recipe_categories WHERE recipe_id = ?", (recipe_id,))
    conn.execute("DELETE FROM recipe_tags WHERE recipe_id = ?", (recipe_id,))
    conn.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))
    conn.commit()
    conn.close()

    # Delete files from disk
    recipe_dir = DATA_DIR / recipe_id
    if recipe_dir.exists():
        shutil.rmtree(recipe_dir)

    return {"message": "Recipe deleted"}


@app.get("/api/categories")
def list_categories():
    """Returns all available categories."""
    conn = get_db()
    rows = conn.execute("SELECT name FROM categories ORDER BY name").fetchall()
    conn.close()
    return [r["name"] for r in rows]


@app.get("/api/tags")
def list_tags():
    """Returns all tags that are currently used by at least one recipe."""
    conn = get_db()
    rows = conn.execute("""
        SELECT DISTINCT t.name FROM tags t
        JOIN recipe_tags rt ON t.id = rt.tag_id
        ORDER BY t.name
    """).fetchall()
    conn.close()
    return [r["name"] for r in rows]


@app.post("/api/categories")
def add_category(data: dict):
    """Add a new category."""
    name = data.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Category name is required")
    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (name,))
    conn.commit()
    conn.close()
    return {"message": f"Category '{name}' added"}


# ─── File Serving ─────────────────────────────────────────────────────────────

@app.get("/api/recipes/{recipe_id}/thumbnail")
def get_thumbnail(recipe_id: str):
    """Serve the thumbnail image for a recipe card."""
    thumb = DATA_DIR / recipe_id / "thumbnail.jpg"
    if thumb.exists():
        return FileResponse(str(thumb), media_type="image/jpeg")
    # Return a placeholder if no thumbnail exists
    raise HTTPException(status_code=404, detail="Thumbnail not found")


@app.get("/api/recipes/{recipe_id}/pdf")
def get_pdf(recipe_id: str):
    """Serve the PDF file for a recipe."""
    pdf = DATA_DIR / recipe_id / "recipe.pdf"
    if pdf.exists():
        return FileResponse(str(pdf), media_type="application/pdf")
    raise HTTPException(status_code=404, detail="PDF not found")


@app.get("/api/recipes/{recipe_id}/images/{filename}")
def get_image(recipe_id: str, filename: str):
    """Serve a single image file from an image recipe."""
    # Security: make sure the filename doesn't try to escape the directory
    safe_name = Path(filename).name
    image_path = DATA_DIR / recipe_id / safe_name
    if image_path.exists():
        return FileResponse(str(image_path))
    raise HTTPException(status_code=404, detail="Image not found")


# ─── Health Check ─────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "message": "Knitting Library API is running"}
