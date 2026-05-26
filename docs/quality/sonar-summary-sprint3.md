# SonarCloud summary Sprint 3

## Informacio general

Data: 25/05/2026
Branca: qa/backend-sonar-sprint3
Base: Desenvolupament actualitzat
Ambit: backend Django / DRF de BuildRank

## Estat inicial

El projecte no tenia configuracio previa de SonarCloud al repositori.
Durant aquesta fase hem creat el projecte Backend-BuildRank a SonarCloud dins l'organitzacio ScoreLab Team.

## Valors SonarCloud

- sonar.organization=scorelab-team
- sonar.projectKey=ScoreLab-Team_Backend-BuildRank

## Configuracio afegida

S'han afegit aquests fitxers:

- backend/sonar-project.properties
- .github/workflows/sonarcloud.yml
- docs/quality/sonar-summary-sprint3.md

El fitxer sonar-project.properties configura l'analisi del backend des de la carpeta backend, analitzant apps i config.

## Coverage

SonarCloud importa la cobertura des del report generat previament amb coverage.py:

- docs/testing/coverage/coverage.xml

Coverage backend disponible:

| Metrica | Resultat |
|---|---:|
| Tests backend | 751 |
| Coverage global | 91% |
| Statements analitzats | 13.483 |
| Statements no coberts | 1.249 |

## Workflow

El workflow .github/workflows/sonarcloud.yml executa l'analisi de SonarCloud en push i pull request contra Desenvolupament.

Per funcionar necessita el secret de GitHub Actions:

- SONAR_TOKEN

## Notes

- No es versiona cap token ni secret.
- El token queda configurat com a secret de GitHub Actions amb el nom SONAR_TOKEN.
- Si SonarCloud Automatic Analysis esta activat, cal desactivar-lo per utilitzar el workflow i importar coverage.
- La primera analisi automatica de SonarCloud no mostrava coverage perquè encara no estava configurada la importacio del coverage.xml.
- Com que el token s'ha vist en una captura, es recomana revocar-lo i generar-ne un de nou.
