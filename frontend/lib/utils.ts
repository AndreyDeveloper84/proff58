import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Объединение классов Tailwind (shadcn-конвенция). */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
