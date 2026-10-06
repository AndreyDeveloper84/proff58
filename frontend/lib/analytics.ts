// Тонкий слой аналитики витрины (§21). Провайдер — Яндекс.Метрика (DRF-2795), и она
// работает только после согласия на аналитические cookie (DRF-2796): компонент
// components/analytics/YandexMetrika сообщает сюда номер счётчика, когда скрипт
// включён, и снимает его при отзыве. track() без счётчика — no-op: UI вызывает
// события всегда, а отправляются они только при согласии.
//
// В параметрах событий — только технические значения (slug, счётчики). Телефонов,
// имён, номеров заказов здесь быть не должно: Метрика — сторонний сервис.

export type ToolTypeSelectPayload = {
  category_slug: string;
  tool_type_slug: string | null; // null — снятие типа (deselect)
  tool_type_label: string | null;
  result_count: number; // счётчик выдачи на момент действия (до навигации — best-effort)
  previous_tool_type: string | null;
  active_filters_count: number; // активных сайдбар-фильтров (без самого типа)
};

export type AnalyticsEvent = {
  name: "tool_type_select";
  payload: ToolTypeSelectPayload;
};

type Ym = (counterId: number, method: string, ...args: unknown[]) => void;

declare global {
  interface Window {
    ym?: Ym & { a?: unknown[]; l?: number };
  }
}

let counterId: number | null = null;

/** Включить/выключить отправку: вызывает YandexMetrika при согласии и при отзыве. */
export function setAnalyticsCounter(id: number | null): void {
  counterId = id;
}

/** Текущий счётчик (для тестов и отладки). */
export function analyticsCounter(): number | null {
  return counterId;
}

export function track(event: AnalyticsEvent): void {
  if (counterId === null || typeof window === "undefined" || typeof window.ym !== "function") {
    return;
  }
  window.ym(counterId, "reachGoal", event.name, event.payload);
}
