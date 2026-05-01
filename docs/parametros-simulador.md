# Parámetros del Simulador (Modelo Simplificado y Rápido)

Este documento define un modelo de simulación simplificado para US29.
Objetivo: obtener resultados útiles y trazables sin resolver física avanzada (termodinámica, CFD, simulación horaria completa).

> **Alcance MVP**: Este simulador no sustituye una auditoría energética profesional. Los
> resultados son **estimaciones orientativas** para comparación de escenarios y apoyo a la decisión.
> No se han usado presupuestos reales por edificio, sino valores medios de mercado. Véase
> `docs/decicions.txt` para las fuentes de referencia y el criterio de elección de los valores.

## 0) Modos de simulación

El motor opera en dos modos:

| Modo | Comportamiento |
|---|---|
| Preview | Calcula el escenario antes/después sin persistir nada en la base de datos. |
| Guardar | Crea un `SimulacioMillora` (versión motor `SIM-1.0`) y sus `SimulacioMilloraItem` por cada mejora. |

En modo preview, el backend devuelve el resultado JSON directamente sin escribir ningún registro.
En modo guardar, cada mejora genera un `SimulacioMilloraItem` con su desglose parcial,
lo que permite consultar el historial y auditar qué impacto proviene de cada actuación.

Estructura de petición del frontend (ambos modos):

```json
{
  "descripcio": "Simulació edifici Mallorca",
  "millores": [
    { "milloraId": 1, "coberturaPercent": 100 },
    { "milloraId": 8, "coberturaPercent": 60 }
  ]
}
```

El backend calcula y devuelve: coste estimado total, reducción de consumo prevista, reducción de emisiones
prevista, ahorro anual estimado, incremento de puntuación, resultado antes/después e ítems parciales
por cada mejora.

## 1) Principios del modelo

- Rápido: cálculo en milisegundos con operaciones algebraicas simples.
- Explicable: cada resultado sale de una fórmula corta y auditable.
- Acotado: nunca permite ahorros imposibles (ni consumos negativos).
- Versionable: los factores se congelan por versión de motor y catálogo.
- Calibrable: los coeficientes pueden ajustarse con datos reales sin reescribir el motor.

## 2) Variables base de entrada

Variables mínimas por edificio:

- consum_electric_kwh_any
- consum_gas_kwh_any
- emissions_kgco2_any (opcional, se puede recalcular)
- superficie_facana_m2
- superficie_coberta_m2
- nombre_habitatges
- barri (para sombras)
- bhs_actual
- certificat_energetic_actual (A..G)

Variables globales (contexto):

- preu_electricitat_eur_kwh (por defecto 0.22, fallback motor; fuente mercado: ~0.22-0.25 €/kWh en Barcelona)
- preu_gas_eur_kwh (por defecto 0.09)
- factor_emissio_electricitat_kg_kwh (por defecto 0.18)
- factor_emissio_gas_kg_kwh (por defecto 0.20)
- radiacio_bcn_kwh_kwp_any (por defecto 1300)
- preu_compensacio_excedent_eur_kwh (por defecto 0.10)
- percent_ibi_bonificable (por defecto 0.50)
- ibi_anual_eur (si aplica bonificación)
- consum_kwh_m2_any_fallback (por defecto 110.0, hipótesis MVP cuando no hay datos reales de vivienda)

## 3) Convenciones para coberturas y factores

- Toda cobertura de usuario entra en percent (0..100) y se transforma a ratio:
  - cobertura = cobertura_percent / 100
- Todos los factores multiplicativos se acotan:
  - min_factor = 0
  - max_factor = 1.5 (solo para factores de aumento)
- Toda reducción se acota para evitar imposibles:
  - reduccion_final = clamp(reduccion_calculada, 0, reduccion_maxima_uso)

Función clamp:

- clamp(x, a, b) = max(a, min(x, b))

## 4) Fórmula general de impacto por mejora

Para mejoras de reducción de demanda/consumo:

- impacte_efectiu = factor_base * cobertura * factor_sinergia * factor_calitat_execucio
- estalvi_kwh = consum_referent_kwh * impacte_efectiu

Donde:

