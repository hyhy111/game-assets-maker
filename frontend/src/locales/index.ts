import { createI18n } from 'vue-i18n'
import zhCN from './zh-CN'
import en from './en'

const LOCALE_STORAGE_KEY = 'gam:locale'

type SupportedLocale = 'zh-CN' | 'en'

function getSavedLocale(): SupportedLocale {
  const saved = localStorage.getItem(LOCALE_STORAGE_KEY)
  return saved === 'en' || saved === 'zh-CN' ? saved : 'zh-CN'
}

const i18n = createI18n({
  legacy: false,
  locale: getSavedLocale(),
  fallbackLocale: 'en',
  messages: {
    'zh-CN': zhCN,
    'en': en,
  },
})

export default i18n

export function setLocale(locale: SupportedLocale) {
  i18n.global.locale.value = locale
  localStorage.setItem(LOCALE_STORAGE_KEY, locale)
}

export function getLocale(): string {
  return i18n.global.locale.value
}

export function toggleLocale() {
  setLocale(getLocale() === 'zh-CN' ? 'en' : 'zh-CN')
}
