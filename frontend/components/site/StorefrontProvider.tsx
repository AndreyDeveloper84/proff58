"use client";

// Контакты магазина, разрешённые на сервере (app/layout.tsx из SiteSettings), —
// для клиентских компонентов (чекаут и т.п.). Вне провайдера — запасные
// значения resolveStorefront(), чтобы изолированный рендер не падал.

import { createContext, useContext } from "react";

import { resolveStorefront, type ResolvedStorefront } from "@/lib/site";

const StorefrontContext = createContext<ResolvedStorefront>(resolveStorefront());

export function StorefrontProvider({
  value,
  children,
}: {
  value: ResolvedStorefront;
  children: React.ReactNode;
}) {
  return <StorefrontContext.Provider value={value}>{children}</StorefrontContext.Provider>;
}

export function useStorefront(): ResolvedStorefront {
  return useContext(StorefrontContext);
}
