import { useUiStore } from '../store/uiStore';
import { en } from './en';
import { vi } from './vi';
import type { Locale, Translations } from './types';

export type { Locale, Translations } from './types';

export function useTranslation(): { locale: Locale; t: Translations } {
  const locale = useUiStore((state) => state.locale);
  return { locale, t: locale === 'vi' ? vi : en };
}
