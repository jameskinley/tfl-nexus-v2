FROM python:3.14-alpine3.23

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY src/ /app/

EXPOSE 8003

ENTRYPOINT [ "fastapi", "run", "--port", "8003", "--host", "0.0.0.0"]

HEALTHCHECK --interval=60s --timeout=30s --start-period=10s --retries=3 CMD [ "curl", "-f", "http://localhost:8003/", "||", "exit", "1" ]