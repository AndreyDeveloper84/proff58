import { ssrHeaders } from "./ssr";
// Тема оформления из SiteSettings (#76). Server-side only — использует INTERNAL_API_BASE_URL.

export interface SiteTheme {
  name: string;
  primary_color: string;
  accent_color: string;
  logo_url: string;
  region: string;
  contacts: Record<string, unknown>;
  /** Ссылка на бота магазина в MAX. Пусто — бот не настроен, плитку не рисуем. */
  max_bot_url?: string;
  /** Публичные бизнес-флаги (T4): выключенный раздел витрина не показывает. */
  features?: { reviews?: boolean };
}

const DEFAULT_THEME: SiteTheme = {
  name: "Профессионал",
  primary_color: "#00a14b",
  accent_color: "#b5e61d",
  logo_url: "",
  region: "Пенза",
  contacts: {},
  max_bot_url: "",
  features: { reviews: false },
};

export async function getSiteTheme(): Promise<SiteTheme> {
  const base = process.env.INTERNAL_API_BASE_URL;
  if (!base) return DEFAULT_THEME;
  try {
    const res = await fetch(`${base.replace(/\/$/, "")}/api/core/theme/`, {
      headers: ssrHeaders(),
      next: { revalidate: 60 },
    });
    if (!res.ok) return DEFAULT_THEME;
    const data = (await res.json()) as Partial<SiteTheme>;
    return {
      ...DEFAULT_THEME,
      ...data,
      contacts:
        data.contacts && typeof data.contacts === "object" && !Array.isArray(data.contacts)
          ? data.contacts
          : {},
    };
  } catch {
    return DEFAULT_THEME;
  }
}
