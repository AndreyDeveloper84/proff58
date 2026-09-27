"use client";

import { useId, useMemo, useRef, useState } from "react";

import {
  cdekManualText,
  cdekPeriodText,
  searchCdekCities,
  type CdekCity,
  type CdekFailure,
} from "@/lib/delivery";
import { formatPrice } from "@/lib/format";
import type { CdekDeliveryState } from "./useCdekDelivery";

const inputClass =
  "h-11 w-full rounded-md border border-line bg-field px-3 text-base text-ink placeholder:text-ink-3 focus:border-accent focus:outline-none";
const secondaryButton =
  "inline-flex h-11 items-center justify-center rounded-md border border-line px-4 text-sm font-medium text-ink hover:bg-raised disabled:opacity-60";

// В Москве пунктов выдачи тысячи: список без фильтра был бы бесконечным.
export const POINTS_SHOWN = 30;
const CITY_DEBOUNCE_MS = 300;

function Problem({ children }: { children: React.ReactNode }) {
  return (
    <p
      role="alert"
      className="rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger"
    >
      {children}
    </p>
  );
}

/** Поле города с подсказками СДЭК (combobox): от двух букв, с паузой на ввод. */
function CityField({
  city,
  onSelect,
  onUnavailable,
}: {
  city: CdekCity | null;
  onSelect: (city: CdekCity | null) => void;
  onUnavailable: () => void;
}) {
  const listId = useId();
  const [text, setText] = useState(city?.full_name || city?.name || "");
  const [options, setOptions] = useState<CdekCity[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [searching, setSearching] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const request = useRef<AbortController | null>(null);

  const search = (query: string) => {
    if (timer.current) clearTimeout(timer.current);
    request.current?.abort();
    if (query.trim().length < 2) {
      setOptions([]);
      setOpen(false);
      setSearching(false);
      return;
    }
    setSearching(true);
    timer.current = setTimeout(async () => {
      const controller = new AbortController();
      request.current = controller;
      const res = await searchCdekCities(query.trim(), controller.signal);
      if (controller.signal.aborted) return;
      setSearching(false);
      if (res.ok) {
        setProblem(null);
        setOptions(res.data);
        setActive(res.data.length ? 0 : -1);
        setOpen(true);
      } else if (res.kind === "unavailable") {
        onUnavailable();
      } else {
        setProblem(res.message);
      }
    }, CITY_DEBOUNCE_MS);
  };

  const choose = (option: CdekCity) => {
    setText(option.full_name || option.name);
    setOpen(false);
    setOptions([]);
    onSelect(option);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown" && options.length) {
      e.preventDefault();
      setOpen(true);
      setActive((i) => (i + 1) % options.length);
    } else if (e.key === "ArrowUp" && options.length) {
      e.preventDefault();
      setActive((i) => (i <= 0 ? options.length - 1 : i - 1));
    } else if (e.key === "Enter") {
      // Enter в поле города не должен отправлять форму заказа.
      e.preventDefault();
      if (open && options[active]) choose(options[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  const showEmpty = open && !searching && options.length === 0;

  return (
    <div className="relative">
      <label htmlFor={`${listId}-input`} className="mb-1 block text-sm text-ink-2">
        Город *
      </label>
      <input
        id={`${listId}-input`}
        type="text"
        role="combobox"
        aria-expanded={open && options.length > 0}
        aria-controls={`${listId}-list`}
        aria-autocomplete="list"
        aria-activedescendant={open && active >= 0 ? `${listId}-opt-${active}` : undefined}
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          if (city) onSelect(null);
          search(e.target.value);
        }}
        onKeyDown={onKeyDown}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onFocus={() => options.length && setOpen(true)}
        className={inputClass}
        placeholder="Начните вводить название"
        autoComplete="off"
      />
      {searching && (
        <p className="mt-1 text-xs text-ink-3" role="status">
          Ищем город…
        </p>
      )}
      {open && options.length > 0 && (
        <ul
          id={`${listId}-list`}
          role="listbox"
          aria-label="Города СДЭК"
          className="absolute inset-x-0 z-20 mt-1 max-h-64 overflow-auto rounded-md border border-line bg-surface py-1 shadow-lg"
        >
          {options.map((option, index) => (
            <li
              key={option.code}
              id={`${listId}-opt-${index}`}
              role="option"
              aria-selected={index === active}
              // mousedown, а не click: иначе blur поля закроет список раньше выбора.
              onMouseDown={(e) => {
                e.preventDefault();
                choose(option);
              }}
              className={`cursor-pointer px-3 py-2 text-sm text-ink ${index === active ? "bg-raised" : ""}`}
            >
              {option.full_name || option.name}
            </li>
          ))}
        </ul>
      )}
      {showEmpty && <p className="mt-1 text-xs text-ink-3">Такого города у СДЭК не нашлось.</p>}
      {problem && (
        <div className="mt-2">
          <Problem>{problem}</Problem>
        </div>
      )}
    </div>
  );
}

function QuoteStatus({
  cdek,
  currency,
  freeByPromo,
}: {
  cdek: CdekDeliveryState;
  currency: string;
  freeByPromo: boolean;
}) {
  const { quote, quoting, failure } = cdek;
  if (quoting) {
    return (
      <p className="text-xs text-ink-3" role="status">
        Считаем стоимость доставки…
      </p>
    );
  }
  if (failure && failure.kind === "busy") {
    return (
      <div className="space-y-2">
        <Problem>{failure.message}</Problem>
        <button type="button" onClick={() => void cdek.requestQuote()} className={secondaryButton}>
          Повторить расчёт
        </button>
      </div>
    );
  }
  if (!quote) return null;
  if (quote.status === "manual_required" || quote.cost === null) {
    return (
      <p className="rounded-md bg-raised px-3 py-2 text-xs leading-5 text-ink-2" role="status">
        {cdekManualText(quote.reason)} Оплата станет доступна после расчёта.
      </p>
    );
  }
  const period = cdekPeriodText(quote.period_min, quote.period_max);
  return (
    <p className="rounded-md bg-raised px-3 py-2 text-sm text-ink" role="status">
      Стоимость доставки:{" "}
      <span className="font-semibold">
        {freeByPromo ? "бесплатно (промокод)" : formatPrice(Number(quote.cost), currency)}
      </span>
      {period && <span className="text-ink-2">, срок {period}</span>}
    </p>
  );
}

function fieldProblem(failure: CdekFailure | null, field: string): string | null {
  return failure?.kind === "invalid" && failure.field === field ? failure.message : null;
}

/** Выбор доставки СДЭК: город → пункт выдачи или адрес курьера → расчёт. */
export function CdekDelivery({
  cdek,
  currency,
  freeByPromo,
}: {
  cdek: CdekDeliveryState;
  currency: string;
  freeByPromo: boolean;
}) {
  const filterId = useId();
  const [filter, setFilter] = useState("");

  const matching = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    const all = cdek.points ?? [];
    if (!needle) return all;
    return all.filter((p) => `${p.name} ${p.address}`.toLowerCase().includes(needle));
  }, [cdek.points, filter]);
  const shown = useMemo(() => {
    const head = matching.slice(0, POINTS_SHOWN);
    // Выбранный пункт не пропадает из списка, даже если фильтр его отсёк.
    if (cdek.selectedPoint && !head.some((p) => p.code === cdek.selectedPoint?.code)) {
      return [cdek.selectedPoint, ...head];
    }
    return head;
  }, [matching, cdek.selectedPoint]);

  if (cdek.fallback) {
    return (
      <div className="space-y-3">
        <p className="rounded-md border border-line bg-raised px-3 py-2 text-xs leading-5 text-ink-2">
          Расчёт СДЭК сейчас недоступен. Укажите город и адрес или пункт выдачи — стоимость
          доставки рассчитает менеджер после оформления, оплата станет доступна после расчёта.
        </p>
        <div>
          <label htmlFor="cdekManualCity" className="mb-1 block text-sm text-ink-2">
            Город *
          </label>
          <input
            id="cdekManualCity"
            type="text"
            value={cdek.manualCity}
            onChange={(e) => cdek.setManualCity(e.target.value)}
            className={inputClass}
            autoComplete="address-level2"
            maxLength={100}
          />
        </div>
        <div>
          <label htmlFor="cdekManualAddress" className="mb-1 block text-sm text-ink-2">
            Адрес или пункт выдачи *
          </label>
          <input
            id="cdekManualAddress"
            type="text"
            value={cdek.manualAddress}
            onChange={(e) => cdek.setManualAddress(e.target.value)}
            className={inputClass}
            autoComplete="street-address"
            maxLength={200}
          />
        </div>
        <button type="button" onClick={cdek.leaveFallback} className={secondaryButton}>
          Попробовать рассчитать снова
        </button>
      </div>
    );
  }

  const pvzProblem = fieldProblem(cdek.failure, "pvz_code");
  const addressProblem = fieldProblem(cdek.failure, "address");
  const cityProblem = fieldProblem(cdek.failure, "city_code");
  const otherProblem =
    cdek.failure?.kind === "invalid" && !pvzProblem && !addressProblem && !cityProblem
      ? cdek.failure.message
      : null;

  return (
    <div className="space-y-3">
      <CityField
        city={cdek.city}
        onSelect={cdek.setCity}
        onUnavailable={() => cdek.enterFallback()}
      />
      {cityProblem && <Problem>{cityProblem}</Problem>}

      <div className="flex flex-wrap gap-3" role="radiogroup" aria-label="Как получить в СДЭК">
        {(
          [
            ["cdek_pvz", "Пункт выдачи"],
            ["cdek_courier", "Курьер до двери"],
          ] as const
        ).map(([value, label]) => (
          <label
            key={value}
            className="flex min-w-[9rem] flex-1 cursor-pointer items-center gap-2 rounded-md border border-line bg-raised p-3 transition has-[:checked]:border-accent"
          >
            <input
              type="radio"
              name="cdekMode"
              value={value}
              checked={cdek.mode === value}
              onChange={() => cdek.setMode(value)}
              className="accent-accent"
            />
            <span className="text-sm text-ink">{label}</span>
          </label>
        ))}
      </div>

      {cdek.city && cdek.mode === "cdek_pvz" && (
        <div className="space-y-2">
          {cdek.pointsLoading && (
            <p className="text-xs text-ink-3" role="status">
              Загружаем пункты выдачи…
            </p>
          )}
          {cdek.pointsFailure && (
            <div className="space-y-2">
              <Problem>{cdek.pointsFailure.message}</Problem>
              <button type="button" onClick={cdek.retryPoints} className={secondaryButton}>
                Загрузить пункты снова
              </button>
            </div>
          )}
          {cdek.points && !cdek.pointsFailure && cdek.points.length === 0 && (
            <p className="text-xs text-ink-2">
              В этом городе нет пунктов выдачи СДЭК — выберите доставку курьером.
            </p>
          )}
          {cdek.points && cdek.points.length > 0 && (
            <>
              <div>
                <label htmlFor={filterId} className="mb-1 block text-sm text-ink-2">
                  Пункт выдачи *
                </label>
                <input
                  id={filterId}
                  type="search"
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && e.preventDefault()}
                  className={inputClass}
                  placeholder="Улица или название пункта"
                />
              </div>
              <ul className="max-h-80 space-y-2 overflow-auto" aria-label="Пункты выдачи СДЭК">
                {shown.map((point) => (
                  <li key={point.code}>
                    <label className="flex cursor-pointer items-start gap-3 rounded-md border border-line bg-raised p-3 transition has-[:checked]:border-accent">
                      <input
                        type="radio"
                        name="cdekPoint"
                        value={point.code}
                        checked={cdek.pvzCode === point.code}
                        onChange={() => cdek.selectPoint(point.code)}
                        className="mt-0.5 accent-accent"
                      />
                      <span>
                        <span className="block text-sm text-ink">{point.address}</span>
                        {point.work_time && (
                          <span className="mt-0.5 block text-xs text-ink-3">{point.work_time}</span>
                        )}
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
              {matching.length > POINTS_SHOWN && (
                <p className="text-xs text-ink-3">
                  Показаны {POINTS_SHOWN} из {matching.length} — уточните улицу в поиске.
                </p>
              )}
              {matching.length === 0 && (
                <p className="text-xs text-ink-3">По этому запросу пунктов нет.</p>
              )}
            </>
          )}
          {pvzProblem && <Problem>{pvzProblem}</Problem>}
        </div>
      )}

      {cdek.city && cdek.mode === "cdek_courier" && (
        <div className="space-y-2">
          <label htmlFor="cdekAddress" className="mb-1 block text-sm text-ink-2">
            Адрес доставки *
          </label>
          <input
            id="cdekAddress"
            type="text"
            value={cdek.address}
            onChange={(e) => cdek.setAddress(e.target.value)}
            onKeyDown={(e) => {
              // Enter в адресе — «рассчитать», а не отправка формы заказа.
              if (e.key === "Enter") {
                e.preventDefault();
                if (cdek.address.trim()) void cdek.requestQuote();
              }
            }}
            className={inputClass}
            placeholder="Улица, дом, квартира"
            autoComplete="street-address"
            maxLength={300}
          />
          {addressProblem && <Problem>{addressProblem}</Problem>}
          <button
            type="button"
            onClick={() => void cdek.requestQuote()}
            disabled={!cdek.address.trim() || cdek.quoting}
            className={secondaryButton}
          >
            Рассчитать доставку
          </button>
        </div>
      )}

      {otherProblem && <Problem>{otherProblem}</Problem>}
      <QuoteStatus cdek={cdek} currency={currency} freeByPromo={freeByPromo} />
    </div>
  );
}
