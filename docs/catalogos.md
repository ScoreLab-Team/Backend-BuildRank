# Catálogos US29 (Base Exhaustiva para Seed + Motor)

Este documento define un conjunto cerrado de catálogos para US29.
Los valores están pensados para Barcelona (zona climática C2) y pueden versionarse por fecha.

## 1) Esquema del modelo CatalegMillora (campos reales)

Campos del modelo Django (`apps/buildings/models.py`):

**Identificación**
- `idMillora` (AutoField, PK)
- `slug` (SlugField, único; identificador estable para seeds, frontend y motor)
- `nom` (CharField max 255)
- `descripcio` (TextField)
- `categoria` (enum: envolupant, instal_lacio_termica, renovables, electricitat, mobilitat, control_i_monitoratge)
- `activa` (BooleanField)

**Impacto y clasificación**
- `impactePunts` (FloatField) — puntos que aporta al ranking BuildRank
- `estalviEnergeticEstimat` (FloatField) — % de ahorro energético estimado (orientativo)
- `nivellConfianca` (enum: Baix, Mig, Alt)
- `costMinim`, `costMaxim` (FloatField) — rango de coste (campos heredados, conservados por compatibilidad)
- `roiEstimatAnys` (FloatField, nullable)

**Parametrización para US29 (motor de simulación)**
- `unitatBase` (enum: m2, unitat, kwp, kwh, habitatge, edifici)
- `costEstimatBase` (FloatField, EUR por unitatBase) — valor orientativo de mercado, no presupuesto oficial
- `mantenimentAnual` (FloatField, EUR/año por unitatBase)
- `vidaUtil` (IntegerField, años)
- `parametresBase` (JSONField) — parámetros técnicos que usa el motor (impactos, limitadores, kpi)

**Bloque legal**
- `ambit` (enum: Privat, Comu, Edifici)
- `requereixAcordComunitat` (BooleanField)
- `tipusAcordEstimat` (enum, ver modelo)
- `requereixLlicenciaMunicipal` (BooleanField)
- `requereixTecnicCompetent` (BooleanField)
- `requereixCeePrePost` (BooleanField) — Certificado Energético antes y después
- `bloquejadorsFrequents` (JSONField) — ej: edificio protegido, fachada catalogada

**Relaciones**
- `normativaAplicable` (M2M → Normativa)
- `ajudesDisponibles` (M2M → AjudaVigent)

Nota: el tipo de licencia municipal (assabentat / comunicat / llicencia_major) se documenta
dentro de `parametresBase["requisits"]["llicencia_per_defecte"]` para cada mejora concreta.

## 2) Catálogo maestro de mejoras (seed inicial recomendado)

### Fuentes de precios y criterio de elección (hipótesis MVP)

Los valores de `costEstimatBase` se han obtenido de referencias de mercado en España/Barcelona.
Se ha tomado un valor medio o conservador del rango disponible, nunca el mínimo absoluto. Todos son
hipótesis del MVP y deberían complementarse con presupuestos reales en versiones futuras.

| Mejora | Referencia de mercado | Criterio adoptado |
|---|---|---|
| Aislamiento exterior SATE | 70–120 €/m² (habitissimo.es); materiales 60–150 €/m² | 95 €/m² (punto medio del rango 70–120) |
| Ventanas PVC / doble vidrio | 450 € por ventana PVC 120×120 con doble vidrio; 590 € triple vidrio (Instal Tancaments) | 420 €/m² como valor unitario estándar |
| Fotovoltaica | 5.500–9.000 € por 5 kW; 6.000–8.000 € por 4,5–5,5 kWp (habitissimo.es) | 1.350 €/kWp (≈ 7.000 € por 5 kWp) |
| Aerotermia centralizada | 7.000–10.000 € por 80–100 m² (ERA architects) | 5.200 €/vivienda como reparto proporcional (referencia global: ~8.500 € por caso tipo) |
| Iluminación LED y sensores | Variable por punto de luz instalado (Barcelona Led) | coste por unidad instalada, no por pieza suelta |

### Impacto esperado por categoría de mejora

