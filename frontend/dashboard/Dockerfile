FROM node:20-alpine AS builder
WORKDIR /app
COPY frontend/dashboard/package*.json ./
RUN npm ci
COPY frontend/dashboard/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
