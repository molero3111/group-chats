from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View

from djangochat.settings import URL_PREFIX
from room.models import Room, Message


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
            'messages': messages,
            'url_prefix': URL_PREFIX
        })
