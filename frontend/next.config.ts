import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Контейнерный деплой Next отдельным сервисом (headless).
  output: "standalone",
  // Фото товаров приходят из Django путём от корня сайта (`/media/…`) — витрина и
  // медиа за одним nginx. Оптимизатор Next не включаем: не требует remotePatterns
  // и отдельного сервиса оптимизации.
  images: { unoptimized: true },

  // «О компании» переехала в админку: страница собирается блоками из макета и
  // редактируется без релиза (/info/about). Рукописная /about удалена, но её
  // адрес живёт в закладках, в выдаче поисковика и в чужих ссылках — поэтому
  // постоянный редирект, а не 404. Постоянный (308) осознанно: адрес сменился
  // навсегда, и поисковик должен перенести на новый вес старого.
  async redirects() {
    return [{ source: "/about", destination: "/info/about", permanent: true }];
  },
};

export default nextConfig;
