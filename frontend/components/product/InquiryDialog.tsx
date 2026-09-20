"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";

type Phase = "idle" | "submitting" | "success" | "error";

// Модалка заявки по товару: «Запросить цену». («Уточнить поступление» — старый
// restock_notify-флоу — заменена самообслуживаемой MAX-подпиской, #517/#519;
// бэкенд ещё принимает restock_notify для истории старых заявок, но фронт
// больше не создаёт таких — kind сужен до единственного реального сценария.)
// Отправляет в BFF /api/inquiry (далее Django /api/leads/inquiries/). Валидация
// телефона — на бэке; здесь только обязательность поля и UX-состояния.
export function InquiryDialog({
  open,
  onClose,
  productId,
  kind,
  title,
}: {
  open: boolean;
  onClose: () => void;
  productId: number;
  kind: "price_request";
  title: string;
}) {
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [message, setMessage] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const dialogRef = useRef<HTMLDivElement>(null);

  // Esc закрывает (кроме отправки); Tab держим внутри модалки (фокус-трап);
  // блокируем скролл фона, пока открыто.
  useEffect(() => {
    if (!open) return;
    const node = dialogRef.current;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && phase !== "submitting") {
        onClose();
        return;
      }
      if (e.key === "Tab" && node) {
        const focusable = node.querySelectorAll<HTMLElement>(
          'a[href],button:not([disabled]),input:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])',
        );
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [open, phase, onClose]);

  // Фокус на первое поле при открытии; возврат фокуса на инициатор при закрытии.
  useEffect(() => {
    if (!open) return;
    const prevActive = document.activeElement as HTMLElement | null;
    dialogRef.current?.querySelector("input")?.focus();
    return () => prevActive?.focus();
  }, [open]);

  if (!open) return null;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!phone.trim() || phase === "submitting") return;
    setPhase("submitting");
    try {
      const res = await fetch("/api/inquiry", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind, product: productId, phone, name, message }),
      });
      setPhase(res.ok ? "success" : "error");
    } catch {
      setPhase("error");
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={() => phase !== "submitting" && onClose()}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="inquiry-dialog-title"
        // UX-04: окно крупнее; при длинном содержимом прокручивается внутри и не уходит
        // за экран (в т.ч. при масштабе 200 %), шапка с крестиком остаётся на месте.
        className="flex max-h-[calc(100dvh-2rem)] w-full max-w-md flex-col overflow-y-auto rounded-lg border border-line bg-surface p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 z-10 -mx-6 -mt-6 mb-3 flex items-center justify-between bg-surface px-6 pb-2 pt-6">
          <h2
            id="inquiry-dialog-title"
            className="font-display text-xl font-semibold text-ink"
          >
            {title}
          </h2>
          <button
            type="button"
            onClick={() => phase !== "submitting" && onClose()}
            aria-label="Закрыть"
            disabled={phase === "submitting"}
            className="-mr-2 grid h-11 w-11 place-items-center rounded-md text-ink-3 hover:bg-raised hover:text-ink"
          >
            <X className="h-5 w-5" aria-hidden />
          </button>
        </div>

        {phase === "success" ? (
          <p className="text-base text-ink-2">
            Заявка отправлена — мы свяжемся с вами по телефону.
          </p>
        ) : (
          <form onSubmit={submit} className="flex flex-col gap-3">
            <input
              type="tel"
              required
              placeholder="Телефон*"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              className="h-11 rounded-md border border-line bg-surface px-3 text-base text-ink outline-none focus:border-accent"
            />
            <input
              type="text"
              placeholder="Имя"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="h-11 rounded-md border border-line bg-surface px-3 text-base text-ink outline-none focus:border-accent"
            />
            <textarea
              placeholder="Комментарий"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={3}
              className="rounded-md border border-line bg-surface px-3 py-2 text-base text-ink outline-none focus:border-accent"
            />
            {phase === "error" && (
              <p className="text-xs text-danger">
                Не удалось отправить заявку. Попробуйте ещё раз.
              </p>
            )}
            <Button type="submit" variant="accent" disabled={phase === "submitting"}>
              {phase === "submitting" && (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              )}
              Отправить
            </Button>
          </form>
        )}
      </div>
    </div>
  );
}
