# Imagen para Render, Hugging Face Spaces u otro servicio con Docker.
# Usa el puerto que indique la plataforma (variable PORT); si no hay, 7860.
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV PORT=7860
EXPOSE 7860
CMD streamlit run app.py --server.port=${PORT} --server.address=0.0.0.0 \
    --server.enableXsrfProtection=false --server.enableCORS=false --server.headless=true
