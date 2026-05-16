FROM python:3.12-slim

LABEL org.opencontainers.image.title="DataWarehouse-Explorer"
LABEL org.opencontainers.image.description="Personal offline data warehouse builder with AI-powered query"
LABEL org.opencontainers.image.source="https://github.com/symmetryseeker/DataWarehouse-Explorer"

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV DW_WAREHOUSE_ROOT=/data
ENV DW_DATABASE_URL=sqlite:///data/warehouse.db
ENV DW_PUBLIC_MODE=0

VOLUME ["/data"]

EXPOSE 5000

CMD ["python", "DataWarehouse_Web.py", "--host", "0.0.0.0", "--port", "5000"]
