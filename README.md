# Room-Based Chat App

Welcome to the Room-Based Chat App! This web application allows users to join chat rooms and engage in real-time conversations with others.
You can view the deployed version at: [https://emmanuelcodinghub.com/chat/](https://emmanuelcodinghub.com/chat/)

## Features

- Join chat rooms.
- Real-time messaging using WebSocket connections.

## Technologies Used

- **Django**: The web framework for the backend.
- **Channels**: Extends Django to handle WebSocket connections and real-time events.
- **Daphne**: An ASGI (Asynchronous Server Gateway Interface) server for serving Django Channels applications.
- **Bootstrap**: Used for styling the frontend.
- **PostgresSQL**: The database for storing user data and chat messages.
- **Redis**: The cache system used in the websocket channel layer

## Getting Started

To run this project locally using Docker, follow these steps:

## 1. Clone this repository to your local machine:

    git clone https://github.com/molero3111/chat_in_django.git
    cd chat_in_django

## 2. Create .env from .env.example file

## 3. Run Docker Compose

    docker compose -p development-django-chat -f docker-compose-development.yml up --build

This command will build and run the containers. You can then access the app at [http://localhost:8000](http://localhost:8000).

## Usage

- Create an account or log in if you already have one.
- Browse available chat rooms and join the ones that interest you.
- Start chatting with other users in real-time.




