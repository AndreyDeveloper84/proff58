"use client";

import { useCallback, useEffect, useState } from "react";

import {
  getCdekPoints,
  quoteCdekDelivery,
  type CdekCity,
  type CdekFailure,
  type CdekMethod,
  type CdekPoint,
  type CdekQuote,
} from "@/lib/delivery";

// Пауза перед расчётом после выбора пункта: человек перебирает пункты кликами,
// а лимит расчётов — 30 в минуту на IP (офис за NAT упрётся быстрее).
export const QUOTE_DEBOUNCE_MS = 400;

type QuoteResult = { key: string; quote?: CdekQuote; failure?: CdekFailure };
type PointsResult = { cityCode: number; points: CdekPoint[]; failure?: CdekFailure };

export type CdekOrderFields = {
  delivery_method: CdekMethod;
  delivery_zone: string;
  delivery_quote_id?: string;
  delivery_address: string;
};

/**
 * Состояние доставки СДЭК на чекауте (DRF-2491).
 *
 * Расчёт хранится вместе с ключом вводных (зона, корзина, способ, город, пункт
 * или адрес) и действует, только пока ключ совпадает с текущим: любое изменение
 * выбора или состава корзины само делает расчёт неактуальным, без эффектов сброса.
 * Поздний ответ на старые вводные не подменит расчёт для новых.
 *
 * СДЭК недоступен — запасной режим: город и адрес свободным текстом, заказ уходит
 * без расчёта, и стоимость считает менеджер (сервер ставит manual_required).
 */
