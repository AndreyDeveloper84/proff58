// Логотипы провайдеров входа — inline SVG: без запросов за картинками и с
// точным цветом в обеих темах. Все декоративные (aria-hidden): название
// провайдера всегда есть рядом текстом или в aria-label кнопки.

type LogoProps = { className?: string };

/**
 * Логотип VK: скруглённый квадрат с вырезанными буквами. Цвет — currentColor,
 * поэтому на синей кнопке VK ID он белый, а буквы «просвечивают» синим фоном.
 */
export function VkLogo({ className }: LogoProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden focusable="false">
      <path
        fill="currentColor"
        fillRule="evenodd"
        d="M1.69 1.69C0 3.38 0 6.1 0 11.52v.96c0 5.43 0 8.14 1.69 9.83C3.38 24 6.1 24 11.52 24h.96c5.43 0 8.14 0 9.83-1.69C24 20.62 24 17.9 24 12.48v-.96c0-5.43 0-8.14-1.69-9.83C20.62 0 17.9 0 12.48 0h-.96C6.1 0 3.38 0 1.69 1.69Zm2.36 5.61c.13 6.24 3.25 9.99 8.72 9.99h.31v-3.57c2.01.2 3.53 1.67 4.14 3.57h2.84c-.78-2.84-2.83-4.41-4.11-5.01 1.28-.74 3.08-2.54 3.51-4.98h-2.58c-.56 1.98-2.22 3.78-3.8 3.95V7.3h-2.58v6.92c-1.6-.4-3.62-2.34-3.71-6.92H4.05Z"
      />
    </svg>
  );
}

/** «Я» Яндекса: красный круг #FC3F1D с белой буквой — цвета фиксированные в обеих темах. */
export function YandexLogo({ className }: LogoProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden focusable="false">
      <circle cx="12" cy="12" r="12" fill="#FC3F1D" />
      <path
        fill="#fff"
        fillRule="evenodd"
        d="M15.9 19.6V4.4h-3.5C9 4.4 7.1 6.2 7.1 8.9c0 2.1 1 3.4 2.8 4.4l-3 6.3h2.7l2.7-5.7h1.1v5.7h2.5ZM13.4 6.4h-1c-1.8 0-2.8.9-2.8 2.5 0 1.7 1 3 2.8 3h1V6.4Z"
      />
    </svg>
  );
}

/** Знак Mail — «@». Цвет — currentColor (белый на синей кнопке). */
export function MailLogo({ className }: LogoProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      aria-hidden
      focusable="false"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.6"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="12" cy="12" r="4" />
      <path d="M16 8v5a3 3 0 0 0 6 0v-1a10 10 0 1 0-3.92 7.94" />
    </svg>
  );
}