| Tipo de mejora | Impacto esperado | Justificación |
|---|---|---|
| Envolvente: SATE, ventanas | Alto | Reducen la demanda energética y mejoran el confort térmico |
| Instalación térmica: aerotermia | Alto | Puede reducir consumo y emisiones en climatización y ACS |
| Renovables: fotovoltaica | Alto / Medio | Reduce energía comprada a la red y emisiones asociadas |
| Iluminación LED y sensores | Bajo / Medio | Impacto menor en vivienda residencial; útil en zonas comunes |
| Monitorización / control BMS | Medio | Mejora la gestión y detección de consumo, pero depende del uso real |

La puntuación (`impactePunts`) no es una certificación energética oficial. Es un peso interno del
sistema BuildRank para convertir una mejora en un cambio estimado de ranking.

### 2.1 Tabla resumen

| id | slug | nom | categoria | unitat_base | costEstimatBase | mantenimentAnual | vidaUtil |
|---|---|---|---|---|---:|---:|---:|
| 1 | aillament-sate-facana | Aislamiento exterior SATE fachada | envolupant | m2 | 95.00 | 1.20 | 30 |
| 2 | aillament-interior-facana | Aislamiento interior fachada | envolupant | m2 | 70.00 | 1.00 | 25 |
| 3 | aillament-coberta | Aislamiento cubierta plana/inclinada | envolupant | m2 | 85.00 | 1.00 | 30 |
| 4 | finestres-eficients | Ventanas eficientes doble/triple vidrio | envolupant | m2 | 420.00 | 3.00 | 30 |
| 5 | estanquitat-infiltracions | Sellado infiltraciones y puentes térmicos | envolupant | m2 | 18.00 | 0.40 | 15 |
| 6 | illuminacio-led | Sustitución a LED | electricitat | unitat | 22.00 | 0.30 | 12 |
| 7 | control-illuminacio | Sensores presencia y regulación | control_i_monitoratge | unitat | 75.00 | 2.50 | 10 |
| 8 | plaques-solars-fotovoltaica | Instalación fotovoltaica autoconsumo | renovables | kwp | 1350.00 | 22.00 | 25 |
| 9 | solar-termica-acs | Solar térmica para ACS | renovables | m2 | 900.00 | 20.00 | 20 |
| 10 | aerotermia-centralitzada | Aerotermia centralizada | instal_lacio_termica | habitatge | 5200.00 | 95.00 | 18 |
| 11 | recuperador-calor-ventilacio | Ventilación con recuperador de calor | instal_lacio_termica | habitatge | 1600.00 | 45.00 | 15 |
| 12 | bomba-circulacio-alta-eficiencia | Bomba circulación alta eficiencia | instal_lacio_termica | unitat | 980.00 | 18.00 | 12 |
| 13 | punts-carrega-ve | Puntos de carga vehículo eléctrico | mobilitat | unitat | 1450.00 | 35.00 | 12 |
| 14 | monitoratge-energetic-bms | Monitorización energética BMS + subcontadores | control_i_monitoratge | edifici | 7800.00 | 260.00 | 12 |
| 15 | bateries-autoconsum | Batería para autoconsumo comunitario | renovables | kwh | 680.00 | 12.00 | 12 |

Nota: para id 15, unitat_base adicional requerida: kwh. Si se quiere mantener el enum cerrado, modelar batería en unitat y guardar capacidad en parametres_base.

### 2.2 Definición completa de parametres_base por mejora

Los siguientes bloques son directamente serializables en JSONField.

#### id=1, slug=aillament-sate-facana

```json
{
  "impactes": {
    "reduccio_demanda_calefaccio": 0.28,
    "reduccio_demanda_refrigeracio": 0.10,
    "reduccio_infiltracions": 0.08
  },
  "limitadors": {
    "cobertura_min": 0,
    "cobertura_max": 100,
    "solapable_amb": ["aillament-coberta", "finestres-eficients", "estanquitat-infiltracions"],
    "exclusiu_amb": ["aillament-interior-facana"]
  },
  "requisits": {
    "patrimoni_revisio_obligatoria": true,
    "llicencia_per_defecte": "comunicat"
  },
  "kpi": {
    "co2_factor_kg_per_kwh_estalviat": 0.18
  }
}
```

#### id=2, slug=aillament-interior-facana

