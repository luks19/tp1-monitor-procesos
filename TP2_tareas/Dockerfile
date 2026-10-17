FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 TP2_DIRECTORIO=/datos
COPY TP2_tareas/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY TP2_tareas ./TP2_tareas
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "TP2_tareas.app:app", "--host", "0.0.0.0", "--port", "8000"]
