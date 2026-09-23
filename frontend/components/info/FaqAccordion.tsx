"use client";

import { useId, useRef, useState, type KeyboardEvent } from "react";

import { cn } from "@/lib/utils";

type Item = { title: string; text: string };

// Вопросы-ответы инфо-страницы: в группе всегда открыт ровно один ответ.
//
// Раньше это были независимые <details>: открыв три вопроса подряд, человек
// получал простыню из трёх ответов, а закрыв последний — пустой список без
// единой подсказки. Теперь новый вопрос сменяет прежний, а повторный клик по
// открытому ничего не делает — пустым блок не остаётся.
//
// Активный пункт хранится по заголовку вопроса (он уникален в секции), а не по
// номеру: правка порядка в админке не открывает внезапно чужой ответ. Каждая
// секция — свой экземпляр со своим состоянием, группы друг на друга не влияют.
export function FaqAccordion({ items }: { items: Item[] }) {
  const [active, setActive] = useState(items[0]?.title ?? "");
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  const baseId = useId();

  // Стрелки и Home/End переводят фокус между вопросами (WAI-ARIA Accordion).
  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const last = items.length - 1;
    const target =
      event.key === "ArrowDown"
        ? index === last ? 0 : index + 1
        : event.key === "ArrowUp"
          ? index === 0 ? last : index - 1
          : event.key === "Home"
            ? 0
            : event.key === "End"
              ? last
              : null;
    if (target === null) return;
    event.preventDefault();
    buttons.current[target]?.focus();
  };

  return (
    <div className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface">
      {items.map((item, index) => {
        const open = item.title === active;
        const buttonId = `${baseId}-q${index}`;
        const panelId = `${baseId}-a${index}`;
        return (
          <div key={item.title}>
            <h3>
              <button
                ref={(node) => {
                  buttons.current[index] = node;
                }}
                id={buttonId}
                type="button"
                aria-expanded={open}
                aria-controls={panelId}
                onClick={() => setActive(item.title)}
                onKeyDown={(event) => onKeyDown(event, index)}
                className={cn(
                  "flex w-full items-center justify-between gap-4 px-5 py-4 text-left text-base font-medium text-ink",
                  // Открытый вопрос не закрывается — курсор не обещает действия.
                  open ? "cursor-default" : "hover:text-accent",
                )}
              >
                {item.title}
                <span
                  aria-hidden
                  className={cn("text-ink-3 transition-transform", open && "rotate-45")}
                >
                  +
                </span>
              </button>
            </h3>
            <div id={panelId} aria-labelledby={buttonId} hidden={!open}>
              <p className="px-5 pb-4 text-sm leading-relaxed text-ink-2">{item.text}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
