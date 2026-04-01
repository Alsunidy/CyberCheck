from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.utils.translation import gettext as _
from .models import Standard, Domain, Control, AssessmentResult


ALLOWED_ASSESSMENT_STATUS = frozenset(dict(AssessmentResult.STATUS_CHOICES))


def _assessment_page_context(standard, user):
    domains = Domain.objects.filter(standard=standard)
    controls = Control.objects.filter(domain__standard=standard)
    previous = AssessmentResult.objects.filter(
        user=user,
        control__in=controls,
    )
    previous_map = {r.control_id: r for r in previous}
    return {
        'standard': standard,
        'domains': domains,
        'previous_map': previous_map,
    }


@login_required
def standards_list(request):
    standards = Standard.objects.all()
    return render(request, 'compliance/standards.html', {'standards': standards})


@login_required
def reports_hub(request):
    standards = Standard.objects.annotate(
        saved_results_count=Count(
            'domain__control__assessmentresult',
            filter=Q(domain__control__assessmentresult__user=request.user),
            distinct=True,
        )
    ).order_by('name')
    return render(request, 'compliance/reports.html', {'standards': standards})

@login_required
def assessment(request, standard_id):
    standard = get_object_or_404(Standard, id=standard_id)

    if request.method == 'POST':
        controls = list(Control.objects.filter(domain__standard=standard))
        for control in controls:
            status = request.POST.get(f'status_{control.id}')
            if status not in ALLOWED_ASSESSMENT_STATUS:
                messages.error(
                    request,
                    _('One or more compliance statuses were missing or invalid. Please review the form and try again.'),
                )
                return render(
                    request,
                    'compliance/assessment.html',
                    _assessment_page_context(standard, request.user),
                )
        try:
            with transaction.atomic():
                for control in controls:
                    status = request.POST.get(f'status_{control.id}')
                    notes = request.POST.get(f'notes_{control.id}', '')
                    evidence = request.FILES.get(f'evidence_{control.id}')
                    defaults = {
                        'status': status,
                        'notes': notes,
                    }
                    if evidence:
                        defaults['evidence_file'] = evidence
                    AssessmentResult.objects.update_or_create(
                        control=control,
                        user=request.user,
                        defaults=defaults,
                    )
        except Exception:
            messages.error(
                request,
                _('We could not save your assessment. Please try again in a moment.'),
            )
            return render(
                request,
                'compliance/assessment.html',
                _assessment_page_context(standard, request.user),
            )
        messages.success(
            request,
            _('Assessment saved successfully. Your results are summarized below.'),
        )
        return redirect('results', standard_id=standard.id)

    return render(
        request,
        'compliance/assessment.html',
        _assessment_page_context(standard, request.user),
    )

def _results_context(standard, user):
    domains = Domain.objects.filter(standard=standard)
    controls = Control.objects.filter(domain__standard=standard)
    assessment_results = AssessmentResult.objects.filter(
        user=user,
        control__in=controls,
    )
    total = assessment_results.count()
    compliant = assessment_results.filter(status='compliant').count()
    partial = assessment_results.filter(status='partial').count()
    non_compliant = assessment_results.filter(status='non_compliant').count()
    score = round((compliant / total) * 100) if total > 0 else 0
    domain_data = []
    for domain in domains:
        domain_results = assessment_results.filter(control__domain=domain)
        domain_data.append({
            'name': domain.name,
            'results': domain_results,
        })
    return {
        'standard': standard,
        'domains': domain_data,
        'score': score,
        'assessed_total': total,
        'compliant_count': compliant,
        'partial_count': partial,
        'non_compliant_count': non_compliant,
    }


@login_required
def results(request, standard_id):
    standard = get_object_or_404(Standard, id=standard_id)
    return render(request, 'compliance/results.html', _results_context(standard, request.user))


@login_required
def results_print(request, standard_id):
    standard = get_object_or_404(Standard, id=standard_id)
    ctx = _results_context(standard, request.user)
    ctx['generated_at'] = timezone.now()
    return render(request, 'compliance/results_print.html', ctx)