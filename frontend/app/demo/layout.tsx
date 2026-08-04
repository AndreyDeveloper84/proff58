import { notFound } from "next/navigation";

/**
 * Витрина компонентов — только для разработки.
 *
 * Страницы /demo, /demo/ui и /demo/screens отдавались снаружи вместе с обычным
 * сайтом: любой посетитель мог открыть внутренний UI-кит с черновой вёрсткой и
 * выдуманными товарами. Из репозитория их не убираем — как справочник по
 * компонентам они полезны, — но наружу закрываем.
 *
 * Открыты, если сборка не production (локальная разработка) либо явно включены
 * переменной DEMO_PAGES=1 в окружении стенда.
 */
export const dynamic = "force-dynamic";

function demoEnabled(): boolean {
  return process.env.NODE_ENV !== "production" || process.env.DEMO_PAGES === "1";
}

export default function DemoLayout({ children }: { children: React.ReactNode }) {
  if (!demoEnabled()) notFound();
  return <>{children}</>;
}
