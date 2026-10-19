FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/src ./src
COPY frontend/public ./public
COPY frontend/index.html frontend/vite.config.ts frontend/tsconfig*.json ./
ENV VITE_API_BASE_URL="" VITE_TILE_URL="/tiles/{z}/{x}/{y}.png" VITE_TILE_MAX_ZOOM=12
RUN npm run build
FROM nginx:stable-alpine
COPY --from=frontend /build/dist /usr/share/nginx/html
COPY deploy/tiles/blank.png /usr/share/nginx/html/blank.png
COPY deploy/server/nginx.conf /etc/nginx/conf.d/default.conf
