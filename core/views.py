from django.contrib.auth import login
from django.shortcuts import render, redirect

from core.forms import SignUpForm


# def signup(request):
#     if request.method == 'POST':
#         form = SignUpForm(request.POST)
#         if form.is_valid():
#             user = form.save()
#             login(request, user)
#             return redirect('rooms')
#     form = SignUpForm()
#     return render(request, 'signup.html', {'form': form})

def signup(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('rooms')
    else:
        form = SignUpForm()
    return render(request, 'signup.html', {'form': form})
