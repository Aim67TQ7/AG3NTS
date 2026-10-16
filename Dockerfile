FROM python:3.12-slim
WORKDIR /srv
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY flux_harness flux_harness
COPY app app
COPY tests tests
COPY deploy/mail_bridge deploy/mail_bridge
COPY guides guides
COPY catalog catalog
COPY web/dist web/dist
COPY web/agent-work-results.html web/agent-work-results.html
RUN python -m unittest discover -s tests -q
ENV PYTHONDONTWRITEBYTECODE=1
ENV FLUX_FRESH=1
USER 1001:1001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8496"]
