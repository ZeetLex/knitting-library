# 🧶 Knitting Recipe Library

A personal digital library for your knitting patterns. Upload PDFs and photos of patterns, browse them in a beautiful grid, and filter by category or tag — all running on your own computer.

---

## What You'll Need Before Starting

- **Docker Desktop** installed on your computer
  - Download from: https://www.docker.com/products/docker-desktop/
  - Available for Mac, Windows, and Linux
  - Make sure it's running (you'll see the whale icon in your menu bar)

That's it! You don't need Python, Node.js, or anything else installed.

---

## Quick Start (First Time Setup)

### Step 1 — Download the project

If you have Git installed:
```bash
git clone https://github.com/your-username/knitting-library.git
cd knitting-library
```

Or download and unzip the project folder, then open a terminal and navigate to it:
```bash
cd path/to/knitting-library
```

### Step 2 — Create the data folder

This folder is where all your recipes will be saved:
```bash
mkdir -p data/recipes
```

### Step 3 — Build and start the application

This command builds the app and starts it. It may take 3–5 minutes the first time (it's downloading everything it needs):

```bash
docker-compose up --build
```

You'll see a lot of output scrolling by — that's normal! Wait until you see something like:

```
knitting-frontend  | nginx: worker process started
```

### Step 4 — Open the app

Open your web browser and go to:

```
http://localhost:3000
```

You should see the Knitting Library home page! 🎉

---

## Starting the App After the First Time

Once you've done the initial setup, starting the app is much faster:

```bash
docker-compose up
```

To stop it:
```bash
docker-compose down
```

Or press `Ctrl + C` in the terminal where it's running.

---

## Using the App

### Adding a Recipe

1. Click the **"Add Recipe"** button in the top-right corner
2. Drag and drop your file onto the upload area, or click to browse
3. You can upload:
   - A single PDF
   - A single photo
   - Multiple photos (they become one recipe)
   - An entire folder of photos
4. Fill in the recipe name (required)
5. Choose a category (Socks, Sweater, Hat, etc.)
6. Add tags like: `wool, fingering weight, easy, colorwork`
7. Click **"Add to Library"**

### Browsing Recipes

- The main page shows all your recipes as cards in a grid
- Use the **grid size buttons** (top right of the grid) to make cards smaller or larger
- Scroll to browse all recipes

### Searching & Filtering

- Use the **search bar** to find recipes by name or tag
- Click **"Filters"** to filter by category or specific tags
- Multiple filters work together — e.g., show only "Socks" with tag "wool"

### Viewing a Recipe

- Click any recipe card to open it
- **PDFs**: shown in a built-in viewer with zoom controls
  - Click "Open Full" to open it in a new browser tab for easier reading
- **Images**: shown in a gallery with:
  - Arrow buttons (or swipe on mobile) to go through pages
  - Zoom in/out buttons
  - A thumbnail strip at the bottom to jump to any page
  - Fullscreen button

### Editing a Recipe

- Open a recipe, then click the **pencil icon** (top right) to edit its title, notes, categories, or tags

### Deleting a Recipe

- Open a recipe, then click the **trash icon** (top right)
- You'll be asked to confirm before anything is deleted

---

## Using on Your iPhone

1. Make sure your phone is on the **same Wi-Fi network** as your computer
2. Find your computer's local IP address:
   - **Mac**: System Settings → Network → Wi-Fi → Details → IP Address
   - **Windows**: Settings → Network → Properties → IPv4 Address
   - It will look something like `192.168.1.42`
3. On your iPhone, open Safari and go to:
   ```
   http://192.168.1.42:3000
   ```
4. For the best experience, tap the **Share button** → **Add to Home Screen**

The app is fully optimized for iPhone with swipe navigation, touch-friendly buttons, and a mobile-friendly layout.

---

## Understanding the Folder Structure

```
knitting-library/
│
├── docker-compose.yml          ← The main file that starts everything
│
├── data/                       ← ALL YOUR DATA LIVES HERE
│   ├── recipes.db              ← The database (recipe names, tags, etc.)
│   └── recipes/                ← Your recipe files
│       ├── [recipe-id]/
│       │   ├── recipe.pdf      ← (for PDF recipes)
│       │   ├── thumbnail.jpg   ← Auto-generated thumbnail
│       │   └── image1.jpg      ← (for image recipes)
│       └── ...
│
└── app/
    ├── backend/                ← The Python API server
    │   ├── main.py             ← All backend logic
    │   ├── requirements.txt    ← Python libraries
    │   └── Dockerfile          ← How to build the backend
    │
    └── frontend/               ← The React web interface
        ├── src/                ← Source code
        ├── nginx.conf          ← Web server configuration
        └── Dockerfile          ← How to build the frontend
```

---

## Backing Up Your Recipes

All your recipes and data are stored in the `data/` folder. To back up everything:

1. Stop the app (optional but recommended):
   ```bash
   docker-compose down
   ```

2. Copy the `data/` folder to your backup location:
   - **Mac/Linux**:
     ```bash
     cp -r data/ ~/Desktop/knitting-backup-2024/
     ```
   - **Windows** (in File Explorer): just copy and paste the `data` folder

3. That's it! The `data/` folder contains both the database and all recipe files.

### Restoring from Backup

To restore, just copy your backup `data/` folder back into the project folder and restart:
```bash
docker-compose up
```

---

## Updating the App

When a new version is available:

```bash
# Stop the app
docker-compose down

# Get the latest code (if using git)
git pull

# Rebuild with the new code
docker-compose up --build
```

Your data in the `data/` folder is safe — it's never touched during updates.

---

## Changing the Port

By default, the app runs on port `3000`. To change it, open `docker-compose.yml` and find this line:

```yaml
ports:
  - "3000:80"
```

Change `3000` to any port you prefer, for example `8080:80` for port 8080.

Then restart with `docker-compose up --build`.

---

## Troubleshooting

### "The page won't load"
- Make sure Docker Desktop is running
- Make sure you ran `docker-compose up` and see it running in the terminal
- Try `http://localhost:3000` (not `https`)

### "Upload failed"
- Check that the file is a PDF or image (JPG, PNG, WebP)
- For very large PDFs, try opening in a new tab using the "Open Full" button instead

### "Thumbnails aren't generating for PDFs"
- This requires `poppler` which is installed inside Docker automatically
- It may be slow for the first PDF — give it a moment

### "I see errors in the terminal"
- Run `docker-compose logs backend` to see backend errors
- Run `docker-compose logs frontend` to see frontend errors

### Starting fresh (deletes everything)
```bash
docker-compose down
docker system prune -f
docker-compose up --build
```
⚠️ Warning: this doesn't delete your `data/` folder (your recipes are safe), but it rebuilds the containers from scratch.

---

## Adding New Categories

Categories are pre-loaded with common types: Socks, Sweater, Hat, Mittens, Scarf, Shawl, Blanket, Cardigan, Cowl, Other.

To add a custom category, you can use the API directly in your browser:

```
http://localhost:3000/api/categories
```

Or use a tool like Postman to POST to `/api/categories` with `{"name": "Your Category"}`.

*(A UI for managing categories will be added in a future update)*

---

## Technical Details (for the curious)

- **Backend**: Python + FastAPI
- **Frontend**: React (served by nginx)
- **Database**: SQLite (stored in `data/recipes.db`)
- **File Storage**: Local disk (stored in `data/recipes/`)
- **Thumbnails**: Generated using Pillow (images) and pdf2image/poppler (PDFs)
- **Containerization**: Docker + Docker Compose
