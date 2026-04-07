from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Max
from compliance.models import Standard, AssessmentResult, AssessmentRun

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
            request.session.set_expiry(60 * 60 * 24 * 14 if request.POST.get('remember_me') else 0)
            return redirect('dashboard')
    return render(request, 'registration/login.html')

def logout_view(request):
    logout(request)
    return redirect('/login')

@login_required
def dashboard(request):
    user = request.user

    # Fetch standards and calculate progress based on the user's latest AssessmentRun per standard
    standards_data = Standard.objects.annotate(
        total_cnt=Count('domain__control', distinct=True),
        # Count how many unique controls the user has EVER answered for this standard
        answered_cnt=Count(
            'assessment_runs__results__control',
            filter=Q(assessment_runs__user=user),
            distinct=True
        )
    )

    # Summary Card Logic
    total_standards = Standard.objects.count()
    completed_count = 0
    pending_count = 0

    for s in standards_data:
        if s.total_cnt > 0:
            if s.answered_cnt >= s.total_cnt:
                completed_count += 1
            elif s.answered_cnt > 0:
                pending_count += 1

    # Overall Compliance Rate (Global across all user results)
    results = AssessmentResult.objects.filter(user=user)
    total_ans = results.count()
    compliant_ans = results.filter(status='compliant').count()
    compliance_rate = round((compliant_ans / total_ans) * 100) if total_ans > 0 else 0

    context = {
        'total_standards': total_standards,
        'completed_count': completed_count,
        'pending_count': pending_count,
        'compliance_rate': compliance_rate,
        'all_assessments': standards_data,
    }
    return render(request, 'pages/dashboard.html', context)