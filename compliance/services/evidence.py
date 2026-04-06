"""Evidence file validation, keyword scoring, and assessment result updates."""
from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from compliance.models import AssessmentResult, EvidenceValidationLog

from .extraction import extract_text
from .keywords import arabic_keyword_candidates_from_evidence, build_keywords_from_text

logger = logging.getLogger('compliance.evidence')

MIN_FILE_BYTES = 1024
ALLOWED_EXTENSIONS = frozenset({'.pdf', '.png', '.jpg', '.jpeg', '.docx'})

_AR_CHAR_RANGES = (
    ('\u0600', '\u06ff'),
    ('\u0750', '\u077f'),
    ('\u08a0', '\u08ff'),
)


def _arabic_char_ratio(text: str) -> float:
    if not text:
        return 0.0
    n = len(text)
    ar = 0
    for c in text:
        o = ord(c)
        if any(ord(a) <= o <= ord(b) for a, b in _AR_CHAR_RANGES):
            ar += 1
    return ar / n


def _latin_letter_ratio(text: str) -> float:
    """Share of letters that are A–Z (helps skip Arabic keyword mining on English OCR)."""
    letters = [c for c in text if unicodedata.category(c).startswith('L')]
    if not letters:
        return 0.0
    latin = sum(
        1
        for c in letters
        if ('A' <= c <= 'Z') or ('a' <= c <= 'z')
    )
    return latin / len(letters)


def _merge_keyword_lists(base: list[str], extra: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for k in list(base) + list(extra):
        if not k:
            continue
        sk = str(k).strip()
        if not sk:
            continue
        key = sk.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(sk)
    return out


def validate_evidence_upload(uploaded_file) -> None:
    """Validate an uploaded evidence file before it is saved."""
    name = getattr(uploaded_file, 'name', '') or ''
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            _('Invalid file type. Allowed types: PDF, PNG, JPG, DOCX.'),
        )
    size = getattr(uploaded_file, 'size', None)
    if size is None:
        uploaded_file.seek(0, 2)
        size = uploaded_file.tell()
        uploaded_file.seek(0)
    if size < MIN_FILE_BYTES:
        raise ValidationError(_('File is too small (minimum 1 KB).'))


def validate_stored_evidence_file(field_file) -> None:
    """Validate an on-disk FileField (extension and size)."""
    name = getattr(field_file, 'name', '') or ''
    if not name:
        raise ValidationError(_('Evidence file is missing.'))
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            _('Invalid stored evidence type. Allowed types: PDF, PNG, JPG, DOCX.'),
        )
    try:
        size = field_file.size
    except (OSError, ValueError):
        size = None
    if size is not None and size < MIN_FILE_BYTES:
        raise ValidationError(_('Evidence file is too small (minimum 1 KB).'))


def _keyword_hit(keyword: str, text_lower: str, *, use_word_boundaries: bool) -> bool:
    """
    Match keyword against lowercased document text.

    For Latin single-token keywords, optional word-boundary matching improves precision.
    Phrases (spaces/hyphens) and non-ASCII keywords use substring match.
    """
    if not keyword:
        return False
    if not use_word_boundaries:
        return keyword in text_lower
    # Arabic / mixed scripts: \b is unreliable — substring
    try:
        keyword.encode('ascii')
    except UnicodeEncodeError:
        return keyword in text_lower
    if ' ' in keyword or '-' in keyword:
        return keyword in text_lower
    # Single ASCII token: avoid matching inside longer words (backup vs backuping)
    pattern = rf'(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])'
    return re.search(pattern, text_lower) is not None


def analyze_evidence(
    text: str,
    keywords: list,
    *,
    use_word_boundaries: bool | None = None,
) -> tuple[float, list[str]]:
    """
    Keyword hit rate over normalized keyword list.

    Returns (score 0..1, list of matched keyword strings).
    """
    if not keywords:
        return 0.0, []

    if use_word_boundaries is None:
        use_word_boundaries = getattr(
            settings,
            'EVIDENCE_SCORE_WORD_BOUNDARIES',
            True,
        )

    normalized: list[str] = []
    seen: set[str] = set()
    for k in keywords:
        if k is None:
            continue
        sk = str(k).strip().lower()
        if sk and sk not in seen:
            seen.add(sk)
            normalized.append(sk)

    if not normalized:
        return 0.0, []

    blob = (text or '').lower()
    matched = [
        k for k in normalized
        if _keyword_hit(k, blob, use_word_boundaries=use_word_boundaries)
    ]
    score = len(matched) / len(normalized)
    return score, matched


