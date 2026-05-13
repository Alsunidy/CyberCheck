"""
AI audit utilities for CyberCheck.

Requires:
  pip install openai pdfplumber
  OPENAI_API_KEY set in Django settings or environment.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pdfplumber
from google import genai
from django.conf import settings
import json
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PDF text extraction
# ---------------------------------------------------------------------------

def extract_text_from_pdf(file_path: str | Path) -> str:
    """
    Extract all text from a PDF file.

    Handles pages that return None from pdfplumber (scanned/image-only pages)
    without crashing, and strips excessive whitespace.
    """
    text_parts: list[str] = []
    with pdfplumber.open(str(file_path)) as pdf:
        for i, page in enumerate(pdf.pages):
            try:
                page_text = page.extract_text()
            except Exception as exc:
                logger.warning("Could not extract text from page %d: %s", i + 1, exc)
                page_text = None
            if page_text:  # BUG FIX: was concatenating None → crash
                text_parts.append(page_text.strip())
    return "\n".join(text_parts)


# ---------------------------------------------------------------------------
# AI audit
# ---------------------------------------------------------------------------

# Valid compliance_level values accepted by EvidenceValidationLog
_VALID_COMPLIANCE_LEVELS = {"FC", "SC", "MC", "NC", "NA"}
_VALID_RESULT_CATEGORIES = {"C", "R"}


def run_ai_audit(evidence_path: str | Path, standard_text: str) -> dict:
    """
    Run an AI compliance audit on a PDF evidence file against a standard description.

    Returns a dict with keys:
        quoted_standard, analysis, recommendations,
        compliance_level (FC/SC/MC/NC/NA), justification, result_category (C/R)

    Raises:
        ValueError  – if OPENAI_API_KEY is not configured
        RuntimeError – if the AI response cannot be parsed
    """
    import openai  # imported here so the module loads even without openai installed

    api_key = getattr(settings, "OPENAI_API_KEY", None) or ""
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY is not set in Django settings. "
            "Add it to cybercheck/settings.py or as an environment variable."
        )

    client = openai.OpenAI(api_key=api_key)

    # BUG FIX: was crashing when page.extract_text() returned None
    evidence_text = extract_text_from_pdf(evidence_path)

    if not evidence_text.strip():
        return {
            "quoted_standard": "",
            "analysis": "Evidence file is empty or unreadable (likely scanned PDF)",
            "recommendations": "Convert PDF to text or use OCR",
            "compliance_level": "NA",
            "justification": "No readable text extracted",
            "result_category": "R",
        }

    prompt = f"""You are a cybersecurity compliance auditor.

Evaluate the following evidence document against the provided compliance standard requirement.

STANDARD REQUIREMENT:
{standard_text}

EVIDENCE DOCUMENT TEXT:
{evidence_text or "(No text could be extracted from this file.)"}

Return ONLY a valid JSON object with these EXACT keys (no extra keys, no markdown):
{{
    "quoted_standard": "<relevant sentence(s) from the standard requirement>",
    "analysis": "<your independent evaluation of how the evidence meets or fails the requirement>",
    "recommendations": "<specific, actionable steps to improve compliance>",
    "compliance_level": "<one of: FC, SC, MC, NC, NA>",
    "justification": "<brief reason for the compliance level you chose>",
    "result_category": "<C for Commendation if fully compliant, R for Recommendation otherwise>"
}}

compliance_level key:
  FC = Full Compliance
  SC = Substantial Compliance
  MC = Minimal Compliance
  NC = Non-Compliance
  NA = Not Applicable
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        raw = response.choices[0].message.content
    except openai.OpenAIError as exc:
        logger.error("OpenAI API call failed: %s", exc)
        raise

    logger.info("RAW AI RESPONSE: %s", raw)

    try:
        data = json.loads(raw)
    except Exception:
        logger.error("AI returned invalid JSON: %s", raw)
        return {
            "quoted_standard": "",
            "analysis": "AI returned invalid JSON response",
            "recommendations": "",
            "compliance_level": "NA",
            "justification": "Parsing failed",
            "result_category": "R",
        }


def run_gemini_audit(evidence_text: str, standard_text: str) -> dict:
    import json
    import logging
    from django.conf import settings
    from google import genai

    logger = logging.getLogger(__name__)

    try:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        prompt = f"""
You are a cybersecurity compliance auditor.

STANDARD:
{standard_text}

EVIDENCE:
{evidence_text}

Return ONLY valid JSON with EXACT keys:
{{
"quoted_standard": "",
"analysis": "",
"recommendations": "",
"compliance_level": "FC|SC|MC|NC|NA",
"justification": "",
"result_category": "C|R"
}}
"""

        response = client.models.generate_content(
            model="models/gemini-flash-latest",
            contents=prompt
        )

        raw = ""

        try:
            raw = response.candidates[0].content.parts[0].text.strip()
        except Exception:
            raw = getattr(response, "text", "").strip()

        logger.info("GEMINI RAW RESPONSE: %s", raw)

        if not raw:
            raise ValueError("Empty response from Gemini")

        # ---------------------------
        # FIX: safe JSON parsing
        # ---------------------------
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.error("Invalid JSON from Gemini: %s", raw)
            return {
                "quoted_standard": "",
                "analysis": "AI returned invalid JSON",
                "recommendations": "",
                "compliance_level": "NA",
                "justification": "Parsing failed",
                "result_category": "R",
            }

        # ---------------------------
        # FINAL SAFE RETURN
        # ---------------------------
        return {
            "quoted_standard": data.get("quoted_standard", ""),
            "analysis": data.get("analysis", ""),
            "recommendations": data.get("recommendations", ""),
            "compliance_level": data.get("compliance_level", "NA"),
            "justification": data.get("justification", ""),
            "result_category": data.get("result_category", "R"),
        }

    except Exception as e:
        logger.error("Gemini audit failed: %s", e)

        return {
            "quoted_standard": "",
            "analysis": "AI failed to generate response",
            "recommendations": "",
            "compliance_level": "NA",
            "justification": str(e),
            "result_category": "R",
        }