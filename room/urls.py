from django.urls import path
from room.views import RoomsView, RoomView, RoomMessagesView, RoomTokenView

urlpatterns = [
    path('', RoomsView.as_view(), name='rooms'),
    path('<slug:slug>/', RoomView.as_view(), name='room'),
    path('<slug:slug>/messages/', RoomMessagesView.as_view(), name='room-messages'),
    path('<slug:slug>/token/', RoomTokenView.as_view(), name='room-token'),
]
