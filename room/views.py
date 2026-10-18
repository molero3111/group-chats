import json
from functools import wraps

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View

from room.models import Room, Message
from room.payloads import message_payload
from room.transports import get_transport
from room.transports.columba import mint_token

# Columba caps an event payload at 64 KB; 4000 characters stays well under it.
MAX_MESSAGE_LENGTH = 4000
CATCH_UP_LIMIT = 100


def api_login_required(view):
    """Like login_required, but answers 401 JSON instead of redirecting to the login page."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'unauthenticated'}, status=401)
        return view(request, *args, **kwargs)
    return wrapper


class RoomsView(View):
    @method_decorator(login_required)
    def get(self, request):
        return render(request, 'rooms.html', {'rooms': Room.objects.all()})


class RoomView(View):
    @method_decorator(login_required)
    def get(self, request, slug):
        room_item = get_object_or_404(Room, slug=slug)

        messages_query = Message.objects.filter(room=room_item).order_by('-id')

        paginator = Paginator(messages_query, 100)
        messages = paginator.get_page(request.GET.get('page', 1))

        return render(request, 'room.html', {
            'room': room_item,
            'messages': messages,
            'chat_config': {
                'transport': get_transport().client_config(request, room_item),
                'messages_url': reverse('room-messages', args=[room_item.slug]),
                'user_id': request.user.id,
            },
        })


class RoomMessagesView(View):
    """POST sends a message as the logged-in user; GET ?after=<id> returns what a client missed."""

    @method_decorator(api_login_required)
    def get(self, request, slug):
        room = get_object_or_404(Room, slug=slug)
        try:
            after = int(request.GET.get('after', 0))
        except ValueError:
            return JsonResponse({'error': 'invalid_after'}, status=400)
        messages = (room.messages.filter(id__gt=after).select_related('user', 'room')
                    .order_by('id')[:CATCH_UP_LIMIT])
        return JsonResponse({'messages': [message_payload(m) for m in messages]})

    @method_decorator(api_login_required)
    def post(self, request, slug):
        room = get_object_or_404(Room, slug=slug)
        content = _posted_content(request)
        if content is None or '\x00' in content:  # PostgreSQL text cannot hold NUL
            return JsonResponse({'error': 'invalid_body'}, status=400)
        content = content.strip()
        if not content:
            return JsonResponse({'error': 'empty'}, status=400)
        if len(content) > MAX_MESSAGE_LENGTH:
            return JsonResponse({'error': 'too_long'}, status=400)

        # The author is always the session user, never anything the client sends.
        message = Message.objects.create(room=room, user=request.user, content=content)
        payload = message_payload(message)
        # robust: a broken transport is logged, never turned into a 500 for a message already saved.
        transaction.on_commit(lambda: get_transport().publish(room, 'message.new', payload), robust=True)
        return JsonResponse(payload, status=201)


def _posted_content(request):
    if request.content_type == 'application/json':
        try:
            content = json.loads(request.body).get('content', '')
        except (ValueError, AttributeError):
            return None
    else:
        content = request.POST.get('content', '')
    return content if isinstance(content, str) else None


class RoomTokenView(View):
    """A fresh Columba client token for this room; the browser fetches one before every (re)connect."""

    @method_decorator(api_login_required)
    def get(self, request, slug):
        if settings.CHAT_TRANSPORT != 'columba':
            raise Http404
        room = get_object_or_404(Room, slug=slug)
        response = JsonResponse({'token': mint_token(request.user, room)})
        response['Cache-Control'] = 'no-store'
        return response
