ARG NODE_IMAGE=node:22-alpine
FROM ${NODE_IMAGE} AS web
WORKDIR /app/web
ARG VITE_BASE_PATH=/
ARG VITE_API_BASE=
ENV VITE_BASE_PATH=$VITE_BASE_PATH
ENV VITE_API_BASE=$VITE_API_BASE
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY api/app ./app
COPY --from=web /app/web/dist ./app/static
EXPOSE 8091
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8091"]
