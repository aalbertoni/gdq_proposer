FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
ENV PORT=8501

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY run.py .
COPY config.py .
COPY core ./core
COPY infra ./infra
COPY services ./services
COPY strategies ./strategies
COPY pages ./pages
COPY queries ./queries
COPY docs ./docs
COPY .env.example ./.env.example

RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/logs /app/presets /app/mock_data /app/aws_test_data \
    && chown -R appuser:appuser /app

USER appuser
EXPOSE 8501

CMD ["sh", "-lc", "python -m streamlit run app.py --server.address=0.0.0.0 --server.port=${PORT:-8501} --server.headless=true --browser.gatherUsageStats=false"]
