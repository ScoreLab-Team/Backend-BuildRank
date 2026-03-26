from django.test import TestCase

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from apps.buildings.models import Localitzacio, GrupComparable, TipusEdifici
from django.contrib.auth import get_user_model
from datetime import date
from apps.buildings.models import Edifici

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
        self.url = reverse('edifici-crear') 

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

    """
    Com de moment en aquest sprint la lliga no esta implementada, no es poden testejar aquestes features
    pero encara aixi els tests estan fets per complir amb la Definition of Done
    def test_get_queryset_filtra_per_liga(self):
        e1 = Edifici.objects.create(idEdifici="E1", liga="A", puntuacioBase=10)
        e2 = Edifici.objects.create(idEdifici="E2", liga="A", puntuacioBase=20)
        e3 = Edifici.objects.create(idEdifici="E3", liga="B", puntuacioBase=30)

        response = self.client.get(self.url, {'liga': 'A'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        ids = [e['idEdifici'] for e in response.data]
        self.assertIn("E1", ids)
        self.assertIn("E2", ids)
        self.assertNotIn("E3", ids) #Només haurien d'apareixer els edificis 1 i 2

    def test_get_queryset_ordenado_por_puntuacioBase_desc(self):
        Edifici.objects.create(idEdifici="E1", liga="A", puntuacioBase=10)
        Edifici.objects.create(idEdifici="E2", liga="A", puntuacioBase=30)
        Edifici.objects.create(idEdifici="E3", liga="A", puntuacioBase=20)

        response = self.client.get(self.url, {'liga': 'A'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        puntuacioBases = [e['puntuacioBase'] for e in response.data]

        self.assertEqual(puntuacioBases, sorted(puntuacioBases, reverse=True)) #Haurien d'estar ordenats de major a menor puntuacioBase

    def test_posicion_dentro_del_top(self):
        e1 = Edifici.objects.create(idEdifici="E1", liga="A", puntuacioBase=100)
        e2 = Edifici.objects.create(idEdifici="E2", liga="A", puntuacioBase=80)
        e3 = Edifici.objects.create(idEdifici="E3", liga="A", puntuacioBase=60)

        url = reverse('edifici-posicion', args=[e2.id])
        response = self.client.get(url, {'top': 2})

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data['posicion'], 2) #Hauria d'estar en posició 2
        self.assertTrue(response.data['esta_en_top']) #Hauria d'estar confirmat en el top
        self.assertEqual(response.data['puntos_para_top'], 0) #Com esta en el top hauria d'estar a 0 punts per el top

    def test_posicion_fuera_del_top(self):
        e1 = Edifici.objects.create(idEdifici="E1", liga="A", puntuacioBase=100)
        e2 = Edifici.objects.create(idEdifici="E2", liga="A", puntuacioBase=80)
        e3 = Edifici.objects.create(idEdifici="E3", liga="A", puntuacioBase=50)

        url = reverse('edifici-posicion', args=[e3.id])
        response = self.client.get(url, {'top': 2})

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data['posicion'], 3) #La posició hauria de ser 3
        self.assertFalse(response.data['esta_en_top']) #Com els args inclouen top 2 no hauria d'estar en el top
        self.assertEqual(response.data['puntos_para_top'], 30) #La diferencia entre el segon (80) i el terçer (50) es 30

    def test_posicion_top_mayor_que_total(self):
        e1 = Edifici.objects.create(idEdifici="E1", liga="A", puntuacioBase=100)

        url = reverse('edifici-posicion', args=[e1.id])
        response = self.client.get(url, {'top': 5})

        self.assertEqual(response.status_code, status.HTTP_200_OK) #Comprovar que no es trenca quan proves un top major que el numero d'edificis

        self.assertTrue(response.data['esta_en_top'])
        self.assertEqual(response.data['puntos_para_top'], 0)

    def test_posicion_solo_misma_liga(self):
        e1 = Edifici.objects.create(idEdifici="E1", liga="A", puntuacioBase=100)
        e2 = Edifici.objects.create(idEdifici="E2", liga="B", puntuacioBase=200)

        url = reverse('edifici-posicion', args=[e1.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data['posicion'], 1) #Comprovar que nomes mira el top en una mateixa lliga
    """