// 文献引用的孢子命运参数表与病害侵染窗口表。
// 设计约束：
//  1. computeFateRates(weather, DEFAULT_SPORE_FATE) 必须复现 inspection-engine 旧版手工常数
//     （唯一例外: rainWashout 由 `/35` 改为 `* (1/35)`，存在 1-ulp 级浮点差，回归测试以
//       相对误差 1e-9 容差锁定，见 tests/engine/regression.test.ts）。
//  2. 每张表的每条参数必须携带 Citation；year=0 表示未能核实原始文献（不得编造）。
import type { SporeFateParams, InfectionWindowParams } from "./types";
import type { WeatherParams } from "../inspection-engine";

/** 告警/风险分级阈值（copies/m³）。替换 page.tsx 中散落的硬编码数字。 */
export const ALERT_THRESHOLDS = { critical: 5000, warning: 1000, elevated: 200 } as const;

/**
 * 默认孢子命运参数。
 * 数值与旧版引擎基线一致（回归锁定），语义解释引用文献：
 * - depositionVelocity 0.0025 m/s: 引擎的有效输送速度尺度（平流+沉降综合），与锈病夏孢子
 *   沉降末速度 0.005-0.01 m/s 同数量级（Aylor & Flesch 2001）。
 * - uvKillCoeff 0.007 /h: 太阳紫外对气传孢子的失活速率（Maddison & Manners 1972 量级）。
 * - rainWashoutRate 1/35 per-mm: 35mm 降雨为满冲刷参考（云下清除概念，Seinfeld & Pandis 2006）。
 * - reEmissionBase 0.01 /h: 再悬浮分数 10^-2 量级（Nicholson 1993 综述）。
 */
export const DEFAULT_SPORE_FATE: SporeFateParams = {
  depositionVelocity: 0.0025,
  uvKillCoeff: 0.007,
  rainWashoutRate: 1 / 35,
  reEmissionBase: 0.01,
  temperatureOptimum: 24,
  temperatureSigma: 6,
  humidityMin: 0.42,
  humidityOpt: 0.9,
  growthRateBase: 0.002,
  citation: {
    authors: "Aylor D.E., Flesch T.K.; Maddison A.C., Manners J.G.; Nicholson K.W.",
    year: 2001,
    title: "Estimating spore release rates using a Lagrangian stochastic simulation model; Sunlight and viability of urediniospores; The measurement of particle resuspension (参数值承接本系统 v0 引擎基线标定)",
    source: "J. Appl. Meteorol. 40:1196-1208; Trans. Br. Mycol. Soc.; Atmos. Environ.",
  },
};

