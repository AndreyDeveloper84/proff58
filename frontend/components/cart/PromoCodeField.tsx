"use client";

import { useState } from "react";
import { Tag, X } from "lucide-react";
import { useCart } from "@/components/cart/CartProvider";
import { ApiError } from "@/lib/api";

// Поле промокода (#571). Скидку считает ТОЛЬКО сервер: отсюда уходит лишь код,
// breakdown приходит в снимке корзины. Рендерится только при включённом флаге
// promotions (cart.promotions_enabled). Ошибки двух видов: 400 на POST
// (невалидный код — не сохраняется) и promo_code_error в снимке (код был
// применён, но, например, истёк или перестал давать выгоду).
export function PromoCodeField() {
  const { cart, applyPromo, removePromo } = useCart();
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!cart?.promotions_enabled) return null;

  const applied = cart.promo_code;
  const serverError = cart.promo_code_error;

  const submit = async () => {
    if (!code.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      await applyPromo(code.trim());
      setCode("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось применить промокод");
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await removePromo();
    } catch {
      setError("Не удалось снять промокод");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-2">
      {applied ? (
        <div className="flex items-center justify-between gap-2 rounded-md border border-line bg-raised px-3 py-2">
          <span className="flex items-center gap-2 text-sm text-ink">
            <Tag className="h-4 w-4 text-accent" aria-hidden />
            Промокод <b>{applied}</b>
          </span>
          <button
            type="button"
            onClick={remove}
            disabled={busy}
            aria-label="Убрать промокод"
            className="rounded p-1 text-ink-3 transition hover:text-danger"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </div>
      ) : (
        <div className="flex gap-2">
          <input
            type="text"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="Промокод"
            aria-label="Промокод"
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                void submit();
              }
            }}
            className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink placeholder:text-ink-3 focus:border-accent focus:outline-none"
          />
          <button
            type="button"
            onClick={() => void submit()}
            disabled={busy || !code.trim()}
            className="shrink-0 rounded-md border border-line px-3 py-2 text-sm font-semibold text-ink transition hover:border-accent disabled:opacity-50"
          >
            Применить
          </button>
        </div>
      )}
      {error && <p className="text-xs text-danger">{error}</p>}
      {!error && serverError && <p className="text-xs text-danger">{serverError.message}</p>}
    </div>
  );
}
