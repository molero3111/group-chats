from django.db import migrations, models


class Migration(migrations.Migration):
    """Nullable seq and db_default last_seq, so the previous release can still insert rows (expand step)."""

    dependencies = [
        ('room', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='message',
            name='seq',
            field=models.PositiveIntegerField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='room',
            name='last_seq',
            field=models.PositiveIntegerField(db_default=0, default=0, editable=False),
        ),
    ]
