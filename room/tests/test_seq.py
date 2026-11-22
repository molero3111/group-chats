from django.contrib.auth.models import User
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from room.models import Message, Room
from room.payloads import message_payload


class MessageSeqTests(TestCase):
    def setUp(self):
        self.ada = User.objects.create_user(username='ada', password='pw')
        self.room = Room.objects.create(name='Work', slug='work')

    def test_payload_includes_seq(self):
        message = Message.objects.create(room=self.room, user=self.ada, content='hi', seq=3)

        self.assertEqual(message_payload(message)['seq'], 3)

    def test_payload_seq_is_none_for_legacy_rows(self):
        message = Message.objects.create(room=self.room, user=self.ada, content='hi', seq=None)

        payload = message_payload(message)

        self.assertIn('seq', payload)
        self.assertIsNone(payload['seq'])

    def test_room_seq_unique(self):
        Message.objects.create(room=self.room, user=self.ada, content='a', seq=1)

        with self.assertRaises(IntegrityError), transaction.atomic():
            Message.objects.create(room=self.room, user=self.ada, content='b', seq=1)

    def test_null_seq_not_unique(self):
        # Rows written by the previous release during a revert window have no seq.
        Message.objects.create(room=self.room, user=self.ada, content='a', seq=None)
        Message.objects.create(room=self.room, user=self.ada, content='b', seq=None)

        self.assertEqual(self.room.messages.filter(seq__isnull=True).count(), 2)

    def test_room_starts_at_zero(self):
        self.assertEqual(Room.objects.get(pk=self.room.pk).last_seq, 0)


class BackfillSeqMigrationTests(TransactionTestCase):
    before = [('room', '0002_room_last_seq_message_seq')]
    after = [('room', '0003_backfill_message_seq')]

    def setUp(self):
        executor = MigrationExecutor(connection)
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(
            MigrationExecutor(connection).loader.graph.leaf_nodes()))
        executor.migrate(self.before)
        apps = executor.loader.project_state(self.before).apps
        UserModel = apps.get_model('auth', 'User')
        RoomModel = apps.get_model('room', 'Room')
        MessageModel = apps.get_model('room', 'Message')
        user = UserModel.objects.create(username='ada')
        a = RoomModel.objects.create(name='A', slug='a')
        b = RoomModel.objects.create(name='B', slug='b')
        RoomModel.objects.create(name='Empty', slug='empty')
        for room, content in [(a, 'A1'), (b, 'B1'), (a, 'A2'), (a, 'A3'), (b, 'B2')]:
            MessageModel.objects.create(room=room, user=user, content=content)

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.after)
        self.apps = executor.loader.project_state(self.after).apps

    def test_backfill_numbers_per_room_by_id(self):
        RoomModel = self.apps.get_model('room', 'Room')
        MessageModel = self.apps.get_model('room', 'Message')

        def seqs(slug):
            return [(m.content, m.seq) for m in MessageModel.objects.filter(room__slug=slug).order_by('id')]

        self.assertEqual(seqs('a'), [('A1', 1), ('A2', 2), ('A3', 3)])
        self.assertEqual(seqs('b'), [('B1', 1), ('B2', 2)])
        self.assertEqual(RoomModel.objects.get(slug='a').last_seq, 3)
        self.assertEqual(RoomModel.objects.get(slug='b').last_seq, 2)
        self.assertEqual(RoomModel.objects.get(slug='empty').last_seq, 0)


class SeqAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(username='root', password='pw')
        self.client.force_login(self.admin)
        self.room = Room.objects.create(name='Work', slug='work', last_seq=13)

    def test_saving_a_room_in_admin_keeps_last_seq(self):
        # A change form opened before 3 more sends would otherwise write the stale 10 back.
        url = f'/admin/room/room/{self.room.pk}/change/'

        response = self.client.post(url, {'name': 'Work renamed', 'slug': 'work', 'last_seq': 10})

        self.assertEqual(response.status_code, 302)
        room = Room.objects.get(pk=self.room.pk)
        self.assertEqual(room.name, 'Work renamed')
        self.assertEqual(room.last_seq, 13)

    def test_message_seq_not_editable_in_admin(self):
        message = Message.objects.create(room=self.room, user=self.admin, content='hi', seq=13)
        url = f'/admin/room/message/{message.pk}/change/'

        self.client.post(url, {'room': self.room.pk, 'user': self.admin.pk, 'content': 'edited', 'seq': ''})

        message.refresh_from_db()
        self.assertEqual(message.content, 'edited')
        self.assertEqual(message.seq, 13)
