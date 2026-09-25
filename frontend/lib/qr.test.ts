import QRCode from "qrcode";
import { describe, expect, it } from "vitest";

import { qrSvgPath } from "./qr";

// Разбираем сгенерированный путь обратно в матрицу: `M{x} {y}h{run}v1h-{run}z`.
function pathToMatrix(path: string, size: number): Uint8Array {
  const matrix = new Uint8Array(size * size);
  for (const [, x, y, run] of path.matchAll(/M(\d+) (\d+)h(\d+)v1h-\d+z/g)) {
    for (let i = 0; i < Number(run); i++) matrix[Number(y) * size + Number(x) + i] = 1;
  }
  return matrix;
}

describe("qrSvgPath", () => {
  const URL = "https://max.ru/proffinstrument";

  // Главное свойство: путь описывает ровно те модули, что дал генератор. Ловит
  // перепутанные x/y и off-by-one в свёртке пробегов — код с такой ошибкой
  // выглядит как QR, но не сканируется.
  it("путь точно повторяет матрицу генератора", () => {
    const { size, path } = qrSvgPath(URL);
    const expected = QRCode.create(URL, { errorCorrectionLevel: "M" }).modules;

    expect(size).toBe(expected.size);
    expect(pathToMatrix(path, size)).toEqual(Uint8Array.from(expected.data));
  });

  it("начинается с поискового квадрата в левом верхнем углу", () => {
    const { path } = qrSvgPath(URL);
    expect(path.startsWith("M0 0h7v1h-7z")).toBe(true);
  });

  it("длина ссылки влияет на версию кода, а сам код остаётся квадратным", () => {
    const short = qrSvgPath("https://max.ru/");
    const long = qrSvgPath(`https://max.ru/${"x".repeat(120)}`);

    expect(short.size).toBeGreaterThanOrEqual(21);
    expect(long.size).toBeGreaterThan(short.size);
  });
});
