import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import enTranslation from './locales/en/translation.json';
import ptBRTranslation from './locales/pt-BR/translation.json';

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    supportedLngs: ['en', 'pt-BR'],
    fallbackLng: 'en',
    debug: import.meta.env.DEV,
    detection: {
      order: ['queryString', 'cookie', 'localStorage', 'sessionStorage', 'navigator', 'htmlTag'],
      caches: ['cookie'],
    },
    resources: {
      en: {
        translation: enTranslation,
      },
      'pt-BR': {
        translation: ptBRTranslation,
      },
    },
    react: {
      useSuspense: false,
    },
  });

export default i18n;
