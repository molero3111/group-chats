from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView
from django.db import Error as DatabaseError, connection
from django.http import JsonResponse
from django.shortcuts import redirect
from django.shortcuts import render
from django.views.generic import View

from core.forms import SignUpForm
from core.net import client_ip
from core.ratelimit import allow

TOO_MANY_ATTEMPTS = 'Too many attempts. Try again in a few minutes.'
SIGNUPS_CLOSED = 'Sign-ups are closed.'


class FrontpageView(View):
    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('rooms')
        return redirect('login')


class HealthzView(View):
    """Deploy health gate: 200 when the database answers, 503 when it doesn't."""

    def get(self, request, *args, **kwargs):
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
        except DatabaseError:
            return JsonResponse({'status': 'unavailable'}, status=503)
        return JsonResponse({'status': 'ok'})


class ThrottledLoginView(LoginView):
    """LoginView with a per-IP limit on attempts; a throttled attempt never checks the password."""

    def post(self, request, *args, **kwargs):
        if not allow('login', client_ip(request), settings.LOGIN_RATE):
            # Unbound, so no authentication runs; it keeps the typed username.
            form = self.get_form_class()(request, initial={'username': request.POST.get('username', '')})
            context = self.get_context_data(form=form, limit_error=TOO_MANY_ATTEMPTS)
            return self.render_to_response(context, status=429)
        return super().post(request, *args, **kwargs)


def _signups_closed():
    return settings.MAX_USERS and User.objects.count() >= settings.MAX_USERS


def _signup_error(request, message, status):
    form = SignUpForm(initial={'email': request.POST.get('email', '')})
    return render(request, 'signup.html', {'form': form, 'limit_error': message}, status=status)


class SignupView(View):
    def get(self, request, *args, **kwargs):
        if _signups_closed():
            return _signup_error(request, SIGNUPS_CLOSED, 403)
        form = SignUpForm()
        return render(request, 'signup.html', {'form': form})

    def post(self, request, *args, **kwargs):
        if _signups_closed():
            return _signup_error(request, SIGNUPS_CLOSED, 403)
        if not allow('signup', client_ip(request), settings.SIGNUP_RATE):
            return _signup_error(request, TOO_MANY_ATTEMPTS, 429)
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('rooms')
        return render(request, 'signup.html', {'form': form})
