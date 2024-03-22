from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from room.models import Room, Message


# Create your views here.
@login_required
def rooms(request):
    return render(request,
                  'rooms.html',
                  {'rooms': Room.objects.all()}
                  )


@login_required
def room(request, slug):
    room_item = Room.objects.get(slug=slug)
    return render(request, 'room.html', {
        'room': room_item,
        'messages': Message.objects.filter(room=room_item)[0:25]
    })
