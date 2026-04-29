FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json index.html vite.config.js ./
COPY src ./src
RUN npm ci && npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
