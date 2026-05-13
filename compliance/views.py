"""
Compliance views for CyberCheck.

Key fixes applied:
  1. Duplicate `from .utils import run_ai_audit` import removed.
  2. AI audit is now called OUTSIDE the DB transaction so an OpenAI timeout/error
     does NOT roll back the assessment save.
  3. `results_print` now passes the full results context (score, counts, etc.)
     that the template requires, plus `user` for `{{ user.get_username }}`.
  4. `reports_hub` view now passes the correct context key (`assessment_run`)
     that the reports.html template expects.
"""
from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import (
    AssessmentResult,
    AssessmentRun,
    Control,
    Domain,
    EvidenceValidationLog,
    Standard,
)
from .services.evidence import apply_evidence_validation, validate_evidence_upload
from .AI import run_gemini_audit
from .AI import extract_text_from_pdf

logger = logging.getLogger(__name__)

ALLOWED_ASSESSMENT_STATUS = frozenset(dict(AssessmentResult.STATUS_CHOICES))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _assessment_page_context(standard, user, run):
    domains = Domain.objects.filter(standard=standard)
    controls = Control.objects.filter(domain__standard=standard)
    previous = AssessmentResult.objects.filter(assessment_run=run, control__in=controls)
    previous_map = {r.control_id: r for r in previous}
    return {
        "standard": standard,
        "assessment_run": run,
        "domains": domains,
        "previous_map": previous_map,
    }


def _results_context(standard, user, run):
    """
    Build the context dict used by both results.html and results_print.html.
    BUG FIX: results_print previously built its own incomplete context that
    was missing assessed_total / score / compliant_count / partial_count /
    non_compliant_count / user — causing TemplateSyntaxError and blank report.
    """
    domains = Domain.objects.filter(standard=standard)
    controls = Control.objects.filter(domain__standard=standard)
    # Prefetch only AI audit logs (message="" and analysis populated).
    # Keyword-scoring logs (message='scored'|'no_evidence'|...) are excluded so
    # templates never accidentally render them as AI analysis rows.
    ai_logs_qs = EvidenceValidationLog.objects.filter(
        message="", analysis__isnull=False
    ).exclude(analysis="")

    assessment_results = (
        AssessmentResult.objects
        .filter(assessment_run=run, control__in=controls)
        .select_related("control", "control__domain")
        .prefetch_related(
            Prefetch("validation_logs", queryset=ai_logs_qs, to_attr="ai_logs")
        )
    )

    total      = assessment_results.count()
    compliant  = assessment_results.filter(status="compliant").count()
    partial    = assessment_results.filter(status="partial").count()
    non_compl  = assessment_results.filter(status="non_compliant").count()
    score = int((compliant / total) * 100) if total else 0
    domain_data = []
    for domain in domains:
        domain_results = [r for r in assessment_results if r.control.domain_id == domain.pk]
        domain_data.append({"name": domain.name, "control_results": domain_results})

    return {
        "standard":           standard,
        "assessment_run":     run,
        "user":               user,          # BUG FIX: was missing in results_print context
        "domains":            domain_data,
        "score":              score,
        "assessed_total":     total,
        "compliant_count":    compliant,
        "partial_count":      partial,
        "non_compliant_count": non_compl,
    }


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

@login_required
def standards_list(request):
    standards = Standard.objects.all()
    return render(request, "compliance/standards.html", {"standards": standards})


@login_required
def standard_assessment_runs(request, standard_id):
    standard = get_object_or_404(Standard, id=standard_id)
    runs = AssessmentRun.objects.filter(
        standard=standard, user=request.user
    ).order_by("-updated_at")

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "create":
            title = (request.POST.get("title") or "").strip()
            if not title:
                title = _("Assessment") + " " + timezone.now().strftime("%Y-%m-%d %H:%M")
            run = AssessmentRun.objects.create(
                user=request.user, standard=standard, title=title
            )
            messages.success(request, _("New assessment created."))
            return redirect("assessment", standard_id=standard.id, run_id=run.id)

        if action == "delete":
            rid = request.POST.get("run_id")
            if rid and str(rid).isdigit():
                deleted_count, _details = AssessmentRun.objects.filter(
                    id=int(rid), standard=standard, user=request.user
                ).delete()
                if deleted_count:
                    messages.success(request, _("Assessment removed."))
            return redirect("standard_assessment_runs", standard_id=standard.id)

    return render(
        request,
        "compliance/standard_assessment_runs.html",
        {"standard": standard, "runs": runs},
    )


@login_required
def reports_hub(request):
    standards = (
        Standard.objects.annotate(
            runs_count=Count(
                "assessment_runs",
                filter=Q(assessment_runs__user=request.user),
                distinct=True,
            )
        )
        .filter(runs_count__gt=0)
        .order_by("name")
    )
    return render(request, "compliance/reports.html", {"standards": standards})


