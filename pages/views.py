from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from compliance.models import Standard, AssessmentResult, Control

def home(request):
    return render(request, 'pages/home.html')

def register_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('dashboard')
    else:
        form = UserCreationForm()
    return render(request, 'registration/register.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            if request.POST.get('remember_me'):
                # Stay signed in for two weeks (uses persistent session cookie)
                request.session.set_expiry(60 * 60 * 24 * 14)
            else:
                # Session ends when the browser is closed
                request.session.set_expiry(0)
            return redirect('dashboard')
        else:
            print("Login failed for user:", username)  # Debugging statement
            pass
    return render(request, 'registration/login.html')

def logout_view(request):
    logout(request)
    return redirect('/login')

@login_required
def dashboard(request):
    user = request.user

    # Standards the user has attempted
    attempted_standards = Standard.objects.filter(
        domain__control__assessmentresult__user=user
    ).distinct()

    total_assessments = attempted_standards.count()

    # Overall compliance rate across all results
    all_results = AssessmentResult.objects.filter(user=user)
    total_controls = all_results.count()
    compliant_controls = all_results.filter(status='compliant').count()
    compliance_rate = round((compliant_controls / total_controls) * 100) if total_controls > 0 else 0

    # Pending = standards not yet started
    total_standards = Standard.objects.count()
    pending = total_standards - total_assessments

    return render(request, 'pages/dashboard.html', {
        'total_assessments': total_assessments,
        'compliance_rate': compliance_rate,
        'pending': pending,
        'total_standards': total_standards,
    })