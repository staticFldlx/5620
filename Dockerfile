FROM node:22-bookworm-slim AS frontend

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ENV VITE_USE_MOCK_API=false VITE_API_BASE_URL=/api/v1
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=frontend /app/frontend/dist ./frontend_dist

CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py load_demo_data && exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-10000} --workers 1 --threads 8 --timeout 120"]
