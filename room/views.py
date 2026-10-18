from functools import wraps

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.decorators import method_decorator
from django.views import View

from room.models import Room, Message
from room.transports.columba import mint_token


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
        room_item = Room.objects.get(slug=slug)

        messages_query = Message.objects.filter(room=room_item).order_by('-id')

        paginator = Paginator(messages_query, 100)
        messages = paginator.get_page(request.GET.get('page', 1))

        return render(request, 'room.html', {
            'room': room_item,
            'messages': messages
        })


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
