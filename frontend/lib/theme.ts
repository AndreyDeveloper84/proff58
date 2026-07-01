// Тема оформления из SiteSettings (#76). Server-side only — использует INTERNAL_API_BASE_URL.
const SSR_HEADERS = { "X-Forwarded-Proto": "https" } as const;

export interface SiteTheme {
  name: string;
  primary_color: string;
  accent_color: string;
  logo_url: string;
}

const DEFAULT_THEME: SiteTheme = {
  name: "Профессионал",
  primary_color: "#00a14b",
  accent_color: "#b5e61d",
  logo_url: "",
};

export async function getSiteTheme(): Promise<SiteTheme> {
  const base = process.env.INTERNAL_API_BASE_URL;
  if (!base) return DEFAULT_THEME;
  try {
    const res = await fetch(`${base.replace(/\/$/, "")}/api/core/theme/`, {
      headers: SSR_HEADERS,
      next: { revalidate: 60 },
    });
    if (!res.ok) return DEFAULT_THEME;
    return (await res.json()) as SiteTheme;
  } catch {
    return DEFAULT_THEME;
  }
}
