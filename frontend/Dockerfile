# syntax=docker/dockerfile:1
# Headless storefront (Next.js standalone). Отдельный контейнер за nginx.
FROM node:22-slim AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
# Кэш npm между деплоями (BuildKit): при изменении lockfile не качаем пакеты заново.
RUN --mount=type=cache,target=/root/.npm npm ci

FROM node:22-slim AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Кэш инкрементальной сборки Next (.next/cache) между деплоями — резко ускоряет next build.
RUN --mount=type=cache,target=/app/.next/cache npm run build

FROM node:22-slim AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
RUN groupadd -r nodejs && useradd -r -g nodejs nextjs
# Next standalone: сервер + только нужные node_modules.
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