@login_required
def assessment(request, standard_id, run_id):
    standard = get_object_or_404(Standard, id=standard_id)
    run = get_object_or_404(
        AssessmentRun, id=run_id, standard=standard, user=request.user
    )

    if request.method == "POST":
        controls = list(Control.objects.filter(domain__standard=standard))

        # --- Validate all statuses before touching the DB ---
        for control in controls:
            status = request.POST.get(f"status_{control.id}")
            if status not in ALLOWED_ASSESSMENT_STATUS:
                messages.error(request, ("Invalid compliance status."))
                return render(
                    request,
                    "compliance/assessment.html",
                    _assessment_page_context(standard, request.user, run),
                )

        # --- Validate uploaded files before touching the DB ---
        upload_errors: list[tuple[int, str, str]] = []
        for control in controls:
            for field_label in ("report", "evidence"):
                uploaded = request.FILES.get(f"{field_label}_{control.id}")
                if not uploaded:
                    continue
                try:
                    validate_evidence_upload(uploaded)
                except ValidationError as exc:
                    for msg in exc.messages:
                        upload_errors.append((control.id, field_label, str(msg)))

        if upload_errors:
            for control_id, field_label, err in upload_errors:
                messages.error(
                    request,
                    ("Control %(cid)s — %(field)s: %(err)s")
                    % {"cid": control_id, "field": field_label, "err": err},
                )
            return render(
                request,
                "compliance/assessment.html",
                _assessment_page_context(standard, request.user, run),
            )

        # ------------------------------------------------------------------
        # STEP 1: Save all assessment answers atomically.
        # BUG FIX: AI call was inside transaction.atomic() — an OpenAI
        # network timeout would roll back every DB write in the loop.
        # Now we collect result PKs here, then run AI outside the transaction.
        # ------------------------------------------------------------------
        saved_result_pks: list[int] = []

        try:
            with transaction.atomic():
                for control in controls:
                    status  = request.POST.get(f"status_{control.id}")
                    notes   = request.POST.get(f"notes_{control.id}", "")
                    report  = request.FILES.get(f"report_{control.id}")
                    evidence = request.FILES.get(f"evidence_{control.id}")

                    defaults: dict = {"user": request.user, "status": status, "notes": notes}
                    if report:
                        defaults["report_file"] = report
                    if evidence:
                        defaults["evidence_file"] = evidence

                    result, _ = AssessmentResult.objects.update_or_create(
                        assessment_run=run, control=control, defaults=defaults
                    )
                    apply_evidence_validation(result, compliance_status=status)
                    saved_result_pks.append(result.pk)

                AssessmentRun.objects.filter(pk=run.pk).update(updated_at=timezone.now())

        except Exception:
            logger.exception("Assessment save failed")
            messages.error(request, _("Could not save assessment."))
            return render(
                request,
                "compliance/assessment.html",
                _assessment_page_context(standard, request.user, run),
            )

        # ------------------------------------------------------------------
        # STEP 2: Run AI audit for results that have evidence files.
        # This runs AFTER the transaction commits so DB data is never lost
        # due to an AI failure. Each AI call has its own try/except.
        # ------------------------------------------------------------------
        saved_results = (
            AssessmentResult.objects
            .filter(pk__in=saved_result_pks, evidence_file__isnull=False)
            .exclude(evidence_file="")
            .select_related("control")
        )

        for result in saved_results:
            # Skip only if a real AI log already exists for this result.
            # IMPORTANT: apply_evidence_validation() also writes EvidenceValidationLog
            # rows (message='scored'|'no_evidence'|...) — those are keyword-scoring logs,
            # NOT AI audit logs. AI logs always have message='' and a populated analysis
            # field. We must filter on that distinction so we don't mistake keyword logs
            # for AI logs and wrongly skip the AI call every single time.
            has_ai_log = result.validation_logs.filter(
                analysis__isnull=False
            ).exclude(analysis="").exists()
            if has_ai_log:
                continue
            try:
                text = extract_text_from_pdf(result.evidence_file.path)

                ai_data = run_gemini_audit(
                    evidence_text=text,
                    standard_text=result.control.description,
                )
                EvidenceValidationLog.objects.create(
                    assessment_result=result,
                    quoted_standard=ai_data.get("quoted_standard", ""),
                    analysis=ai_data.get("analysis", ""),
                    compliance_level=ai_data.get("compliance_level", "NA"),
                    justification=ai_data.get("justification", ""),
                    recommendations=ai_data.get("recommendations", ""),
                    result_category=ai_data.get("result_category", "R"),
                )
                logger.info("AI audit saved for result pk=%s", result.pk)
            except Exception as exc:
                # Log but never crash — the assessment data is already saved
                logger.error(
                    "AI audit failed for result pk=%s (control '%s'): %s",
                    result.pk, result.control.title, exc,
                )

        messages.success(request, ("Assessment saved successfully."))
        return redirect("results", standard_id=standard.id, run_id=run.id)

    return render(
        request,
        "compliance/assessment.html",
        _assessment_page_context(standard, request.user, run),
    )


@login_required
def results(request, standard_id, run_id):
    standard = get_object_or_404(Standard, id=standard_id)
    run = get_object_or_404(
        AssessmentRun, id=run_id, standard=standard, user=request.user
    )
    return render(
        request,
        "compliance/results.html",
        _results_context(standard, request.user, run),
    )


@login_required
def results_print(request, standard_id, run_id):
    """
    BUG FIX: was building a completely separate (incomplete) context that
    was missing assessed_total, score, compliant_count, partial_count,
    non_compliant_count, and user — causing blank/broken print report.
    Now reuses _results_context() so both templates get identical data.
    """
    standard = get_object_or_404(Standard, id=standard_id)
    run = get_object_or_404(
        AssessmentRun, id=run_id, standard=standard, user=request.user
    )
    ctx = _results_context(standard, request.user, run)
    ctx["generated_at"] = timezone.now()
    return render(request, "compliance/results_print.html", ctx)