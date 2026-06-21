const localeModules = import.meta.glob('../locales/*.js', { eager: true });

function codeFromPath(path) {
  return path.split('/').pop().replace(/\.js$/, '');
}

const localeEntries = Object.entries(localeModules)
  .filter(([path]) => !codeFromPath(path).startsWith('_'))
  .map(([path, module]) => {
    const code = module.language?.code || codeFromPath(path);
    return {
      code,
      messages: module.default || {},
      meta: {
        code,
        name: module.language?.name || code.toUpperCase(),
        nativeName: module.language?.nativeName || module.language?.name || code.toUpperCase(),
        flag: module.language?.flag || '🌐',
        locale: module.language?.locale || code,
        order: module.language?.order ?? 999,
      },
    };
  })
  .sort((a, b) => a.meta.order - b.meta.order || a.meta.nativeName.localeCompare(b.meta.nativeName));

export const LANGUAGE_OPTIONS = localeEntries.map(entry => entry.meta);

export const SUPPORTED_LANGUAGES = LANGUAGE_OPTIONS.map(language => language.code);

const translations = localeEntries.reduce((all, entry) => {
  all[entry.code] = entry.messages;
  return all;
}, {});

export function getLanguageLocale(language) {
  return LANGUAGE_OPTIONS.find(option => option.code === language)?.locale || LANGUAGE_OPTIONS[0].locale;
}

export function isSupportedLanguage(language) {
  return SUPPORTED_LANGUAGES.includes(language);
}

export function useT(language) {
  return function t(key) {
    const fallback = translations.en || {};
    const dict = translations[language] || fallback;
    return dict[key] !== undefined
      ? dict[key]
      : fallback[key] !== undefined
        ? fallback[key]
        : key;
  };
}

export default translations;