```json
{
  "impactes": {
    "reduccio_demanda_calefaccio": 0.18,
    "reduccio_demanda_refrigeracio": 0.06,
    "reduccio_infiltracions": 0.04
  },
  "limitadors": {
    "cobertura_min": 0,
    "cobertura_max": 100,
    "solapable_amb": ["aillament-coberta", "finestres-eficients", "estanquitat-infiltracions"],
    "exclusiu_amb": ["aillament-sate-facana"]
  },
  "requisits": {
    "patrimoni_revisio_obligatoria": false,
    "llicencia_per_defecte": "assabentat"
  },
  "kpi": {
    "co2_factor_kg_per_kwh_estalviat": 0.18
  }
}
```

#### id=3, slug=aillament-coberta

```json
{
  "impactes": {
    "reduccio_demanda_calefaccio": 0.12,
    "reduccio_demanda_refrigeracio": 0.16
  },
  "limitadors": {
    "cobertura_min": 0,
    "cobertura_max": 100,
    "solapable_amb": ["aillament-sate-facana", "aillament-interior-facana", "finestres-eficients"],
    "exclusiu_amb": []
  },
  "requisits": {
    "patrimoni_revisio_obligatoria": true,
    "llicencia_per_defecte": "comunicat"
  },
  "kpi": {
    "co2_factor_kg_per_kwh_estalviat": 0.18
  }
}
```

#### id=4, slug=finestres-eficients

```json
{
  "impactes": {
    "reduccio_demanda_calefaccio": 0.15,
    "reduccio_demanda_refrigeracio": 0.07,
    "reduccio_infiltracions": 0.12,
    "millora_confort": 0.20
  },
  "limitadors": {
    "cobertura_min": 0,
    "cobertura_max": 100,
    "solapable_amb": ["aillament-sate-facana", "aillament-interior-facana", "estanquitat-infiltracions"],
    "exclusiu_amb": []
  },
  "requisits": {
    "patrimoni_revisio_obligatoria": true,
    "llicencia_per_defecte": "assabentat"
  },
  "kpi": {
    "co2_factor_kg_per_kwh_estalviat": 0.18
  }
}
```

#### id=5, slug=estanquitat-infiltracions

```json
{
  "impactes": {
    "reduccio_demanda_calefaccio": 0.08,
    "reduccio_demanda_refrigeracio": 0.03,
    "reduccio_infiltracions": 0.20
  },
  "limitadors": {
    "cobertura_min": 0,
    "cobertura_max": 100,
    "solapable_amb": ["aillament-sate-facana", "aillament-interior-facana", "finestres-eficients"],
    "exclusiu_amb": []
  },
  "requisits": {
    "patrimoni_revisio_obligatoria": false,
    "llicencia_per_defecte": "assabentat"
  },
  "kpi": {
    "co2_factor_kg_per_kwh_estalviat": 0.18
  }
}
```

#### id=6, slug=illuminacio-led

```json
{
  "impactes": {
    "reduccio_consum_illuminacio": 0.75,
    "reduccio_consum_electric_total_tipica": 0.12
  },
  "limitadors": {
    "cobertura_min": 0,
    "cobertura_max": 100,
    "solapable_amb": ["control-illuminacio", "monitoratge-energetic-bms"],
    "exclusiu_amb": []
  },
  "requisits": {
    "patrimoni_revisio_obligatoria": false,
    "llicencia_per_defecte": "assabentat"
  },
  "kpi": {
    "co2_factor_kg_per_kwh_estalviat": 0.18
  }
}
```

#### id=7, slug=control-illuminacio

```json
{
  "impactes": {
    "reduccio_consum_illuminacio_addicional": 0.18
  },
  "limitadors": {
    "cobertura_min": 0,
    "cobertura_max": 100,
    "solapable_amb": ["illuminacio-led", "monitoratge-energetic-bms"],
    "exclusiu_amb": []
  },
  "requisits": {
    "patrimoni_revisio_obligatoria": false,
    "llicencia_per_defecte": "assabentat"
  },
  "kpi": {
    "co2_factor_kg_per_kwh_estalviat": 0.18
  }
}
```

#### id=8, slug=plaques-solars-fotovoltaica

```json
{
  "impactes": {
    "produccio_kwh_per_kwp_any": 1300,
    "factor_perdues_sistema": 0.14,
    "factor_ombra_base": 0.90,
    "autoconsum_directe_base": 0.55,
    "excedent_compensat_base": 0.45
  },
  "limitadors": {
    "cobertura_min": 0,
    "cobertura_max": 100,
    "solapable_amb": ["bateries-autoconsum", "monitoratge-energetic-bms"],
    "exclusiu_amb": []
  },
  "requisits": {
    "patrimoni_revisio_obligatoria": true,
    "llicencia_per_defecte": "comunicat"
  },
  "kpi": {
    "co2_evitat_kg_per_kwh_fv": 0.18
  }
}
```

