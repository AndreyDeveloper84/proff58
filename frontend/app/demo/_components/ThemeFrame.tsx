"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";

// SP2.1 (#474): демо-обёртка с переключателем темы. Задаёт data-theme на своём
// поддереве (light-first по умолчанию), позволяя увидеть обе темы на /demo/*.
// Компоненты внутри используют только семантические токены — переключение их не трогает.
export function ThemeFrame({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<"light" | "dark">("light");
  return (
    <div data-theme={theme} className="min-h-screen bg-canvas text-ink">
      <div className="sticky top-0 z-10 flex items-center justify-end gap-2 border-b border-line bg-surface/90 px-4 py-2 backdrop-blur">
        <span className="text-xs text-ink-3">Предпросмотр темы:</span>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setTheme((t) => (t === "light" ? "dark" : "light"))}
        >
          {theme === "light" ? "☀ Светлая" : "🌙 Тёмная"}
        </Button>
      </div>
      {children}
    </div>
  );
}
