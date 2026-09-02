import type { InfoBlock } from "@/lib/info-pages";

// Базовые блоки инфо-страницы — те же четыре, что и у статей: абзац, список,
// врезка, таблица. Разбирает их один и тот же парсер на сервере, поэтому и
// выглядеть они должны одинаково; отличается только обрамление секций.

function Table({ head, rows }: { head: string[]; rows: string[][] }) {
  return (
    // Таблица зон доставки на телефоне шире экрана. Скроллим её саму, а не
    // страницу: горизонтальная прокрутка всего документа ломает чтение.
    <div className="overflow-x-auto rounded-lg border border-line">
      <table className="w-full min-w-[32rem] border-collapse text-sm">
        <thead className="bg-raised text-ink">
          <tr>
            {head.map((cell) => (
              <th key={cell} scope="col" className="px-4 py-3 text-left font-medium">
                {cell}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="text-ink-2">
          {rows.map((row, index) => (
            <tr key={index} className="border-t border-line">
              {row.map((cell, cellIndex) => (
                <td key={cellIndex} className="px-4 py-3">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function InfoBlocks({ blocks }: { blocks: InfoBlock[] }) {
  if (blocks.length === 0) return null;
  return (
    <div className="space-y-4">
      {blocks.map((block, index) => {
        if (block.kind === "text") {
          return (
            <p key={index} className="text-base leading-relaxed text-ink-2">
              {block.text}
            </p>
          );
        }
        if (block.kind === "list") {
          return (
            <ul key={index} className="space-y-2 text-base leading-relaxed text-ink-2">
              {block.items.map((item, itemIndex) => (
                <li key={itemIndex} className="flex gap-3">
                  <span aria-hidden className="mt-2 size-1.5 shrink-0 rounded-full bg-accent" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          );
        }
        if (block.kind === "note") {
          return (
            <p
              key={index}
              className="rounded-lg border border-info-line bg-info-bg px-4 py-3 text-sm leading-relaxed text-ink"
            >
              {block.text}
            </p>
          );
        }
        return <Table key={index} head={block.head} rows={block.rows} />;
      })}
    </div>
  );
}
