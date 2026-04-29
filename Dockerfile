FROM tiangolo/uvicorn-gunicorn-fastapi:python3.11

# libpq-dev + gcc — для psycopg2
# Системные зависимости Playwright устанавливаются вместе с ним ниже,
# поэтому apt-get update не чистим до конца этого блока
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Chromium + все системные зависимости в одном слое
# (playwright сам вызывает apt-get update внутри)
RUN playwright install chromium --with-deps

COPY . .

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

EXPOSE 80
