import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import (
    AssessmentRun,
    AssessmentResult,
    Control,
    Domain,
    Standard,
)
from .services.evidence import apply_evidence_validation, validate_evidence_upload

logger = logging.getLogger(__name__)

ALLOWED_ASSESSMENT_STATUS = frozenset(dict(AssessmentResult.STATUS_CHOICES))


def _assessment_page_context(standard, user, run):
    domains = Domain.objects.filter(standard=standard)
    controls = Control.objects.filter(domain__standard=standard)
    previous = AssessmentResult.objects.filter(
        assessment_run=run,
        control__in=controls,
    )
    previous_map = {r.control_id: r for r in previous}
    return {
        'standard': standard,
        'assessment_run': run,
        'domains': domains,
        'previous_map': previous_map,
    }


@login_required
def standards_list(request):
    standards = Standard.objects.all()
    return render(request, 'compliance/standards.html', {'standards': standards})


@login_required
def standard_assessment_runs(request, standard_id):
    standard = get_object_or_404(Standard, id=standard_id)
    runs = AssessmentRun.objects.filter(
        standard=standard,
        user=request.user,
    ).order_by('-updated_at')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create':
            title = (request.POST.get('title') or '').strip()
            if not title:
                title = _('Assessment') + ' ' + timezone.now().strftime('%Y-%m-%d %H:%M')
            run = AssessmentRun.objects.create(
                user=request.user,
                standard=standard,
                title=title,
            )
            messages.success(request, _('New assessment created. You can fill it in below.'))
            return redirect('assessment', standard_id=standard.id, run_id=run.id)
        if action == 'delete':
            rid = request.POST.get('run_id')
            if rid and str(rid).isdigit():
                deleted_count, _details = AssessmentRun.objects.filter(
                    id=int(rid),
                    standard=standard,
                    user=request.user,
                ).delete()
                if deleted_count:
                    messages.success(request, _('Assessment removed.'))
            return redirect('standard_assessment_runs', standard_id=standard.id)

    return render(
        request,
        'compliance/standard_assessment_runs.html',
        {'standard': standard, 'runs': runs},
    )


@login_required
def reports_hub(request):
    standards = (
        Standard.objects.annotate(
            runs_count=Count(
                'assessment_runs',
                filter=Q(assessment_runs__user=request.user),
                distinct=True,
            ),
        )
        .filter(runs_count__gt=0)
        .order_by('name')
    )
    return render(request, 'compliance/reports.html', {'standards': standards})


@login_required
def assessment(request, standard_id, run_id):
    standard = get_object_or_404(Standard, id=standard_id)
    run = get_object_or_404(
        AssessmentRun,
        id=run_id,
        standard=standard,
        user=request.user,
    )

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
                    _assessment_page_context(standard, request.user, run),
                )
        upload_errors: list[tuple[int, str]] = []
        for control in controls:
            report = request.FILES.get(f'report_{control.id}')
            evidence = request.FILES.get(f'evidence_{control.id}')
            for label, uploaded in (('report', report), ('evidence', evidence)):
                if not uploaded:
                    continue
                try:
                    validate_evidence_upload(uploaded)
                except ValidationError as exc:
                    for msg in exc.messages:
                        upload_errors.append((control.id, label, str(msg)))

        if upload_errors:
            for control_id, field_label, err in upload_errors:
                messages.error(
                    request,
                    _('Control %(cid)s — %(field)s: %(err)s')
                    % {'cid': control_id, 'field': field_label, 'err': err},
                )
            return render(
                request,
                'compliance/assessment.html',
                _assessment_page_context(standard, request.user, run),
            )

        try:
            with transaction.atomic():
                for control in controls:
                    status = request.POST.get(f'status_{control.id}')
                    notes = request.POST.get(f'notes_{control.id}', '')
                    report = request.FILES.get(f'report_{control.id}')
                    evidence = request.FILES.get(f'evidence_{control.id}')
                    defaults = {
                        'user': request.user,
                        'status': status,
                        'notes': notes,
                    }
                    if report:
                        defaults['report_file'] = report
                    if evidence:
                        defaults['evidence_file'] = evidence
                    result, _created = AssessmentResult.objects.update_or_create(
                        assessment_run=run,
                        control=control,
                        defaults=defaults,
                    )
                    apply_evidence_validation(
                        result,
                        compliance_status=status,
                    )
                AssessmentRun.objects.filter(pk=run.pk).update(updated_at=timezone.now())
        except Exception:
            logger.exception('Assessment save failed')
            messages.error(
                request,
                _('We could not save your assessment. Please try again in a moment.'),
            )
            return render(
                request,
                'compliance/assessment.html',
                _assessment_page_context(standard, request.user, run),
            )
        messages.success(
            request,
            _('Assessment saved successfully. Your results are summarized below.'),
        )
        return redirect('results', standard_id=standard.id, run_id=run.id)

    return render(
        request,
        'compliance/assessment.html',
        _assessment_page_context(standard, request.user, run),
    )


def _results_context(standard, user, run):
    domains = Domain.objects.filter(standard=standard)
    controls = Control.objects.filter(domain__standard=standard)
    assessment_results = AssessmentResult.objects.filter(
        assessment_run=run,
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
            'control_results': domain_results,
        })
    return {
        'standard': standard,
        'assessment_run': run,
        'domains': domain_data,
        'score': score,
        'assessed_total': total,
        'compliant_count': compliant,
        'partial_count': partial,
        'non_compliant_count': non_compliant,
    }


@login_required
def results(request, standard_id, run_id):
    standard = get_object_or_404(Standard, id=standard_id)
    run = get_object_or_404(
        AssessmentRun,
        id=run_id,
        standard=standard,
        user=request.user,
    )
    return render(
        request,
        'compliance/results.html',
        _results_context(standard, request.user, run),
    )


@login_required
def results_print(request, standard_id, run_id):
    standard = get_object_or_404(Standard, id=standard_id)
    run = get_object_or_404(
        AssessmentRun,
        id=run_id,
        standard=standard,
        user=request.user,
    )
    ctx = _results_context(standard, request.user, run)
    ctx['generated_at'] = timezone.now()
    return render(request, 'compliance/results_print.html', ctx)
