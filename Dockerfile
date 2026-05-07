FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir web3

COPY src/ src/
COPY pyproject.toml .

ENV PYTHONPATH=src

CMD ["python", "-m", "wallet_cleanup_bot.main"]
