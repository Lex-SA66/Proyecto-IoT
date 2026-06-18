# Usa una imagen ligera de Python
FROM python:3.9-slim

# Crea el directorio de trabajo
WORKDIR /app

# Copia los archivos de requerimientos y el script
COPY src/servidor_uno_q/requirements.txt requirements.txt
COPY src/servidor_uno_q/servidor_kms.py servidor_kms.py

# Instala las dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Expone el puerto 5000 para Flask
EXPOSE 5000

# Ejecuta el servidor
CMD ["python", "servidor_kms.py"]