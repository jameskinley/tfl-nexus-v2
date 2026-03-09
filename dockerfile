FROM python:3.14-slim

WORKDIR /app

COPY requirements.txt .

RUN apt-get update && apt-get install -y --no-install-recommends \
	git \
	curl \
	build-essential \
	libpq-dev && \
	rm -rf /var/lib/apt/lists/*

RUN grep -vE '^pywin32' requirements.txt > requirements_linux.txt && \
	echo "psycopg[binary]" >> requirements_linux.txt && \
	pip install --no-cache-dir -r requirements_linux.txt

COPY src/ /app/

#api
EXPOSE 9000

#mcp
EXPOSE 9002

ENTRYPOINT [ "python", "-u", "app.py" ]

HEALTHCHECK --interval=60s --timeout=30s --start-period=10s --retries=3 CMD ["curl","-f","http://localhost:9000/"]