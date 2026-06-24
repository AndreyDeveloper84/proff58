// Тонкий слой аналитики витрины (§21). Реальный провайдер (GA4 / Яндекс.Метрика) ещё не
// подключён, поэтому track() — намеренный no-op с TODO: события типизированы и вызываются из
// UI уже сейчас, чтобы при подключении провайдера осталось заменить только тело track().

export type ToolTypeSelectPayload = {
  category_slug: string;
  tool_type_slug: string | null; // null — снятие типа (deselect)
  tool_type_label: string | null;
  result_count: number; // счётчик выдачи на момент действия (до навигации — best-effort)
  previous_tool_type: string | null;
  active_filters_count: number; // активных сайдбар-фильтров (без самого типа)
};

export type AnalyticsEvent = { name: "tool_type_select"; payload: ToolTypeSelectPayload };

export function track(event: AnalyticsEvent): void {
  // TODO(analytics): подключить реальный провайдер. Сейчас no-op — не блокирует UI и не падает
  // при SSR/отсутствии window. Контракт payload зафиксирован типами выше (§21).
  void event;
}
