"""OCR, page text cleanup, and chart extraction helpers."""
from app.core.foundation import *
from app.ai.prompts import *

def _normalise_recognition_mode(value: str) -> str:
    return "ai_vision_only"


def _ocr_languages_for(language: str, cfg: dict) -> str:
    return "ai_vision"


def _ocr_engine_for(cfg: dict) -> str:
    return "ai_vision"


def _is_truthy(value: str, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _ocr_preprocess_image(path: Path):
    from PIL import Image, ImageOps, ImageFilter

    img = Image.open(path)
    img = ImageOps.exif_transpose(img).convert("L")
    img = ImageOps.autocontrast(img)
    if img.width < 1400:
        scale = min(3, max(2, int(1600 / max(1, img.width))))
        img = img.resize((img.width * scale, img.height * scale), Image.Resampling.LANCZOS)
    img = img.filter(ImageFilter.SHARPEN)
    threshold = 185
    img = img.point(lambda p: 255 if p > threshold else 0, mode="1").convert("L")
    return ImageOps.expand(img, border=24, fill=255)


def _ocr_preprocess_grayscale(path: Path):
    from PIL import Image, ImageOps, ImageEnhance, ImageFilter

    img = Image.open(path)
    img = ImageOps.exif_transpose(img).convert("L")
    img = ImageOps.autocontrast(img)
    img = ImageEnhance.Contrast(img).enhance(1.35)
    if img.width < 1400:
        scale = min(3, max(2, int(1600 / max(1, img.width))))
        img = img.resize((img.width * scale, img.height * scale), Image.Resampling.LANCZOS)
    img = img.filter(ImageFilter.SHARPEN)
    return ImageOps.expand(img, border=24, fill=255)


def _run_tesseract_image(img, languages: str, psm: int = 6, timeout: int = 120, config: Optional[list[str]] = None) -> str:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        img.save(tmp_path)
        cmd = ["tesseract", tmp_path, "stdout", "-l", languages, "--oem", "1", "--psm", str(psm)]
        if config:
            cmd.extend(config)
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        if res.returncode != 0:
            detail = (res.stderr or res.stdout or "tesseract failed").strip()
            raise RuntimeError(detail[:500])
        return res.stdout or ""
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _run_tesseract_tsv_image(img, languages: str, psm: int = 6, timeout: int = 120, config: Optional[list[str]] = None) -> list[dict]:
    text = _run_tesseract_image(img, languages, psm=psm, timeout=timeout, config=[*(config or []), "tsv"])
    fields = ["level", "page_num", "block_num", "par_num", "line_num", "word_num", "left", "top", "width", "height", "conf", "text"]
    rows = []
    for raw in (text or "").splitlines()[1:]:
        parts = raw.split("\t", 11)
        if len(parts) != len(fields):
            continue
        rows.append(dict(zip(fields, parts)))
    return rows


_OCR_KNITTING_TERMS = {
    "arbeid", "arbeidet", "begynn", "diagram", "fell", "felling", "garn", "garnforbruk",
    "garnforslag", "gjenta", "glattstrikk", "icord", "kant", "kantmaske", "kast", "legg",
    "maske", "masker", "mkrets", "mnd", "nakken", "nyfødt", "omg", "omgang",
    "omkrets", "oppleggskanten", "pinne", "pinnen", "plukk",
    "prematur", "rett", "rettsiden", "rundt", "sammen", "sett", "size", "sizes",
    "skein", "stitch", "stitches", "strikk", "strikkefasthet", "struktur", "størrelser",
    "teknikker", "tråd", "veiledende", "vrang", "vrangsiden", "yarn",
}


_OCR_KNITTING_STEMS = (
    "arbeid", "blokk", "bryt", "diagram", "fell", "fest", "forkort", "garn", "gjenta",
    "glattstrikk", "icord", "kant", "legg", "mask", "mål", "mnd", "nakke", "nyfødt",
    "omg", "omkrets", "opplegg", "pinn", "plukk", "prematur", "rett", "sammen",
    "sett", "size", "skein", "snurp", "stitch", "strikk", "struktur", "størrelse",
    "teknikk", "tråd", "vask", "veiled", "vrang", "yarn",
)


def _ocr_line_has_recipe_signal(line: str) -> bool:
    text = (line or "").strip()
    if not text:
        return False
    lower = text.lower()
    words = re.findall(r"[A-Za-zÆØÅæøå]{1,}", lower)
    if any(word in _OCR_KNITTING_TERMS for word in words):
        return True
    if any(any(word.startswith(stem) for stem in _OCR_KNITTING_STEMS) for word in words):
        return True
    if re.search(r"\d+\s*(?:cm|g|mnd|mm)\b", lower):
        return True
    if re.search(r"\b(?:r|vr|km|ssk|smn)\b", lower) and re.search(r"\d", lower):
        return True
    if re.search(r"\d+\s*(?:\([^)]+\)\s*){2,}\d+", lower):
        return True
    return False


def _ocr_line_quality(line: str) -> float:
    text = (line or "").strip()
    if not text:
        return 0.0
    chars = [ch for ch in text if not ch.isspace()]
    if not chars:
        return 0.0
    alpha = sum(1 for ch in chars if ch.isalpha())
    digits = sum(1 for ch in chars if ch.isdigit())
    symbols = sum(1 for ch in chars if not ch.isalnum() and ch not in ".,;:()/-+%")
    words = re.findall(r"[A-Za-zÆØÅæøå]{2,}", text)
    lower_words = {w.lower() for w in words}
    term_hits = len(lower_words & _OCR_KNITTING_TERMS)
    number_patterns = len(re.findall(r"\d+\s*(?:\([^)]+\)\s*)*\d*|\d+\s*(?:cm|g|mnd|mm)", text, re.I))
    useful_punctuation = len(re.findall(r"[*(),.:/-]", text))
    symbol_ratio = symbols / max(1, len(chars))
    alpha_ratio = alpha / max(1, len(chars))
    long_letter_runs = len(re.findall(r"[A-ZÆØÅ]{5,}", text))

    short_words = sum(1 for word in words if len(word) <= 2)
    short_word_ratio = short_words / max(1, len(words))
    score = alpha * 0.14 + digits * 0.35 + len(words) * 1.1
    score += term_hits * 10.0 + number_patterns * 4.0 + min(useful_punctuation, 8) * 0.5
    if len(text) <= 2 and not digits:
        score -= 8.0
    if not _ocr_line_has_recipe_signal(text):
        score -= 10.0
    if symbol_ratio > 0.28 and term_hits == 0:
        score -= 18.0 * symbol_ratio
    if alpha_ratio < 0.35 and not _ocr_line_has_recipe_signal(text):
        score -= 7.0
    if long_letter_runs >= 2 and term_hits == 0:
        score -= 6.0 * long_letter_runs
    if short_word_ratio > 0.42 and term_hits == 0:
        score -= 9.0
    if len(words) >= 2 and term_hits == 0:
        vowel_words = sum(1 for word in words if re.search(r"[aeiouyæøåAEIOUYÆØÅ]", word))
        if vowel_words / max(1, len(words)) < 0.45:
            score -= 10.0
    return score


def _ocr_candidate_score(text: str) -> float:
    lines = [line for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return 0.0
    line_scores = [_ocr_line_quality(line) for line in lines]
    useful_lines = sum(1 for score in line_scores if score >= 4.0)
    weak_lines = sum(1 for score in line_scores if score < 1.0)
    words = re.findall(r"\S+", text)
    return sum(line_scores) + useful_lines * 5.0 + len(words) * 0.35 - weak_lines * 2.5


def _ocr_int(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _ocr_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _ocr_words_to_lines(rows: list[dict], source: str, image_size: tuple[int, int]) -> list[dict]:
    grouped: dict[tuple[int, int, int, int], list[dict]] = defaultdict(list)
    for row in rows:
        text = re.sub(r"\s+", " ", str(row.get("text") or "")).strip()
        conf = _ocr_float(row.get("conf"), -1.0)
        if not text or conf < 0:
            continue
        key = (
            _ocr_int(row.get("page_num"), 1),
            _ocr_int(row.get("block_num"), 0),
            _ocr_int(row.get("par_num"), 0),
            _ocr_int(row.get("line_num"), 0),
        )
        grouped[key].append({
            "text": text,
            "conf": conf,
            "left": _ocr_int(row.get("left")),
            "top": _ocr_int(row.get("top")),
            "width": _ocr_int(row.get("width")),
            "height": _ocr_int(row.get("height")),
            "word_num": _ocr_int(row.get("word_num")),
        })

    lines = []
    image_width, image_height = image_size
    for key, words in grouped.items():
        words.sort(key=lambda item: (item["word_num"], item["left"]))
        text = " ".join(word["text"] for word in words).strip()
        if not text:
            continue
        left = min(word["left"] for word in words)
        top = min(word["top"] for word in words)
        right = max(word["left"] + word["width"] for word in words)
        bottom = max(word["top"] + word["height"] for word in words)
        weighted = sum(word["conf"] * max(1, len(word["text"])) for word in words)
        weight = sum(max(1, len(word["text"])) for word in words)
        conf = weighted / max(1, weight)
        quality = _ocr_line_quality(text)
        width_ratio = (right - left) / max(1, image_width)
        height_ratio = (bottom - top) / max(1, image_height)
        lines.append({
            "key": key,
            "source": source,
            "text": text,
            "conf": conf,
            "quality": quality,
            "score": quality + max(0.0, conf - 45.0) * 0.35,
            "bbox": (left, top, right, bottom),
            "width_ratio": width_ratio,
            "height_ratio": height_ratio,
        })
    lines.sort(key=lambda item: (item["bbox"][1], item["bbox"][0], item["key"]))
    return lines


def _ocr_text_fingerprint(text: str) -> str:
    return re.sub(r"[^0-9a-zæøå]+", "", (text or "").lower())


def _ocr_lines_similar(a: str, b: str) -> bool:
    if not a or not b:
        return False
    shorter, longer = sorted((a, b), key=len)
    if len(shorter) < 12:
        return a == b
    if shorter in longer and len(shorter) / max(1, len(longer)) >= 0.58:
        return True
    return SequenceMatcher(None, a, b).ratio() >= 0.82


def _dedupe_ocr_lines(lines: list[dict]) -> list[dict]:
    best: dict[str, dict] = {}
    order = []
    for line in lines:
        key = _ocr_text_fingerprint(line.get("text", ""))
        if len(key) < 4:
            continue
        matched_key = next((existing for existing in order if _ocr_lines_similar(key, existing)), None)
        if matched_key is None:
            order.append(key)
            best[key] = line
            continue
        if line.get("score", 0) > best[matched_key].get("score", 0):
            best[matched_key] = line
    return [best[key] for key in order]


def _ocr_line_bucket(line: dict, page_height: int) -> str:
    text = line.get("text", "")
    conf = float(line.get("conf", 0.0))
    quality = float(line.get("quality", 0.0))
    top = line.get("bbox", (0, 0, 0, 0))[1]
    lower = text.lower()
    has_signal = _ocr_line_has_recipe_signal(text)
    words = re.findall(r"[A-Za-zÆØÅæøå]{2,}", text)
    chars = [ch for ch in text if not ch.isspace()]
    symbols = sum(1 for ch in chars if not ch.isalnum() and ch not in ".,;:()/-+%*")
    symbol_ratio = symbols / max(1, len(chars))

    if re.search(r"\bdiagram\b", lower):
        return "diagram"
    if conf < 35 or quality < 3:
        return "uncertain" if has_signal else "rejected"
    if symbol_ratio > 0.34 and not has_signal:
        return "rejected"
    if not has_signal and conf < 70:
        return "uncertain" if len(words) >= 3 else "rejected"
    if top < page_height * 0.14 and (conf >= 55 or has_signal):
        return "header"
    if re.search(r"\d+\s*(?:\([^)]+\)\s*){1,}\d+|\d+\s*(?:cm|g|mnd|mm)\b", lower):
        return "counts"
    return "body" if has_signal or conf >= 74 else "uncertain"


def _format_ocr_evidence_page(page_no: int, path: Path, buckets: dict[str, list[dict]], metrics: dict, diagram_md: str = "") -> str:
    sections = [
        f"## OCR evidence page {page_no}: {path.name}",
        f"Quality: avg_conf={metrics.get('avg_conf', 0):.1f}, accepted_lines={metrics.get('accepted_lines', 0)}, uncertain_lines={metrics.get('uncertain_lines', 0)}, rejected_lines={metrics.get('rejected_lines', 0)}",
    ]
    if diagram_md:
        sections.extend(["", "### Diagram evidence", diagram_md])
    labels = [
        ("header", "Header/title candidates"),
        ("counts", "Sizes/counts/material lines"),
        ("body", "Instruction/body lines"),
        ("diagram", "Diagram/legend text"),
        ("uncertain", "Low-confidence but possibly useful lines"),
    ]
    for key, title in labels:
        lines = buckets.get(key) or []
        if not lines:
            continue
        sections.extend(["", f"### {title}"])
        for line in lines[:80]:
            bbox = line.get("bbox", (0, 0, 0, 0))
            sections.append(f"- conf {line.get('conf', 0):.0f}, y {bbox[1]}: {line.get('text', '')}")
    rejected = buckets.get("rejected") or []
    if rejected:
        samples = "; ".join(line.get("text", "")[:70] for line in rejected[:8])
        sections.extend(["", f"Rejected noise summary: {len(rejected)} lines hidden. Samples: {samples}"])
    return "\n".join(sections).strip()


def _format_ocr_final_text(page_no: int, path: Path, buckets: dict[str, list[dict]], diagram_md: str = "") -> str:
    lines = [f"<!-- Page {page_no}: {path.name} -->"]
    ordered = []
    for key in ("header", "counts", "body", "diagram", "uncertain"):
        ordered.extend(buckets.get(key) or [])
    ordered.sort(key=lambda item: (item["bbox"][1], item["bbox"][0]))
    last_y = None
    for line in ordered:
        y = line["bbox"][1]
        if last_y is not None and y - last_y > 52 and lines[-1] != "":
            lines.append("")
        lines.append(line["text"])
        last_y = y
    if diagram_md:
        if lines[-1] != "":
            lines.append("")
        lines.append(diagram_md)
    return "\n".join(lines).strip()


def _cleanup_ocr_markdown(text: str, unclear_marker: str = "[unclear]") -> str:
    lines = []
    for raw in (text or "").splitlines():
        line = re.sub(r"[ \t]+", " ", raw).strip()
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        # Keep OCR conservative: only strip repeated decoration, never rewrite knitting tokens.
        line = re.sub(r"^[|:;,.·•\-\s]+$", "", line).strip()
        if line:
            chars = [ch for ch in line if not ch.isspace()]
            alnum = sum(1 for ch in chars if ch.isalnum())
            symbols = sum(1 for ch in chars if not ch.isalnum() and ch not in ".,;:()/-+%*")
            symbol_ratio = symbols / max(1, len(chars))
            quality = _ocr_line_quality(line)
            if len(line) <= 2 and not any(ch.isdigit() for ch in line):
                continue
            if symbol_ratio > 0.38 and quality < 5.0:
                continue
            if alnum <= 2 and quality < 4.0:
                continue
            if not _ocr_line_has_recipe_signal(line):
                continue
            if quality < 4.0:
                continue
            if quality < -4.0:
                continue
        if line:
            lines.append(line)
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines).strip()


def _line_groups(active_indexes: list[int], max_gap: int = 2) -> list[tuple[int, int]]:
    if not active_indexes:
        return []
    groups = []
    start = prev = active_indexes[0]
    for idx in active_indexes[1:]:
        if idx - prev <= max_gap:
            prev = idx
            continue
        groups.append((start, prev))
        start = prev = idx
    groups.append((start, prev))
    return groups


def _group_centres(groups: list[tuple[int, int]]) -> list[int]:
    return [int(round((a + b) / 2)) for a, b in groups]


def _regular_line_sequence(centres: list[int], min_lines: int) -> list[int]:
    centres = sorted({int(c) for c in centres})
    if len(centres) < min_lines:
        return []
    best: list[int] = []
    for i, start in enumerate(centres):
        for j in range(i + 1, min(len(centres), i + 8)):
            spacing = centres[j] - start
            if spacing < 20 or spacing > 130:
                continue
            seq = [start, centres[j]]
            expected = centres[j] + spacing
            tolerance = max(4, int(spacing * 0.32))
            while True:
                match = min((c for c in centres if c > seq[-1]), key=lambda c: abs(c - expected), default=None)
                if match is None or abs(match - expected) > tolerance:
                    break
                seq.append(match)
                expected = match + spacing
            if len(seq) > len(best):
                best = seq
    return best if len(best) >= min_lines else []


def _edge_line_centres(pixels, x1: int, y1: int, x2: int, y2: int, axis: str) -> list[int]:
    if axis == "x":
        span = max(1, y2 - y1)
        threshold = max(8, int(span * 0.15))
        active = [x for x in range(x1, x2) if sum(1 for y in range(y1, y2) if pixels[x, y] == 0) >= threshold]
        margin = max(8, int((x2 - x1) * 0.015))
        centres = _group_centres(_line_groups(active, max_gap=3))
        return [x for x in centres if x1 + margin <= x <= x2 - margin]
    else:
        span = max(1, x2 - x1)
        threshold = max(8, int(span * 0.15))
        active = [y for y in range(y1, y2) if sum(1 for x in range(x1, x2) if pixels[x, y] == 0) >= threshold]
        margin = max(8, int((y2 - y1) * 0.015))
        centres = _group_centres(_line_groups(active, max_gap=3))
        return [y for y in centres if y1 + margin <= y <= y2 - margin]


def _detect_light_chart_regions(path: Path, existing: list[dict]) -> list[dict]:
    from PIL import Image, ImageOps, ImageFilter

    img = Image.open(path)
    img = ImageOps.exif_transpose(img).convert("L")
    small = img
    max_dim = 900
    scale = 1.0
    if max(img.size) > max_dim:
        scale = max_dim / max(img.size)
        small = img.resize((int(img.width * scale), int(img.height * scale)), Image.Resampling.BILINEAR)
    edge = ImageOps.autocontrast(small.filter(ImageFilter.FIND_EDGES))
    width, height = edge.size
    candidates: list[dict] = []
    existing_boxes = [chart.get("bbox") or [] for chart in existing]

    def overlaps_existing(box: list[int]) -> bool:
        x1, y1, x2, y2 = box
        for raw in existing_boxes:
            if len(raw) != 4:
                continue
            ex1, ey1, ex2, ey2 = [int(v * scale) for v in raw]
            ix = max(0, min(x2, ex2) - max(x1, ex1))
            iy = max(0, min(y2, ey2) - max(y1, ey1))
            if ix * iy > 0.35 * min(max(1, (x2 - x1) * (y2 - y1)), max(1, (ex2 - ex1) * (ey2 - ey1))):
                return True
        return False

    for threshold in (32, 46):
        bw = edge.point(lambda p: 0 if p > threshold else 255, mode="L")
        pixels = bw.load()
        for band_h in (180, 260, 380, 520):
            if band_h > height + 80:
                continue
            step_y = max(55, band_h // 4)
            for y1 in range(0, max(1, height - band_h + 1), step_y):
                y2 = min(height, y1 + band_h)
                x_centres = _regular_line_sequence(_edge_line_centres(pixels, 0, y1, width, y2, "x"), 5)
                if len(x_centres) < 5:
                    continue
                spacing_x = int(round((max(x_centres) - min(x_centres)) / max(1, len(x_centres) - 1)))
                x1 = max(0, min(x_centres) - max(8, spacing_x // 2))
                x2 = min(width, max(x_centres) + max(8, spacing_x // 2))
                y_centres = _regular_line_sequence(_edge_line_centres(pixels, x1, y1, x2, y2, "y"), 4)
                if len(y_centres) < 4:
                    continue
                box = [min(x_centres), min(y_centres), max(x_centres), max(y_centres)]
                grid_w = box[2] - box[0]
                grid_h = box[3] - box[1]
                if grid_w < 90 or grid_h < 80:
                    continue
                if overlaps_existing(box):
                    continue
                score = len(x_centres) * len(y_centres) + min(grid_w, grid_h) * 0.02
                candidates.append({
                    "score": score,
                    "x_lines": x_centres,
                    "y_lines": y_centres,
                    "bbox": box,
                })

    candidates.sort(key=lambda item: item["score"], reverse=True)
    accepted: list[dict] = []
    for candidate in candidates:
        x1, y1, x2, y2 = candidate["bbox"]
        duplicate = False
        for other in accepted:
            ox1, oy1, ox2, oy2 = other["bbox"]
            ix = max(0, min(x2, ox2) - max(x1, ox1))
            iy = max(0, min(y2, oy2) - max(y1, oy1))
            if ix * iy > 0.45 * min((x2 - x1) * (y2 - y1), (ox2 - ox1) * (oy2 - oy1)):
                duplicate = True
                break
        if duplicate:
            continue
        accepted.append(candidate)
        if len(accepted) >= 2:
            break
    return [{
        "x_lines": [int(round(x / scale)) for x in item["x_lines"]],
        "y_lines": [int(round(y / scale)) for y in item["y_lines"]],
        "bbox": [int(round(v / scale)) for v in item["bbox"]],
        "light_grid": True,
    } for item in accepted]


def _detect_chart_regions(path: Path) -> list[dict]:
    from PIL import Image, ImageOps

    img = Image.open(path)
    img = ImageOps.exif_transpose(img).convert("L")
    small = img
    max_dim = 1800
    scale = 1.0
    if max(img.size) > max_dim:
        scale = max_dim / max(img.size)
        small = img.resize((int(img.width * scale), int(img.height * scale)), Image.Resampling.BILINEAR)
    bw = ImageOps.autocontrast(small).point(lambda p: 0 if p < 155 else 255, mode="L")
    width, height = bw.size
    pixels = bw.load()

    full_col_counts = []
    for x in range(width):
        full_col_counts.append(sum(1 for y in range(height) if pixels[x, y] == 0))
    active_full_cols = [i for i, count in enumerate(full_col_counts) if count >= max(60, int(height * 0.20))]
    full_col_groups = _line_groups(active_full_cols, max_gap=3)
    full_cols = _group_centres(full_col_groups)
    if len(full_cols) < 4:
        return _detect_light_chart_regions(path, [])
    x_scan1 = max(0, min(full_cols) - 8)
    x_scan2 = min(width - 1, max(full_cols) + 8)

    row_counts = []
    for y in range(height):
        row_counts.append(sum(1 for x in range(x_scan1, x_scan2 + 1) if pixels[x, y] == 0))
    scan_width = max(1, x_scan2 - x_scan1 + 1)
    active_rows = [i for i, count in enumerate(row_counts) if count >= max(24, int(scan_width * 0.32))]
    row_groups = _line_groups(active_rows, max_gap=2)
    row_centres = _group_centres(row_groups)

    clusters: list[list[int]] = []
    for y in row_centres:
        if not clusters or y - clusters[-1][-1] > 45:
            clusters.append([y])
        else:
            clusters[-1].append(y)

    charts = []
    for rows in clusters:
        if len(rows) < 4:
            continue
        y1 = max(0, rows[0] - 6)
        y2 = min(height - 1, rows[-1] + 6)
        col_counts = []
        for x in range(width):
            col_counts.append(sum(1 for y in range(y1, y2 + 1) if pixels[x, y] == 0))
        active_cols = [i for i, count in enumerate(col_counts) if count >= max(18, int((y2 - y1) * 0.42))]
        col_groups = _line_groups(active_cols, max_gap=2)
        cols = _group_centres(col_groups)
        if len(cols) < 4:
            continue
        # Keep the densest ruled segment if labels/noise created extra vertical groups.
        col_clusters: list[list[int]] = []
        for x in cols:
            if not col_clusters or x - col_clusters[-1][-1] > 55:
                col_clusters.append([x])
            else:
                col_clusters[-1].append(x)
        cols = max(col_clusters, key=len)
        if len(cols) < 4:
            continue
        x_lines = [int(round(x / scale)) for x in cols]
        y_lines = [int(round(y / scale)) for y in rows]
        charts.append({
            "x_lines": x_lines,
            "y_lines": y_lines,
            "bbox": [min(x_lines), min(y_lines), max(x_lines), max(y_lines)],
        })
    charts.extend(_detect_light_chart_regions(path, charts))
    return charts


def _ocr_chart_title(path: Path, chart: dict, languages: str) -> str:
    from PIL import Image, ImageOps

    try:
        img = Image.open(path)
        img = ImageOps.exif_transpose(img).convert("L")
        x1 = max(0, min(chart["x_lines"]) - 15)
        x2 = min(img.width, max(chart["x_lines"]) + 140)
        y1 = max(0, min(chart["y_lines"]) - 95)
        y2 = max(1, min(chart["y_lines"]) - 8)
        if y2 <= y1:
            return ""
        crop = ImageOps.autocontrast(img.crop((x1, y1, x2, y2)))
        crop = ImageOps.expand(crop, border=12, fill=255)
        title = _run_tesseract_image(crop, languages, psm=7, timeout=45)
        title = re.sub(r"\s+", " ", title).strip(" -:\n\t")
        return title[:80]
    except Exception:
        return ""


def _extract_chart_markdown(path: Path, languages: str) -> str:
    specs = _extract_chart_specs(path, languages)
    blocks = []
    for spec in specs:
        blocks.append(
            "\n".join([
                f"## {spec['title']}",
                "",
                "```klchart-v1",
                spec["chart_code"],
                "```",
                "",
                "_Diagram symbols are detected from the grid image and should be reviewed against the original._",
            ])
        )
    return "\n\n".join(blocks).strip()


def _chart_palette_for_cells(cells: list[list[str]]) -> list[dict]:
    symbols = sorted({cell for row in cells for cell in row if cell and cell != "."})
    defaults = [
        ("A", "#159bd7", "main colour"),
        ("B", "#222222", "dark symbol"),
        ("C", "#d94f45", "accent"),
        ("D", "#5aa86a", "accent 2"),
    ]
    palette = [{"symbol": ".", "label": "empty", "color": "#ffffff"}]
    for symbol in symbols:
        match = next((item for item in defaults if item[0] == symbol), None)
        palette.append({
            "symbol": symbol,
            "label": match[2] if match else f"symbol {symbol}",
            "color": match[1] if match else "#777777",
        })
    return palette


def _chart_code(title: str, columns: int, rows: int, cells: list[list[str]], repeat_count: Optional[int] = None) -> str:
    lines = [
        f'title "{title}"',
        f"size {columns}x{rows}",
    ]
    if repeat_count:
        lines.append(f"repeat {repeat_count}")
    lines.append("legend . empty")
    for entry in _chart_palette_for_cells(cells):
        if entry["symbol"] != ".":
            lines.append(f"legend {entry['symbol']} {entry['label']}")
    # Store row 1 as the bottom knitted row. This is friendlier for knitting charts
    # and keeps visual reconstruction deterministic.
    for row_number, visual_row in enumerate(reversed(cells), start=1):
        lines.append(f"row {row_number}: {''.join(visual_row)}")
    return "\n".join(lines)


def _detect_repeat_count_near_chart(path: Path, chart: dict, languages: str) -> Optional[int]:
    from PIL import Image, ImageOps

    try:
        img = Image.open(path)
        img = ImageOps.exif_transpose(img).convert("L")
        x1 = max(0, min(chart["x_lines"]) - 40)
        x2 = min(img.width, max(chart["x_lines"]) + 40)
        y1 = min(img.height - 1, max(chart["y_lines"]) + 4)
        y2 = min(img.height, max(chart["y_lines"]) + 130)
        if y2 <= y1:
            return None
        crop = ImageOps.expand(ImageOps.autocontrast(img.crop((x1, y1, x2, y2))), border=10, fill=255)
        text = _run_tesseract_image(crop, languages, psm=7, timeout=30)
        match = re.search(r"(?:repeat|gjenta)\s+(\d+)", text, re.I)
        return int(match.group(1)) if match else None
    except Exception:
        return None


def _extract_chart_specs(path: Path, languages: str) -> list[dict]:
    from PIL import Image, ImageOps

    charts = _detect_chart_regions(path)
    if not charts:
        return []
    img = Image.open(path)
    rgb = ImageOps.exif_transpose(img).convert("RGB")
    specs = []
    for index, chart in enumerate(charts, start=1):
        xs = chart["x_lines"]
        ys = chart["y_lines"]
        columns = max(0, len(xs) - 1)
        rows = max(0, len(ys) - 1)
        if columns < 2 or rows < 2:
            continue
        cells: list[list[str]] = []
        filled = 0
        confidence_hits = []
        for visual_row in range(rows):
            row = []
            y_top, y_bottom = ys[visual_row], ys[visual_row + 1]
            for col in range(columns):
                x_left, x_right = xs[col], xs[col + 1]
                pad_x = max(2, int((x_right - x_left) * 0.20))
                pad_y = max(2, int((y_bottom - y_top) * 0.20))
                xa, xb = max(0, x_left + pad_x), min(rgb.width, x_right - pad_x)
                ya, yb = max(0, y_top + pad_y), min(rgb.height, y_bottom - pad_y)
                if xb <= xa or yb <= ya:
                    row.append(".")
                    continue
                total = 0
                blueish = 0
                dark = 0
                saturated = 0
                for y in range(ya, yb):
                    for x in range(xa, xb):
                        r, g, b = rgb.getpixel((x, y))
                        total += 1
                        if b > 115 and b > r + 25 and b > g - 10:
                            blueish += 1
                        if r < 85 and g < 85 and b < 85:
                            dark += 1
                        if max(r, g, b) - min(r, g, b) > 55 and max(r, g, b) < 245:
                            saturated += 1
                ratio = max(blueish, dark, saturated) / max(1, total)
                dark_ratio = dark / max(1, total)
                if ratio > 0.22 and blueish >= dark:
                    row.append("A")
                    filled += 1
                    confidence_hits.append(min(1.0, ratio * 2.8))
                elif ratio > 0.18 or (dark_ratio > 0.025 and dark >= 8):
                    row.append("B")
                    filled += 1
                    confidence_hits.append(min(1.0, max(ratio, dark_ratio) * 2.5))
                else:
                    row.append(".")
            cells.append(row)
        title = "" if chart.get("light_grid") else _ocr_chart_title(path, chart, languages)
        title = title or f"Chart {index}"
        repeat_count = None if chart.get("light_grid") else _detect_repeat_count_near_chart(path, chart, languages)
        confidence = sum(confidence_hits) / max(1, len(confidence_hits)) if filled else 0.0
        if confidence < 0.2:
            continue
        specs.append({
            "title": title,
            "rows": rows,
            "columns": columns,
            "source_bbox": chart.get("bbox") or [min(xs), min(ys), max(xs), max(ys)],
            "palette": _chart_palette_for_cells(cells),
            "cells": cells,
            "chart_code": _chart_code(title, columns, rows, cells, repeat_count),
            "repeat_count": repeat_count,
            "confidence": round(confidence, 3),
        })
    return specs


def _ocr_page_to_result(path: Path, languages: str, diagram_enabled: bool, page_no: int, max_variants: int = 4) -> dict:
    if diagram_enabled:
        diagram_md = _extract_chart_markdown(path, languages)
    else:
        diagram_md = ""
    line_candidates = []
    configs = [
        ["-c", "preserve_interword_spaces=1"],
        ["-c", "preserve_interword_spaces=1", "-c", "textord_heavy_nr=1"],
    ]
    images = [
        ("gray", _ocr_preprocess_grayscale(path)),
        ("binary", _ocr_preprocess_image(path)),
    ]
    variants_run = 0
    for image_label, img in images:
        for psm in (6, 4, 11):
            for config in configs:
                if variants_run >= max(1, max_variants):
                    break
                variants_run += 1
                try:
                    rows = _run_tesseract_tsv_image(img, languages, psm=psm, config=config)
                    lines = _ocr_words_to_lines(rows, f"{image_label}/psm{psm}", img.size)
                    if lines:
                        line_candidates.extend(lines)
                except Exception:
                    continue
            if variants_run >= max(1, max_variants):
                break
        if variants_run >= max(1, max_variants):
            break

    deduped = _dedupe_ocr_lines(line_candidates)
    if not deduped:
        text_candidates = []
        for _, img in images[:1]:
            for psm in (6, 4):
                try:
                    cleaned = _cleanup_ocr_markdown(_run_tesseract_image(img, languages, psm=psm, config=configs[0]))
                except Exception:
                    continue
                if cleaned:
                    text_candidates.append(cleaned)
        text = max(text_candidates, key=_ocr_candidate_score, default="")
        text = text if _ocr_candidate_score(text) >= 6 else ""
        return {
            "text": "\n\n".join(part for part in (f"<!-- Page {page_no}: {path.name} -->\n\n{text}" if text else "", diagram_md) if part).strip(),
            "evidence": f"## OCR evidence page {page_no}: {path.name}\n\n{text or '[no usable OCR lines]'}".strip(),
            "warnings": [f"Page {page_no}: Tesseract returned no structured TSV lines."],
            "metrics": {"avg_conf": 0.0, "accepted_lines": 0, "uncertain_lines": 0, "rejected_lines": 0, "variants_run": variants_run},
        }

    page_height = max(img.height for _, img in images)
    buckets: dict[str, list[dict]] = defaultdict(list)
    for line in deduped:
        buckets[_ocr_line_bucket(line, page_height)].append(line)
    for key in list(buckets.keys()):
        buckets[key].sort(key=lambda item: (item["bbox"][1], item["bbox"][0], -item.get("score", 0)))

    accepted = [line for key in ("header", "counts", "body", "diagram") for line in buckets.get(key, [])]
    avg_conf = sum(float(line.get("conf", 0.0)) for line in accepted) / max(1, len(accepted))
    metrics = {
        "avg_conf": avg_conf,
        "accepted_lines": len(accepted),
        "uncertain_lines": len(buckets.get("uncertain") or []),
        "rejected_lines": len(buckets.get("rejected") or []),
        "variants_run": variants_run,
    }
    warnings = []
    if accepted and avg_conf < 55:
        warnings.append(f"Page {page_no}: OCR confidence is low; review against the original image.")
    if len(buckets.get("rejected") or []) > max(8, len(accepted)):
        warnings.append(f"Page {page_no}: decorative or diagram noise was heavily filtered.")
    if not accepted and buckets.get("uncertain"):
        warnings.append(f"Page {page_no}: only low-confidence OCR lines were found.")

    text = _format_ocr_final_text(page_no, path, buckets, diagram_md=diagram_md)
    evidence = _format_ocr_evidence_page(page_no, path, buckets, metrics, diagram_md=diagram_md)
    return {"text": text, "evidence": evidence, "warnings": warnings, "metrics": metrics}


def _ocr_page_to_markdown(path: Path, languages: str, diagram_enabled: bool) -> str:
    return _ocr_page_to_result(path, languages, diagram_enabled, 1).get("text", "")


def _collect_ocr_markdown_from_paths(
    paths: list[Path],
    language: str,
    cfg: dict,
    progress_job_id: str = "",
) -> tuple[str, str, int, str, str, list[str]]:
    languages = _ocr_languages_for(language, cfg)
    diagram_enabled = _is_truthy(cfg.get("ocr_diagram_enabled"), True)
    engine = _ocr_engine_for(cfg)
    max_variants = int(_clamped_float(cfg.get("ocr_max_variants"), 4, 1, 12))
    page_workers = int(_clamped_float(cfg.get("ocr_page_workers"), 2, 1, 4))
    pages_by_index: dict[int, str] = {}
    evidence_by_index: dict[int, str] = {}
    warnings = []
    def run_one(idx: int, path: Path) -> tuple[int, str, str, list[str], str]:
        page_text = ""
        page_warnings: list[str] = []
        used_engine = engine
        if used_engine == "paddleocr":
            diagram_md = _extract_chart_markdown(path, languages) if diagram_enabled else ""
            try:
                ocr_text = _run_paddleocr_image(path, language)
            except Exception:
                used_engine = "tesseract"
                page_result = _ocr_page_to_result(path, languages, diagram_enabled, idx, max_variants=max_variants)
                page_text = page_result.get("text", "")
                evidence = page_result.get("evidence", "")
                page_warnings.extend(page_result.get("warnings", []))
            else:
                ocr_text = _cleanup_ocr_markdown(ocr_text)
                page_text = "\n\n".join(part for part in (f"<!-- Page {idx}: {path.name} -->", diagram_md, ocr_text) if part).strip()
                evidence = f"## OCR evidence page {idx}: {path.name}\n\nEngine: PaddleOCR\n\n{page_text}".strip()
        else:
            page_result = _ocr_page_to_result(path, languages, diagram_enabled, idx, max_variants=max_variants)
            page_text = page_result.get("text", "")
            evidence = page_result.get("evidence", "")
            page_warnings.extend(page_result.get("warnings", []))
        return idx, page_text, evidence, page_warnings, used_engine

    if page_workers > 1 and len(paths) > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        if progress_job_id:
            _update_ai_job(progress_job_id, pages_sent=0, progress_stage="ocr_pages")
        with ThreadPoolExecutor(max_workers=min(page_workers, len(paths))) as pool:
            futures = {pool.submit(run_one, idx, path): idx for idx, path in enumerate(paths, start=1)}
            completed = 0
            for future in as_completed(futures):
                if progress_job_id and _ai_job_cancelled(progress_job_id):
                    break
                idx, page_text, evidence, page_warnings, used_engine = future.result()
                if used_engine != "paddleocr":
                    engine = used_engine
                if page_text:
                    pages_by_index[idx] = page_text
                if evidence:
                    evidence_by_index[idx] = evidence
                warnings.extend(page_warnings)
                completed += 1
                if progress_job_id:
                    _update_ai_job(progress_job_id, pages_sent=completed, progress_stage=f"ocr_page_{completed}")
    else:
        for idx, path in enumerate(paths, start=1):
            if progress_job_id:
                _update_ai_job(progress_job_id, pages_sent=idx - 1, progress_stage=f"ocr_page_{idx}")
                if _ai_job_cancelled(progress_job_id):
                    break
            idx, page_text, evidence, page_warnings, used_engine = run_one(idx, path)
            if used_engine != "paddleocr":
                engine = used_engine
            if page_text:
                pages_by_index[idx] = page_text
            if evidence:
                evidence_by_index[idx] = evidence
            warnings.extend(page_warnings)
            if progress_job_id:
                _update_ai_job(progress_job_id, pages_sent=idx, progress_stage=f"ocr_page_{idx}")
    return (
        "\n\n---\n\n".join(pages_by_index[idx] for idx in sorted(pages_by_index)).strip(),
        "\n\n---\n\n".join(evidence_by_index[idx] for idx in sorted(evidence_by_index)).strip(),
        len(paths),
        languages,
        engine,
        warnings,
    )


def _paddle_lang_for(language: str) -> str:
    return "en"


def _run_paddleocr_image(path: Path, language: str) -> str:
    try:
        from paddleocr import PaddleOCR  # type: ignore
    except Exception as e:
        raise RuntimeError(f"PaddleOCR is not installed: {e}")

    try:
        engine = PaddleOCR(use_angle_cls=True, lang=_paddle_lang_for(language), show_log=False)
    except TypeError:
        engine = PaddleOCR(use_angle_cls=True, lang=_paddle_lang_for(language))
    result = engine.ocr(str(path), cls=True)
    lines = []
    for page in result or []:
        for item in page or []:
            try:
                text = item[1][0]
                confidence = float(item[1][1])
            except Exception:
                continue
            if text and confidence >= 0.35:
                lines.append(str(text).strip())
    return _cleanup_ocr_markdown("\n".join(lines))


def _collect_ocr_markdown(recipe_id: str, conn, max_pages: int, language: str, cfg: dict) -> tuple[str, str, int, str, str, list[str]]:
    paths = _collect_recipe_image_paths(recipe_id, conn, max_pages)
    return _collect_ocr_markdown_from_paths(paths, language, cfg)



__all__ = [name for name in globals() if not name.startswith("__")]