export function useCdekDelivery(zone: string, cartFingerprint: string) {
  const [mode, setModeState] = useState<CdekMethod>("cdek_pvz");
  const [city, setCityState] = useState<CdekCity | null>(null);
  const [pvzCode, setPvzCode] = useState("");
  const [address, setAddressState] = useState("");
  const [result, setResult] = useState<QuoteResult | null>(null);
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const [pointsResult, setPointsResult] = useState<PointsResult | null>(null);
  const [pointsNonce, setPointsNonce] = useState(0);
  const [fallback, setFallback] = useState(false);
  const [manualCity, setManualCity] = useState("");
  const [manualAddress, setManualAddress] = useState("");

  const target = mode === "cdek_pvz" ? pvzCode : address.trim();
  const key = [zone, cartFingerprint, mode, city?.code ?? "", target].join("|");
  const quote = result?.key === key ? (result.quote ?? null) : null;
  const failure = result?.key === key ? (result.failure ?? null) : null;
  const quoting = pendingKey === key;

  const enterFallback = useCallback(
    (prefill?: { city?: string; address?: string }) => {
      setFallback(true);
      if (prefill?.city) setManualCity((prev) => prev || prefill.city || "");
      if (prefill?.address) setManualAddress((prev) => prev || prefill.address || "");
    },
    [],
  );

  const leaveFallback = useCallback(() => {
    setFallback(false);
    setResult(null);
    setPointsResult(null);
    setPointsNonce((n) => n + 1);
  }, []);

  const requestQuote = useCallback(async (): Promise<CdekQuote | null> => {
    if (!city) return null;
    const requestKey = key;
    setPendingKey(requestKey);
    const res = await quoteCdekDelivery({
      zone,
      method: mode,
      city_code: city.code,
      city_name: city.name,
      ...(mode === "cdek_pvz" ? { pvz_code: pvzCode } : { address: address.trim() }),
    });
    setPendingKey((prev) => (prev === requestKey ? null : prev));
    if (res.ok) {
      setResult({ key: requestKey, quote: res.data });
      return res.data;
    }
    const { kind, message, field } = res;
    setResult({ key: requestKey, failure: { kind, message, field } });
    if (kind === "unavailable") enterFallback({ city: city.name });
    return null;
  }, [key, zone, mode, city, pvzCode, address, enterFallback]);

  // Пункт выдачи выбран — считаем сами, без кнопки. Для курьера расчёт по кнопке:
  // адрес дописывают посимвольно, считать каждую букву незачем.
  const autoQuote = !fallback && mode === "cdek_pvz" && city !== null && pvzCode !== "";
  useEffect(() => {
    if (!autoQuote || quote || quoting || failure) return;
    const timer = setTimeout(() => void requestQuote(), QUOTE_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [autoQuote, quote, quoting, failure, requestQuote]);

  // Пункты выдачи города: грузим, когда выбран город и способ «пункт выдачи».
  const needPoints = !fallback && mode === "cdek_pvz" && city !== null;
  const pointsCityCode = city?.code ?? 0;
  const cityName = city?.name;
  const pointsReady = pointsResult !== null && pointsResult.cityCode === pointsCityCode;
  useEffect(() => {
    if (!needPoints || pointsReady) return;
    let active = true;
    getCdekPoints(pointsCityCode).then((res) => {
      if (!active) return;
      if (res.ok) {
        setPointsResult({ cityCode: pointsCityCode, points: res.data });
        return;
      }
      const { kind, message, field } = res;
      setPointsResult({ cityCode: pointsCityCode, points: [], failure: { kind, message, field } });
      if (kind === "unavailable") enterFallback({ city: cityName });
    });
    return () => {
      active = false;
    };
  }, [needPoints, pointsReady, pointsCityCode, cityName, pointsNonce, enterFallback]);

  const points = needPoints && pointsReady ? pointsResult.points : null;
  const pointsFailure = needPoints && pointsReady ? (pointsResult.failure ?? null) : null;
  const selectedPoint = points?.find((p) => p.code === pvzCode) ?? null;

  const setMode = (value: CdekMethod) => setModeState(value);
  const setCity = (value: CdekCity | null) => {
    setCityState(value);
    setPvzCode("");
  };
  const selectPoint = (code: string) => setPvzCode(code);
  const setAddress = (value: string) => setAddressState(value);
  const retryPoints = () => {
    setPointsResult(null);
    setPointsNonce((n) => n + 1);
  };

  /** Что мешает оформить заказ со СДЭК; null — можно оформлять. */
  function blocker(): string | null {
    if (fallback) {
      if (!manualCity.trim()) return "Укажите город доставки СДЭК.";
      if (!manualAddress.trim()) return "Укажите адрес или пункт выдачи СДЭК.";
      return null;
    }
    if (!city) return "Выберите город доставки СДЭК из списка.";
    if (mode === "cdek_pvz" && !pvzCode) return "Выберите пункт выдачи СДЭК.";
    if (mode === "cdek_courier" && !address.trim()) return "Укажите адрес доставки курьером СДЭК.";
    if (quoting) return "Дождитесь расчёта стоимости доставки.";
    if (quote) return null;
    if (failure) return failure.message;
    return mode === "cdek_courier"
      ? "Нажмите «Рассчитать доставку», чтобы узнать стоимость."
      : "Дождитесь расчёта стоимости доставки.";
  }

  /** Поля заказа для POST /api/orders. Без расчёта — запасной режим (считает менеджер). */
  function orderFields(): CdekOrderFields {
    if (fallback || !quote) {
      return {
        delivery_method: mode,
        delivery_zone: zone,
        delivery_address: [manualCity.trim(), manualAddress.trim()].filter(Boolean).join(", "),
      };
    }
    return {
      delivery_method: mode,
      delivery_zone: zone,
      delivery_quote_id: quote.quote_id,
      delivery_address: "",
    };
  }

  /** Что подставить в запасной режим из уже сделанного выбора. */
  function fallbackPrefill(): { city?: string; address?: string } {
    const pointText = selectedPoint ? `пункт выдачи ${selectedPoint.code}, ${selectedPoint.address}` : "";
    return {
      city: city?.name,
      address: mode === "cdek_pvz" ? pointText : address.trim(),
    };
  }

  return {
    zone,
    mode,
    setMode,
    city,
    setCity,
    points,
    pointsLoading: needPoints && !pointsReady,
    pointsFailure,
    retryPoints,
    pvzCode,
    selectPoint,
    selectedPoint,
    address,
    setAddress,
    quote,
    quoting,
    failure,
    requestQuote,
    fallback,
    enterFallback,
    leaveFallback,
    fallbackPrefill,
    manualCity,
    setManualCity,
    manualAddress,
    setManualAddress,
    blocker,
    orderFields,
  };
}

export type CdekDeliveryState = ReturnType<typeof useCdekDelivery>;
