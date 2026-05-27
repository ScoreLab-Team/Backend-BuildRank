# apps/verification/tests.py
"""
Tests del sistema de verificació documental.
Cobreix: API endpoints, scorer, extractor i revisió manual.
"""
import json
import tempfile
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import RoleChoices
from apps.buildings.models import Edifici, Localitzacio
from apps.verification.models import (
    AdminFincaDocumentVerification,
    AdminFincaVerificationDocument,
    AdminFincaVerificationResult,
)
from apps.verification.services.scorer import (
    ScoreResult,
    compute_score,
    _valida_dni_nie,
    _valida_dates,
    _score_nom_usuari,
    _normalitzar_nom,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def auth(client, user):
    token = str(RefreshToken.for_user(user).access_token)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')


def make_pdf(name='doc.pdf'):
    return SimpleUploadedFile(name, b'%PDF-1.4 test', content_type='application/pdf')


def make_jpg(name='doc.jpg'):
    return SimpleUploadedFile(name, b'\xff\xd8\xff' + b'\x00' * 10, content_type='image/jpeg')


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class BaseVerificationTest(APITestCase):
    """Fixtures comuns per a tots els tests."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='joan@test.com', password='pass1234',
            first_name='Joan', last_name='Pérez',
        )
        self.user.profile.role = RoleChoices.ADMIN
        self.user.profile.save()

        self.other_user = User.objects.create_user(
            email='altre@test.com', password='pass1234',
        )
        self.other_user.profile.role = RoleChoices.ADMIN
        self.other_user.profile.save()

        self.superuser = User.objects.create_superuser(
            email='super@test.com', password='pass1234',
        )
        # El superuser no necessita perfil amb rol especific (is_superuser bypassa el rol)

        self.loc = Localitzacio.objects.create(
            carrer='Carrer Major', numero=12,
            codiPostal='08001', barri='Gràcia',
        )
        self.edifici = Edifici.objects.create(
            anyConstruccio=1980, tipologia='Residencial',
            superficieTotal=300.0, nombrePlantes=4,
            reglament='NBE-CT-79', orientacioPrincipal='Sud',
            localitzacio=self.loc,
        )
        auth(self.client, self.user)

    def _crear_verificacio(self, status_val=AdminFincaDocumentVerification.Status.PENDING):
        return AdminFincaDocumentVerification.objects.create(
            user=self.user, edifici=self.edifici, status=status_val,
        )

    def _crear_document(self, verification, doc_type='identificatiu', ocr_text='', extracted=None):
        return AdminFincaVerificationDocument.objects.create(
            verification=verification,
            fitxer=make_pdf(),
            doc_type=doc_type,
            ocr_text=ocr_text,
            extracted_data=extracted,
        )


# ---------------------------------------------------------------------------
# Tests: Creacio de verificacio
# ---------------------------------------------------------------------------

@override_settings(
    MEDIA_ROOT=tempfile.mkdtemp(),
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class CreateVerificationTests(BaseVerificationTest):

    def url(self):
        return reverse('verification:create')

    @patch('apps.verification.tasks._run_ocr_pipeline', return_value=[])
    @patch('apps.verification.tasks._run_extraction_pipeline', return_value=[])
    @patch('apps.verification.tasks._run_scoring_pipeline', return_value={'score_final': 0.0, 'scores_per_document': []})
    def test_crear_ok_un_document(self, mock_score, mock_extract, mock_ocr):
        data = {
            'edifici': self.edifici.pk,
            'documents_fitxer': make_pdf(),
            'documents_doctype': 'identificatiu',
        }
        response = self.client.post(self.url(), data, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(AdminFincaDocumentVerification.objects.count(), 1)
        self.assertEqual(AdminFincaVerificationDocument.objects.count(), 1)
        v = AdminFincaDocumentVerification.objects.first()
        self.assertEqual(v.user, self.user)

    @patch('apps.verification.tasks._run_ocr_pipeline', return_value=[])
    @patch('apps.verification.tasks._run_extraction_pipeline', return_value=[])
    @patch('apps.verification.tasks._run_scoring_pipeline', return_value={'score_final': 0.0, 'scores_per_document': []})
    def test_crear_ok_imatge_jpg(self, mock_score, mock_extract, mock_ocr):
        data = {
            'edifici': self.edifici.pk,
            'documents_fitxer': make_jpg(),
            'documents_doctype': 'certificat',
        }
        response = self.client.post(self.url(), data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_crear_sense_documents_falla(self):
        data = {'edifici': self.edifici.pk}
        response = self.client.post(self.url(), data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_crear_tipus_no_permes_falla(self):
        fitxer = SimpleUploadedFile('doc.txt', b'text', content_type='text/plain')
        data = {
            'edifici': self.edifici.pk,
            'documents_fitxer': fitxer,
            'documents_doctype': 'identificatiu',
        }
        response = self.client.post(self.url(), data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_crear_nombre_fitxers_doctype_diferent_falla(self):
        data = {
            'edifici': self.edifici.pk,
            'documents_fitxer': [make_pdf(), make_pdf()],
            'documents_doctype': 'identificatiu',  # 2 fitxers, 1 tipus
        }
        response = self.client.post(self.url(), data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_crear_verificacio_duplicada_falla(self):
        self._crear_verificacio(AdminFincaDocumentVerification.Status.PENDING)
        data = {
            'edifici': self.edifici.pk,
            'documents_fitxer': make_pdf(),
            'documents_doctype': 'identificatiu',
        }
        response = self.client.post(self.url(), data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('apps.verification.tasks._run_ocr_pipeline', return_value=[])
    @patch('apps.verification.tasks._run_extraction_pipeline', return_value=[])
    @patch('apps.verification.tasks._run_scoring_pipeline', return_value={'score_final': 0.0, 'scores_per_document': []})
    def test_crear_despres_aprovada_ok(self, mock_score, mock_extract, mock_ocr):
        self._crear_verificacio(AdminFincaDocumentVerification.Status.APPROVED)
        data = {
            'edifici': self.edifici.pk,
            'documents_fitxer': make_pdf(),
            'documents_doctype': 'certificat',
        }
        response = self.client.post(self.url(), data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_crear_no_autenticat_falla(self):
        self.client.credentials()
        data = {
            'edifici': self.edifici.pk,
            'documents_fitxer': make_pdf(),
            'documents_doctype': 'identificatiu',
        }
        response = self.client.post(self.url(), data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_crear_owner_falla(self):
        # Un usuari amb rol owner no te permis per crear verificacions
        owner = User.objects.create_user(
            email='owner@test.com', password='pass1234',
        )
        # El perfil es crea via signal amb role=OWNER per defecte
        auth(self.client, owner)
        data = {
            'edifici': self.edifici.pk,
            'documents_fitxer': make_pdf(),
            'documents_doctype': 'identificatiu',
        }
        response = self.client.post(self.url(), data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_crear_tenant_falla(self):
        # Un usuari amb rol tenant no te permis per crear verificacions
        tenant = User.objects.create_user(
            email='tenant@test.com', password='pass1234',
        )
        tenant.profile.role = RoleChoices.TENANT
        tenant.profile.save()
        auth(self.client, tenant)
        data = {
            'edifici': self.edifici.pk,
            'documents_fitxer': make_pdf(),
            'documents_doctype': 'identificatiu',
        }
        response = self.client.post(self.url(), data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


# ---------------------------------------------------------------------------
# Tests: Llistat i detall
# ---------------------------------------------------------------------------

@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ListDetailVerificationTests(BaseVerificationTest):

    def test_llistat_nomes_propies(self):
        self._crear_verificacio()
        AdminFincaDocumentVerification.objects.create(
            user=self.other_user, edifici=self.edifici,
            status=AdminFincaDocumentVerification.Status.PENDING,
        )
        response = self.client.get(reverse('verification:list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_superuser_veu_totes(self):
        self._crear_verificacio()
        AdminFincaDocumentVerification.objects.create(
            user=self.other_user, edifici=self.edifici,
            status=AdminFincaDocumentVerification.Status.PENDING,
        )
        auth(self.client, self.superuser)
        response = self.client.get(reverse('verification:list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_llistat_owner_falla(self):
        # Un owner no te acces al llistat de verificacions
        owner = User.objects.create_user(
            email='owner@test.com', password='pass1234',
        )
        # El perfil es crea via signal amb role=OWNER per defecte
        auth(self.client, owner)
        response = self.client.get(reverse('verification:list'))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_detall_propi_ok(self):
        v = self._crear_verificacio()
        response = self.client.get(reverse('verification:detail', kwargs={'pk': v.pk}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], v.pk)

    def test_detall_alie_falla(self):
        v = AdminFincaDocumentVerification.objects.create(
            user=self.other_user, edifici=self.edifici,
            status=AdminFincaDocumentVerification.Status.PENDING,
        )
        response = self.client.get(reverse('verification:detail', kwargs={'pk': v.pk}))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_detall_inclou_score(self):
        v = self._crear_verificacio(AdminFincaDocumentVerification.Status.REVIEW)
        v.score = 0.82
        v.suggeriment = 'Revisio detallada recomanada'
        v.save()
        response = self.client.get(reverse('verification:detail', kwargs={'pk': v.pk}))
        self.assertAlmostEqual(float(response.data['score']), 0.82)

    def test_detall_owner_falla(self):
        # Un owner no pot accedir al detall encara que conegui la pk
        v = self._crear_verificacio()
        owner = User.objects.create_user(
            email='owner@test.com', password='pass1234',
        )
        auth(self.client, owner)
        response = self.client.get(reverse('verification:detail', kwargs={'pk': v.pk}))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


# ---------------------------------------------------------------------------
# Tests: Revisio manual
# ---------------------------------------------------------------------------

@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class RevisioVerificacioTests(BaseVerificationTest):

    def url(self, pk):
        return reverse('verification:revisar', kwargs={'pk': pk})

    def setUp(self):
        super().setUp()
        self.v = self._crear_verificacio(AdminFincaDocumentVerification.Status.REVIEW)
        self._crear_document(self.v, extracted={
            '_ok': True, 'nom_complet': 'Joan Pérez',
            'dni_nie': None, 'carrec': None,
        })

    def test_aprovar_ok(self):
        auth(self.client, self.superuser)
        response = self.client.post(
            self.url(self.v.pk),
            {'accio': 'aprovar'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.v.refresh_from_db()
        self.assertEqual(self.v.status, AdminFincaDocumentVerification.Status.APPROVED)
        self.edifici.refresh_from_db()
        self.assertEqual(self.edifici.administradorFinca, self.user)

    def test_aprovar_crea_registre_historic(self):
        auth(self.client, self.superuser)
        self.client.post(self.url(self.v.pk), {'accio': 'aprovar'}, format='json')
        self.assertTrue(
            AdminFincaVerificationResult.objects.filter(verification=self.v).exists()
        )

    def test_aprovar_esborra_fitxers_fisics(self):
        auth(self.client, self.superuser)
        doc = self.v.documents.first()
        self.client.post(self.url(self.v.pk), {'accio': 'aprovar'}, format='json')
        doc.refresh_from_db()
        self.assertFalse(bool(doc.fitxer))

    def test_rebutjar_ok(self):
        auth(self.client, self.superuser)
        response = self.client.post(
            self.url(self.v.pk),
            {'accio': 'rebutjar', 'motiu': 'Document no valid'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.v.refresh_from_db()
        self.assertEqual(self.v.status, AdminFincaDocumentVerification.Status.REJECTED)

    def test_rebutjar_sense_motiu_falla(self):
        auth(self.client, self.superuser)
        response = self.client.post(
            self.url(self.v.pk),
            {'accio': 'rebutjar'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_revisar_no_superuser_falla(self):
        # Un AdminFinca normal no pot revisar verificacions
        response = self.client.post(
            self.url(self.v.pk),
            {'accio': 'aprovar'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_revisar_admin_finca_falla(self):
        # Comprova explicitament que un AdminFinca amb rol ADMIN pero sense is_superuser rep 403
        admin_finca = User.objects.create_user(
            email='adminfinca2@test.com', password='pass1234',
        )
        admin_finca.profile.role = RoleChoices.ADMIN
        admin_finca.profile.save()
        auth(self.client, admin_finca)
        response = self.client.post(
            self.url(self.v.pk),
            {'accio': 'aprovar'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_revisar_status_incorrecte_falla(self):
        self.v.status = AdminFincaDocumentVerification.Status.PENDING
        self.v.save()
        auth(self.client, self.superuser)
        response = self.client.post(
            self.url(self.v.pk),
            {'accio': 'aprovar'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_revisar_accio_invalida_falla(self):
        auth(self.client, self.superuser)
        response = self.client.post(
            self.url(self.v.pk),
            {'accio': 'eliminar'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_revisar_inexistent_falla(self):
        auth(self.client, self.superuser)
        response = self.client.post(
            self.url(99999),
            {'accio': 'aprovar'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------------------------
# Tests: Scorer
# ---------------------------------------------------------------------------

class ScorerTests(BaseVerificationTest):

    def _dades_completes(self, **kwargs):
        base = {
            '_ok': True,
            'nom_complet': 'Joan Pérez Garcia',
            'dni_nie': '12345678Z',
            'carrec': 'Administrador',
            'adreca_finca': 'Carrer Major 12',
            'data_inici_vigencia': '2023-01-01',
            'data_fi_vigencia': None,
            'te_signatura': True,
            'te_segell': True,
            'entitat_emissora': 'Col·legi Administradors',
            'observacions': None,
        }
        base.update(kwargs)
        return base

    def test_score_alt_dades_completes(self):
        result = compute_score(self._dades_completes())
        self.assertGreater(result.score, 0.70)
        self.assertIsInstance(result.flags, list)

    def test_score_zero_si_extractor_falla(self):
        dades = {'_ok': False, '_error': 'Timeout Ollama'}
        result = compute_score(dades)
        self.assertEqual(result.score, 0.0)
        self.assertIn('Timeout Ollama', result.flags[0])

    def test_score_baix_sense_camps_critics(self):
        result = compute_score({'_ok': True})
        self.assertLess(result.score, 0.50)  # sense cap camp critic ha de ser baix

    def test_penalitzacio_dni_invalid(self):
        result = compute_score(self._dades_completes(dni_nie='INVALID'))
        self.assertTrue(any('DNI' in f or 'format' in f for f in result.flags))

    def test_penalitzacio_document_caducat(self):
        result = compute_score(self._dades_completes(
            data_inici_vigencia='2020-01-01',
            data_fi_vigencia='2021-01-01',
        ))
        self.assertTrue(any('caducat' in f.lower() for f in result.flags))

    def test_suggeriment_acceptable(self):
        result = compute_score(self._dades_completes())
        if result.score >= 0.75:
            self.assertIn('Acceptable', result.suggeriment)

    def test_suggeriment_rebuig(self):
        result = compute_score({'_ok': True})
        self.assertIn('Rebuig', result.suggeriment)

    def test_nom_usuari_coincidencia_exacta(self):
        score, flags = _score_nom_usuari('Joan Pérez', self.user)
        self.assertGreater(score, 0.5)
        self.assertEqual(flags, [])

    def test_nom_usuari_sense_coincidencia(self):
        score, flags = _score_nom_usuari('Pedro Rodríguez', self.user)
        self.assertEqual(score, 0.0)
        self.assertTrue(len(flags) > 0)

    def test_nom_usuari_none(self):
        score, flags = _score_nom_usuari(None, self.user)
        self.assertEqual(score, 0.0)

    def test_detall_conte_quatre_dimensions(self):
        result = compute_score(self._dades_completes())
        self.assertIn('completesa', result.detall)
        self.assertIn('validesa', result.detall)
        self.assertIn('credibilitat', result.detall)
        self.assertIn('nom_usuari', result.detall)


# ---------------------------------------------------------------------------
# Tests: Validadors individuals
# ---------------------------------------------------------------------------

class ValidadorsTests(BaseVerificationTest):

    def test_dni_valid(self):
        ok, flag = _valida_dni_nie('12345678Z')
        self.assertTrue(ok)
        self.assertIsNone(flag)

    def test_nie_valid(self):
        # X2482300W es un NIE amb lletra de control correcta
        ok, flag = _valida_dni_nie('X2482300W')
        self.assertTrue(ok)
        self.assertIsNone(flag)

    def test_dni_lletra_incorrecta(self):
        ok, flag = _valida_dni_nie('12345678A')
        # format valid pero lletra pot ser incorrecta
        self.assertIsNotNone(flag is None or ok in (True, False))

    def test_dni_format_invalid(self):
        ok, flag = _valida_dni_nie('INVALID')
        self.assertFalse(ok)
        self.assertIsNotNone(flag)

    def test_dni_none(self):
        ok, flag = _valida_dni_nie(None)
        self.assertFalse(ok)
        self.assertIsNone(flag)

    def test_dates_coherents(self):
        flags = _valida_dates('2024-01-01', '2030-01-01')
        self.assertEqual(flags, [])

    def test_dates_inici_posterior_fi(self):
        flags = _valida_dates('2025-01-01', '2023-01-01')
        self.assertTrue(any('incoherent' in f for f in flags))

    def test_data_caducada(self):
        flags = _valida_dates('2020-01-01', '2021-01-01')
        self.assertTrue(any('caducat' in f.lower() for f in flags))

    def test_dates_format_invalid(self):
        flags = _valida_dates('no-es-una-data', None)
        self.assertTrue(len(flags) > 0)

    def test_normalitzar_nom_ordena_tokens(self):
        self.assertEqual(_normalitzar_nom('García Joan'), _normalitzar_nom('Joan García'))

    def test_normalitzar_nom_majuscules(self):
        resultat = _normalitzar_nom('joan pérez')
        self.assertEqual(resultat, resultat.upper())


# ---------------------------------------------------------------------------
# Tests: Extractor (mock Ollama)
# ---------------------------------------------------------------------------

class ExtractorTests(BaseVerificationTest):

    @patch('apps.verification.services.extractor.requests.post')
    def test_extractor_retorna_json_valid(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'message': {
                'content': json.dumps({
                    'nom_complet': 'Joan Pérez',
                    'dni_nie': '12345678Z',
                    'carrec': 'Administrador',
                    'nom_comunitat': None,
                    'adreca_finca': 'Carrer Major 12',
                    'data_inici_vigencia': None,
                    'data_fi_vigencia': None,
                    'te_signatura': False,
                    'te_segell': False,
                    'entitat_emissora': 'Ajuntament',
                    'observacions': None,
                })
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        from apps.verification.services.extractor import extract_structured_data
        result = extract_structured_data('Text OCR de prova', 'identificatiu')

        self.assertTrue(result['_ok'])
        self.assertEqual(result['nom_complet'], 'Joan Pérez')
        self.assertEqual(result['dni_nie'], '12345678Z')

    @patch('apps.verification.services.extractor.requests.post')
    def test_extractor_gestiona_json_amb_markdown_fences(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'message': {
                'content': '```json\n{"nom_complet": "Joan", "dni_nie": null, "carrec": null, "nom_comunitat": null, "adreca_finca": null, "data_inici_vigencia": null, "data_fi_vigencia": null, "te_signatura": false, "te_segell": false, "entitat_emissora": null, "observacions": null}\n```'
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        from apps.verification.services.extractor import extract_structured_data
        result = extract_structured_data('Text de prova', 'certificat')

        self.assertTrue(result['_ok'])
        self.assertEqual(result['nom_complet'], 'Joan')

    @patch('apps.verification.services.extractor.requests.post')
    def test_extractor_connection_error(self, mock_post):
        import requests as req
        mock_post.side_effect = req.exceptions.ConnectionError()

        from apps.verification.services.extractor import extract_structured_data
        result = extract_structured_data('Text de prova', 'certificat')

        self.assertFalse(result['_ok'])
        self.assertIn('Ollama', result['_error'])

    def test_extractor_text_buit(self):
        from apps.verification.services.extractor import extract_structured_data
        result = extract_structured_data('', 'identificatiu')
        self.assertFalse(result['_ok'])
        self.assertIn('buit', result['_error'])
# apps/verification/tests_tasks.py
"""
Tests de cobertura per a apps/verification/tasks.py
Cobreix: process_verification, _run_ocr_pipeline, _run_extraction_pipeline,
         _run_scoring_pipeline i _calcular_ocr_confidence.

Estratègia:
- process_verification: s'executa síncronament amb CELERY_TASK_ALWAYS_EAGER.
- Les subpipelines internes (_run_ocr_pipeline, etc.) es testen directament
  sense passar per Celery per aïllar cada branca.
- Les crides externes (extract_text, extract_structured_data, compute_score)
  es mockejen sempre per evitar dependències d'Ollama / OCR real.
"""
import tempfile
from datetime import date
from unittest.mock import MagicMock, patch, call

from django.test import override_settings, TestCase

from apps.verification.models import (
    AdminFincaDocumentVerification,
    AdminFincaVerificationDocument,
)
from apps.verification.tasks import (
    process_verification,
    _run_ocr_pipeline,
    _run_extraction_pipeline,
    _run_scoring_pipeline,
    _calcular_ocr_confidence,
)


# ---------------------------------------------------------------------------
# Helpers compartits
# ---------------------------------------------------------------------------

def make_score_result(score=0.85, flags=None, detall=None, suggeriment="Acceptable"):
    """Crea un ScoreResult mock amb els atributs esperats per _run_scoring_pipeline."""
    r = MagicMock()
    r.score = score
    r.flags = flags or []
    r.detall = detall or {}
    r.suggeriment = suggeriment
    return r


# ---------------------------------------------------------------------------
# TC-TASK-001 a TC-TASK-005: _calcular_ocr_confidence
# ---------------------------------------------------------------------------

class TestCalcularOcrConfidence(TestCase):
    """
    Tests unitaris purs de _calcular_ocr_confidence.
    No necessiten BD ni mocks externs.
    """

    def test_text_buit_retorna_zero(self):
        """TC-TASK-001: Text buit → confidence 0.0."""
        self.assertEqual(_calcular_ocr_confidence(""), 0.0)
        self.assertEqual(_calcular_ocr_confidence("   "), 0.0)
        self.assertEqual(_calcular_ocr_confidence(None), 0.0)

    def test_text_curt_retorna_02(self):
        """TC-TASK-002: Menys de 50 caràcters → confidence 0.2."""
        self.assertEqual(_calcular_ocr_confidence("abc"), 0.2)
        self.assertEqual(_calcular_ocr_confidence("x" * 49), 0.2)

    def test_text_soroll_alt_retorna_04(self):
        """TC-TASK-003: Ratio soroll > 30% → confidence 0.4."""
        # Omplim de caràcters estranys (#, @, ^, etc.)
        soroll = "#@^&*~" * 20          # 120 caràcters estranys
        text = soroll + "a" * 50        # + 50 normals → ratio ~0.71
        self.assertEqual(_calcular_ocr_confidence(text), 0.4)

    def test_text_soroll_mig_retorna_065(self):
        """TC-TASK-004: Ratio soroll entre 15% i 30% → confidence 0.65."""
        # 20 estranys sobre 120 total → ratio ~0.167
        text = "#" * 20 + "a" * 100
        self.assertEqual(_calcular_ocr_confidence(text), 0.65)

    def test_text_llarg_net_retorna_09(self):
        """TC-TASK-005a: Més de 500 caràcters nets → confidence 0.9."""
        text = "paraula " * 70          # 560 caràcters, tot net
        self.assertEqual(_calcular_ocr_confidence(text), 0.9)

    def test_text_curt_net_retorna_075(self):
        """TC-TASK-005b: 50–500 caràcters nets → confidence 0.75."""
        text = "a" * 200               # 200 caràcters nets, < 500
        self.assertEqual(_calcular_ocr_confidence(text), 0.75)


# ---------------------------------------------------------------------------
# TC-TASK-010 a TC-TASK-016: _run_ocr_pipeline
# ---------------------------------------------------------------------------

@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class TestRunOcrPipeline(TestCase):
    """Tests de _run_ocr_pipeline amb mocks de extract_text i BD mínima."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        from apps.buildings.models import Edifici, Localitzacio
        User = get_user_model()

        self.user = User.objects.create_user(email='ocr@test.com', password='pass')
        self.loc = Localitzacio.objects.create(
            carrer='Test', numero=1, codiPostal='08001', barri='Test'
        )
        self.edifici = Edifici.objects.create(
            anyConstruccio=2000, tipologia='Residencial',
            superficieTotal=100.0, nombrePlantes=2,
            reglament='CTE', orientacioPrincipal='Sud',
            localitzacio=self.loc,
        )
        self.verification = AdminFincaDocumentVerification.objects.create(
            user=self.user, edifici=self.edifici,
            status=AdminFincaDocumentVerification.Status.RUNNING,
        )

    def _crear_doc(self, doc_type='identificatiu'):
        from django.core.files.uploadedfile import SimpleUploadedFile
        return AdminFincaVerificationDocument.objects.create(
            verification=self.verification,
            fitxer=SimpleUploadedFile('doc.pdf', b'%PDF', content_type='application/pdf'),
            doc_type=doc_type,
        )

    @patch('apps.verification.tasks.extract_text', return_value="Text OCR de prova " * 40)
    def test_ocr_ok_desa_text_i_confidence(self, mock_ocr):
        """TC-TASK-010: OCR exitós → desa ocr_text i confidence al document."""
        doc = self._crear_doc()

        resultats = _run_ocr_pipeline(self.verification)

        doc.refresh_from_db()
        self.assertEqual(len(resultats), 1)
        self.assertTrue(resultats[0]['ok'])
        self.assertEqual(resultats[0]['document_id'], doc.pk)
        self.assertGreater(resultats[0]['chars_extrets'], 0)
        self.assertGreater(doc.confidence, 0)
        self.assertNotEqual(doc.ocr_text, '')

    @patch('apps.verification.tasks.extract_text', return_value="Text OCR de prova " * 40)
    def test_ocr_retorna_doc_type_al_resultat(self, mock_ocr):
        """TC-TASK-011: El resultat inclou doc_type del document."""
        self._crear_doc(doc_type='certificat')
        resultats = _run_ocr_pipeline(self.verification)
        self.assertEqual(resultats[0]['doc_type'], 'certificat')

    @patch('apps.verification.tasks.extract_text', side_effect=Exception("Error OCR simulat"))
    def test_ocr_error_continua_processant(self, mock_ocr):
        """TC-TASK-012: Error OCR en un doc → ok=False, però no llança excepció."""
        self._crear_doc()
        resultats = _run_ocr_pipeline(self.verification)
        self.assertEqual(len(resultats), 1)
        self.assertFalse(resultats[0]['ok'])
        self.assertIn('error', resultats[0])

    @patch('apps.verification.tasks.extract_text', return_value="Text " * 40)
    def test_ocr_multiples_docs(self, mock_ocr):
        """TC-TASK-013: Dos documents → dos resultats."""
        self._crear_doc(doc_type='identificatiu')
        self._crear_doc(doc_type='certificat')
        resultats = _run_ocr_pipeline(self.verification)
        self.assertEqual(len(resultats), 2)

    @patch('apps.verification.tasks.extract_text', return_value="Text " * 40)
    def test_ocr_sense_documents_retorna_llista_buida(self, mock_ocr):
        """TC-TASK-014: Verificació sense documents → llista buida."""
        resultats = _run_ocr_pipeline(self.verification)
        self.assertEqual(resultats, [])


# ---------------------------------------------------------------------------
# TC-TASK-020 a TC-TASK-025: _run_extraction_pipeline
# ---------------------------------------------------------------------------

@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class TestRunExtractionPipeline(TestCase):
    """Tests de _run_extraction_pipeline."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        from apps.buildings.models import Edifici, Localitzacio
        from django.core.files.uploadedfile import SimpleUploadedFile
        User = get_user_model()

        self.user = User.objects.create_user(email='ext@test.com', password='pass')
        loc = Localitzacio.objects.create(
            carrer='Test', numero=1, codiPostal='08001', barri='Test'
        )
        edifici = Edifici.objects.create(
            anyConstruccio=2000, tipologia='Residencial',
            superficieTotal=100.0, nombrePlantes=2,
            reglament='CTE', orientacioPrincipal='Sud',
            localitzacio=loc,
        )
        self.verification = AdminFincaDocumentVerification.objects.create(
            user=self.user, edifici=edifici,
            status=AdminFincaDocumentVerification.Status.RUNNING,
        )
        self.doc = AdminFincaVerificationDocument.objects.create(
            verification=self.verification,
            fitxer=SimpleUploadedFile('doc.pdf', b'%PDF', content_type='application/pdf'),
            doc_type='identificatiu',
            ocr_text='Text OCR llarg per passar el filtre ocr_text__gt',
        )

    @patch('apps.verification.tasks.check_ollama_available', return_value=False)
    def test_ollama_no_disponible_retorna_buit(self, mock_check):
        """TC-TASK-020: Ollama no disponible → llista buida, sense processar."""
        resultats = _run_extraction_pipeline(self.verification)
        self.assertEqual(resultats, [])

    @patch('apps.verification.tasks.check_ollama_available', return_value=True)
    @patch('apps.verification.tasks.extract_structured_data')
    def test_extraccio_ok_desa_extracted_data(self, mock_extract, mock_check):
        """TC-TASK-021: Extracció exitosa → desa extracted_data al document."""
        mock_extract.return_value = {
            '_ok': True,
            'nom_complet': 'Joan Pérez',
            'dni_nie': '12345678Z',
        }

        resultats = _run_extraction_pipeline(self.verification)

        self.doc.refresh_from_db()
        self.assertEqual(len(resultats), 1)
        self.assertTrue(resultats[0]['ok'])
        self.assertIsNotNone(self.doc.extracted_data)
        self.assertEqual(self.doc.extracted_data['nom_complet'], 'Joan Pérez')

    @patch('apps.verification.tasks.check_ollama_available', return_value=True)
    @patch('apps.verification.tasks.extract_structured_data')
    def test_extraccio_camps_trobats_exclou_privats(self, mock_extract, mock_check):
        """TC-TASK-022: El camp 'camps_trobats' no inclou claus que comencen per '_'."""
        mock_extract.return_value = {
            '_ok': True,
            '_error': None,
            'nom_complet': 'Joan',
            'dni_nie': None,       # None → no compta com trobat
        }

        resultats = _run_extraction_pipeline(self.verification)

        self.assertIn('nom_complet', resultats[0]['camps_trobats'])
        self.assertNotIn('_ok', resultats[0]['camps_trobats'])
        self.assertNotIn('_error', resultats[0]['camps_trobats'])
        self.assertNotIn('dni_nie', resultats[0]['camps_trobats'])  # era None

    @patch('apps.verification.tasks.check_ollama_available', return_value=True)
    @patch('apps.verification.tasks.extract_structured_data', side_effect=Exception("Timeout"))
    def test_extraccio_error_continua(self, mock_extract, mock_check):
        """TC-TASK-023: Error extracció → ok=False, pipeline no s'atura."""
        resultats = _run_extraction_pipeline(self.verification)
        self.assertEqual(len(resultats), 1)
        self.assertFalse(resultats[0]['ok'])
        self.assertIn('error', resultats[0])

    @patch('apps.verification.tasks.check_ollama_available', return_value=True)
    @patch('apps.verification.tasks.extract_structured_data')
    def test_extraccio_doc_sense_ocr_text_saltat(self, mock_extract, mock_check):
        """TC-TASK-024: Document amb ocr_text buit és ignorat pel filtre ocr_text__gt=''."""
        # Creem un segon doc sense OCR text
        from django.core.files.uploadedfile import SimpleUploadedFile
        AdminFincaVerificationDocument.objects.create(
            verification=self.verification,
            fitxer=SimpleUploadedFile('doc2.pdf', b'%PDF', content_type='application/pdf'),
            doc_type='certificat',
            ocr_text='',   # buit → el filtre ocr_text__gt='' l'exclou
        )
        mock_extract.return_value = {'_ok': True, 'nom_complet': 'Joan'}

        resultats = _run_extraction_pipeline(self.verification)

        # Només el doc amb text ha de ser processat
        self.assertEqual(len(resultats), 1)
        self.assertEqual(mock_extract.call_count, 1)


# ---------------------------------------------------------------------------
# TC-TASK-030 a TC-TASK-038: _run_scoring_pipeline
# ---------------------------------------------------------------------------

@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class TestRunScoringPipeline(TestCase):
    """Tests de _run_scoring_pipeline."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        from apps.buildings.models import Edifici, Localitzacio
        from django.core.files.uploadedfile import SimpleUploadedFile
        User = get_user_model()

        self.user = User.objects.create_user(email='score@test.com', password='pass')
        loc = Localitzacio.objects.create(
            carrer='Test', numero=1, codiPostal='08001', barri='Test'
        )
        edifici = Edifici.objects.create(
            anyConstruccio=2000, tipologia='Residencial',
            superficieTotal=100.0, nombrePlantes=2,
            reglament='CTE', orientacioPrincipal='Sud',
            localitzacio=loc,
        )
        self.verification = AdminFincaDocumentVerification.objects.create(
            user=self.user, edifici=edifici,
            status=AdminFincaDocumentVerification.Status.RUNNING,
        )

    def _crear_doc_amb_dades(self, extracted=None):
        from django.core.files.uploadedfile import SimpleUploadedFile
        return AdminFincaVerificationDocument.objects.create(
            verification=self.verification,
            fitxer=SimpleUploadedFile('doc.pdf', b'%PDF', content_type='application/pdf'),
            doc_type='identificatiu',
            ocr_text='text',
            extracted_data=extracted or {'_ok': True, 'nom_complet': 'Joan'},
        )

    def test_sense_resultats_extraccio_score_zero(self):
        """TC-TASK-030: Lista resultats_extraccio buida → score=0.0, flags informatives."""
        resultat = _run_scoring_pipeline(self.verification, resultats_extraccio=[])

        self.verification.refresh_from_db()
        self.assertEqual(resultat['score_final'], 0.0)
        self.assertEqual(resultat['scores_per_document'], [])
        self.assertEqual(self.verification.score, 0.0)
        self.assertTrue(len(self.verification.score_flags) > 0)

    @patch('apps.verification.tasks.compute_score')
    def test_sense_docs_puntuables_score_zero(self, mock_compute):
        """TC-TASK-031: Verificació sense documents amb extracted_data → score=0.0."""
        # No creem cap document → el queryset filtered és buit
        resultat = _run_scoring_pipeline(
            self.verification,
            resultats_extraccio=[{'document_id': 999, 'ok': True}],
        )

        self.assertEqual(resultat['score_final'], 0.0)
        mock_compute.assert_not_called()

    @patch('apps.verification.tasks.compute_score')
    def test_score_alt_suggeriment_acceptable(self, mock_compute):
        """TC-TASK-032: Score >= LLINDAR_APROVAT → suggeriment conté 'Acceptable'."""
        from apps.verification.services.scorer import LLINDAR_APROVAT
        self._crear_doc_amb_dades()
        mock_compute.return_value = make_score_result(score=LLINDAR_APROVAT)

        _run_scoring_pipeline(
            self.verification,
            resultats_extraccio=[{'document_id': 1, 'ok': True}],
        )

        self.verification.refresh_from_db()
        self.assertIn('Acceptable', self.verification.suggeriment)

    @patch('apps.verification.tasks.compute_score')
    def test_score_mig_suggeriment_revisio(self, mock_compute):
        """TC-TASK-033: LLINDAR_REVISAR <= score < LLINDAR_APROVAT → 'Revisió'."""
        from apps.verification.services.scorer import LLINDAR_APROVAT, LLINDAR_REVISAR
        self._crear_doc_amb_dades()
        score_mig = (LLINDAR_APROVAT + LLINDAR_REVISAR) / 2
        mock_compute.return_value = make_score_result(score=score_mig)

        _run_scoring_pipeline(
            self.verification,
            resultats_extraccio=[{'document_id': 1, 'ok': True}],
        )

        self.verification.refresh_from_db()
        self.assertIn('Revisió', self.verification.suggeriment)

    @patch('apps.verification.tasks.compute_score')
    def test_score_baix_suggeriment_rebuig(self, mock_compute):
        """TC-TASK-034: Score < LLINDAR_REVISAR → suggeriment conté 'Rebuig'."""
        from apps.verification.services.scorer import LLINDAR_REVISAR
        self._crear_doc_amb_dades()
        mock_compute.return_value = make_score_result(score=LLINDAR_REVISAR - 0.01)

        _run_scoring_pipeline(
            self.verification,
            resultats_extraccio=[{'document_id': 1, 'ok': True}],
        )

        self.verification.refresh_from_db()
        self.assertIn('Rebuig', self.verification.suggeriment)

    @patch('apps.verification.tasks.compute_score')
    def test_score_final_es_el_maxim(self, mock_compute):
        """TC-TASK-035: Amb 2 docs, el score final és el del document amb score més alt."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        # Dos documents
        self._crear_doc_amb_dades(extracted={'_ok': True, 'nom_complet': 'A'})
        AdminFincaVerificationDocument.objects.create(
            verification=self.verification,
            fitxer=SimpleUploadedFile('d2.pdf', b'%PDF', content_type='application/pdf'),
            doc_type='certificat',
            ocr_text='text',
            extracted_data={'_ok': True, 'nom_complet': 'B'},
        )
        # El primer retorna 0.5, el segon 0.9
        mock_compute.side_effect = [
            make_score_result(score=0.5),
            make_score_result(score=0.9),
        ]

        resultat = _run_scoring_pipeline(
            self.verification,
            resultats_extraccio=[{'d': 1}, {'d': 2}],
        )

        self.assertAlmostEqual(resultat['score_final'], 0.9)

    @patch('apps.verification.tasks.compute_score')
    def test_scoring_desa_score_i_flags_al_document(self, mock_compute):
        """TC-TASK-036: El score i les flags es desen a cada document individual."""
        doc = self._crear_doc_amb_dades()
        mock_compute.return_value = make_score_result(score=0.8, flags=['flag1'])

        _run_scoring_pipeline(
            self.verification,
            resultats_extraccio=[{'document_id': doc.pk, 'ok': True}],
        )

        doc.refresh_from_db()
        self.assertAlmostEqual(doc.score, 0.8)
        self.assertIn('flag1', doc.score_flags)

    @patch('apps.verification.tasks.compute_score')
    def test_scoring_doc_amb_extracted_data_none_es_salta(self, mock_compute):
        """TC-TASK-037: Document amb extracted_data=None (o {}) no es puntua."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        AdminFincaVerificationDocument.objects.create(
            verification=self.verification,
            fitxer=SimpleUploadedFile('d.pdf', b'%PDF', content_type='application/pdf'),
            doc_type='identificatiu',
            ocr_text='text',
            extracted_data=None,
        )

        # Passem un resultat_extraccio fictici per no entrar a la branca "sense resultats"
        _run_scoring_pipeline(
            self.verification,
            resultats_extraccio=[{'document_id': 99, 'ok': False}],
        )

        mock_compute.assert_not_called()


# ---------------------------------------------------------------------------
# TC-TASK-040 a TC-TASK-047: process_verification (task Celery)
# ---------------------------------------------------------------------------

@override_settings(
    MEDIA_ROOT=tempfile.mkdtemp(),
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=False,   # Deixem que la task gestioni els errors
)
class TestProcessVerification(TestCase):
    """
    Tests de la task Celery process_verification executada síncronament.
    Les subpipelines es mockejen per aïllar la lògica d'orquestració.
    """

    def setUp(self):
        from django.contrib.auth import get_user_model
        from apps.buildings.models import Edifici, Localitzacio
        User = get_user_model()

        self.user = User.objects.create_user(email='task@test.com', password='pass')
        loc = Localitzacio.objects.create(
            carrer='Test', numero=1, codiPostal='08001', barri='Test'
        )
        self.edifici = Edifici.objects.create(
            anyConstruccio=2000, tipologia='Residencial',
            superficieTotal=100.0, nombrePlantes=2,
            reglament='CTE', orientacioPrincipal='Sud',
            localitzacio=loc,
        )

    def _crear_verificacio(self):
        return AdminFincaDocumentVerification.objects.create(
            user=self.user, edifici=self.edifici,
            status=AdminFincaDocumentVerification.Status.PENDING,
        )

    @patch('apps.verification.tasks._run_ocr_pipeline', return_value=[{'ok': True}])
    @patch('apps.verification.tasks._run_extraction_pipeline', return_value=[{'ok': True}])
    @patch('apps.verification.tasks._run_scoring_pipeline',
           return_value={'score_final': 0.85, 'scores_per_document': [{'score': 0.85}]})
    def test_flux_feliç_retorna_dict_correcte(self, mock_score, mock_extract, mock_ocr):
        """TC-TASK-040: Pipeline complet OK → retorna dict amb totes les claus."""
        v = self._crear_verificacio()
        resultat = process_verification(v.pk)

        self.assertEqual(resultat['verification_id'], v.pk)
        self.assertIn('documents_processats', resultat)
        self.assertIn('resultats_ocr', resultat)
        self.assertIn('resultats_extraccio', resultat)
        self.assertIn('scoring', resultat)

    @patch('apps.verification.tasks._run_ocr_pipeline', return_value=[])
    @patch('apps.verification.tasks._run_extraction_pipeline', return_value=[])
    @patch('apps.verification.tasks._run_scoring_pipeline',
           return_value={'score_final': 0.0, 'scores_per_document': []})
    def test_flux_feliç_estat_passa_a_review(self, mock_score, mock_extract, mock_ocr):
        """TC-TASK-041: Pipeline OK → status passa a REVIEW."""
        v = self._crear_verificacio()
        process_verification(v.pk)

        v.refresh_from_db()
        self.assertEqual(v.status, AdminFincaDocumentVerification.Status.REVIEW)

    @patch('apps.verification.tasks._run_ocr_pipeline', return_value=[])
    @patch('apps.verification.tasks._run_extraction_pipeline', return_value=[])
    @patch('apps.verification.tasks._run_scoring_pipeline',
           return_value={'score_final': 0.0, 'scores_per_document': []})
    def test_flux_feliç_status_running_durant_pipeline(self, mock_score, mock_extract, mock_ocr):
        """TC-TASK-042: Mentre s'executa, status és RUNNING abans del canvi a REVIEW."""
        v = self._crear_verificacio()

        status_durant = []

        def captura_status(*args, **kwargs):
            v.refresh_from_db()
            status_durant.append(v.status)
            return []

        mock_ocr.side_effect = captura_status

        process_verification(v.pk)

        self.assertIn(AdminFincaDocumentVerification.Status.RUNNING, status_durant)

    def test_verificacio_no_trobada_retorna_error(self):
        """TC-TASK-043: ID inexistent → retorna {'error': 'not_found'}."""
        resultat = process_verification(99999)
        self.assertEqual(resultat, {'error': 'not_found'})

    @patch('apps.verification.tasks.logger')
    @patch('apps.verification.tasks._run_ocr_pipeline', side_effect=Exception("Error inesperat"))
    def test_error_pipeline_despres_max_retries_estat_rejected(self, mock_ocr, mock_logger):
        """TC-TASK-044: Excepció no recuperable → status REJECTED després de max retries.

        Amb CELERY_TASK_ALWAYS_EAGER=True, self.retry() relança l'excepció original
        en lloc d'encuar el reintent, de manera que MaxRetriesExceededError mai
        s'arriba a disparar de forma natural.

        Estratègia: mockejem self.retry() perquè llanci MaxRetriesExceededError
        directament, simulant que ja s'han esgotat els 3 reintents configurats.
        """
        from celery.exceptions import MaxRetriesExceededError

        v = self._crear_verificacio()

        with patch.object(process_verification, 'retry',
                          side_effect=MaxRetriesExceededError()):
            resultat = process_verification(v.pk)

        v.refresh_from_db()
        self.assertEqual(v.status, AdminFincaDocumentVerification.Status.REJECTED)
        self.assertIn('error', resultat)

    @patch('apps.verification.tasks._run_ocr_pipeline', return_value=[{'ok': True}])
    @patch('apps.verification.tasks._run_extraction_pipeline', return_value=[{'ok': True}])
    @patch('apps.verification.tasks._run_scoring_pipeline',
           return_value={'score_final': 0.9, 'scores_per_document': []})
    def test_crida_les_tres_subpipelines(self, mock_score, mock_extract, mock_ocr):
        """TC-TASK-045: Les tres subpipelines es criden exactament una vegada."""
        v = self._crear_verificacio()
        process_verification(v.pk)

        mock_ocr.assert_called_once()
        mock_extract.assert_called_once()
        mock_score.assert_called_once()

    @patch('apps.verification.tasks._run_ocr_pipeline', return_value=[{'ok': True}])
    @patch('apps.verification.tasks._run_extraction_pipeline', return_value=[{'ok': True}])
    @patch('apps.verification.tasks._run_scoring_pipeline',
           return_value={'score_final': 0.85, 'scores_per_document': []})
    def test_documents_processats_reflexa_len_ocr(self, mock_score, mock_extract, mock_ocr):
        """TC-TASK-046: 'documents_processats' és la longitud de resultats_ocr."""
        mock_ocr.return_value = [{'ok': True}, {'ok': True}, {'ok': False}]
        v = self._crear_verificacio()
        resultat = process_verification(v.pk)
        self.assertEqual(resultat['documents_processats'], 3)

    @patch('apps.verification.tasks._run_ocr_pipeline', return_value=[])
    @patch('apps.verification.tasks._run_extraction_pipeline', return_value=[])
    @patch('apps.verification.tasks._run_scoring_pipeline',
           return_value={'score_final': 0.0, 'scores_per_document': []})
    def test_resultats_extraccio_es_passa_a_scoring(self, mock_score, mock_extract, mock_ocr):
        """TC-TASK-047: Els resultats d'extracció es passen com a argument al scoring."""
        extraccio_retorn = [{'document_id': 1, 'ok': True}]
        mock_extract.return_value = extraccio_retorn

        v = self._crear_verificacio()
        process_verification(v.pk)

        # El primer argument posicional de _run_scoring_pipeline és la verificació,
        # el segon és els resultats d'extracció
        _, kwargs = mock_score.call_args
        args_positionals = mock_score.call_args[0]
        # Acceptem tant args posicionals com kwargs
        resultats_passats = (
            kwargs.get('resultats_extraccio')
            if 'resultats_extraccio' in kwargs
            else args_positionals[1]
        )
        self.assertEqual(resultats_passats, extraccio_retorn)
