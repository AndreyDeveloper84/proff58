"use client";

import { animate, useInView, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import type { HomeStat } from "@/lib/home-content";

export function StatCounter({ value, suffix, label }: HomeStat) {
  const reduce = useReducedMotion();
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-60px" });
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    if (!inView) return;
    if (reduce) {
      const raf = requestAnimationFrame(() => setDisplay(value));
      return () => cancelAnimationFrame(raf);
    }
    const controls = animate(0, value, {
      duration: 1.4,
      ease: "easeOut",
      onUpdate: (v) => setDisplay(Math.round(v)),
    });
    return () => controls.stop();
  }, [inView, reduce, value]);

  return (
    <div ref={ref} className="text-center">
      <div className="font-display text-3xl font-bold text-accent sm:text-4xl">
        {display.toLocaleString("ru-RU")}
        {suffix}
      </div>
      <div className="mt-1 text-sm text-ink-3">{label}</div>
    </div>
  );
}
