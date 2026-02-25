FROM python:3.14-alpine3.23

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY src/ /app/

EXPOSE 9000
RUN apk add --no-cache curl

ENTRYPOINT [ "python", "-u", "app.py" ]

HEALTHCHECK --interval=60s --timeout=30s --start-period=10s --retries=3 CMD "curl -f http://localhost:9000/ || exit 1"