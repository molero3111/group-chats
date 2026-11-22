from django.db import migrations


def backfill(apps, schema_editor):
    """Number each room's existing messages 1, 2, 3... in id order and record the newest seq."""
    Room = apps.get_model('room', 'Room')
    Message = apps.get_model('room', 'Message')
    for room in Room.objects.all():
        messages = list(Message.objects.filter(room=room).order_by('id').only('id'))
        for seq, message in enumerate(messages, start=1):
            message.seq = seq
        Message.objects.bulk_update(messages, ['seq'], batch_size=500)
        room.last_seq = len(messages)
        room.save(update_fields=['last_seq'])


class Migration(migrations.Migration):

    dependencies = [
        ('room', '0002_room_last_seq_message_seq'),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
