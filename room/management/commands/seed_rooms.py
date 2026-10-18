from django.core.management import BaseCommand, call_command

from room.models import Room


class Command(BaseCommand):
    help = 'Load the room fixtures, but only into an empty rooms table.'

    def handle(self, *args, **options):
        if Room.objects.exists():
            self.stdout.write('Rooms already exist; skipping fixtures.')
            return
        call_command('loaddata', 'rooms_fixture', verbosity=options['verbosity'])
