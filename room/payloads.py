from room.models import Message, Room


def message_payload(message: Message) -> dict:
    """The event body every transport delivers for a new message."""
    return {
        'id': message.id,
        'room': message.room.slug,
        'user': {'id': message.user_id, 'username': message.user.username},
        'content': message.content,
        'created_at': message.created_at.isoformat(),
    }


def room_topic(room: Room) -> str:
    # Columba topics allow only [A-Za-z0-9:_\-.]; slugs are free text, ids are not.
    return f'room:{room.id}'


def room_group(room: Room) -> str:
    return f'chat_{room.id}'
