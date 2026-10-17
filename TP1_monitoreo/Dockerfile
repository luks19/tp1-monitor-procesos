FROM python:3.11-slim

WORKDIR /app

COPY TP1_monitoreo/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY TP1_monitoreo/ .

CMD ["python3", "src/main.py"]
