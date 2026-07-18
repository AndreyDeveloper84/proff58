"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { MessageSquareText } from "lucide-react";
import {
  maxCancel,
  maxLinkStart,
  maxStart,
  maxStatus,
  type MaxAttempt,
  type MaxAttemptStatus,
} from "@/lib/auth";

// Поток авторизации/привязки через MAX (#492): создаём попытку, на мобильном
// открываем диплинк бота, на десктопе показываем QR; опрашиваем статус (§7.3) и по
// completed зовём onCompleted (вход/обновление). Токен бота на фронт не приходит —
// только диплинк с одноразовым секретом попытки.
//
// `start`/`pollStatus` (#520): опциональный override для сценариев за пределами
// login/link — напр. отслеживание гостевого заказа (свои start/status-эндпоинты,
// без побочного login()). Без override — обычное mode-based поведение как раньше.

type Phase = "idle" | "starting" | "waiting" | "completed" | "error";
const TERMINAL_FAIL = ["expired", "cancelled", "failed"];

function isMobile(): boolean {
  return typeof navigator !== "undefined" && /Mobi|Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
}

export function MaxAuthFlow({
  mode = "login",
  ctaLabel,
  onCompleted,
  start: customStart,
  pollStatus = maxStatus,
}: {
  mode?: "login" | "link";
  ctaLabel?: string;
  onCompleted: () => void;
  start?: () => Promise<MaxAttempt>;
  pollStatus?: (attemptId: string) => Promise<MaxAttemptStatus>;
}) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [attempt, setAttempt] = useState<MaxAttempt | null>(null);
  const [qr, setQr] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const poll = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPoll = useCallback(() => {
    if (poll.current) {
      clearInterval(poll.current);
      poll.current = null;
    }
  }, []);

  useEffect(() => () => stopPoll(), [stopPoll]);

  const start = useCallback(async () => {
    setPhase("starting");
    setMessage("");
    setQr(null);
    try {
      const a = customStart ? await customStart() : mode === "link" ? await maxLinkStart() : await maxStart();
      setAttempt(a);
      setPhase("waiting");

      if (isMobile()) {
        // Мобильный: открываем бота MAX; пользователь вернётся — статус подхватит polling.
        window.location.href = a.deeplink;
      } else {
        // Десктоп: QR с диплинком (self-contained, генерируем на клиенте).
        const QR = (await import("qrcode")).default;
        setQr(await QR.toDataURL(a.deeplink, { width: 220, margin: 1 }));
      }

      stopPoll();
      poll.current = setInterval(async () => {
        try {
          const s = await pollStatus(a.attempt_id);
          if (s.status === "completed") {
            stopPoll();
            setPhase("completed");
            onCompleted();
          } else if (TERMINAL_FAIL.includes(s.status)) {
            stopPoll();
            setPhase("error");
            setMessage(
              s.status === "expired"
                ? "Срок действия ссылки истёк."
                : s.status === "cancelled"
                  ? "Вход отменён."
                  : "Не удалось подтвердить вход.",
            );
          }
        } catch {
          // Временная ошибка сети — продолжаем опрос до следующего тика.
        }
      }, 2500);
    } catch (e) {
      setPhase("error");
      setMessage(e instanceof Error ? e.message : "Не удалось начать вход через MAX.");
    }
  }, [mode, onCompleted, stopPoll, customStart, pollStatus]);

  const cancel = useCallback(async () => {
    stopPoll();
    if (attempt) {
      try {
        await maxCancel(attempt.attempt_id);
      } catch {
        /* отмена «best-effort» */
      }
    }
    setPhase("idle");
    setAttempt(null);
    setQr(null);
    setMessage("");
  }, [attempt, stopPoll]);

  if (phase === "idle" || phase === "starting") {
    return (
      <button
        type="button"
        onClick={start}
        disabled={phase === "starting"}
        data-event="max_auth_started"
        className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-brand px-4 py-2.5 text-sm font-semibold text-white transition hover:brightness-95 disabled:opacity-50"
      >
        <MessageSquareText className="h-4 w-4" aria-hidden />
        {phase === "starting" ? "Создаём ссылку…" : (ctaLabel ?? "Войти через MAX")}
      </button>
    );
  }

  if (phase === "completed") {
    return <p className="text-center text-sm font-medium text-brand">Готово! Входим…</p>;
  }

  // waiting / error
  return (
    <div className="rounded-lg border border-line bg-surface p-4 text-center">
      {qr ? (
        <>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={qr} alt="QR-код для входа через MAX" className="mx-auto rounded-md" width={220} height={220} />
          <p className="mt-3 text-sm text-ink-2">
            Отсканируйте QR-код телефоном и подтвердите вход в MAX.
          </p>
        </>
      ) : (
        <p className="text-sm text-ink-2">Откройте MAX и подтвердите вход, затем вернитесь на сайт.</p>
      )}

      {attempt && (
        <a
          href={attempt.deeplink}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-3 inline-flex items-center gap-2 text-sm font-medium text-accent hover:underline"
        >
          <MessageSquareText className="h-4 w-4" aria-hidden />
          Открыть MAX
        </a>
      )}

      {message && <p className="mt-3 text-sm text-danger">{message}</p>}

      <div className="mt-4">
        {phase === "error" ? (
          <button type="button" onClick={start} className="text-sm font-medium text-accent hover:underline">
            Повторить
          </button>
        ) : (
          <button type="button" onClick={cancel} className="text-sm text-ink-3 hover:text-ink">
            Отменить
          </button>
        )}
      </div>
    </div>
  );
}
