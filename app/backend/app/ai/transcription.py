"""Versioned subscription transcription options; no app or credential imports."""
PROMPT_VERSION = "formatted-v1"
DEFAULTS = {
    "ai_chatgpt_mode": "formatted",
    "ai_chatgpt_reasoning": "low",
    "ai_chatgpt_detail": "original",
    "ai_chatgpt_concurrency": "2",
}
NONE_MODELS = {"gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-6-sol", "gpt-6-luna"}


def options(cfg):
    result = {key: str(cfg.get(key, default)) for key, default in DEFAULTS.items()}
    allowed = {"ai_chatgpt_mode": {"formatted", "legacy"}, "ai_chatgpt_reasoning": {"low", "medium", "none"},
               "ai_chatgpt_detail": {"original", "high"}, "ai_chatgpt_concurrency": {"1", "2"}}
    if any(result[key] not in choices for key, choices in allowed.items()):
        raise ValueError("invalid_transcription_options")
    if result["ai_chatgpt_reasoning"] == "none" and cfg.get("ai_chatgpt_model") not in NONE_MODELS:
        raise ValueError("unsupported_reasoning")
    return result


FORMAT_INSTRUCTIONS = {
    "en": "Transcribe this page faithfully as readable Markdown. Use only headings present in the source, paragraphs, and genuine tables. Join typographic line wraps within paragraphs; keep separate instructions separate.",
    "no": "Transkriber siden nøyaktig som lesbar Markdown. Bruk bare overskrifter som finnes i originalen, avsnitt og faktiske tabeller. Slå sammen typografiske linjeskift i avsnitt; hold separate instruksjoner adskilt.",
    "de": "Schreibe diese Seite originalgetreu als lesbares Markdown ab. Verwende nur vorhandene Überschriften, Absätze und tatsächliche Tabellen. Verbinde typografische Zeilenumbrüche innerhalb von Absätzen; trenne einzelne Anweisungen.",
    "fr": "Transcris fidèlement cette page en Markdown lisible. Utilise uniquement les titres existants, les paragraphes et les véritables tableaux. Réunis les lignes coupées dans les paragraphes et sépare les instructions distinctes.",
    "es": "Transcribe fielmente esta página en Markdown legible. Utiliza solo los títulos existentes, párrafos y tablas reales. Une los saltos tipográficos dentro de los párrafos y separa las instrucciones distintas.",
    "hu": "Írd át ezt az oldalt hűen, olvasható Markdown formában. Csak az eredeti címeket, bekezdéseket és valódi táblázatokat használd. A bekezdésen belüli tipográfiai sortöréseket egyesítsd; a külön utasításokat tartsd külön.",
}
FIDELITY = """Preserve the original language, wording, instruction order, every number, size sequence, unit, abbreviation, and repeat symbol. Do not summarize, translate, calculate, fix apparent errors, invent headings, expand abbreviations, or add explanations. Escape literal Markdown metacharacters such as knitting repeat asterisks and underscores so they remain visible. Preserve explicit row/round numbers as literal labels, not automatically numbered lists. Mark unreadable spans as [illegible]; never guess. Return only the page transcription, without a code fence."""
TRANSLATED_FIDELITY = {
    "no": "Behold originalspråk, ordlyd, instruksjonsrekkefølge, alle tall, størrelsesrekker, enheter, forkortelser og gjentakelsessymboler. Ikke oppsummer, oversett, beregn, rett tilsynelatende feil, finn på overskrifter, utvid forkortelser eller legg til forklaringer. Unnvik bokstavelige Markdown-tegn som stjerner og understreker i strikkegjentakelser slik at tegnene forblir synlige. Behold eksplisitte rad- og omgangstall som bokstavelige etiketter, ikke automatisk nummererte lister. Merk uleselige partier som [uleselig]; aldri gjett. Returner bare sidens transkripsjon uten kodeblokk.",
    "de": "Bewahre Originalsprache, Wortlaut, Reihenfolge, jede Zahl, Größenfolge, Einheit, Abkürzung und jedes Wiederholungszeichen. Nicht zusammenfassen, übersetzen, rechnen, scheinbare Fehler korrigieren, Überschriften erfinden, Abkürzungen ausschreiben oder Erklärungen ergänzen. Maskiere wörtliche Markdown-Zeichen wie Wiederholungssterne und Unterstriche, damit sie sichtbar bleiben. Erhalte ausdrückliche Reihen- und Rundennummern als wörtliche Beschriftungen statt automatisch nummerierter Listen. Markiere unleserliche Stellen mit [unleserlich]; niemals raten. Gib nur die Abschrift der Seite ohne Codeblock zurück.",
    "fr": "Conserve la langue, le texte, l’ordre des instructions, tous les nombres, suites de tailles, unités, abréviations et symboles de répétition. Ne résume pas, ne traduis pas, ne calcule pas, ne corrige pas les erreurs apparentes, n’invente pas de titres, ne développe pas les abréviations et n’ajoute pas d’explications. Échappe les caractères Markdown littéraux, notamment les astérisques et les tirets bas, pour qu’ils restent visibles. Conserve les numéros explicites des rangs et tours comme libellés littéraux, sans numérotation automatique. Indique [illisible] pour les passages illisibles ; ne devine jamais. Renvoie uniquement la transcription de la page sans bloc de code.",
    "es": "Conserva el idioma, las palabras, el orden de las instrucciones, todos los números, secuencias de tallas, unidades, abreviaturas y símbolos de repetición. No resumas, traduzcas, calcules, corrijas errores aparentes, inventes títulos, desarrolles abreviaturas ni añadas explicaciones. Escapa los caracteres Markdown literales, como asteriscos y guiones bajos de las repeticiones, para que sigan visibles. Conserva los números explícitos de filas y vueltas como etiquetas literales, sin numeración automática. Marca los fragmentos ilegibles como [ilegible]; nunca adivines. Devuelve solo la transcripción de la página, sin bloque de código.",
    "hu": "Őrizd meg az eredeti nyelvet, megfogalmazást, utasítássorrendet, minden számot, méretsorozatot, mértékegységet, rövidítést és ismétlésjelet. Ne foglalj össze, ne fordíts, ne számolj, ne javíts látszólagos hibákat, ne találj ki címeket, ne oldj fel rövidítéseket és ne adj magyarázatot. A szó szerinti Markdown-jeleket, például az ismétlési csillagokat és aláhúzásokat úgy jelöld, hogy láthatók maradjanak. A sorok és körök számait szó szerinti címkeként őrizd meg, ne automatikusan számozott listaként. Az olvashatatlan részeket [olvashatatlan] jelöléssel add vissza; soha ne találgass. Csak az oldal átírását add vissza, kódblokk nélkül.",
}


def formatted_prompt(language):
    return FORMAT_INSTRUCTIONS.get(language, FORMAT_INSTRUCTIONS["en"]) + "\n\n" + TRANSLATED_FIDELITY.get(language, FIDELITY)
