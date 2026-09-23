// Единственное всплывающее уведомление витрины (toast): «скопировано», «товары
// удалены» и т. п. Вырос из стора уведомлений о копировании контакта (UX-03).
//
// Стор на модуле, а не React-контекст: уведомления нужны и шапке, и подвалу, и
// корзине, и 404 — всем им хватает одного региона (components/ui/ToastRegion,
// смонтирован в layout), а провайдер ради одной строки состояния был бы лишним
// слоем. Таймер тоже живёт здесь, а не в компоненте: уход со страницы не оставит
// «зависшее» уведомление.
//
// Сообщение одно: новое заменяет прежнее, перезапускает таймер и снимает паузу —
// стопки из повторных нажатий не образуется.
//
// Модуль без React и без window при импорте — безопасен для SSR.

export type Toast =
  | { kind: "success"; id: number; message: string }
  // Буфер недоступен: показываем сам текст, чтобы его можно было выделить руками.
  | { kind: "manual"; id: number; message: string; value: string };

export const DEFAULT_TOAST_MS = 4000;

let current: Toast | null = null;
let timer: ReturnType<typeof setTimeout> | null = null;
// Момент, когда уведомление должно скрыться, — пока таймер идёт.
let deadline = 0;
// Остаток времени на паузе (hover/focus по карточке); null — паузы нет.
let pausedRemaining: number | null = null;
let seq = 0;
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((listener) => listener());
}

function clearTimer() {
  if (timer) clearTimeout(timer);
  timer = null;
  pausedRemaining = null;
}

function startTimer(ms: number) {
  deadline = Date.now() + ms;
  timer = setTimeout(dismissToast, ms);
}

export function subscribeToast(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function getToast(): Toast | null {
  return current;
}

export function dismissToast() {
  clearTimer();
  current = null;
  emit();
}

/** Короткое уведомление об успехе; скрывается само через `durationMs`. */
export function showToast(message: string, { durationMs = DEFAULT_TOAST_MS } = {}) {
  clearTimer();
  current = { kind: "success", id: ++seq, message };
  startTimer(durationMs);
  emit();
}

/**
 * Ручное копирование: сообщение + поле с выделенным текстом. Без таймера —
 * человеку нужно время выделить и скопировать текст; закрывается кнопкой.
 */
export function showManualCopy(message: string, value: string) {
  clearTimer();
  current = { kind: "manual", id: ++seq, message, value };
  emit();
}

/** Остановить таймер, запомнив остаток (курсор или фокус на карточке). */
export function pauseToast() {
  if (!timer) return;
  clearTimeout(timer);
  timer = null;
  pausedRemaining = Math.max(0, deadline - Date.now());
}

/** Досчитать запомненный остаток после паузы. Без паузы — ничего не делает. */
export function resumeToast() {
  if (pausedRemaining === null || !current) return;
  const remaining = pausedRemaining;
  pausedRemaining = null;
  startTimer(remaining);
}
