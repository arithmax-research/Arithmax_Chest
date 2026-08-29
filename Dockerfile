FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY achest ./achest

RUN pip install --no-cache-dir '.[all]'

EXPOSE 8000
CMD ["uvicorn", "achest.server:app", "--host", "0.0.0.0", "--port", "8000"]
