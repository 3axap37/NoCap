### Build stage — install Python deps
FROM python:3.11-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

### Runtime stage — lean image
FROM python:3.11-slim

# poppler for pdf2image (runtime only, no build tools)
RUN apt-get update \
    && apt-get install -y --no-install-recommends poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Copy only the installed packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app
COPY . .

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
