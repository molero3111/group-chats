from django.contrib.auth import login
from django.db import Error as DatabaseError, connection
from django.http import JsonResponse
from django.shortcuts import redirect
from django.shortcuts import render
from django.views.generic import View

from core.forms import SignUpForm


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


class SignupView(View):
    def get(self, request, *args, **kwargs):
        form = SignUpForm()
        return render(request, 'signup.html', {'form': form})

    def post(self, request, *args, **kwargs):
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('rooms')
        return render(request, 'signup.html', {'form': form})
