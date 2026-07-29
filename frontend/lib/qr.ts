import QRCode from "qrcode";

/**
 * Матрица QR-кода, свёрнутая в один SVG-путь.
 *
 * Синхронно (`QRCode.create`, а не `toDataURL`) — чтобы код рисовался прямо в
 * серверном компоненте, без async-обёртки и без картинки в `public/`, которая
 * молча протухнет при смене ссылки. Путь строится горизонтальными пробегами
 * чёрных модулей: один `<path>` вместо сотен `<rect>`.
 */
export function qrSvgPath(
  text: string,
  errorCorrectionLevel: "L" | "M" | "Q" | "H" = "M",
): { size: number; path: string } {
  const { modules } = QRCode.create(text, { errorCorrectionLevel });
  const { size, data } = modules;
  const runs: string[] = [];

  for (let y = 0; y < size; y++) {
    let x = 0;
    while (x < size) {
      if (!data[y * size + x]) {
        x++;
        continue;
      }
      let run = 1;
      while (x + run < size && data[y * size + x + run]) run++;
      runs.push(`M${x} ${y}h${run}v1h-${run}z`);
      x += run;
    }
  }

  return { size, path: runs.join("") };
}