#### id=9, slug=solar-termica-acs

```json
{
  "impactes": {
    "reduccio_demanda_acs": 0.55,
    "fraccio_solar_acs_objetiu": 0.60
  },
  "limitadors": {
    "cobertura_min": 0,
    "cobertura_max": 100,
    "solapable_amb": ["aerotermia-centralitzada", "monitoratge-energetic-bms"],
    "exclusiu_amb": []
  },
  "requisits": {
    "patrimoni_revisio_obligatoria": true,
    "llicencia_per_defecte": "comunicat"
  },
  "kpi": {
    "co2_factor_kg_per_kwh_estalviat": 0.20
  }
}
```

#### id=10, slug=aerotermia-centralitzada

```json
{
  "impactes": {
    "substitucio_gas": 1.0,
    "cop_mitja": 3.2,
    "reduccio_emissions_calefaccio": 0.45,
    "reduccio_consum_primari_no_renovable": 0.30
  },
  "limitadors": {
    "cobertura_min": 0,
    "cobertura_max": 100,
    "solapable_amb": ["plaques-solars-fotovoltaica", "solar-termica-acs", "monitoratge-energetic-bms"],
    "exclusiu_amb": []
  },
  "requisits": {
    "patrimoni_revisio_obligatoria": false,
    "llicencia_per_defecte": "llicencia_major"
  },
  "kpi": {
    "co2_factor_kg_per_kwh_substituit": 0.20
  }
}
```

#### id=11, slug=recuperador-calor-ventilacio

```json
{
  "impactes": {
    "rendiment_recuperacio": 0.70,
    "reduccio_demanda_calefaccio": 0.10,
    "reduccio_demanda_refrigeracio": 0.04
  },
  "limitadors": {
    "cobertura_min": 0,
    "cobertura_max": 100,
    "solapable_amb": ["aillament-sate-facana", "aillament-interior-facana", "finestres-eficients"],
    "exclusiu_amb": []
  },
  "requisits": {
    "patrimoni_revisio_obligatoria": false,
    "llicencia_per_defecte": "comunicat"
  },
  "kpi": {
    "co2_factor_kg_per_kwh_estalviat": 0.18
  }
}
```

#### id=12, slug=bomba-circulacio-alta-eficiencia

```json
{
  "impactes": {
    "reduccio_consum_auxiliars_termics": 0.35
  },
  "limitadors": {
    "cobertura_min": 0,
    "cobertura_max": 100,
    "solapable_amb": ["aerotermia-centralitzada", "monitoratge-energetic-bms"],
    "exclusiu_amb": []
  },
  "requisits": {
    "patrimoni_revisio_obligatoria": false,
    "llicencia_per_defecte": "assabentat"
  },
  "kpi": {
    "co2_factor_kg_per_kwh_estalviat": 0.18
  }
}
```

#### id=13, slug=punts-carrega-ve

```json
{
  "impactes": {
    "increment_demanda_electrica_per_punt_kwh_any": 2200,
    "factor_flexibilitat_gestio_carrega": 0.25
  },
  "limitadors": {
    "cobertura_min": 0,
    "cobertura_max": 100,
    "solapable_amb": ["plaques-solars-fotovoltaica", "bateries-autoconsum", "monitoratge-energetic-bms"],
    "exclusiu_amb": []
  },
  "requisits": {
    "patrimoni_revisio_obligatoria": false,
    "llicencia_per_defecte": "comunicat"
  },
  "kpi": {
    "co2_evitat_mobilitat_si_substitueix_combustio": 0.35
  }
}
```

#### id=14, slug=monitoratge-energetic-bms

```json
{
  "impactes": {
    "reduccio_consum_total_per_optimitzacio": 0.08,
    "deteccio_anomalies": 0.15
  },
  "limitadors": {
    "cobertura_min": 0,
    "cobertura_max": 100,
    "solapable_amb": [
      "aillament-sate-facana",
      "aillament-interior-facana",
      "aillament-coberta",
      "finestres-eficients",
      "estanquitat-infiltracions",
      "illuminacio-led",
      "control-illuminacio",
      "plaques-solars-fotovoltaica",
      "solar-termica-acs",
      "aerotermia-centralitzada",
      "recuperador-calor-ventilacio",
      "bomba-circulacio-alta-eficiencia",
      "punts-carrega-ve",
      "bateries-autoconsum"
    ],
    "exclusiu_amb": []
  },
  "requisits": {
    "patrimoni_revisio_obligatoria": false,
    "llicencia_per_defecte": "assabentat"
  },
  "kpi": {
    "co2_factor_kg_per_kwh_estalviat": 0.18
  }
}
```

