from django.contrib.auth.views import LogoutView, LoginView
from django.urls import path

from core import views

urlpatterns = [
    path('', views.frontpage, name='frontpage'),
    path('login/', LoginView.as_view(template_name='login.html'), name='login'),
    path('signup/', views.signup, name='signup'),
    path('logout/', LogoutView.as_view(), name='logout')
]
