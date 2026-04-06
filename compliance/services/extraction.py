"""Extract plain text from evidence files (PDF, DOCX, images via OCR)."""
from __future__ import annotations

import logging
import os
import shutil
from io import BytesIO
from pathlib import Path

from django.conf import settings

logger = logging.getLogger('compliance.evidence')

# Typical Windows installer paths (UB Mannheim / official builds)
_TESSERACT_WINDOWS_PATHS = (
    r'C:\Program Files\Tesseract-OCR\tesseract.exe',
    r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
)


def _iter_windows_tesseract_paths() -> list[Path]:
    out: list[Path] = []
    for p in _TESSERACT_WINDOWS_PATHS:
        out.append(Path(p))
    local = os.environ.get('LOCALAPPDATA', '')
    if local:
        out.append(Path(local) / 'Programs' / 'Tesseract-OCR' / 'tesseract.exe')
    prog = os.environ.get('ProgramFiles', '')
    if prog:
        out.append(Path(prog) / 'Tesseract-OCR' / 'tesseract.exe')
    pf86 = os.environ.get('ProgramFiles(x86)', '')
    if pf86:
        out.append(Path(pf86) / 'Tesseract-OCR' / 'tesseract.exe')
    return out


def _configure_tesseract_executable() -> str | None:
    """
    Point pytesseract at tesseract. Returns the executable path used, or None.

    Order: Django settings, TESSERACT_CMD env, PATH (shutil.which), then common Windows paths.
    """
    import pytesseract

    cmd = (
        getattr(settings, 'TESSERACT_CMD', None)
        or os.environ.get('TESSERACT_CMD', '')
        or ''
    ).strip()
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd
        return cmd

    which = shutil.which('tesseract')
    if which:
        pytesseract.pytesseract.tesseract_cmd = which
        logger.info('Tesseract on PATH: %s', which)
        return which

    if os.name == 'nt':
        for path in _iter_windows_tesseract_paths():
            if path.is_file():
                resolved = str(path.resolve())
                pytesseract.pytesseract.tesseract_cmd = resolved
                logger.info('Tesseract found at %s', resolved)
                return resolved

    return None


def _ensure_tessdata_prefix(tesseract_exe: str) -> None:
    """
    Set TESSDATA_PREFIX so Tesseract finds eng.traineddata (common Windows portable issue).

    Uses settings.TESSDATA_PREFIX / env if set; otherwise ``<tesseract_dir>/tessdata`` when present.
    """
    configured = (getattr(settings, 'TESSDATA_PREFIX', None) or '').strip()
    if configured:
        os.environ['TESSDATA_PREFIX'] = configured.rstrip('/\\')
        return

    env_existing = (os.environ.get('TESSDATA_PREFIX') or '').strip()
    exe_path = Path(tesseract_exe).resolve()
    tessdata = exe_path.parent / 'tessdata'
    if not tessdata.is_dir():
        if env_existing:
            return
        logger.warning(
            'No tessdata folder next to Tesseract (%s). Install language data or set TESSDATA_PREFIX.',
            exe_path.parent,
        )
        return

    # Prefer auto path when eng data exists; fixes broken or missing env on Windows installers.
    eng = tessdata / 'eng.traineddata'
    if env_existing and Path(env_existing, 'eng.traineddata').is_file():
        return
    os.environ['TESSDATA_PREFIX'] = str(tessdata)
    if not eng.is_file():
        logger.warning(
            'Tesseract tessdata folder has no eng.traineddata (%s). '
            'Re-run the installer including English, or download traineddata from GitHub tesseract-ocr/tessdata.',
            eng,
        )


def _get_pdf_reader():
    """Prefer ``pypdf`` (PyPI: pypdf); fall back to legacy ``PyPDF2`` if installed."""
    try:
        from pypdf import PdfReader
        return PdfReader
    except ImportError:
        pass
    try:
        from PyPDF2 import PdfReader
        return PdfReader
    except ImportError as exc:
        raise ImportError(
            'PDF evidence needs the "pypdf" package. In the same Python environment '
            'you use for `python manage.py runserver`, run:\n'
            '  python -m pip install pypdf\n'
            'or from the CyberCheck project folder:\n'
            '  python -m pip install -r requirements.txt',
        ) from exc


def _suffix(name: str) -> str:
    if not name:
        return ''
    return Path(name).suffix.lower()


