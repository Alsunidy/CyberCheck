from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Standard, Domain, Control, AssessmentResult

@login_required
def standards_list(request):
    standards = Standard.objects.all()
    return render(request, 'compliance/standards.html', {'standards': standards})

@login_required
def assessment(request, standard_id):
    standard = get_object_or_404(Standard, id=standard_id)
    domains = Domain.objects.filter(standard=standard)

    if request.method == 'POST':
        controls = Control.objects.filter(domain__standard=standard)
        for control in controls:
            status = request.POST.get(f'status_{control.id}')
            notes = request.POST.get(f'notes_{control.id}', '')
            evidence = request.FILES.get(f'evidence_{control.id}')
            AssessmentResult.objects.update_or_create(
                control=control,
                user=request.user,
                defaults={
                    'status': status,
                    'notes': notes,
                    'evidence_file': evidence,
                }
            )
        return redirect(f'/results/{standard.id}')

    return render(request, 'compliance/assessment.html', {
        'standard': standard,
        'domains': domains,
    })

@login_required
def results(request, standard_id):
    standard = get_object_or_404(Standard, id=standard_id)
    domains = Domain.objects.filter(standard=standard)
    controls = Control.objects.filter(domain__standard=standard)
    assessment_results = AssessmentResult.objects.filter(
        user=request.user,
        control__in=controls
    )

    total = assessment_results.count()
    compliant = assessment_results.filter(status='compliant').count()
    score = round((compliant / total) * 100) if total > 0 else 0

    domain_data = []
    for domain in domains:
        domain_results = assessment_results.filter(control__domain=domain)
        domain_data.append({
            'name': domain.name,
            'results': domain_results,
        })

    return render(request, 'compliance/results.html', {
        'standard': standard,
        'domains': domain_data,
        'score': score,
    })