# pull official base image
FROM python:3.11-slim

# set work directory
WORKDIR /app

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# install system dependencies
RUN apt-get update && \
    apt-get -y install build-essential gdal-bin python3-gdal libgdal-dev

# install dependencies
RUN pip install --upgrade pip
COPY ./requirements.txt .
RUN pip install -r requirements.txt

# copy project
COPY . .

# make start_notes_api.sh executable
RUN chmod +x start_chat_app.sh

# command to start Daphne
CMD ["./start_chat_app.sh"]
