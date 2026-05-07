FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir eth-account==0.8.0 eth-utils==2.3.2

COPY src/ src/
COPY pyproject.toml .

ENV PYTHONPATH=src

CMD ["python", "-m", "wallet_cleanup_bot.main"]
