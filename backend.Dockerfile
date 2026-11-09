FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt backend/requirements-test.txt /app/
RUN pip install --no-cache-dir -r requirements-test.txt

COPY . /app/

ENV PYTHONUNBUFFERED=1
ENV DOCKER_HOST=unix:///var/run/docker.sock

CMD ["python", "-m", "uvicorn", "backend.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
