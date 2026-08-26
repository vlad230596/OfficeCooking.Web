ARG APP_VERSION=dev
ARG BUILD_DATE=unknown

FROM node:22-alpine AS build
ARG APP_VERSION
ARG BUILD_DATE
ENV VITE_APP_VERSION=$APP_VERSION \
    VITE_BUILD_DATE=$BUILD_DATE
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . ./
RUN npm run build

FROM nginx:1.27-alpine
ARG APP_VERSION
ARG BUILD_DATE
LABEL org.opencontainers.image.version=$APP_VERSION \
      org.opencontainers.image.created=$BUILD_DATE
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
