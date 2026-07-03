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
        "fr": (
            "Transcris le texte visible du modèle depuis l'image. Réponds uniquement avec le texte. "
            "Conserve les sauts de ligne, les nombres, les abréviations et l'ordre. N'explique pas, ne nettoie pas, ne résume pas et n'utilise Markdown que si c'est naturellement nécessaire."
        ),
        "de": (
            "Transkribiere den sichtbaren Anleitungstext aus dem Bild. Gib nur den Text zurück. "
            "Behalte Zeilenumbrüche, Zahlen, Abkürzungen und die Reihenfolge bei. Erkläre nichts, bereinige nichts, fasse nichts zusammen und verwende Markdown nur, wenn es natürlich nötig ist."
        ),
        "es": (
            "Transcribe el texto visible del patrón desde la imagen. Devuelve solo el texto. "
            "Conserva los saltos de línea, los números, las abreviaturas y el orden. No expliques, no limpies, no resumas y no uses Markdown salvo que sea necesario de forma natural."
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
        "fr": (
            "Tu reçois le texte brut d'une page de modèle de tricot. Nettoie-le en Markdown lisible pour cette page. "
            "Conserve la langue d'origine, les nombres, les nombres de mailles, les tailles, les abréviations, les informations sur le fil, les aiguilles et les rangs/tours. "
            "N'ajoute aucune information nouvelle. Retourne uniquement le texte nettoyé."
        ),
        "de": (
            "Du erhältst Rohtext von einer Seite einer Strickanleitung. Bereinige ihn zu gut lesbarem Markdown für diese Seite. "
            "Bewahre die Originalsprache, Zahlen, Maschenzahlen, Größen, Abkürzungen, Garn- und Nadelangaben sowie Reihen-/Rundenangaben. "
            "Füge keine neuen Informationen hinzu. Gib nur den bereinigten Text zurück."
        ),
        "es": (
            "Recibes texto sin procesar de una página de un patrón de tejido. Límpialo como Markdown legible para esta página. "
            "Conserva el idioma original, los números, los conteos de puntos, las tallas, las abreviaturas, los datos de hilo, agujas y las indicaciones de filas/vueltas. "
            "No añadas información nueva. Devuelve solo el texto limpio."
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
