"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Image from "next/image";
import { MessageSquareText } from "lucide-react";
import { ApiError } from "@/lib/api";
import {
  maxCancel,
  maxConfirm,
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
//
// `failureMessages`: причина отказа (`failure_reason`) → текст. Виджет общий, а
// причины по месту значат разное, поэтому карту передаёт тот, кто его вставляет
// (lib/max-auth-messages.ts); причина без текста — общее «Не удалось подтвердить».
//
// Код из бота (DRF-2740). Бот больше не завершает вход сам — пересланная ссылка
// впускала чужой браузер. Он присылает шестизначный код, и завершает попытку тот
// браузер, где код введён (`maxConfirm`). Поле кода показано сразу, пока идёт
// ожидание: на телефоне страница уходит в MAX, и человек возвращается уже с кодом.
// `codeEntry={false}` — для отслеживания заказа: там бот завершает попытку сам.

type Phase = "idle" | "starting" | "waiting" | "completed" | "error";
const TERMINAL_FAIL = ["expired", "cancelled", "failed"];
const POLL_INTERVAL_MS = 2500;
const CODE_LENGTH = 6;

function isMobile(): boolean {
  return (
    typeof navigator !== "undefined" &&
    /Mobi|Android|iPhone|iPad|iPod/i.test(navigator.userAgent)
  );
}

export function MaxAuthFlow({
  mode = "login",
  ctaLabel,
  onCompleted,
  start: customStart,
  pollStatus = maxStatus,
  failureMessages,
  codeEntry = true,
}: {
  mode?: "login" | "link";
  ctaLabel?: string;
  onCompleted: () => void;
  start?: () => Promise<MaxAttempt>;
  pollStatus?: (attemptId: string) => Promise<MaxAttemptStatus>;
  failureMessages?: Record<string, string>;
  codeEntry?: boolean;
}) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [attempt, setAttempt] = useState<MaxAttempt | null>(null);
  const [qr, setQr] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  // Нейтральная подсказка ожидания (confirmation_required) — не ошибка, другой стиль.
  const [hint, setHint] = useState("");
  const [code, setCode] = useState("");
  const [codeError, setCodeError] = useState("");
  const [confirming, setConfirming] = useState(false);
  const poll = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Поколение опроса: ответ, пришедший после stopPoll/нового старта, ничего не планирует.
  const pollGen = useRef(0);
  // Ушедший и ещё не отвеченный опрос: перед вводом кода его нужно дождаться —
  // иначе ответ со старой cookie пришёл бы после login() и стёр новую сессию.
  const inFlight = useRef<Promise<unknown> | null>(null);
  // Текущий шаг опроса — чтобы дёрнуть его сразу, когда вкладка снова на экране.
  const tickRef = useRef<(() => Promise<void>) | null>(null);
  // Перезапуск опроса с новым поколением (после неверного кода): шаг опроса
  // замыкает своё поколение, поэтому старый `tick` после stopPoll() мёртв —
  // нужен новый, с текущим поколением.
  const restartPollRef = useRef<(() => void) | null>(null);

  const stopPoll = useCallback(() => {
    pollGen.current += 1;
    if (poll.current) {
      clearTimeout(poll.current);
      poll.current = null;
    }
  }, []);

  useEffect(() => () => stopPoll(), [stopPoll]);

  const start = useCallback(async () => {
    setPhase("starting");
    setMessage("");
    setHint("");
    setQr(null);
    setCode("");
    setCodeError("");
    try {
      const a = customStart
        ? await customStart()
        : mode === "link"
          ? await maxLinkStart()
          : await maxStart();
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

      // Опрос строго последовательный: следующий запрос — только после ответа на
      // предыдущий. С setInterval на медленном сервере летело несколько опросов
      // сразу: один завершал вход и получал новую cookie сессии, а отставшие
      // возвращались со старой — Django отвечал на них удалением cookie, и
      // человека выкидывало из только что открытого кабинета.
      const startPoll = () => {
        stopPoll();
        const gen = pollGen.current;
        const tick = async () => {
          let done = false;
          try {
            const request = pollStatus(a.attempt_id);
            inFlight.current = request;
            const s = await request;
            if (gen !== pollGen.current) return;
            if (s.status === "completed") {
              done = true;
              stopPoll();
              setPhase("completed");
              onCompleted();
            } else if (s.status === "confirmation_required") {
              // Бот выдал код — ждём его ввода здесь. Без этой ветки опрос крутился бы
              // молча, и человек не знал бы, что делать.
              setHint(
                codeEntry
                  ? "Бот прислал код — введите его ниже."
                  : "Подтвердите действие в приложении MAX.",
              );
            } else if (TERMINAL_FAIL.includes(s.status)) {
              done = true;
              stopPoll();
              setPhase("error");
              setMessage(
                s.status === "expired"
                  ? "Срок действия ссылки истёк."
                  : s.status === "cancelled"
                    ? "Вход отменён."
                    : // Object.hasOwn: причина приходит с сервера, «constructor» и
                      // подобное не должны находить текст в прототипе.
                      s.failure_reason &&
                        failureMessages &&
                        Object.hasOwn(failureMessages, s.failure_reason)
                      ? failureMessages[s.failure_reason]
                      : "Не удалось подтвердить вход.",
              );
            }
          } catch {
            // Временная ошибка сети — продолжаем опрос со следующего шага.
          } finally {
            inFlight.current = null;
          }
          if (!done && gen === pollGen.current) {
            poll.current = setTimeout(tick, POLL_INTERVAL_MS);
          }
        };
        tickRef.current = tick;
        poll.current = setTimeout(tick, POLL_INTERVAL_MS);
      };
      restartPollRef.current = startPoll;
      startPoll();
    } catch (e) {
      setPhase("error");
      setMessage(
        e instanceof Error ? e.message : "Не удалось начать вход через MAX.",
      );
    }
  }, [
    mode,
    onCompleted,
    stopPoll,
    customStart,
    pollStatus,
    failureMessages,
    codeEntry,
  ]);

  // Вернулись из MAX (вкладка снова видна): не ждать очередные 2,5 с, спросить сразу.
  useEffect(() => {
    if (phase !== "waiting") return;
    const onVisible = () => {
      if (
        document.visibilityState !== "visible" ||
        !tickRef.current ||
        inFlight.current
      )
        return;
      if (poll.current) {
        clearTimeout(poll.current);
        poll.current = null;
      }
      void tickRef.current();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [phase]);

  const submitCode = useCallback(
    async (value: string) => {
      if (!attempt || confirming || value.length !== CODE_LENGTH) return;
      setConfirming(true);
      setCodeError("");
      // Остановить опрос и дождаться ответа на уже ушедший запрос: после login()
      // ответ со старой cookie заставил бы Django удалить новую сессию.
      stopPoll();
      try {
        await inFlight.current;
      } catch {
        /* ответ опроса нас уже не интересует */
      }
      try {
        const s = await maxConfirm(attempt.attempt_id, value);
        if (s.status === "completed") {
          setPhase("completed");
          onCompleted();
          return;
        }
        setPhase("error");
        setMessage(
          s.status === "expired"
            ? "Срок действия кода истёк. Начните заново."
            : s.failure_reason &&
                failureMessages &&
                Object.hasOwn(failureMessages, s.failure_reason)
              ? failureMessages[s.failure_reason]
              : "Не удалось подтвердить вход.",
        );
      } catch (e) {
        if (e instanceof ApiError && e.code === "wrong_code") {
          const left = (e as ApiError & { attemptsLeft?: number }).attemptsLeft;
          setCodeError(
            typeof left === "number" && left > 0
              ? `Неверный код. Осталось попыток: ${left}.`
              : "Неверный код.",
          );
          setCode("");
          // Попытка жива — опрос продолжается (вдруг человек запросит новый код).
          restartPollRef.current?.();
        } else if (e instanceof ApiError && e.code === "code_not_issued") {
          setCodeError("Код ещё не выдан — откройте MAX и нажмите «Начать».");
          setCode("");
          restartPollRef.current?.();
        } else if (e instanceof ApiError && e.status === 409) {
          // Попытка закрыта: причину отказа (например, «номер не совпадает») бэк
          // кладёт в тело 409 — показываем её, а не общий текст.
          setPhase("error");
          setMessage(
            e.failureReason &&
              failureMessages &&
              Object.hasOwn(failureMessages, e.failureReason)
              ? failureMessages[e.failureReason]
              : e.code === "already_authenticated"
                ? e.message
                : "Код больше не действует. Начните заново.",
          );
        } else {
          setCodeError("Не удалось проверить код. Попробуйте ещё раз.");
        }
      } finally {
        setConfirming(false);
      }
    },
    [attempt, confirming, stopPoll, onCompleted, failureMessages],
  );

  const onCodeChange = useCallback(
    (raw: string) => {
      const digits = raw.replace(/\D/g, "").slice(0, CODE_LENGTH);
      setCode(digits);
      setCodeError("");
      if (digits.length === CODE_LENGTH) void submitCode(digits);
    },
    [submitCode],
  );

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
    setHint("");
    setCode("");
    setCodeError("");
  }, [attempt, stopPoll]);

  if (phase === "idle" || phase === "starting") {
    return (
      <button
        type="button"
        onClick={start}
        disabled={phase === "starting"}
        data-event="max_auth_started"
        className="inline-flex min-h-11 w-full items-center justify-center gap-2.5 rounded-md bg-accent px-4 py-2 text-sm font-semibold text-accent-ink transition hover:brightness-95 disabled:opacity-50"
      >
        {/* Логотип белым силуэтом, как текст кнопки: цветное кольцо MAX на зелёном
            почти не контрастирует, а белая плашка под ним выглядела заплаткой. */}
        <Image
          src="/brands/max-colored.png"
          alt=""
          aria-hidden
          width={24}
          height={24}
          className="h-6 w-6 shrink-0 brightness-0 invert"
        />
        {phase === "starting"
          ? "Создаём ссылку…"
          : (ctaLabel ?? "Войти через MAX")}
      </button>
    );
  }

  if (phase === "completed") {
    return (
      <p className="text-center text-sm font-medium text-accent">
        Готово! Входим…
      </p>
    );
  }

  // waiting / error
  return (
    <div className="rounded-lg border border-line bg-surface p-4 text-center">
      {qr ? (
        <>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={qr}
            alt="QR-код для входа через MAX"
            className="mx-auto rounded-md"
            width={220}
            height={220}
          />
          {/* Сканер в MAX «Устройства» привязывает компьютер к аккаунту MAX и наш код
              отвергает («не тот QR-код»). Нужна обычная камера телефона. */}
          <p className="mt-3 text-sm text-ink-2">
            Наведите на QR-код обычную камеру телефона — откроется чат с ботом в
            MAX.
            {codeEntry
              ? " Нажмите «Начать» — бот пришлёт код, введите его здесь."
              : " Нажмите «Начать», и подключение подтвердится."}
          </p>
          <p className="mt-1 text-xs text-ink-3">
            Сканер в разделе MAX «Устройства» этот код не примет — он для входа
            в сам MAX.
          </p>
        </>
      ) : (
        <p className="text-sm text-ink-2">
          {codeEntry
            ? "Откройте MAX и нажмите «Начать» — бот пришлёт код. Вернитесь сюда и введите его."
            : "Откройте MAX и подтвердите действие, затем вернитесь на сайт."}
        </p>
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

      {hint && !message && (
        <p className="mt-3 text-sm font-medium text-accent">{hint}</p>
      )}
      {message && <p className="mt-3 text-sm text-danger">{message}</p>}

      {codeEntry && phase === "waiting" && (
        <form
          className="mx-auto mt-4 flex max-w-xs items-start gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            void submitCode(code);
          }}
        >
          <div className="min-w-0 flex-1 text-left">
            <input
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              pattern="[0-9]*"
              maxLength={CODE_LENGTH}
              value={code}
              onChange={(event) => onCodeChange(event.target.value)}
              placeholder="Код из MAX"
              aria-label="Код из MAX"
              aria-invalid={codeError ? true : undefined}
              disabled={confirming}
              className="h-11 w-full rounded-md border border-line bg-surface px-3 text-center text-lg tracking-[0.3em] text-ink outline-none focus:border-accent disabled:opacity-50"
            />
            {codeError && (
              <p role="alert" className="mt-1 text-xs text-danger">
                {codeError}
              </p>
            )}
          </div>
          <button
            type="submit"
            disabled={confirming || code.length !== CODE_LENGTH}
            className="inline-flex h-11 shrink-0 items-center rounded-md bg-accent px-4 text-sm font-semibold text-accent-ink disabled:opacity-50"
          >
            {confirming ? "Проверяем…" : "Подтвердить"}
          </button>
        </form>
      )}

      <div className="mt-4">
        {phase === "error" ? (
          <button
            type="button"
            onClick={start}
            className="text-sm font-medium text-accent hover:underline"
          >
            Повторить
          </button>
        ) : (
          <button
            type="button"
            onClick={cancel}
            className="text-sm text-ink-3 hover:text-ink"
          >
            Отменить
          </button>
        )}
      </div>
    </div>
  );
}
