# 1. Start with an official Python base image.
# Using a "slim" version keeps the final container small.
FROM python:3.11-slim

# 2. Set environment variables.
# This prevents Python from buffering output, so logs appear instantly.
ENV PYTHONUNBUFFERED True

# 3. Set the working directory inside the container.
WORKDIR /app

# 4. Copy the requirements file first. This helps Docker use its cache
# efficiently, making future builds faster if the requirements haven't changed.
COPY requirements.txt .

# 5. Install the Python dependencies listed in requirements.txt.
# --no-cache-dir keeps the image smaller.
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copy the rest of your application code into the container.
COPY main.py .

# 7. Specify the command to run when the container starts.
# [cite_start]We use gunicorn, a production-ready web server you've included[cite: 1],
# to run the Flask object named "app" inside your main.py file.
# Cloud Run expects the application to listen for traffic on port 8080.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "main:app"]