#### id=15, slug=bateries-autoconsum

```json
{
  "impactes": {
    "increment_autoconsum_directe": 0.20,
    "cicles_any": 280,
    "eficiencia_roundtrip": 0.90
  },
  "limitadors": {
    "cobertura_min": 0,
    "cobertura_max": 100,
    "solapable_amb": ["plaques-solars-fotovoltaica", "monitoratge-energetic-bms"],
    "exclusiu_amb": []
  },
  "requisits": {
    "patrimoni_revisio_obligatoria": false,
    "llicencia_per_defecte": "assabentat"
  },
  "kpi": {
    "co2_evitat_kg_per_kwh_desplacat": 0.18
  }
}
```

## 3) Catálogo de ayudas y marco legal (por mejora)

Formato recomendado para el campo ajudes_i_marcs_legals: markdown largo o JSON serializado con bloques.

### 3.1 Estructura recomendada

```json
{
  "next_generation": {
    "aplicable": true,
    "trams": [
      {"estalvi_min": 0.30, "subvencio_percent": 0.40},
      {"estalvi_min": 0.45, "subvencio_percent": 0.60},
      {"estalvi_min": 0.60, "subvencio_percent": 0.80}
    ],
    "observacions": "Subvención sobre coste elegible y con requisitos documentales"
  },
  "ibi_barcelona": {
    "aplicable": false,
    "percent_bonificacio": 0.50,
    "durada_anys": 3,
    "condicio": "Solo instalaciones renovables según ordenanza vigente"
  },
  "irpf_rehabilitacio": {
    "aplicable": true,
    "observacions": "Deducciones estatales según tipo de obra y ahorro"
  },
  "enllacos": [
    "https://habitatge.gencat.cat",
    "https://ajuntament.barcelona.cat",
    "https://www.idae.es"
  ]
}
```

### 3.2 Matriz aplicada a cada mejora

| slug | next_generation | ibi_barcelona | irpf_rehabilitacio | comentario legal principal |
|---|---|---|---|---|
| aillament-sate-facana | si | no | si | Revisar patrimonio y tratamiento de fachada |
| aillament-interior-facana | si | no | si | Alternativa en edificios protegidos |
| aillament-coberta | si | no | si | Puede requerir comunicado o licencia |
| finestres-eficients | si | no | si | En protegidos, limitaciones estéticas |
| estanquitat-infiltracions | si | no | si | Actuación menor habitual |
| illuminacio-led | si | no | si | Justificación energética fácil |
| control-illuminacio | si | no | si | Complemento a LED |
| plaques-solars-fotovoltaica | si | si | si | IBI 50% 3 años según ordenanza vigente |
| solar-termica-acs | si | potencial | si | Puede tener tratamiento municipal específico |
| aerotermia-centralitzada | si | no | si | Obra mayor en muchos casos |
| recuperador-calor-ventilacio | si | no | si | Puede requerir actuaciones en patios/fachada |
| bomba-circulacio-alta-eficiencia | si | no | si | Mejora de instalación común |
| punts-carrega-ve | no | no | no | Regido por normativa BT y comunidad |
| monitoratge-energetic-bms | no | no | no | Normalmente sin subvención directa general |
| bateries-autoconsum | si | potencial | si | A menudo vinculado a fotovoltaica |

## 4) Catálogo de normativa y comprobaciones automáticas

### 4.1 Reglas CTE DB-HE (motor de validación)

- regla_cte_01_envolupant:
  - aplica_a: aillament-sate-facana, aillament-interior-facana, aillament-coberta, finestres-eficients
  - condicion: transmitancia_resultant <= limit_cte_zona_c2
  - severidad: alta
  - mensaje_error: La solución no cumple mínimos CTE DB-HE para zona C2

