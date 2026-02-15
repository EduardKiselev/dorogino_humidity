FROM nginx:alpine

# Копируем конфигурацию
COPY nginx.conf /etc/nginx/nginx.conf

# Устанавливаем certbot для ручного получения сертификатов
RUN apk add --no-cache certbot

# Создаем директорию для ACME challenge
RUN mkdir -p /var/www/certbot

# Права доступа
RUN chown -R nginx:nginx /var/www/certbot

EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]