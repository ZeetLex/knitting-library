"""Render the authored reference pages for a controlled transcription benchmark."""
import argparse
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--font', type=Path, default=Path('C:/Windows/Fonts/consola.ttf'))
parser.add_argument('--output', type=Path, default=Path('data-test/speed-corpus'))
args = parser.parse_args()
reference = Path(__file__).resolve().parents[1] / 'app/backend/tests/fixtures/transcription_reference.json'
pages = json.loads(reference.read_text(encoding='utf-8'))
args.output.mkdir(parents=True, exist_ok=True)
font = ImageFont.truetype(str(args.font), 28)
for filename, text in pages.items():
    image = Image.new('RGB', (1488, 2105), 'white')
    draw = ImageDraw.Draw(image)
    for index, line in enumerate(text.splitlines()):
        draw.text((65, 65 + index * 54), line, font=font, fill='black')
    image.save(args.output / filename)
(args.output / 'reference.json').write_text(json.dumps(pages, ensure_ascii=False, indent=2), encoding='utf-8')
print('Six authored reference pages rendered. No inference submitted.')
