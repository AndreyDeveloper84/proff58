"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";

type Phase = "idle" | "submitting" | "success" | "error";

// Модалка заявки по товару: «Запросить цену» / «Уточнить поступление».
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
  kind: "price_request" | "restock_notify";
  title: string;
}) {
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [message, setMessage] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const dialogRef = useRef<HTMLDivElement>(null);

  // Esc закрывает (кроме отправки); блокируем скролл фона, пока открыто.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && phase !== "submitting") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, phase, onClose]);

  // Фокус на первое поле при открытии.
  useEffect(() => {
    if (open) dialogRef.current?.querySelector("input")?.focus();
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
        aria-label={title}
        className="w-full max-w-sm rounded-lg border border-line bg-surface p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-display text-lg font-semibold text-ink">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Закрыть"
            className="text-ink-3 hover:text-ink"
          >
            <X className="h-5 w-5" aria-hidden />
          </button>
        </div>

        {phase === "success" ? (
          <p className="text-sm text-ink-2">
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
              className="h-9 rounded-md border border-line bg-surface px-3 text-sm text-ink outline-none focus:border-accent"
            />
            <input
              type="text"
              placeholder="Имя"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="h-9 rounded-md border border-line bg-surface px-3 text-sm text-ink outline-none focus:border-accent"
            />
            <textarea
              placeholder="Комментарий"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={3}
              className="rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-accent"
            />
            {phase === "error" && (
              <p className="text-xs text-red-600">
                Не удалось отправить. Проверьте телефон и попробуйте ещё раз.
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
