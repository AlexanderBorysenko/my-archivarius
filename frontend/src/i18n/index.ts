import { createI18n } from 'vue-i18n'
import en from './en'
import uk from './uk'
import ru from './ru'

export type Language = 'en' | 'uk' | 'ru'
const SUPPORTED: Language[] = ['en', 'uk', 'ru']
export const DEFAULT_LANG: Language = 'en'

export function mapLang(code: string | null | undefined): Language {
  if (!code) return DEFAULT_LANG
  const base = code.split('-')[0].toLowerCase() as Language
  return SUPPORTED.includes(base) ? base : DEFAULT_LANG
}

export function bcp47(lang: Language): string {
  return ({ en: 'en-US', uk: 'uk-UA', ru: 'ru-RU' } as const)[lang]
}

function resolveInitialLocale(): Language {
  const stored = localStorage.getItem('ui_language')
  if (stored && SUPPORTED.includes(stored as Language)) return stored as Language
  return mapLang(navigator.language)
}

// Slavic plural index for 4-form messages: "zero | one | few | many".
function slavicPlural(choice: number, choicesLength: number): number {
  if (choice === 0) return 0
  const teen = choice > 10 && choice < 20
  const endsOne = choice % 10 === 1
  const endsFew = choice % 10 >= 2 && choice % 10 <= 4
  if (!teen && endsOne) return 1
  if (!teen && endsFew) return 2
  return choicesLength > 3 ? 3 : 2
}

export const i18n = createI18n({
  legacy: false,
  locale: resolveInitialLocale(),
  fallbackLocale: DEFAULT_LANG,
  messages: { en, uk, ru },
  pluralRules: { ru: slavicPlural, uk: slavicPlural },
})

export function setLocale(lang: Language) {
  i18n.global.locale.value = lang
  localStorage.setItem('ui_language', lang)
}
