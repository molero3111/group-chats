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

# copy wait-for-it.sh
COPY ./wait-for-it.sh .

# make wait-for-it.sh executable
RUN chmod +x wait-for-it.sh

# copy project
COPY . .

# run wait-for-it.sh
ENTRYPOINT ["./wait-for-it.sh", "db:5432", "--"]
