import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Контейнерный деплой Next отдельным сервисом (headless).
  output: "standalone",
};

export default nextConfig;
