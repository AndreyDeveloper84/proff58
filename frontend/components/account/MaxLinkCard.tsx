"use client";

import { useCallback, useEffect, useState } from "react";
import { Check } from "lucide-react";
import { maxAccountStatus, maxUnlink } from "@/lib/auth";
import { MaxAuthFlow } from "./MaxAuthFlow";

// Карточка «Способы входа» в ЛК (§5.4): статус привязки MAX + подключить/отключить.
export function MaxLinkCard() {
  const [linked, setLinked] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const s = await maxAccountStatus();
    setLinked(s.linked);
  }, []);

  useEffect(() => {
    let active = true;
    maxAccountStatus().then((s) => {
      if (active) setLinked(s.linked);
    });
    return () => {
      active = false;
    };
  }, []);

  const unlink = useCallback(async () => {
    if (!window.confirm("Отключить вход через MAX?")) return;
    setBusy(true);
    try {
      await maxUnlink();
      await refresh();
    } finally {
      setBusy(false);
    }
  }, [refresh]);

  if (linked === null) return null;

  return (
    <div className="mt-6 border-t pt-4">
      <h2 className="mb-2 font-semibold">Вход через MAX</h2>
      {linked ? (
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <span className="inline-flex items-center gap-1.5 font-medium text-brand">
            <Check className="h-4 w-4" aria-hidden />
            MAX подключён
          </span>
          <button
            type="button"
            onClick={unlink}
            disabled={busy}
            className="text-danger underline disabled:opacity-50"
          >
            Отключить MAX
          </button>
        </div>
      ) : (
        <div className="max-w-sm">
          <p className="mb-2 text-sm text-ink-2">
            Подключите MAX, чтобы входить без пароля и получать уведомления о заказах.
          </p>
          <MaxAuthFlow mode="link" ctaLabel="Подключить MAX" onCompleted={refresh} />
        </div>
      )}
    </div>
  );
}
