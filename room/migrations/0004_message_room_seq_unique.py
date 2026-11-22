from django.db import migrations, models

NAME = 'message_room_seq_unique'
CONSTRAINT = models.UniqueConstraint(fields=('room', 'seq'), name=NAME)


def add_constraint(apps, schema_editor):
    Message = apps.get_model('room', 'Message')
    quote = schema_editor.quote_name
    table = quote(Message._meta.db_table)
    room, seq = (quote(Message._meta.get_field(f).column) for f in ('room', 'seq'))
    if schema_editor.connection.vendor != 'postgresql':
        # A plain unique index; schema_editor.add_constraint would rebuild SQLite tables from a
        # model state that does not have the constraint yet.
        schema_editor.execute(f'CREATE UNIQUE INDEX {quote(NAME)} ON {table} ({room}, {seq})')
        return
    # Build the index without blocking writes, then attach it as the constraint, which only
    # needs a brief lock. A build interrupted earlier leaves an invalid index: drop it first.
    schema_editor.execute(f'DROP INDEX CONCURRENTLY IF EXISTS {quote(NAME)}')
    schema_editor.execute(f'CREATE UNIQUE INDEX CONCURRENTLY {quote(NAME)} ON {table} ({room}, {seq})')
    schema_editor.execute(f'ALTER TABLE {table} ADD CONSTRAINT {quote(NAME)} UNIQUE USING INDEX {quote(NAME)}')


def remove_constraint(apps, schema_editor):
    Message = apps.get_model('room', 'Message')
    quote = schema_editor.quote_name
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute(f'ALTER TABLE {quote(Message._meta.db_table)} DROP CONSTRAINT {quote(NAME)}')
    else:
        schema_editor.execute(f'DROP INDEX {quote(NAME)}')


class Migration(migrations.Migration):
    atomic = False  # CREATE INDEX CONCURRENTLY cannot run inside a transaction

    dependencies = [
        ('room', '0003_backfill_message_seq'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[migrations.AddConstraint(model_name='message', constraint=CONSTRAINT)],
            database_operations=[migrations.RunPython(add_constraint, remove_constraint)],
        ),
    ]
