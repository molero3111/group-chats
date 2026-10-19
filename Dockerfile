FROM python:3.14-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY ./requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x start.sh wait-for-it.sh

# Wait for the database before running the compose command.
ENTRYPOINT ["./wait-for-it.sh", "db:5432", "--"]
