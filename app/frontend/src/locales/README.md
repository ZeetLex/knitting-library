# Locale Files

Each language lives in its own JavaScript file. English (`en.js`) is the reference file.

To add a language:

1. Copy `en.js` to a new file named with the language code, for example `de.js`.
2. Update the exported `language` metadata at the top of the file.
3. Translate the values, but keep the keys exactly the same.
4. Rebuild the frontend.

The language picker is generated automatically from every locale file except files whose names start with `_`.

Missing keys fall back to English, so an incomplete translation will still work while it is being finished.
