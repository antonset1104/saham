FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SAHAM_CLOUD_MODE=1

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app

RUN groupadd --system saham && useradd --system --gid saham --home /app saham \
    && mkdir -p /app/Database /app/Arsip_Data_Harian /app/Logs \
    && chown -R saham:saham /app

USER saham
EXPOSE 8501 8503
CMD ["python", "cloudflare/runner.py"]
