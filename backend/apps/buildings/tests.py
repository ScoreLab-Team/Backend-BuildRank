from django.test import TestCase

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from apps.buildings.models import Localitzacio, GrupComparable, TipusEdifici
from django.contrib.auth import get_user_model
from datetime import date

User = get_user_model()

class EdificiAPITests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(email='test@example.com', password='password123')
        self.client.force_authenticate(user=self.user)

        self.grup = GrupComparable.objects.create(
            idGrup=1,
            zonaClimatica="C2",
            tipologia=TipusEdifici.RESIDENCIAL,
            rangSuperficie="0-100"
        )

        # Creem una localització base per als tests de creació d'edificis
        self.loc = Localitzacio.objects.create(
            carrer="Carrer de Prova",
            numero=10,
            codiPostal="08001",
            barri="Test",
            latitud=41.0,
            longitud=2.0,
            zonaClimatica="C2"
        )
        self.url = reverse('edifici-list') 

    def test_error_camps_obligatoris_buits(self):
        """
        Verifica que la API devuelve errores cuando los campos obligatorios no se envían.
        """
        # Solo enviamos campos opcionales o algunos no requeridos
        data = {
            "anyConstruccio": 2010,
            "superficieTotal": 150.0
            # No enviamos tipologia, reglament ni orientacioPrincipal
        }
        response = self.client.post(self.url, data)

        # Debe devolver 400 Bad Request
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Comprobamos los campos obligatorios que faltan
        self.assertIn('tipologia', response.data)
        self.assertIn('reglament', response.data)
        self.assertIn('orientacioPrincipal', response.data)

        # Opcional: verificar que el código de error es 'required'
        self.assertEqual(response.data['tipologia'][0].code, 'required')
        self.assertEqual(response.data['reglament'][0].code, 'required')
        self.assertEqual(response.data['orientacioPrincipal'][0].code, 'required')

    def test_error_any_construccio_futur(self):
        data = {
            "idEdifici": "ERR_ANY",
            "anyConstruccio": 2099,
            "tipologia": "Residencial",
            "superficieTotal": 100.0,
            "orientacioPrincipal": "Nord",
            "puntuacioBase": 0,
            "localitzacio": self.loc.id,
            "grupComparable": self.grup.id
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("anyConstruccio", response.data)

    def test_error_superficie_negativa(self):
        data = {
            "idEdifici": "ERR_SUP",
            "anyConstruccio": 2000,
            "tipologia": "Residencial",
            "superficieTotal": -5.0, # Valor fora de rang
            "orientacioPrincipal": "Sud",
            "puntuacioBase": 0,
            "localitzacio": self.loc.id
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("La superfície total ha de ser més gran que 0", str(response.data['superficieTotal']))

    def test_error_codi_postal_invalid(self):
        url_loc = reverse('localitzacio-list')
        data = {
            "carrer": "Carrer Fals",
            "numero": 123,
            "codiPostal": "0801", # Només 4 dígits, hauria de fallar
            "barri": "Test",
            "latitud": 0,
            "longitud": 0,
            "zonaClimatica": "X"
        }
        response = self.client.post(url_loc, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("codiPostal", response.data)