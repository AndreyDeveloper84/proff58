import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Контейнерный деплой Next отдельным сервисом (headless).
  output: "standalone",
  // Реальные фото товаров приходят абсолютными URL из Django/медиа — не прогоняем
  // через оптимизатор Next (не требует remotePatterns и сервиса оптимизации).
  images: { unoptimized: true },
};

export default nextConfig;
