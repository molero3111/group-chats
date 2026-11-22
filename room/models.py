from django.contrib.auth.models import User
from django.db import models


# Create your models here.

class Room(models.Model):
    name = models.CharField(max_length=255)
    slug = models.CharField(max_length=100, unique=True)
    # The seq of the newest message; bumped under a row lock when a message is sent.
    last_seq = models.PositiveIntegerField(default=0, db_default=0)

    def __str__(self):
        return self.slug


class Message(models.Model):
    room = models.ForeignKey(Room, related_name='messages', on_delete=models.CASCADE)
    user = models.ForeignKey(User, related_name='messages', on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    # 1, 2, 3... within the room, so a client can see when it missed one. NULL only for rows
    # written by an older release after this column existed (a deploy revert).
    seq = models.PositiveIntegerField(null=True, blank=True)

    def __str__(self):
        return f"{self.user} - {self.content} - {self.room}"

    class Meta:
        ordering = ('created_at',)
        constraints = [models.UniqueConstraint(fields=['room', 'seq'], name='message_room_seq_unique')]
