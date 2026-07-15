"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { login, otpLogin, register } from "@/lib/auth";
import { MaxAuthFlow } from "@/components/account/MaxAuthFlow";

// Куда вернуть после входа (§16.7): ?next=<path> из URL, иначе профиль.
function nextTarget(): string {
  if (typeof window === "undefined") return "/account/profile";
  const n = new URLSearchParams(window.location.search).get("next");
  return n && n.startsWith("/") ? n : "/account/profile";
}

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register" | "otp">("login");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (mode === "login") {
        await login(phone, password);
      } else if (mode === "register") {
        await register({ phone, password, full_name: name });
      } else {
        await otpLogin(phone, otp);
      }
      router.push(nextTarget());
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Ошибка");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-md mx-auto mt-16 p-6">
      <h1 className="text-2xl font-bold mb-6">
        {mode === "login" ? "Вход" : mode === "register" ? "Регистрация" : "Вход по коду MAX"}
      </h1>

      {/* Вход/регистрация через MAX — заметный, но не единственный способ (§6). */}
      <div className="mb-5">
        <MaxAuthFlow mode="login" onCompleted={() => router.push(nextTarget())} />
        <div className="my-4 flex items-center gap-3 text-xs text-gray-400">
          <span className="h-px flex-1 bg-gray-200" />
          или
          <span className="h-px flex-1 bg-gray-200" />
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <input
          type="tel"
          placeholder="Телефон"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          className="w-full border rounded px-3 py-2"
          required
        />

        {mode !== "otp" && (
          <input
            type="password"
            placeholder="Пароль"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full border rounded px-3 py-2"
            required
          />
        )}

        {mode === "register" && (
          <input
            type="text"
            placeholder="Имя"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full border rounded px-3 py-2"
          />
        )}

        {mode === "otp" && (
          <input
            type="text"
            placeholder="Код из MAX"
            value={otp}
            onChange={(e) => setOtp(e.target.value)}
            className="w-full border rounded px-3 py-2"
            required
            maxLength={4}
          />
        )}

        {error && <p className="text-red-600 text-sm">{error}</p>}

        <button
          type="submit"
          disabled={loading}
          className="w-full bg-green-600 text-white rounded py-2 hover:bg-green-700 disabled:opacity-50"
        >
          {loading ? "..." : mode === "register" ? "Зарегистрироваться" : "Войти"}
        </button>
      </form>

      <div className="mt-4 text-sm text-gray-600 space-y-1">
        {mode !== "login" && (
          <button onClick={() => setMode("login")} className="underline block">Вход по паролю</button>
        )}
        {mode !== "register" && (
          <button onClick={() => setMode("register")} className="underline block">Регистрация</button>
        )}
        {mode !== "otp" && (
          <button onClick={() => setMode("otp")} className="underline block">Вход по коду MAX</button>
        )}
      </div>
    </div>
  );
}
