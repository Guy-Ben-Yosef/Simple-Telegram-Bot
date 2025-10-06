FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8080
EXPOSE 8080

# use gunicorn in production
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "main:app", "--workers", "1", "--threads", "8"]
