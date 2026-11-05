FROM python:3.13-slim-trixie
WORKDIR /worker
COPY measured/worker.py ./worker.py
USER 65534:65534
ENTRYPOINT ["python3", "-u", "/worker/worker.py"]
