FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /code
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 proxy \
    && useradd --uid 10001 --gid 10001 --no-create-home proxy \
    && mkdir /data && chown proxy:proxy /data && chmod 0700 /data
COPY app ./app
COPY init_db.py .
COPY examples/call_proxy.py ./call_proxy.py
USER 10001:10001
ENV ZT_DATABASE_URL=sqlite:////data/zero_trust.db
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-proxy-headers", "--no-access-log", "--limit-concurrency", "100"]
