from typing import Protocol

from django.http import HttpRequest

from room.models import Room


class Transport(Protocol):
    """Delivers saved messages to browsers. Browsers only receive; sending is an HTTP POST."""

    def publish(self, room: Room, event: str, payload: dict) -> None:
        """Fan an event out to everyone in the room. Never raises on delivery failure."""

    def client_config(self, request: HttpRequest, room: Room) -> dict:
        """What the room page's chat.js needs to open a connection."""