def review_status_from_score(
    score: float,
    *,
    matched_count: int,
    keyword_total: int,
    text_too_short: bool = False,
) -> str:
    """
    Map score to review_status with extra precision gates.

    - Very short extracted text cannot be approved (unreliable OCR/PDF).
    - When many keywords are configured, require multiple hits for approval.
    """
    min_hits_setting = getattr(settings, 'EVIDENCE_APPROVED_MIN_MATCHES', None)
    if min_hits_setting is not None:
        min_hits_for_approved = max(1, int(min_hits_setting))
    else:
        min_hits_for_approved = 2 if keyword_total >= 3 else 1

    if text_too_short:
        if score >= 0.3:
            return 'partial'
        return 'rejected'

    if score >= 0.7:
        if matched_count < min_hits_for_approved:
            return 'partial'
        return 'approved'
    if score >= 0.3:
        return 'partial'
    return 'rejected'


def _log(result_id: int, message: str, extra: dict | None = None) -> None:
    EvidenceValidationLog.objects.create(
        assessment_result_id=result_id,
        message=message,
        extra=extra or {},
    )


def apply_evidence_validation(
    result: AssessmentResult,
    *,
    compliance_status: str,
) -> None:
    """
    Set ai_score, matched_keywords, and review_status from evidence and control keywords.

    If ``review_status_admin_override`` is True, only ai_score / matched_keywords are updated;
    review_status is left unchanged.

    Policy for no evidence:
    - compliant → review_status rejected (claims compliance without proof)
    - otherwise → pending (avoid double-penalizing non-compliance in the evidence layer)
    """
    override = result.review_status_admin_override
    rid = result.pk

    field = result.evidence_file
    has_file = bool(field and field.name)

    if not has_file:
        result.ai_score = None
        result.matched_keywords = []
        if not override:
            if compliance_status == 'compliant':
                result.review_status = 'rejected'
            else:
                # Non-compliant / partial without evidence: no automated evidence verdict.
                result.review_status = 'pending'
        result.save(
            update_fields=['ai_score', 'matched_keywords', 'review_status'],
        )
        _log(
            rid,
            'no_evidence',
            {'compliance_status': compliance_status, 'override': override},
        )
        return

    try:
        validate_stored_evidence_file(field)
    except ValidationError as exc:
        logger.warning('Stored evidence validation failed: %s', exc)
        result.ai_score = None
        result.matched_keywords = []
        if not override:
            result.review_status = 'pending'
        result.save(
            update_fields=['ai_score', 'matched_keywords', 'review_status'],
        )
        _log(
            rid,
            'validation_failed',
            {'error': '; '.join(exc.messages) if getattr(exc, 'messages', None) else str(exc)},
        )
        return

    try:
        text = extract_text(field)
    except Exception as exc:
        logger.exception('Text extraction failed for assessment result %s', rid)
        result.ai_score = None
        result.matched_keywords = []
        if not override:
            result.review_status = 'pending'
        result.save(
            update_fields=['ai_score', 'matched_keywords', 'review_status'],
        )
        _log(rid, 'extraction_failed', {'error': str(exc)})
        return

    raw_keywords = result.control.keywords or []
    if not raw_keywords:
        keywords = build_keywords_from_text(
            result.control.title,
            result.control.description,
        )
        used_fallback = True
    else:
        keywords = raw_keywords
        used_fallback = False

    stripped = (text or '').strip()
    min_len = int(getattr(settings, 'EVIDENCE_MIN_EXTRACTED_LENGTH', 40))
    text_too_short = len(stripped) < min_len

    keyword_supplement: list[str] = []
    if (
        used_fallback
        and len(stripped) >= 80
        and _arabic_char_ratio(stripped) >= 0.30
        and _latin_letter_ratio(stripped) < 0.45
    ):
        keyword_supplement = arabic_keyword_candidates_from_evidence(stripped, limit=8)
        if keyword_supplement:
            keywords = _merge_keyword_lists(keywords, keyword_supplement)

    # Fallback keywords are auto-guessed: use substring matching for better recall (PDF vs OCR).
    score, matched = analyze_evidence(
        text,
        keywords,
        use_word_boundaries=False if used_fallback else None,
    )

    result.ai_score = score
    result.matched_keywords = matched
    if not override:
        result.review_status = review_status_from_score(
            score,
            matched_count=len(matched),
            keyword_total=len(
                {str(k).strip().lower() for k in keywords if str(k).strip()},
            ),
            text_too_short=text_too_short,
        )
    result.save(
        update_fields=['ai_score', 'matched_keywords', 'review_status'],
    )
    _log(
        rid,
        'scored',
        {
            'ai_score': score,
            'matched_count': len(matched),
            'keyword_count': len({str(k).strip().lower() for k in keywords if str(k).strip()}),
            'override': override,
            'keywords_fallback': used_fallback,
            'keyword_supplement_count': len(keyword_supplement),
            'text_too_short': text_too_short,
            'extracted_length': len(stripped),
        },
    )
