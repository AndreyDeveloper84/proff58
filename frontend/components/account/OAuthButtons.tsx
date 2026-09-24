import { cn } from "@/lib/utils";
import { oauthStartHref, type OAuthProviderId } from "@/lib/oauth";
import { MailLogo, VkLogo, YandexLogo } from "./oauth-logos";

// Кнопки входа через провайдеров. Это обычные ссылки: старт — переход верхнего
// уровня на /api/oauth/<provider>/start/ (Django уводит 302 на провайдера), не
// fetch и не next/link — клиентский роутер Next этот адрес не знает.
//
// Брендинг по гайдлайнам: VK ID — основная кнопка #0077FF с белым «VK ID»;
// Mail — вход через тот же VK ID (via=mail_ru), синяя кнопка с «@»; Яндекс ID —
// дополнительный (белый) вариант с красным «Я», белый и в тёмной теме.

type Button = {
  key: string;
  label: string;
  href: string;
  Logo: typeof VkLogo;
  tone: "blue" | "white";
};

function buttonsFor(providers: OAuthProviderId[], next: string | null): Button[] {
  const out: Button[] = [];
  if (providers.includes("vkid")) {
    out.push(
      { key: "vkid", label: "VK ID", href: oauthStartHref("vkid", { next }), Logo: VkLogo, tone: "blue" },
      {
        key: "mail",
        label: "Mail",
        href: oauthStartHref("vkid", { via: "mail_ru", next }),
        Logo: MailLogo,
        tone: "blue",
      },
    );
  }
  if (providers.includes("yandex")) {
    out.push({
      key: "yandex",
      label: "Яндекс ID",
      href: oauthStartHref("yandex", { next }),
      Logo: YandexLogo,
      tone: "white",
    });
  }
  return out;
}

// Колонки по числу кнопок. Три в ряд не влезают в узкую карточку («Яндекс ID»
// с логотипом шире трети телефона), поэтому до ширины ~23rem контейнера —
// две синие рядом и Яндекс ID во всю ширину под ними.
const GRID: Record<number, string> = {
  1: "grid-cols-1",
  2: "grid-cols-2",
  3: "grid-cols-2 @[23rem]:grid-cols-3",
};

export function OAuthButtons({
  providers,
  next,
}: {
  providers: OAuthProviderId[];
  next: string | null;
}) {
  const buttons = buttonsFor(providers, next);
  if (buttons.length === 0) return null;

  return (
    <div className="@container">
      <ul className={cn("grid gap-3", GRID[buttons.length])}>
        {buttons.map(({ key, label, href, Logo, tone }, index) => (
          <li
            key={key}
            className={cn(buttons.length === 3 && index === 2 && "col-span-2 @[23rem]:col-span-1")}
          >
            <a
              href={href}
              aria-label={`Войти через ${label}`}
              data-provider={key}
              className={cn(
                "inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-md px-3 text-sm font-semibold whitespace-nowrap transition",
                "focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-card",
                // На синем фокус — белое кольцо внутри кнопки (видно в обеих темах)
                // плюс синее снаружи: одно белое снаружи пропало бы на светлой карточке.
                tone === "blue"
                  ? "bg-[#0077FF] text-white hover:bg-[#0071F2] focus-visible:outline-2 focus-visible:-outline-offset-4 focus-visible:outline-white focus-visible:ring-[#0077FF]"
                  : "border border-[#E0E0E0] bg-white text-[#1A1A1A] hover:bg-[#F2F2F2] focus-visible:outline-none focus-visible:ring-accent",
              )}
            >
              <Logo className="h-5 w-5 shrink-0" />
              {label}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
