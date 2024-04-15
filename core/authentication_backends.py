from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class CustomAuthenticationBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        user = get_user_model()
        if '@' in username:
            try:
                user = user.objects.get(email=username)
                username = user.username
            except user.DoesNotExist:
                username = None
        return super().authenticate(request, username=username, password=password, **kwargs)