- regla_cte_02_renovables_acs:
  - aplica_a: solar-termica-acs, aerotermia-centralitzada
  - condicion: cobertura_acs_renovable >= objectiu_cte
  - severidad: media
  - mensaje_error: Cobertura renovable ACS insuficiente

- regla_cte_03_rendiment_instal_lacio:
  - aplica_a: aerotermia-centralitzada
  - condicion: cop_mitja >= 3.0
  - severidad: alta
  - mensaje_error: COP inferior al mínimo requerido

### 4.2 Reglas ordenanzas Barcelona

- regla_bcn_01_patrimoni_facana:
  - aplica_a: aillament-sate-facana, finestres-eficients, plaques-solars-fotovoltaica
  - condicion: si edifici_protegit=true -> requiere informe patrimonio
  - severidad: alta

- regla_bcn_02_tipus_llicencia:
  - aplica_a: todas
  - condicion: mapear tipo de mejora a assabentat/comunicat/llicencia_major
  - severidad: media

- regla_bcn_03_ocupacio_coberta:
  - aplica_a: plaques-solars-fotovoltaica, solar-termica-acs
  - condicion: m2_instal_lats <= m2_coberta_disponible
  - severidad: alta

## 5) Catálogo de estados de workflow legal/documental

Estados cerrados para MilloraImplementada:

1. pendent_validacio
2. en_revisio
3. validada_oficial
4. rebutjada

Transiciones permitidas:

- pendent_validacio -> en_revisio
- en_revisio -> validada_oficial
- en_revisio -> rebutjada
- rebutjada -> pendent_validacio

Campos complementarios por estado:

- pendent_validacio:
  - documentacion_minima: presupuesto, memoria_tecnica, fotos
- en_revisio:
  - revisor_id, data_inici_revisio
- validada_oficial:
  - data_validacio, informe_validacio, impacte_bhs_aplicat
- rebutjada:
  - motiu_rebuig, comentaris_revisio, accions_requerides

## 6) Catálogo de parámetros globales del motor

Versionado recomendado: motor_version = "SIM-1.0" (versión actual del motor `engine.py`)

```json
{
  "motor_version": "SIM-1.0",
  "context_global": {
    "ciutat": "Barcelona",
    "zona_climatica": "C2",
    "preu_energia_kwh_electricitat": 0.22,
    "preu_energia_kwh_gas": 0.09,
    "factor_emissio_electricitat_kg_kwh": 0.18,
    "factor_emissio_gas_kg_kwh": 0.20,
    "inflacio_energetica_anual": 0.02,
    "taxa_descompte": 0.04,
    "preu_compensacio_excedent_kwh": 0.10,
    "radiacio_bcn_kwh_kwp_any": 1300,
    "factor_ombres_per_barri": {
      "eixample": 0.85,
      "ciutat_vella": 0.80,
      "sants_montjuic": 0.90,
      "sarria_sant_gervasi": 0.92,
      "gracia": 0.88,
      "horta_guinardo": 0.93,
      "nou_barris": 0.94,
      "sant_andreu": 0.93,
      "sant_marti": 0.91,
      "les_corts": 0.92
    }
  }
}
```

## 7) Catálogo de perfiles de consumo (load profiles)

Perfiles cerrados:

- residencial_estandard:
  - autoconsum_dia: 0.52
  - autoconsum_nit: 0.48
  - punta_horaria: 20:00-23:00

- residencial_envellit:
  - autoconsum_dia: 0.60
  - autoconsum_nit: 0.40
  - punta_horaria: 19:00-22:00

- mixt_residencial_comercial:
  - autoconsum_dia: 0.68
  - autoconsum_nit: 0.32
  - punta_horaria: 13:00-16:00

Uso en motor:

- para fotovoltaica, estimar autoconsum real = min(generacio_horaria, demanda_horaria)
- excedent = max(generacio_horaria - demanda_horaria, 0)
- benefici_net = autoconsum * preu_kwh + excedent * preu_compensacio

## 8) Catálogo de escenarios interactivos (US29-T2)

Escenarios cerrados:

1. autoconsum
- inputs: m2_plaques, orientacio, inclinacio, barri
- calculos: kwp_instalable, produccio_any, autoconsum_directe, excedent
- output principal: estalvi_economic_anual, co2_evitat, ROI

2. rehabilitacio_certificat
- inputs: lletra_actual, lletra_objectiu, paquet_millores
- calculos: reduccio_consum_primari, reduccio_emissions, estimacio_revaloritzacio_percent
- output principal: salt_certificat, impacte_valor_immoble

