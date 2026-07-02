import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const localesDir = path.resolve(__dirname, '../src/locales');
const requiredLocales = new Set(['en', 'no', 'hu', 'fr', 'de', 'es']);
const metadataFields = ['code', 'name', 'nativeName', 'flag', 'locale', 'order'];

function loadLocale(filePath) {
  const source = fs.readFileSync(filePath, 'utf8');
  const languageStart = source.match(/export\s+const\s+language\s*=\s*/);
  const dictStart = source.match(/const\s+\w+\s*=\s*/);

  if (!languageStart || !dictStart) {
    throw new Error(`${path.basename(filePath)} does not match the expected locale file shape`);
  }

  return {
    language: Function(`"use strict"; return (${extractObject(source, languageStart.index + languageStart[0].length)});`)(),
    messages: Function(`"use strict"; return (${extractObject(source, dictStart.index + dictStart[0].length)});`)(),
  };
}

function extractObject(source, startAt) {
  const start = source.indexOf('{', startAt);
  if (start === -1) {
    throw new Error('Could not find object literal');
  }

  let depth = 0;
  let quote = '';
  let escaped = false;

  for (let i = start; i < source.length; i += 1) {
    const char = source[i];

    if (quote) {
      if (escaped) {
        escaped = false;
      } else if (char === '\\') {
        escaped = true;
      } else if (char === quote) {
        quote = '';
      }
      continue;
    }

    if (char === '"' || char === "'" || char === '`') {
      quote = char;
      continue;
    }
    if (char === '{') {
      depth += 1;
      continue;
    }
    if (char === '}') {
      depth -= 1;
      if (depth === 0) {
        return source.slice(start, i + 1);
      }
    }
  }

  throw new Error('Could not find end of object literal');
}

function placeholders(value) {
  return [...String(value).matchAll(/\{[A-Za-z0-9_]+\}/g)].map(match => match[0]).sort();
}

function sameList(a, b) {
  return a.length === b.length && a.every((item, index) => item === b[index]);
}

const localeFiles = fs.readdirSync(localesDir)
  .filter(file => file.endsWith('.js') && !file.startsWith('_'))
  .sort();

const locales = new Map(localeFiles.map((file) => {
  const code = path.basename(file, '.js');
  return [code, loadLocale(path.join(localesDir, file))];
}));

const errors = [];

for (const code of requiredLocales) {
  if (!locales.has(code)) {
    errors.push(`Missing required locale: ${code}`);
  }
}

for (const [code, locale] of locales) {
  for (const field of metadataFields) {
    if (locale.language[field] === undefined || locale.language[field] === '') {
      errors.push(`${code}: missing language metadata field "${field}"`);
    }
  }
  if (locale.language.code !== code) {
    errors.push(`${code}: metadata code "${locale.language.code}" does not match filename`);
  }
}

const english = locales.get('en')?.messages;
if (!english) {
  errors.push('English reference locale is missing');
} else {
  const referenceKeys = Object.keys(english).sort();
  const referenceKeySet = new Set(referenceKeys);

  for (const [code, locale] of locales) {
    const keys = Object.keys(locale.messages).sort();
    const keySet = new Set(keys);

    for (const key of referenceKeys) {
      if (!keySet.has(key)) {
        errors.push(`${code}: missing key "${key}"`);
      }
    }

    for (const key of keys) {
      if (!referenceKeySet.has(key)) {
        errors.push(`${code}: extra key "${key}"`);
      }
    }

    for (const key of referenceKeys) {
      if (!keySet.has(key)) continue;
      const expected = placeholders(english[key]);
      const actual = placeholders(locale.messages[key]);
      if (!sameList(expected, actual)) {
        errors.push(`${code}: placeholder mismatch for "${key}" expected ${expected.join(', ') || '(none)'} got ${actual.join(', ') || '(none)'}`);
      }
    }
  }
}

if (errors.length) {
  console.error(errors.join('\n'));
  process.exit(1);
}

console.log(`Validated ${locales.size} locales: ${[...locales.keys()].join(', ')}`);
