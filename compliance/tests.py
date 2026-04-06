from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from compliance.models import AssessmentResult, AssessmentRun, Control, Domain, Standard
from compliance.services.evidence import (
    analyze_evidence,
    apply_evidence_validation,
    review_status_from_score,
    validate_evidence_upload,
)


class BuildKeywordsTests(TestCase):
    def test_arabic_tokens_from_title_description(self):
        from compliance.services.keywords import build_keywords_from_text

        kws = build_keywords_from_text('النسخ الاحتياطي', 'سياسة استعادة البيانات')
        self.assertTrue(
            any(any('\u0600' <= ch <= '\u06ff' for ch in kw) for kw in kws),
            msg='Expected Arabic keywords from Arabic title/description',
        )


class AnalyzeEvidenceTests(TestCase):
    def test_empty_keywords_returns_zero_score(self):
        score, matched = analyze_evidence('any text', [])
        self.assertEqual(score, 0.0)
        self.assertEqual(matched, [])

    def test_keyword_substring_matching(self):
        score, matched = analyze_evidence(
            'We backup data daily and test recovery.',
            ['backup', 'recovery', 'audit'],
        )
        self.assertEqual(matched, ['backup', 'recovery'])
        self.assertAlmostEqual(score, 2 / 3, places=5)

    def test_deduplicates_keywords(self):
        score, matched = analyze_evidence('backup only', ['backup', 'backup', 'Backup'])
        self.assertEqual(matched, ['backup'])
        self.assertAlmostEqual(score, 1.0)

    def test_word_boundary_avoids_stem_false_positive(self):
        score, matched = analyze_evidence(
            'We are backuping servers daily',
            ['backup'],
            use_word_boundaries=True,
        )
        self.assertEqual(matched, [])
        self.assertEqual(score, 0.0)

    def test_word_boundary_matches_whole_token(self):
        score, matched = analyze_evidence(
            'We do a backup nightly',
            ['backup'],
            use_word_boundaries=True,
        )
        self.assertEqual(matched, ['backup'])
        self.assertAlmostEqual(score, 1.0)

    def test_phrase_with_hyphen_uses_substring(self):
        score, matched = analyze_evidence(
            'Enable multi-factor authentication today',
            ['multi-factor'],
            use_word_boundaries=True,
        )
        self.assertEqual(matched, ['multi-factor'])


class ReviewStatusFromScoreTests(TestCase):
    def test_boundaries(self):
        self.assertEqual(
            review_status_from_score(0.7, matched_count=1, keyword_total=1),
            'approved',
        )
        self.assertEqual(
            review_status_from_score(0.71, matched_count=2, keyword_total=2),
            'approved',
        )
        self.assertEqual(
            review_status_from_score(0.7, matched_count=1, keyword_total=5),
            'partial',
        )
        self.assertEqual(
            review_status_from_score(0.7, matched_count=2, keyword_total=5),
            'approved',
        )
        self.assertEqual(
            review_status_from_score(0.3, matched_count=1, keyword_total=3),
            'partial',
        )
        self.assertEqual(
            review_status_from_score(0.29, matched_count=0, keyword_total=3),
            'rejected',
        )
        self.assertEqual(
            review_status_from_score(0.0, matched_count=0, keyword_total=1),
            'rejected',
        )

    def test_short_text_never_approved(self):
        self.assertEqual(
            review_status_from_score(
                0.95,
                matched_count=5,
                keyword_total=5,
                text_too_short=True,
            ),
            'partial',
        )
        self.assertEqual(
            review_status_from_score(
                0.1,
                matched_count=0,
                keyword_total=3,
                text_too_short=True,
            ),
            'rejected',
        )


class ValidateEvidenceUploadTests(TestCase):
    def test_rejects_wrong_extension(self):
        f = SimpleUploadedFile('x.exe', b'0' * 1200, content_type='application/octet-stream')
        with self.assertRaises(ValidationError):
            validate_evidence_upload(f)

    def test_rejects_too_small(self):
        f = SimpleUploadedFile('doc.pdf', b'tiny', content_type='application/pdf')
        with self.assertRaises(ValidationError):
            validate_evidence_upload(f)

    def test_accepts_minimal_pdf_sized_file(self):
        body = b'%PDF-1.4 fake' + b'0' * 1100
        f = SimpleUploadedFile('doc.pdf', body, content_type='application/pdf')
        validate_evidence_upload(f)


class ApplyEvidenceValidationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='u1', password='x')
        self.standard = Standard.objects.create(name='S', description='d')
        self.domain = Domain.objects.create(standard=self.standard, name='D')
        self.control = Control.objects.create(
            domain=self.domain,
            title='Backup Policy',
            description='Backups',
            keywords=['backup', 'recovery'],
        )
        self.run = AssessmentRun.objects.create(
            user=self.user,
            standard=self.standard,
            title='Test run',
        )

    def test_compliant_without_evidence_is_rejected(self):
        r = AssessmentResult.objects.create(
            assessment_run=self.run,
            control=self.control,
            user=self.user,
            status='compliant',
            review_status='pending',
        )
        apply_evidence_validation(r, compliance_status='compliant')
        r.refresh_from_db()
        self.assertIsNone(r.ai_score)
        self.assertEqual(r.review_status, 'rejected')

    def test_non_compliant_without_evidence_is_pending(self):
        r = AssessmentResult.objects.create(
            assessment_run=self.run,
            control=self.control,
            user=self.user,
            status='non_compliant',
            review_status='pending',
        )
        apply_evidence_validation(r, compliance_status='non_compliant')
        r.refresh_from_db()
        self.assertEqual(r.review_status, 'pending')

    def test_admin_override_preserves_review_status_without_evidence(self):
        r = AssessmentResult.objects.create(
            assessment_run=self.run,
            control=self.control,
            user=self.user,
            status='compliant',
            review_status='approved',
            review_status_admin_override=True,
        )
        apply_evidence_validation(r, compliance_status='compliant')
        r.refresh_from_db()
        self.assertEqual(r.review_status, 'approved')
        self.assertIsNone(r.ai_score)

    def test_logs_created(self):
        from compliance.models import EvidenceValidationLog

        r = AssessmentResult.objects.create(
            assessment_run=self.run,
            control=self.control,
            user=self.user,
            status='compliant',
        )
        apply_evidence_validation(r, compliance_status='compliant')
        self.assertTrue(
            EvidenceValidationLog.objects.filter(
                assessment_result=r,
                message='no_evidence',
            ).exists(),
        )

    def test_empty_keywords_on_control_uses_fallback_when_evidence_present(self):
        c = Control.objects.create(
            domain=self.domain,
            title='Backup Policy',
            description='recovery and data protection',
            keywords=[],
        )
        r = AssessmentResult.objects.create(
            assessment_run=self.run,
            control=c,
            user=self.user,
            status='compliant',
            review_status='pending',
        )
        body = b'%PDF-1.4\n' + b'x' * 1100
        r.evidence_file.save('ev.pdf', ContentFile(body), save=True)
        with patch(
            'compliance.services.evidence.extract_text',
            return_value='our daily backup and recovery process for data',
        ):
            apply_evidence_validation(r, compliance_status='compliant')
        r.refresh_from_db()
        self.assertIsNotNone(r.ai_score)
        self.assertGreater(r.ai_score, 0)
        self.assertNotEqual(r.review_status, 'pending')
        log = r.validation_logs.filter(message='scored').first()
        self.assertIsNotNone(log)
        self.assertTrue(log.extra.get('keywords_fallback'))