3. electrificacio
- inputs: percent_substitucio_gas, nombre_punts_carrega, potencia_contractada
- calculos: demanda_electrica_nova, demanda_gas_residual, canvis_emissions
- output principal: cost_energetic_nou, estalvi_o_sobrecost, impacte_CO2

## 9) Catálogo de deduplicación y límites físicos

Reglas cerradas para evitar sobreestimación:

- Regla de cobertura efectiva por vector energético:
  - cobertura_efectiva = min(1.0, suma_cobertures_ponderades)

- Regla de reducción máxima por uso:
  - calefaccio: reduccio_total <= 0.90
  - refrigeracio: reduccio_total <= 0.85
  - illuminacio: reduccio_total <= 0.90
  - ACS: reduccio_total <= 0.85

- Regla de exclusividad de soluciones incompatibles:
  - si existe mejora A y mejora B en exclusiu_amb -> mantener la de mayor impacto_coste_efectivo

- Regla edificio perfecto:
  - si bhs_actual >= 100 -> bhs_simulat = 100

## 10) Catálogo de persistencia de resultados (SimulacioMillora.resultat)

Estructura del campo `resultat` (JSONField) del modelo `SimulacioMillora`. El campo `hipotesiBase`
guarda una copia de los datos energéticos en el momento de la simulación (para reproducibilidad).

```json
{
  "motor_version": "SIM-1.0",
  "timestamp": "2026-04-21T00:00:00Z",
  "input": {
    "edifici_id": 123,
    "millores": [
      {"slug": "illuminacio-led", "cobertura_percent": 100},
      {"slug": "plaques-solars-fotovoltaica", "cobertura_percent": 60}
    ],
    "context_override": {
      "preu_energia_kwh_electricitat": 0.25
    }
  },
  "snapshot_abans": {
    "consum_kwh_any": 120000,
    "emissions_kgco2_any": 26000,
    "bhs": 57.4,
    "certificat_energetic": "E"
  },
  "resultat": {
    "consum_previst_kwh_any": 89000,
    "estalvi_kwh_any": 31000,
    "emissions_previstes_kgco2_any": 17400,
    "emissions_evitades_kgco2_any": 8600,
    "cost_total_inversio_eur": 142000,
    "estalvi_anual_eur": 12450,
    "manteniment_anual_total_eur": 940,
    "roi_simple_anys": 11.41,
    "roi_real_anys": 12.33,
    "nou_bhs": 71.8,
    "nou_certificat_energetic": "C",
    "benefici_net_amb_ajudes_eur": 48600
  },
  "desglossament_per_millora": [
    {
      "slug": "illuminacio-led",
      "cost_eur": 11000,
      "estalvi_kwh_any": 9000,
      "estalvi_eur_any": 2250,
      "co2_evitat_kg_any": 1620,
      "avisos_legals": []
    },
    {
      "slug": "plaques-solars-fotovoltaica",
      "cost_eur": 131000,
      "estalvi_kwh_any": 22000,
      "estalvi_eur_any": 10200,
      "co2_evitat_kg_any": 3960,
      "avisos_legals": ["Revisar ocupación de cubierta", "Tramitar bonificación IBI"]
    }
  ],
  "validacions": {
    "cte_ok": true,
    "ordenanca_ok": true,
    "errors": [],
    "warnings": ["Edificio en zona con sombras elevadas"]
  }
}
```

## 11) Catálogo de seeds mínimos obligatorios para US29-T1

Para cumplir US29-T1 como mínimo deben existir en base de datos:

1. aillament-sate-facana
2. finestres-eficients
3. plaques-solars-fotovoltaica
4. illuminacio-led
5. aerotermia-centralitzada

Y en todos ellos:

- costEstimatBase informado
- mantenimentAnual informado
- vidaUtil informado
- parametres_base con al menos un impacto cuantitativo
- ajudesDisponibles con al menos 1 AjudaVigent asociada (M2M)

## 12) Recomendación de versionado de catálogos

- catalog_version: "2026.04-bcn-c2-v1"
- motor_version: "SIM-1.0" (versión actual) → "SIM-1.1" cuando se recalibre
- estrategia:
  - congelar cálculos por versión
  - no recalcular simulaciones históricas con parámetros nuevos
  - permitir nueva simulación con versión actualizada