- factor_base: viene de parametres_base de la mejora.
- cobertura: proporción aplicada (0..1).
- factor_sinergia: corrige solapamiento con otras mejoras (por defecto 1.0).
- factor_calitat_execucio: por defecto 0.90 si no hay auditoría técnica, 1.0 si validada.

## 5) Fotovoltaica simplificada (detalle completo)

1. Potencia instalable

- kwp_instalats = superficie_panells_m2 * densitat_kwp_m2
- densitat_kwp_m2 por defecto: 0.20 kwp/m2

2. Producción teórica anual

- produccio_teorica_kwh_any = kwp_instalats * radiacio_bcn_kwh_kwp_any

3. Pérdidas del sistema

- factor_perdua_conversion (inversor+cableado+temperatura): por defecto 0.86
- factor_inclinacio_orientacio: tabla según orientación/inclinación
- factor_ombres = factor_ombra_per_barri * factor_ombra_local

4. Producción neta anual

- produccio_neta_kwh_any = produccio_teorica_kwh_any * factor_perdua_conversion * factor_inclinacio_orientacio * factor_ombres

5. Reparto autoconsumo/excedente

- autoconsum_directe_kwh = produccio_neta_kwh_any * percent_autoconsum_directe
- excedent_kwh = produccio_neta_kwh_any - autoconsum_directe_kwh

6. Valor económico anual

- estalvi_autoconsum_eur = autoconsum_directe_kwh * preu_electricitat_eur_kwh
- compensacio_excedent_eur = excedent_kwh * preu_compensacio_excedent_eur_kwh
- benefici_fv_anual_eur = estalvi_autoconsum_eur + compensacio_excedent_eur

Tabla recomendada de factor_inclinacio_orientacio:

- sur 30-35 grados: 1.00
- sureste/suroeste 20-40 grados: 0.95
- este/oeste 15-35 grados: 0.90
- norte: 0.75
- inclinación subóptima extrema: multiplicar por 0.85 adicional

Tabla recomendada de factor_ombra_per_barri (Barcelona):

- eixample: 0.85
- ciutat_vella: 0.80
- gracia: 0.88
- sant_marti: 0.91
- nou_barris: 0.94
- por defecto ciudad: 0.90

## 6) Envolvente (aislamiento, ventanas, infiltraciones)

Aplicar sobre consumos térmicos de referencia (si no hay desglose fino):

- consum_termic_ref_kwh = consum_gas_kwh_any + (consum_electric_kwh_any * fraccio_electric_termica)
- fraccio_electric_termica por defecto: 0.10

6.1 SATE fachada

- factor_base_calefaccio por defecto: 0.28
- estalvi_kwh_calefaccio = consum_termic_ref_kwh * factor_base_calefaccio * cobertura

6.2 Aislamiento interior

- factor_base_calefaccio por defecto: 0.18
- estalvi_kwh_calefaccio = consum_termic_ref_kwh * 0.18 * cobertura

6.3 Aislamiento cubierta

- factor_base_termic_global por defecto: 0.14
- estalvi_kwh_termic = consum_termic_ref_kwh * 0.14 * cobertura

6.4 Ventanas eficientes

- factor_base_termic_global por defecto: 0.12
- estalvi_kwh_termic = consum_termic_ref_kwh * 0.12 * cobertura

6.5 Estanqueidad/infiltraciones

- factor_base_termic_global por defecto: 0.08
- estalvi_kwh_termic = consum_termic_ref_kwh * 0.08 * cobertura

## 7) Electricidad interior (LED y control)

7.1 LED

- fraccio_illuminacio_sobre_electric por defecto: 0.16
- reduccio_led_sobre_illuminacio por defecto: 0.75
- estalvi_led_kwh = consum_electric_kwh_any * fraccio_illuminacio_sobre_electric * reduccio_led_sobre_illuminacio * cobertura

7.2 Control de iluminación

- reduccio_addicional_sobre_illuminacio por defecto: 0.18
- si hay LED aplicado, base_illuminacio = consum_post_led_illuminacio
- si no hay LED, base_illuminacio = consum_pre_illuminacio
- estalvi_control_kwh = base_illuminacio * reduccio_addicional_sobre_illuminacio * cobertura

