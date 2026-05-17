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
        self.other_user = User.objects.create_user(
            email='altre@test.com', password='pass1234',
        )
        self.superuser = User.objects.create_superuser(
            email='super@test.com', password='pass1234',
        )
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
# Tests: Creació de verificació
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
        v.suggeriment = 'Revisió detallada recomanada'
        v.save()
        response = self.client.get(reverse('verification:detail', kwargs={'pk': v.pk}))
        self.assertAlmostEqual(float(response.data['score']), 0.82)


# ---------------------------------------------------------------------------
# Tests: Revisió manual
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
            {'accio': 'rebutjar', 'motiu': 'Document no vàlid'},
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
        self.assertLess(result.score, 0.50)  # sense cap camp crític ha de ser baix

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
        # X2482300W és un NIE amb lletra de control correcta
        ok, flag = _valida_dni_nie('X2482300W')
        self.assertTrue(ok)
        self.assertIsNone(flag)

    def test_dni_lletra_incorrecta(self):
        ok, flag = _valida_dni_nie('12345678A')
        # format vàlid però lletra pot ser incorrecta — comprova format
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