def _prepare_ocr_image_variants(image) -> list:
    """Build RGB/grayscale (and upscaled) variants for more reliable Tesseract reads."""
    from PIL import Image

    variants: list[Image.Image] = []
    img = image.copy()

    if img.mode == 'P':
        img = img.convert('RGBA')

    if img.mode == 'RGBA':
        background = Image.new('RGB', img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        img = background
    elif img.mode == 'LA':
        background = Image.new('RGB', img.size, (255, 255, 255))
        l_ch, a_ch = img.split()
        gray_rgb = Image.merge('RGB', (l_ch, l_ch, l_ch))
        background.paste(gray_rgb, mask=a_ch)
        img = background
    elif img.mode not in ('RGB', 'L'):
        img = img.convert('RGB')

    rgb = img if img.mode == 'RGB' else img.convert('RGB')
    gray = rgb.convert('L')
    variants.append(rgb)
    variants.append(gray)

    w, h = rgb.size
    longest = max(w, h)
    if longest < 600:
        scale = 900 / longest
        nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
        try:
            resample = Image.Resampling.LANCZOS
        except AttributeError:
            resample = Image.LANCZOS
        variants.append(rgb.resize((nw, nh), resample))
        variants.append(gray.resize((nw, nh), resample))

    return variants


def _parse_tesseract_lang_list(raw: str) -> list[str]:
    return [p.strip() for p in (raw or '').replace(',', ' ').split() if p.strip()]


def _ocr_try_langs_on_variants(variants, langs: list[str], pytesseract_module) -> str:
    """Return first non-empty OCR result for given language list (tried in order)."""
    from pytesseract import TesseractError

    psm_modes = ('6', '3', '11', '4', '13')
    for variant in variants:
        for lang in langs:
            for psm in psm_modes:
                config = f'--oem 3 --psm {psm}'
                try:
                    text = pytesseract_module.image_to_string(
                        variant,
                        lang=lang,
                        config=config,
                    ) or ''
                except TesseractError:
                    continue
                stripped = text.strip()
                if stripped:
                    logger.info(
                        'OCR extracted %s chars (lang=%s psm=%s)',
                        len(stripped),
                        lang,
                        psm,
                    )
                    return text
    return ''


def _ocr_image_to_string(image, pytesseract_module) -> str:
    """
    Run Tesseract with preprocessing and multiple PSM attempts.

    Uses TESSERACT_OCR_LANG first for all variants; only if that yields no text,
    tries TESSERACT_OCR_FALLBACK_LANGS (e.g. ara+eng). Avoids mis-reading English
    images with Arabic models when eng would work on a later PSM/variant.
    """
    variants = _prepare_ocr_image_variants(image)
    primary = getattr(settings, 'TESSERACT_OCR_LANG', 'eng') or 'eng'
    fallbacks_raw = getattr(settings, 'TESSERACT_OCR_FALLBACK_LANGS', '') or ''

    text = _ocr_try_langs_on_variants(variants, [primary], pytesseract_module)
    if text.strip():
        return text

    extra = [x for x in _parse_tesseract_lang_list(fallbacks_raw) if x != primary]
    if extra:
        text = _ocr_try_langs_on_variants(variants, extra, pytesseract_module)
        if text.strip():
            return text

    logger.warning(
        'OCR returned no text after all variants. Try a higher-resolution image, '
        'clearer contrast, PDF instead of photo, or set TESSERACT_OCR_LANG / '
        'TESSERACT_OCR_FALLBACK_LANGS (e.g. ara+eng for Arabic documents).'
    )
    return ''


def extract_text(file, filename: str | None = None) -> str:
    """
    Return extracted text from a PDF, DOCX, or image (PNG/JPG/JPEG).

    ``file`` may be:
    - str / Path (filesystem path)
    - Django UploadedFile or FieldFile (must support .read(); .name used for type)
    - BinaryIO with optional ``filename`` for extension detection
    """
    if isinstance(file, (str, Path)):
        path = Path(file)
        suffix = path.suffix.lower()
        with open(path, 'rb') as fh:
            raw = fh.read()
    else:
        name = filename or getattr(file, 'name', '') or ''
        suffix = _suffix(name)
        raw = file.read()
        reset = getattr(file, 'seek', None)
        if callable(reset):
            try:
                file.seek(0)
            except (OSError, ValueError):
                pass

    if suffix not in ('.pdf', '.docx', '.png', '.jpg', '.jpeg'):
        raise ValueError(f'Unsupported extension for text extraction: {suffix!r}')

    if suffix == '.pdf':
        PdfReader = _get_pdf_reader()
        reader = PdfReader(BytesIO(raw))
        parts: list[str] = []
        for page in reader.pages:
            parts.append(page.extract_text() or '')
        return '\n'.join(parts)

    if suffix == '.docx':
        import docx
        doc = docx.Document(BytesIO(raw))
        return '\n'.join(p.text for p in doc.paragraphs)

    # Images — OCR (requires Tesseract binary, not only pip install pytesseract)
    import pytesseract
    from PIL import Image
    from pytesseract import TesseractError, TesseractNotFoundError

    tesseract_exe = _configure_tesseract_executable()
    if not tesseract_exe:
        logger.warning(
            'Tesseract OCR is not installed or not found. Image evidence will score as empty text. '
            'Install from https://github.com/UB-Mannheim/tesseract/wiki or set TESSERACT_CMD. '
            'Alternatively use PDF or DOCX.'
        )
        return ''

    _ensure_tessdata_prefix(tesseract_exe)

    image = Image.open(BytesIO(raw))
    try:
        try:
            return _ocr_image_to_string(image, pytesseract)
        except TesseractNotFoundError:
            logger.warning(
                'Tesseract failed to run (not on PATH or bad install). OCR skipped; use PDF/DOCX or fix TESSERACT_CMD.'
            )
            return ''
        except TesseractError as exc:
            logger.warning('Tesseract OCR error (tessdata/lang?): %s', exc)
            return ''
    finally:
        image.close()