## 8) Traducción rápida a BHS

- El motor acumula los `impactePunts` de cada mejora aplicada y los suma al score base del edificio.
- Regla de tope:
  - si bhs_actual >= 100 -> bhs_simulat = 100
  - en general -> bhs_simulat = clamp(score_base + impacte_total_punts, 0, 100)

## 9) Pipeline de cálculo (orden fijo)

1. Snapshot inicial (datos energéticos del edificio o fallback por superficie)
2. Aplicar envolvente (SATE/interior/cubierta/ventanas/infiltraciones)
3. Aplicar mejoras térmicas e iluminación
4. Aplicar fotovoltaica
5. Calcular emisiones
6. Calcular ahorro estimado
7. Recalcular BHS
8. Generar desglose por mejora

## 10) Reglas de robustez y UX

- Tiempo máximo de simulación objetivo: < 300 ms por escenario.
- Si falta un dato clave, usar valor por defecto + warning explícito.
- Nunca romper la simulación por un input parcial; degradar con suposiciones.
- Devolver siempre:
  - supuestos_usados
  - factores_aplicados
  - limites_activados
  - warnings

## 11) Estructura JSON de parámetros (para config central)

```json
{
  "motor_version": "SIM-1.0",
  "defaults": {
    "preu_electricitat_eur_kwh": 0.22,
    "preu_gas_eur_kwh": 0.09,
    "factor_emissio_electricitat": 0.18,
    "factor_emissio_gas": 0.20,
    "radiacio_bcn_kwh_kwp_any": 1300,
    "densitat_kwp_m2": 0.20,
    "factor_perdua_conversion_fv": 0.86,
    "percent_autoconsum_directe": 0.55,
    "preu_compensacio_excedent": 0.10,
    "fraccio_illuminacio": 0.16,
    "reduccio_led": 0.75,
    "reduccio_control_illum": 0.18,
    "epsilon_divisio": 0.000001
  },
  "ombres_barri": {
    "eixample": 0.85,
    "ciutat_vella": 0.80,
    "gracia": 0.88,
    "sant_marti": 0.91,
    "nou_barris": 0.94,
    "default": 0.90
  }
}
```

## 12) Calibración recomendada (post-lanzamiento)

- Recoger facturas antes/después (12 meses) para edificios con mejoras reales.
- Calcular error relativo por tipología de mejora.
- Ajustar factores base por regresión simple o escalado por categoría.
- Publicar nueva versión de parámetros:
  - catalog_version: 2026.04-bcn-c2-v1
  - motor_version: SIM-1.0 (actual) → SIM-1.1 cuando se recalibre

## 13) Límites de este modelo (declaración explícita)

Este simulador NO calcula:

- dinámica horaria completa HVAC
- puentes térmicos con geometría 3D
- microclima por calle con trazado solar minuto a minuto
- comportamiento ocupacional estocástico avanzado

Este simulador SÍ ofrece:

- estimaciones consistentes entre escenarios
- comparación rápida de alternativas
- trazabilidad de cómo se ha calculado cada número
- apoyo para decisión preliminar técnica y económica

### Por qué se usan valores orientativos y no valores exactos

El sistema no dispone de los datos que se necesitarían para un cálculo exacto:

- facturas reales de energía
- consumo energético histórico completo por vivienda
- certificados energéticos oficiales para todos los casos
- inventario de instalaciones existente
- superficie real de fachada por edificio (con número de fachadas, altura, andamiaje necesario)
- presupuestos de empresas para cada obra
- condiciones de obra y estado previo de la fachada
- subvenciones aplicables para cada caso concreto

Por tanto, el motor aplica la fórmula:

```
cost_orientatiu = quantitat_estimada × costEstimatBase × cobertura
```

donde `costEstimatBase` es un valor medio de mercado (no un presupuesto). Los resultados se deben
leer como:

- **Sí**: estimación orientativa, escenario de comparación, apoyo a la decisión
- **No**: presupuesto final, certificación energética, auditoría profesional

Esta distinción evita dar una falsa sensación de precisión en una fase MVP.
