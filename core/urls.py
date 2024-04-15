from django.contrib.auth.views import LogoutView, LoginView
from django.urls import path

from core.views import FrontpageView, SignupView

urlpatterns = [
    path('', FrontpageView.as_view(), name='frontpage'),
    path('signup/', SignupView.as_view(), name='signup'),
    path('login/', LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', LogoutView.as_view(), name='logout')
]
