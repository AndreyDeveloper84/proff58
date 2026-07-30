import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Контейнерный деплой Next отдельным сервисом (headless).
  output: "standalone",
  // Фото товаров приходят из Django путём от корня сайта (`/media/…`) — витрина и
  // медиа за одним nginx. Оптимизатор Next не включаем: не требует remotePatterns
  // и отдельного сервиса оптимизации.
  images: { unoptimized: true },
};

export default nextConfig;
