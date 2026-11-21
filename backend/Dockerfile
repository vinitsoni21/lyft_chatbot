# ---- build stage: install packages ----
FROM python:3.11-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- runtime stage: small final image ----
FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY app ./app

ENV DATABASE_URL=sqlite:////data/app.db
RUN mkdir -p /data

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]