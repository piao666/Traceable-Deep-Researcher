FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --legacy-peer-deps
COPY . .
ARG NEXT_PUBLIC_TDR_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_TDR_API_URL=${NEXT_PUBLIC_TDR_API_URL}
ENV BACKEND_URL=http://research:8000
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV BACKEND_URL=http://research:8000
COPY --from=builder --chown=node:node /app/package.json ./
COPY --from=builder --chown=node:node /app/next.config.mjs ./
COPY --from=builder --chown=node:node /app/public ./public
COPY --from=builder --chown=node:node /app/.next ./.next
COPY --from=builder --chown=node:node /app/node_modules ./node_modules
USER node
EXPOSE 3000
CMD ["npm", "run", "start"]
