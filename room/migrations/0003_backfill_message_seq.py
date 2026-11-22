from django.db import migrations

# Number each room's messages 1, 2, 3... in id order in one statement, then record each room's
# newest seq. UPDATE ... FROM with a window function works on PostgreSQL and SQLite 3.33+.
NUMBER_MESSAGES = """
UPDATE room_message SET seq = numbered.rn
FROM (SELECT id, ROW_NUMBER() OVER (PARTITION BY room_id ORDER BY id) AS rn FROM room_message) AS numbered
WHERE room_message.id = numbered.id
"""
RECORD_LAST_SEQ = """
UPDATE room_room SET last_seq = COALESCE(
    (SELECT MAX(seq) FROM room_message WHERE room_message.room_id = room_room.id), 0)
"""


class Migration(migrations.Migration):

    dependencies = [
        ('room', '0002_room_last_seq_message_seq'),
    ]

    operations = [
        migrations.RunSQL(NUMBER_MESSAGES, migrations.RunSQL.noop),
        migrations.RunSQL(RECORD_LAST_SEQ, migrations.RunSQL.noop),
    ]
