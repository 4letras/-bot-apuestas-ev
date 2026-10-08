FROM python:3.12-slim

# Evitar buffers en logs
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código del proyecto
COPY . .

# Ejecutar el bot
CMD ["python", "bot.py"]
