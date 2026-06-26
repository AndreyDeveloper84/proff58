"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { X } from "lucide-react";
import { isValidPhone, normalizePhone } from "@/lib/validation";

type InquiryModalProps = { open: boolean; onClose: () => void };
type Status = "idle" | "submitting" | "success" | "error";

export function InquiryModal({ open, onClose }: InquiryModalProps) {
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [message, setMessage] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState("");
  const firstFieldRef = useRef<HTMLInputElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  // Esc закрывает; фокус — в первое поле при открытии; Tab-фокус-трап внутри диалога.
  useEffect(() => {
    if (!open) return;
    firstFieldRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key === "Tab") {
        const container = dialogRef.current;
        if (!container) return;
        const focusable = Array.from(
          container.querySelectorAll<HTMLElement>(
            'button, [href], input, textarea, select, [tabindex]:not([tabindex="-1"])'
          )
        ).filter((el) => !el.hasAttribute("disabled"));
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey) {
          if (document.activeElement === first) {
            e.preventDefault();
            last.focus();
          }
        } else {
          if (document.activeElement === last) {
            e.preventDefault();
            first.focus();
          }
        }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  // Сброс ошибки/статуса при открытии (чтобы старая ошибка не показывалась при переоткрытии).
  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => {
      setStatus("idle");
      setError("");
    }, 0);
    return () => clearTimeout(t);
  }, [open]);

  // Авто-закрытие после успеха.
  useEffect(() => {
    if (status !== "success") return;
    const t = setTimeout(() => {
      onClose();
      setStatus("idle");
      setName("");
      setPhone("");
      setMessage("");
    }, 1800);
    return () => clearTimeout(t);
  }, [status, onClose]);

  if (!open) return null;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (status === "submitting") return;
    if (!name.trim()) {
      setError("Укажите имя.");
      return;
    }
    if (!isValidPhone(phone)) {
      setError("Укажите корректный номер телефона.");
      return;
    }
    setError("");
    setStatus("submitting");
    try {
      const res = await fetch("/api/inquiry", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind: "consultation",
          phone: normalizePhone(phone),
          name: name.trim(),
          message: message.trim(),
        }),
      });
      if (!res.ok) throw new Error(String(res.status));
      setStatus("success");
    } catch {
      setStatus("error");
      setError("Не удалось отправить заявку. Попробуйте ещё раз.");
    }
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4" onClick={onClose}>
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="inquiry-title"
        className="w-full max-w-md rounded-lg border border-line bg-surface p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between">
          <h2 id="inquiry-title" className="font-display text-xl font-semibold text-ink">
            Получить консультацию
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="grid h-8 w-8 place-items-center rounded-md text-ink-3 hover:bg-raised hover:text-ink"
            aria-label="Закрыть"
          >
            <X className="h-5 w-5" aria-hidden />
          </button>
        </div>

        {status === "success" ? (
          <p className="py-6 text-center text-ink-2">
            Спасибо! Мы свяжемся с вами в ближайшее время.
          </p>
        ) : (
          <form onSubmit={submit} className="space-y-3" noValidate>
            <input
              ref={firstFieldRef}
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ваше имя"
              aria-label="Ваше имя"
              className="w-full rounded-md border border-line bg-canvas px-3 py-2.5 text-sm text-ink outline-none focus:border-accent"
            />
            <input
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="Телефон"
              aria-label="Телефон"
              className="w-full rounded-md border border-line bg-canvas px-3 py-2.5 text-sm text-ink outline-none focus:border-accent"
            />
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Что подобрать? (необязательно)"
              aria-label="Что подобрать?"
              rows={3}
              className="w-full rounded-md border border-line bg-canvas px-3 py-2.5 text-sm text-ink outline-none focus:border-accent"
            />
            {error && <p className="text-sm text-danger">{error}</p>}
            <button
              type="submit"
              disabled={status === "submitting"}
              className="w-full rounded-md bg-accent px-5 py-3 text-sm font-semibold text-accent-ink transition hover:brightness-110 disabled:opacity-60"
            >
              {status === "submitting" ? "Отправляем…" : "Отправить заявку"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
