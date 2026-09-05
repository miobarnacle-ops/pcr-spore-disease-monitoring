"""Pydantic v2 schema models for the offline dispersion pipeline.

Every model emits camelCase JSON (matching lib/dispersion/types.ts) via
`alias_generator=to_camel`, accepts both snake_case and camelCase input
(`populate_by_name=True`), and rejects unknown fields (`extra="forbid"`).
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class Citation(CamelModel):
    authors: str
    year: int
    title: str
    source: str


class SporeFateParams(CamelModel):
    deposition_velocity: float = 0.0025
    uv_kill_coeff: float = 0.007
    rain_washout_rate: float = 1 / 35
    re_emission_base: float = 0.01
    temperature_optimum: float = 24
    temperature_sigma: float = 6
    humidity_min: float = 0.42
    humidity_opt: float = 0.9
    growth_rate_base: float = 0.002
    citation: Citation


class InfectionWindowParams(CamelModel):
    disease_id: str
    disease_name: str
    temp_min: float
    temp_max: float
    temp_opt: float
    dew_hours_min: float
    rh_threshold: float
    latent_period_days: float
    citation: Citation


class FitReport(CamelModel):
    rmse_log10: float
    bias_log10: float
    n_observations: int
    relative_errors: dict[str, float]


class FateParamsArtifact(CamelModel):
    defaults: SporeFateParams
    calibrated: SporeFateParams
    fit_report: FitReport


class InfectionWindowsArtifact(CamelModel):
    diseases: list[InfectionWindowParams]


class ABModelMetrics(CamelModel):
    rmse_log10: float
    bias_log10: float


class ABHorizonResult(CamelModel):
    horizon_hours: int
    n_observations: int
    gaussian: ABModelMetrics
    eulerian: ABModelMetrics


class ABResultsArtifact(CamelModel):
    horizons: list[ABHorizonResult]
    config: dict[str, float | int]
    notes: str


# --- Default fate parameters (TS engine baseline, regressions-locked) ---

FATE_CITATION = Citation(
    authors="Aylor D.E.; Maddison A.C., Manners J.G.; Nicholson K.W.",
    year=2001,
    title="Estimating spore release rates using a Lagrangian stochastic simulation model; "
    "Sunlight and viability of urediniospores; particle resuspension "
    "(values inherit v0 engine baseline calibration)",
    source="J. Appl. Meteorol. 40:1196-1208; Trans. Br. Mycol. Soc.; Atmos. Environ.",
)

DEFAULT_FATE = SporeFateParams(
    deposition_velocity=0.0025,
    uv_kill_coeff=0.007,
    rain_washout_rate=1 / 35,
    re_emission_base=0.01,
    temperature_optimum=24,
    temperature_sigma=6,
    humidity_min=0.42,
    humidity_opt=0.9,
    growth_rate_base=0.002,
    citation=FATE_CITATION,
)

# --- Infection window parameters (8 diseases, plant-pathology literature) ---

INFECTION_WINDOWS: list[InfectionWindowParams] = [
    InfectionWindowParams(
        disease_id="wheat_stripe_rust",
        disease_name="小麦条锈病",
        temp_min=8, temp_max=16, temp_opt=12,
        dew_hours_min=6, rh_threshold=80, latent_period_days=14,
        citation=Citation(
            authors="Chen X.", year=2005,
            title="Epidemiology and control of stripe rust [Puccinia striiformis f. sp. tritici] on wheat",
            source="Plant Disease 89:992-1015",
        ),
    ),
    InfectionWindowParams(
        disease_id="wheat_fusarium",
        disease_name="小麦赤霉病",
        temp_min=15, temp_max=30, temp_opt=25,
        dew_hours_min=12, rh_threshold=85, latent_period_days=7,
        citation=Citation(
            authors="Parry D.W. et al.", year=1995,
            title="Fusarium ear blight (scab) in small grain cereals: a review",
            source="Plant Pathology 44:207-238",
        ),
    ),
    InfectionWindowParams(
        disease_id="wheat_powdery",
        disease_name="小麦白粉病",
        temp_min=10, temp_max=25, temp_opt=20,
        dew_hours_min=0, rh_threshold=65, latent_period_days=8,
        citation=Citation(
            authors="Agrios G.N.", year=2005,
            title="Plant Pathology, 5th edition (powdery mildew epidemiology)",
            source="Plant Pathology 5th ed Elsevier",
        ),
    ),
    InfectionWindowParams(
        disease_id="maize_northern_blight",
        disease_name="玉米大斑病",
        temp_min=18, temp_max=27, temp_opt=23,
        dew_hours_min=8, rh_threshold=90, latent_period_days=10,
        citation=Citation(
            authors="White D.G. ed.", year=1999,
            title="Compendium of Corn Diseases",
            source="Compendium of Corn Diseases APS Press",
        ),
    ),
    InfectionWindowParams(
        disease_id="maize_rust",
        disease_name="玉米锈病",
        temp_min=16, temp_max=25, temp_opt=20,
        dew_hours_min=6, rh_threshold=85, latent_period_days=10,
        citation=Citation(
            authors="White D.G. ed.", year=1999,
            title="Compendium of Corn Diseases (Puccinia sorghi)",
            source="Compendium of Corn Diseases APS Press",
        ),
    ),
    InfectionWindowParams(
        disease_id="apple_ring_rot",
        disease_name="苹果轮纹病",
        temp_min=20, temp_max=30, temp_opt=26,
        dew_hours_min=8, rh_threshold=85, latent_period_days=14,
        citation=Citation(
            authors="Jones A.L. Aldwinckle H.S. eds.", year=1990,
            title="Compendium of Apple and Pear Diseases",
            source="Compendium of Apple and Pear Diseases APS Press",
        ),
    ),
    InfectionWindowParams(
        disease_id="apple_scab",
        disease_name="苹果黑星病",
        temp_min=6, temp_max=24, temp_opt=18,
        dew_hours_min=9, rh_threshold=90, latent_period_days=10,
        citation=Citation(
            authors="MacHardy W.E.", year=1996,
            title="Apple Scab: Biology, Epidemiology, and Management",
            source="Apple Scab: Biology Epidemiology and Management APS Press",
        ),
    ),
    InfectionWindowParams(
        disease_id="grape_downy",
        disease_name="葡萄霜霉病",
        temp_min=15, temp_max=25, temp_opt=22,
        dew_hours_min=4, rh_threshold=95, latent_period_days=6,
        citation=Citation(
            authors="Gessler C. Pertot I. Perazzolli M.", year=2011,
            title="Plasmopara viticola: a review of knowledge on management and damage",
            source="Phytopathologia Mediterranea 50:3-44",
        ),
    ),
]
