"use client";

import { useEffect, useRef, useState } from "react";
import { Switch } from "@/components/ui/switch";
import { ApiError } from "@/lib/api";
import { getNotificationPreferences, updateNotificationPreferences } from "@/lib/notifications";
import type { NotificationPreferences, NotificationPreferencesPatch } from "@/lib/types";

// Версия текста согласия на маркетинговые рассылки (#515 AC: marketing_enabled=True
// фиксирует explicit consent). Поднимать вместе с изменением текста согласия.
const MARKETING_CONSENT_VERSION = "v1";

type SaveState = "idle" | "saving" | "saved" | "error";

// Секция «Уведомления» в профиле (#519): статусы заказов/поступление товара/
// акции — по категориям, плюс мастер-переключатель канала MAX. Привязку самого
// MAX (подключить/отключить) показывает соседняя MaxLinkCard — здесь только то,
// ЧТО присылать, а не САМ ли канал подключён.
export function NotificationPreferencesCard() {
  const [prefs, setPrefs] = useState<NotificationPreferences | null>(null);
  const [loadError, setLoadError] = useState("");
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [saveError, setSaveError] = useState("");
  const savedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let active = true;
    getNotificationPreferences()
      .then((p) => {
        if (active) setPrefs(p);
      })
      .catch((err) => {
        if (active) {
          setLoadError(
            err instanceof ApiError ? err.message : "Не удалось загрузить настройки уведомлений.",
          );
        }
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => () => {
    if (savedTimer.current) clearTimeout(savedTimer.current);
  }, []);

  async function save(patch: NotificationPreferencesPatch, optimistic: Partial<NotificationPreferences>) {
    if (!prefs) return;
    const previous = prefs;
    setPrefs({ ...prefs, ...optimistic });
    setSaveState("saving");
    setSaveError("");
    try {
      const updated = await updateNotificationPreferences(patch);
      setPrefs(updated);
      setSaveState("saved");
      if (savedTimer.current) clearTimeout(savedTimer.current);
      savedTimer.current = setTimeout(() => setSaveState("idle"), 1800);
    } catch (err) {
      setPrefs(previous);
      setSaveState("error");
      setSaveError(err instanceof ApiError ? err.message : "Не удалось сохранить настройки.");
    }
  }

  if (!prefs) {
    return (
      <div className="mt-6 border-t border-line pt-4">
        <h2 className="mb-2 font-semibold text-ink">Уведомления</h2>
        <p className="text-sm text-ink-3" role={loadError ? "alert" : "status"}>
          {loadError || "Загрузка настроек…"}
        </p>
      </div>
    );
  }

  return (
    <div className="mt-6 border-t border-line pt-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="font-semibold text-ink">Уведомления</h2>
        <p className="text-xs text-ink-3" aria-live="polite">
          {saveState === "saving" ? "Сохраняем…" : saveState === "saved" ? "Сохранено" : ""}
        </p>
      </div>

      {saveState === "error" && (
        <p role="alert" className="mb-3 text-sm text-danger">
          {saveError}
        </p>
      )}

      <div className="space-y-4">
        <ToggleRow
          id="pref-max-enabled"
          label="Уведомления в MAX"
          description="Общий переключатель: выключите, чтобы не получать ничего, не отключая сам MAX."
          checked={prefs.max_enabled}
          disabled={saveState === "saving"}
          onChange={(v) => save({ max_enabled: v }, { max_enabled: v })}
        />
        <ToggleRow
          id="pref-order-updates"
          label="Статусы заказов"
          checked={prefs.order_updates_enabled}
          disabled={saveState === "saving"}
          onChange={(v) => save({ order_updates_enabled: v }, { order_updates_enabled: v })}
        />
        <ToggleRow
          id="pref-product-availability"
          label="Товары в наличии"
          description="Уведомления по подписке «Сообщить о поступлении» на карточке товара."
          checked={prefs.product_availability_enabled}
          disabled={saveState === "saving"}
          onChange={(v) => save({ product_availability_enabled: v }, { product_availability_enabled: v })}
        />
        <ToggleRow
          id="pref-marketing"
          label="Акции и скидки"
          description="Выключено по умолчанию — рекламные сообщения только с вашего согласия."
          checked={prefs.marketing_enabled}
          disabled={saveState === "saving"}
          onChange={(v) =>
            save(
              v
                ? { marketing_enabled: true, consent_version: MARKETING_CONSENT_VERSION }
                : { marketing_enabled: false },
              { marketing_enabled: v },
            )
          }
        />
        {prefs.marketing_enabled && prefs.marketing_consent_at && (
          <p className="pl-1 text-xs text-ink-3">
            Согласие на рекламные рассылки дано{" "}
            {new Date(prefs.marketing_consent_at).toLocaleDateString("ru-RU")}.
          </p>
        )}
      </div>
    </div>
  );
}

function ToggleRow({
  id,
  label,
  description,
  checked,
  disabled,
  onChange,
}: {
  id: string;
  label: string;
  description?: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <p className="text-sm font-medium text-ink">{label}</p>
        {description && <p className="text-xs text-ink-3">{description}</p>}
      </div>
      <Switch id={id} checked={checked} disabled={disabled} onChange={onChange} label={label} />
    </div>
  );
}
