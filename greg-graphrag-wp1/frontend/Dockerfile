# ETAPA 1: Build (Node.js)
FROM node:alpine3.22 AS build
WORKDIR /app
COPY package*.json ./
# Instalación limpia para evitar paquetes de desarrollo vulnerables
RUN npm install
COPY . .
ARG PUBLIC_API_URL
ENV PUBLIC_API_URL=$PUBLIC_API_URL
RUN npm run build


FROM nginx:1.27-alpine AS runtime

RUN apk update && apk upgrade && \
    apk add --no-cache libcrypto3 libssl3 zlib


RUN rm -rf /etc/nginx/conf.d/default.conf && \
    rm -rf /usr/share/nginx/html/* && \
    chmod -R 0555 /usr/share/nginx/html


COPY ./nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html


RUN touch /var/run/nginx.pid && \
    chown -R nginx:nginx /var/run/nginx.pid /var/cache/nginx /var/log/nginx

USER nginx

EXPOSE 80