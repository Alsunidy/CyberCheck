"""Derive default keywords from control title/description (Latin + Arabic tokens)."""
from __future__ import annotations

import re

_STOP = frozenset({
    'that', 'with', 'from', 'have', 'this', 'shall', 'must', 'will', 'upon', 'into',
    'such', 'each', 'their', 'based', 'within', 'define', 'implement', 'conduct',
    'establish', 'maintain', 'including', 'appropriate', 'organization', 'organizational',
    'procedures', 'critical', 'systems', 'information', 'periodic', 'formal',
})

# Arabic script blocks (no \p{Arabic} in std re)
_AR_RE = re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]{3,}')


def build_keywords_from_text(title: str, description: str) -> list[str]:
    """
    Build keywords when Control.keywords is empty: English tokens + Arabic tokens from
    title/description so Arabic evidence (PDF/OCR) can match the same control.
    """
    blob = f'{title} {description}'
    out: list[str] = []
    seen: set[str] = set()

    for w in re.findall(r"[A-Za-z][A-Za-z0-9']+", blob):
        lw = w.lower()
        if len(lw) < 4 or lw in _STOP:
            continue
        if lw not in seen:
            seen.add(lw)
            out.append(lw)
        if len(out) >= 8:
            break

    for w in _AR_RE.findall(blob):
        w = w.strip()
        if len(w) < 3 or w in seen:
            continue
        seen.add(w)
        out.append(w)
        if len(out) >= 14:
            break

    return out if out else ['security', 'policy', 'compliance', 'cyber']


_AR_STOP = frozenset({
    'التي', 'الذي', 'الذين', 'اللذين', 'هذا', 'هذه', 'هؤلاء', 'ذلك', 'تلك', 'هناك',
    'من', 'في', 'على', 'عن', 'إلى', 'عند', 'كان', 'كانت', 'يكون', 'قد', 'لا', 'ما', 'مع',
    'أن', 'إن', 'لم', 'لن', 'كل', 'بين', 'غير', 'أيضا', 'أيضاً', 'ذات', 'ذو',
})


def arabic_keyword_candidates_from_evidence(text: str, limit: int = 8) -> list[str]:
    """
    Frequent Arabic tokens from extracted evidence (for fallback scoring when control
    metadata is English but the uploaded proof is Arabic).
    """
    from collections import Counter

    words = [w for w in _AR_RE.findall(text or '') if len(w) >= 4 and w not in _AR_STOP]
    if not words:
        return []
    return [w for w, _ in Counter(words).most_common(limit)]
