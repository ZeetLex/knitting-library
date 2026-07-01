"""AI prompt and transcription text helpers."""
from app.core.foundation import *

def _default_ai_scan_prompt(language: str = "en") -> str:
    prompts = {
        "no": (
            "Transkriber synlig oppskriftstekst fra bildet. Svar kun med teksten. "
            "Behold linjeskift, tall, forkortelser og rekkefølge. Ikke forklar, rydd, oppsummer eller bruk Markdown hvis det ikke trengs."
        ),
        "hu": (
            "Írd át a képen látható mintaszöveget. Csak a szöveget add vissza. "
            "Őrizd meg a sortöréseket, számokat, rövidítéseket és sorrendet. Ne magyarázz, ne tisztítsd át, ne foglald össze, és ne használj Markdown-t, ha nem szükséges."
        ),
    }
    return prompts.get(language, (
        "Transcribe the visible recipe text from the image. Return only the text. "
        "Keep line breaks, numbers, abbreviations, and order. Do not explain, clean up, summarize, or use Markdown unless it is naturally needed."
    ))


def _default_ai_cleanup_prompt(language: str = "en") -> str:
    prompts = {
        "no": (
            "Du får rå tekst fra én side i en strikkeoppskrift. Rydd teksten til lesbar Markdown for denne siden. "
            "Behold originalspråk, tall, masketall, størrelser, forkortelser, garn, pinner og rad-/omgangstekst. "
            "Ikke legg til ny informasjon. Returner kun den ryddede teksten."
        ),
        "hu": (
            "Egy kötésminta-oldal nyers szövegét kapod. Tisztítsd olvasható Markdown szöveggé erre az oldalra. "
            "Őrizd meg az eredeti nyelvet, számokat, szemszámokat, méreteket, rövidítéseket, fonalat, tűket és sor/kör utasításokat. "
            "Ne adj hozzá új információt. Csak a tisztított szöveget add vissza."
        ),
    }
    return prompts.get(language, (
        "You receive raw text from one page of a knitting pattern. Clean it into readable Markdown for this page. "
        "Preserve the original language, numbers, stitch counts, sizes, abbreviations, yarn, needle details, and row/round wording. "
        "Do not add new information. Return only the cleaned text."
    ))


def _clean_ai_transcription(content: str) -> str:
    content = (content or "").strip()
    content = re.sub(r"(?is)<\|channel\>.*?(?=<\|channel\>|$)", "", content).strip()
    content = re.sub(r"(?is)<think>.*?</think>", "", content).strip()
    content = re.sub(r"(?is)^```(?:markdown|md|text)?\s*", "", content).strip()
    content = re.sub(r"(?is)\s*```$", "", content).strip()
    content = re.sub(r"(?is)^(?:final answer|transcription|markdown)\s*:\s*", "", content).strip()
    return content



__all__ = [name for name in globals() if not name.startswith("__")]
