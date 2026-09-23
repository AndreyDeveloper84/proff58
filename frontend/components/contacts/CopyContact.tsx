"use client";

import { useSyncExternalStore, type MouseEvent, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { showManualCopy, showToast } from "@/lib/toast";

const MESSAGES = {
  phone: {
    ok: "Номер скопирован в буфер обмена",
    hint: "Скопировать номер телефона",
    manual: "Не удалось скопировать автоматически. Номер выделен — скопируйте его вручную.",
  },
  address: {
    ok: "Адрес скопирован в буфер обмена",
    hint: "Скопировать адрес",
    manual: "Не удалось скопировать автоматически. Адрес выделен — скопируйте его вручную.",
  },
} as const;

// Запасной путь для страниц без Clipboard API (http, старый WebView): временное
// поле + execCommand. Возвращает false, если и он не сработал.
function legacyCopy(text: string): boolean {
  try {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand("copy");
    area.remove();
    return ok;
  } catch {
    return false;
  }
}

export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Запрет или потеря фокуса — пробуем запасной путь ниже.
  }
  return legacyCopy(text);
}

/**
 * Контакт, который копируется по нажатию (UX-03).
 *
 * `value` — что именно уходит в буфер: отображаемый номер без `tel:` или ПОЛНЫЙ адрес,
 * даже когда на экране стоит короткая подпись магазина (`children`). Уведомление об
 * успехе показывается только после реального копирования; если буфер недоступен —
 * текст выводится выделенным, чтобы его можно было скопировать руками.
 *
 * Для телефона — `PhoneContact`: там нажатие ещё и звонит с телефона.
 */
export function CopyContact({
  kind,
  value,
  children,
  className,
}: {
  kind: keyof typeof MESSAGES;
  value: string;
  children?: ReactNode;
  className?: string;
}) {
  const text = MESSAGES[kind];
  const onClick = async () => {
    if (await copyText(value)) showToast(text.ok);
    else showManualCopy(text.manual, value);
  };
  return (
    <button
      type="button"
      onClick={onClick}
      title={text.hint}
      aria-label={`${text.hint}: ${value}`}
      className={cn("cursor-copy text-left transition hover:text-accent", className)}
    >
      {children ?? value}
    </button>
  );
}

// Мышь с наведением — «ПК»: там номер копируют, звонить с компьютера нечем.
// Решаем по типу указателя, а не по ширине экрана: планшет в альбомной
// ориентации шире многих ноутбуков, но звонить с него как раз можно.
const COPY_POINTER_QUERY = "(hover: hover) and (pointer: fine)";

function subscribePointer(onChange: () => void) {
  if (typeof window.matchMedia !== "function") return () => {};
  const query = window.matchMedia(COPY_POINTER_QUERY);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

function prefersCopy(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia(COPY_POINTER_QUERY).matches;
}

/**
 * Номер в международном виде для буфера: «8 (8412) 20-20-87» → «+7 8412 20-20-87».
 * Скобки убираем: вставленный в мессенджер или форму номер со скобками часто
 * не распознаётся как телефон.
 */
export function internationalPhone(display: string): string {
  return display
    .trim()
    .replace(/^(\+7|8)(?=[\s(])/, "+7")
    .replace(/[()]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Телефон магазина — одинаково в шапке, подвале, карточке товара и на инфо-страницах.
 *
 * Всегда настоящая `tel:`-ссылка: без JS и на телефоне/планшете она открывает
 * звонок. На устройстве с мышью нажатие (и Enter с клавиатуры) копирует номер и
 * показывает «Номер скопирован». Касание пальцем на ноутбуке с сенсорным экраном
 * остаётся звонком — смотрим на то, чем нажали, а не только на устройство.
 *
 * Доступное имя начинается с видимого текста и дополняется скрытым пояснением
 * действия. На сервере режим — «звонок», клиент уточняет его после гидратации.
 * Отдельной надписи «Позвонить» больше нет: номер и есть действие.
 */
export function PhoneContact({
  display,
  href,
  children,
  className,
  "data-event": dataEvent,
}: {
  /** Номер как на экране, из настроек витрины: «8 (8412) 20-20-87». */
  display: string;
  /** tel:-ссылка того же номера. */
  href: string;
  /** Видимое содержимое; по умолчанию сам номер. Иконка берёт цвет текста. */
  children?: ReactNode;
  className?: string;
  "data-event"?: string;
}) {
  const copyMode = useSyncExternalStore(subscribePointer, prefersCopy, () => false);
  const number = internationalPhone(display);

  const onClick = async (event: MouseEvent<HTMLAnchorElement>) => {
    const pointerType = (event.nativeEvent as PointerEvent).pointerType;
    if (!copyMode || pointerType === "touch" || pointerType === "pen") return;
    event.preventDefault();
    if (await copyText(number)) showToast("Номер скопирован");
    else showManualCopy(MESSAGES.phone.manual, number);
  };

  return (
    <a
      href={href}
      onClick={onClick}
      title={copyMode ? "Скопировать номер" : "Позвонить"}
      data-event={dataEvent}
      className={cn(
        "transition-colors hover:text-accent focus-visible:text-accent",
        copyMode && "cursor-copy",
        className,
      )}
    >
      {children ?? display}
      <span className="sr-only">
        {copyMode ? `, скопировать номер ${number}` : `, позвонить по номеру ${number}`}
      </span>
    </a>
  );
}
