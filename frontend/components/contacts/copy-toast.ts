// Единственное уведомление о копировании контакта (UX-03).
//
// Стор на модуле, а не React-контекст: кнопки копирования стоят и в шапке, и в
// подвале, и на 404 — всем им нужен один и тот же регион, и провайдер ради одной
// строки состояния был бы лишним слоем. Сообщение одно: новое заменяет прежнее и
// перезапускает таймер, очереди из повторных нажатий не образуется.

export type CopyToast =
  | { kind: "success"; id: number; message: string }
  // Буфер недоступен: показываем сам текст, чтобы его можно было выделить руками.
  | { kind: "manual"; id: number; message: string; value: string };

const SUCCESS_MS = 2600;

let current: CopyToast | null = null;
let timer: ReturnType<typeof setTimeout> | null = null;
let seq = 0;
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((listener) => listener());
}

export function subscribeCopyToast(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function getCopyToast(): CopyToast | null {
  return current;
}

export function dismissCopyToast() {
  if (timer) clearTimeout(timer);
  timer = null;
  current = null;
  emit();
}

export function showCopySuccess(message: string) {
  if (timer) clearTimeout(timer);
  current = { kind: "success", id: ++seq, message };
  timer = setTimeout(dismissCopyToast, SUCCESS_MS);
  emit();
}

// Без таймера: человеку нужно время выделить и скопировать текст вручную.
export function showCopyManual(message: string, value: string) {
  if (timer) clearTimeout(timer);
  timer = null;
  current = { kind: "manual", id: ++seq, message, value };
  emit();
}
