"use client";

// Состояние входа, посчитанное на сервере (app/layout.tsx), — для клиентских
// частей шапки и нижней навигации. Здесь только перенос значения вниз по дереву:
// решение принимается один раз и одинаково для всей страницы.

import { createContext, useContext } from "react";

import type { AuthState } from "@/lib/auth-state";

// Дефолт — "unknown": компонент, отрисованный вне провайдера (юнит-тест,
// изолированный рендер), должен вести себя нейтрально — ссылки по назначению.
// Дефолт "anonymous" отправлял бы вошедшего на форму входа.
const AuthStateContext = createContext<AuthState>("unknown");

export function AuthStateProvider({
  state,
  children,
}: {
  state: AuthState;
  children: React.ReactNode;
}) {
  return <AuthStateContext.Provider value={state}>{children}</AuthStateContext.Provider>;
}

export function useAuthState(): AuthState {
  return useContext(AuthStateContext);
}
