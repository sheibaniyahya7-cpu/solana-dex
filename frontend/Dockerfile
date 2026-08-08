# ─── Base Stage ───────────────────────────────────────────────────────────────
FROM node:20-alpine AS base

ENV NODE_ENV=production
WORKDIR /app

# ─── Dependencies Stage ────────────────────────────────────────────────────────
FROM base AS deps

# Install dependencies needed for native modules
RUN apk add --no-cache libc6-compat

COPY package.json package-lock.json ./
# NODE_ENV=production makes npm omit devDependencies, but the builder stage
# needs typescript/tailwind/postcss to compile.
RUN npm ci --include=dev

# ─── Builder Stage ────────────────────────────────────────────────────────────
FROM base AS builder

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Build Next.js app
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ─── Runner Stage ─────────────────────────────────────────────────────────────
FROM base AS runner

WORKDIR /app

ENV NEXT_TELEMETRY_DISABLED=1

# Create non-root user
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public

# Leverage Next.js output tracing
RUN mkdir .next && chown nextjs:nodejs .next

COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# 127.0.0.1, not localhost: the server binds IPv4 only, and busybox wget gives
# up on the ::1 answer instead of trying the next address.
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD wget -qO- http://127.0.0.1:3000/ || exit 1

CMD ["node", "server.js"]