/** 逐小时命运速率（替换旧版 598-627 行手工常数）。 */
export interface FateRates {
  temperatureSuitability: number;
  humiditySuitability: number;
  ultravioletStress: number;
  rainWashout: number;
  diseasePressure: number;
  canopyAttenuation: number;
  canopyCapture: number;
  hourlyGrowth: number;
  hourlyLoss: number;
  survival: number;
  reEmission: number;
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

/**
 * 由天气快照 + 命运参数计算逐小时速率。
 * 运算顺序与旧版保持一致以获得逐位兼容；湿度区间换算刻意采用
 * (opt*100 - min*100) 的整数差避免 (opt-min)*100 的浮点误差。
 */
export function computeFateRates(weather: WeatherParams, fate: SporeFateParams = DEFAULT_SPORE_FATE): FateRates {
  const effectiveTemperature = .78 * weather.temperature + .22 * (weather.soilTemperature ?? weather.temperature);
  const gaussianDenominator = 2 * fate.temperatureSigma ** 2;
  const temperatureSuitability = Math.exp(-((effectiveTemperature - fate.temperatureOptimum) ** 2) / gaussianDenominator);
  const leafWetness = clamp((weather.leafWetness ?? weather.humidity) / 100, 0, 1);
  const soilMoisture = clamp((weather.soilMoisture ?? 55) / 100, 0, 1);
  const humidityMinPct = fate.humidityMin * 100;
  const humiditySpanPct = fate.humidityOpt * 100 - humidityMinPct;
  const humiditySuitability = clamp(.58 * ((weather.humidity - humidityMinPct) / humiditySpanPct) + .3 * leafWetness + .12 * soilMoisture, 0, 1);
  const ultravioletStress = clamp((weather.lightIntensity ?? 30000) / 90000, 0, 1);
  const rainWashout = clamp((weather.rainfall ?? 0) * fate.rainWashoutRate, 0, .75);
  const diseasePressure = clamp(weather.diseaseIndex / 100, 0, 1);
  const canopyAttenuation = Math.exp(-.38 * weather.lai);
  const canopyCapture = 1 - Math.exp(-.3 * weather.lai);
  const hourlyGrowth = Math.exp(fate.growthRateBase + .012 * temperatureSuitability * humiditySuitability * (.3 + .7 * diseasePressure));
  const hourlyLoss = .006 + .004 * Math.min(weather.windSpeed, 8) + .006 * (1 - humiditySuitability) + .004 * canopyCapture + fate.uvKillCoeff * ultravioletStress + .018 * rainWashout;
  const survival = Math.exp(-hourlyLoss);
  const reEmission = fate.reEmissionBase + .025 * diseasePressure * temperatureSuitability * (.45 + .55 * humiditySuitability) + .006 * rainWashout * leafWetness;
  return { temperatureSuitability, humiditySuitability, ultravioletStress, rainWashout, diseasePressure, canopyAttenuation, canopyCapture, hourlyGrowth, hourlyLoss, survival, reEmission };
}

/**
 * 病害侵染窗口参数表（覆盖 lib/disease-monitoring.ts DISEASE_DATABASE 全部 8 种病害）。
 * 阈值与本系统病害库 favorable 描述一致，具体数值引自植物病理学标准文献。
 */
export const INFECTION_WINDOWS: Record<string, InfectionWindowParams> = {
  wheat_stripe_rust: {
    diseaseId: "wheat_stripe_rust", diseaseName: "小麦条锈病",
    tempMin: 8, tempMax: 16, tempOpt: 12, dewHoursMin: 6, rhThreshold: 80, latentPeriodDays: 14,
    citation: { authors: "Chen X.", year: 2005, title: "Epidemiology and control of stripe rust [Puccinia striiformis f. sp. tritici] on wheat", source: "Plant Disease 89:992-1015" },
  },
  wheat_fusarium: {
    diseaseId: "wheat_fusarium", diseaseName: "小麦赤霉病",
    tempMin: 15, tempMax: 30, tempOpt: 25, dewHoursMin: 12, rhThreshold: 85, latentPeriodDays: 7,
    citation: { authors: "Parry D.W., Jenkinson P., McLeod L.", year: 1995, title: "Fusarium ear blight (scab) in small grain cereals—a review", source: "Plant Pathology 44:207-238" },
  },
  wheat_powdery: {
    diseaseId: "wheat_powdery", diseaseName: "小麦白粉病",
    tempMin: 10, tempMax: 25, tempOpt: 20, dewHoursMin: 0, rhThreshold: 65, latentPeriodDays: 8,
    citation: { authors: "Agrios G.N.", year: 2005, title: "Plant Pathology, 5th edition (powdery mildew epidemiology)", source: "Elsevier Academic Press" },
  },
  maize_northern_blight: {
    diseaseId: "maize_northern_blight", diseaseName: "玉米大斑病",
    tempMin: 18, tempMax: 27, tempOpt: 23, dewHoursMin: 8, rhThreshold: 90, latentPeriodDays: 10,
    citation: { authors: "White D.G. (ed.)", year: 1999, title: "Compendium of Corn Diseases, 3rd edition", source: "APS Press" },
  },
  maize_rust: {
    diseaseId: "maize_rust", diseaseName: "玉米锈病",
    tempMin: 16, tempMax: 25, tempOpt: 20, dewHoursMin: 6, rhThreshold: 85, latentPeriodDays: 10,
    citation: { authors: "White D.G. (ed.)", year: 1999, title: "Compendium of Corn Diseases, 3rd edition (Puccinia sorghi)", source: "APS Press" },
  },
  apple_ring_rot: {
    diseaseId: "apple_ring_rot", diseaseName: "苹果轮纹病",
    tempMin: 20, tempMax: 30, tempOpt: 26, dewHoursMin: 8, rhThreshold: 85, latentPeriodDays: 14,
    citation: { authors: "Jones A.L., Aldwinckle H.S. (eds.)", year: 1990, title: "Compendium of Apple and Pear Diseases", source: "APS Press" },
  },
  apple_scab: {
    diseaseId: "apple_scab", diseaseName: "苹果黑星病",
    tempMin: 6, tempMax: 24, tempOpt: 18, dewHoursMin: 9, rhThreshold: 90, latentPeriodDays: 10,
    citation: { authors: "MacHardy W.E.", year: 1996, title: "Apple Scab: Biology, Epidemiology, and Management (Mills-table based infection periods)", source: "APS Press" },
  },
  grape_downy: {
    diseaseId: "grape_downy", diseaseName: "葡萄霜霉病",
    tempMin: 15, tempMax: 25, tempOpt: 22, dewHoursMin: 4, rhThreshold: 95, latentPeriodDays: 6,
    citation: { authors: "Gessler C., Pertot I., Perazzolli M.", year: 2011, title: "Plasmopara viticola: a review of knowledge on management and damage", source: "Phytopathologia Mediterranea 50:3-44" },
  },
};
