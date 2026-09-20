"use client";

import Link from "next/link";
import { useId, useRef, useState } from "react";
import { Minus, Plus, X } from "lucide-react";
import { formatPrice } from "@/lib/format";
import type { CartLine } from "@/lib/types";
import { ProductImage } from "@/components/product/ProductImage";

export function CartItemRow({
  line,
  selected,
  onSelect,
  onUpdate,
  onRemove,
  disabled,
}: {
  line: CartLine;
  selected: boolean;
  onSelect: (itemId: number, selected: boolean) => void;
  // Возвращает false, если сервер количество не принял: строка тогда честно
  // показывает прежнее число и пометку «не сохранено». void/true — успех.
  onUpdate: (itemId: number, qty: number) => void | boolean | Promise<void | boolean>;
  onRemove: (itemId: number) => void;
  disabled?: boolean;
}) {
  // UX-06: количество редактируется прямо в поле между «−» и «+».
  //
  // draft — то, что человек набирает; null значит «не редактирует», и поле
  // показывает число с сервера. На сервер уходит только подтверждённое значение
  // (Enter или уход из поля), а не каждый символ: иначе «159» стало бы тремя
  // запросами 1 → 15 → 159 с пересчётом скидок на каждом.
  const [draft, setDraft] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  // Число, запрос на которое сейчас в полёте. Живёт ровно до ответа: Enter и
  // следующий за ним blur приносят одно и то же значение, второй запрос не нужен.
  const inFlightRef = useRef<number | null>(null);
  const errorId = useId();

  const submit = async (qty: number) => {
    if (inFlightRef.current === qty) return;
    inFlightRef.current = qty;
    setSaving(true);
    let ok = true;
    try {
      ok = (await onUpdate(line.id, qty)) !== false;
    } catch {
      ok = false;
    } finally {
      inFlightRef.current = null;
      setSaving(false);
    }
    // Черновик сбрасываем в любом исходе: дальше поле показывает ответ сервера —
    // новое число при успехе, прежнее при отказе. Введённое не выдаём за сохранённое.
    setDraft(null);
    setFieldError(ok ? null : "Не сохранено — количество прежнее. Попробуйте ещё раз");
  };

  // Единое правило для пустого и любого невалидного ввода (ноль, минус, дробь,
  // буквы, число вне безопасного целого): ничего не отправляем, возвращаем прежнее
  // число и объясняем почему. Ноль товар НЕ удаляет — для этого есть крестик.
  const commit = () => {
    if (draft === null) return;
    const text = draft.trim();
    const qty = /^\d+$/.test(text) ? Number(text) : NaN;
    if (!Number.isSafeInteger(qty) || qty < 1) {
      setDraft(null);
      setFieldError("Введите целое число от 1");
      return;
    }
    setFieldError(null);
    if (qty === line.quantity) {
      setDraft(null);
      return;
    }
    void submit(qty);
  };

  // «−»/«+» считают от числа с сервера. Несохранённый черновик к моменту клика уже
  // ушёл своим запросом (blur случается раньше click). Пока тот в полёте, шаг
  // игнорируется: иначе «ввёл 15, нажал +» отправило бы 15, а следом 3 (старое
  // число + 1) — и второе, более позднее, откатило бы только что введённое.
  const step = (delta: number) => {
    if (inFlightRef.current !== null) return;
    setDraft(null);
    setFieldError(null);
    void submit(line.quantity + delta);
  };

  const shown = draft ?? String(line.quantity);

  const price = line.price_final ? Number(line.price_final) : null;
  const total = line.line_total ? Number(line.line_total) : null;
  const basePrice = line.price_base ? Number(line.price_base) : null;
  const hasDiscount = basePrice != null && price != null && basePrice > price;

  return (
    <article className="grid grid-cols-[20px_72px_minmax(0,1fr)_44px] items-center gap-x-3 gap-y-2 border-b border-line bg-surface px-3 py-4 last:border-b-0 sm:px-4 lg:grid-cols-[20px_112px_minmax(0,1fr)_120px_minmax(148px,auto)_130px_44px] lg:gap-x-4">
      <input
        type="checkbox"
        checked={selected}
        disabled={disabled}
        onChange={(event) => onSelect(line.id, event.target.checked)}
        aria-label={`Выбрать ${line.name}`}
        className="h-5 w-5 rounded border-line accent-accent"
      />

      {/* Фото товара из каталога. Раньше здесь стояла зашитая картинка из макета —
          одинаковая для любого товара, даже с тремя настоящими фотографиями. */}
      <Link
        href={`/product/${line.slug}`}
        className="block"
        aria-label={`Открыть товар «${line.name}»`}
      >
        <ProductImage
          src={line.image ?? undefined}
          alt=""
          sizes="96px"
          className="h-[72px] w-[72px] lg:h-24 lg:w-24"
        />
      </Link>

      <div className="min-w-0 self-center">
        <Link
          href={`/product/${line.slug}`}
          className="line-clamp-2 text-sm font-semibold text-ink transition hover:text-accent lg:text-base"
        >
          {line.name}
        </Link>
        <p className="mt-1 text-xs text-ink-3">Код товара: {line.product_id}</p>
        <p className="mt-1 text-xs font-medium text-accent">В корзине</p>
        <div className="mt-2 flex items-baseline gap-2 lg:hidden">
          {total != null ? (
            <span className="text-base font-bold text-ink">{formatPrice(total)}</span>
          ) : (
            <span className="text-xs text-ink-3">Цена по запросу</span>
          )}
          {hasDiscount && (
            <span className="text-xs text-ink-3 line-through">
              {formatPrice(basePrice! * line.quantity)}
            </span>
          )}
        </div>
      </div>

      <div className="hidden text-right lg:block">
        {price != null ? (
          <>
            <p className="text-base font-semibold text-ink">{formatPrice(price)}</p>
            {hasDiscount && (
              <p className="mt-1 text-xs text-ink-3 line-through">
                {formatPrice(basePrice!)}
              </p>
            )}
          </>
        ) : (
          <span className="text-xs text-ink-3">По запросу</span>
        )}
      </div>

      <div className="col-span-2 col-start-3 flex flex-col items-start gap-1 lg:col-span-1 lg:col-start-auto lg:items-center">
        <div className="flex h-11 items-center rounded-md border border-line bg-surface">
          <button
            type="button"
            disabled={disabled || saving || line.quantity <= 1}
            onClick={() => step(-1)}
            className="grid h-11 w-11 place-items-center text-ink-2 transition hover:text-accent disabled:opacity-35"
            aria-label="Уменьшить количество"
          >
            <Minus className="h-4 w-4" aria-hidden />
          </button>
          {/* type="text" + inputMode, а не type="number": тот молча принимает «e»,
              минус и дробь, крутится колесом мыши и на части мобильных не даёт
              выделить всё число. Цифровую клавиатуру даёт inputMode.
              На время запроса поле readOnly, а не disabled: disabled сбрасывает фокус
              на <body>, и клавиатурный пользователь терял бы место в корзине.
              text-base (16 px) — чтобы iOS не приближал страницу при фокусе. */}
          <input
            type="text"
            inputMode="numeric"
            pattern="[0-9]*"
            autoComplete="off"
            enterKeyHint="done"
            maxLength={16}
            value={shown}
            readOnly={disabled || saving}
            aria-busy={saving || undefined}
            aria-label={`Количество: ${line.name}`}
            aria-invalid={fieldError ? true : undefined}
            aria-describedby={fieldError ? errorId : undefined}
            onFocus={(event) => event.currentTarget.select()}
            onChange={(event) => {
              setDraft(event.target.value);
              setFieldError(null);
            }}
            onBlur={commit}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                commit();
              } else if (event.key === "Escape") {
                setDraft(null);
                setFieldError(null);
              }
            }}
            // Ширина по числу знаков: «159» и «12000» помещаются целиком.
            style={{ width: `${Math.max(3, shown.length) + 1.5}ch` }}
            className="h-11 min-w-0 border-x border-line bg-transparent px-1 text-center text-base font-semibold tabular-nums text-ink outline-none focus-visible:bg-raised read-only:opacity-70"
          />
          <button
            type="button"
            disabled={disabled || saving}
            onClick={() => step(1)}
            className="grid h-11 w-11 place-items-center text-ink-2 transition hover:text-accent disabled:opacity-35"
            aria-label="Увеличить количество"
          >
            <Plus className="h-4 w-4" aria-hidden />
          </button>
        </div>
        {fieldError && (
          <p id={errorId} role="alert" className="max-w-[16rem] text-xs text-danger lg:text-center">
            {fieldError}
          </p>
        )}
      </div>

      <div className="hidden text-right lg:block">
        {total != null ? (
          <span className="text-lg font-bold text-ink">{formatPrice(total)}</span>
        ) : (
          <span className="text-sm text-ink-3">&mdash;</span>
        )}
      </div>

      <button
        type="button"
        disabled={disabled}
        onClick={() => onRemove(line.id)}
        className="col-start-4 row-start-1 grid h-11 w-11 shrink-0 place-items-center self-start rounded-md text-ink-3 transition hover:bg-raised hover:text-danger disabled:opacity-40 lg:col-start-auto lg:row-start-auto lg:self-center"
        aria-label={`Удалить ${line.name} из корзины`}
      >
        <X className="h-4 w-4" aria-hidden />
      </button>
    </article>
  );
}
