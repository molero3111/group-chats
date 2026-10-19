from django.contrib.auth.views import LogoutView, LoginView
from django.urls import path

from core.views import FrontpageView, HealthzView, SignupView

urlpatterns = [
    path('', FrontpageView.as_view(), name='frontpage'),
    path('healthz', HealthzView.as_view(), name='healthz'),
    path('signup/', SignupView.as_view(), name='signup'),
    path('login/', LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', LogoutView.as_view(), name='logout')
]
