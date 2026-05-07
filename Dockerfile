FROM python:3.12-slim

WORKDIR /ados

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .
COPY ados/ ados/

ENTRYPOINT ["python", "server.py", "config.yaml"]
