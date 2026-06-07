# webui/views.py
from django.shortcuts import render
from .forms import LoginForm, RegisterForm

def home_view(request):
    """
    Renders the main upload and tagline landing page.
    """
    return render(request, 'home.html')

def result_view(request, item_id):
    """
    Renders the classification result card details for a specific WasteItem.
    """
    return render(request, 'result.html', {'item_id': str(item_id)})

def login_view(request):
    """
    Renders the authentication login page.
    """
    form = LoginForm()
    return render(request, 'login.html', {'form': form})

def register_view(request):
    """
    Renders the citizen registration page.
    """
    form = RegisterForm()
    return render(request, 'register.html', {'form': form})

def profile_view(request):
    """
    Renders the citizen profile and classification history page.
    """
    return render(request, 'profile.html')

