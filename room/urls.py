from django.urls import path
from room.views import RoomsView, RoomView

urlpatterns = [
    path('', RoomsView.as_view(), name='rooms'),
    path('<slug:slug>/', RoomView.as_view(), name='room'),
]

