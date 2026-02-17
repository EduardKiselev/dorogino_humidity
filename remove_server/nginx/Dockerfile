FROM nginx:alpine

# Копируем ВРЕМЕННУЮ конфигурацию
COPY nginx.conf /etc/nginx/nginx.conf

# Создаем директорию для ACME challenge
RUN mkdir -p /var/www/certbot

# Права доступа
RUN chown -R nginx:nginx /var/www/certbot

EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]