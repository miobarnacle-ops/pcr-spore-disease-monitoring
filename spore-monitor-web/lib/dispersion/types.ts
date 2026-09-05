// 孢子扩散引擎共享类型定义。
// 全部为 type/interface/纯类型导出，编译期擦除，不产生运行时依赖。
import type { ForecastResult, Point, SamplingPoint } from "../inspection-engine";

/** 文献引用条目。year=0 表示未能核实原始文献（报告中需注明，不得编造）。 */
export interface Citation {
  authors: string;
  year: number;
  title: string;
  source: string;
}

/** 单时刻风观测：预报第 hour 小时的风速(m/s)与风向(°，气象约定：来向，0=北)。 */
export interface WindReading {
  hour: number;
  speed: number;
  direction: number;
}

/** 风场时序（传感器/气象站导入）。缺省时引擎使用日变化合成风。 */
export type WindSeries = WindReading[];

/** 粒子滤波源项估计结果 —— 数字孪生闭环的输出。 */
export interface SourceEstimate {
  x: number;
  y: number;
  /** 释放速率，copies/s */
  strength: number;
  logStrengthMean: number;
  logStrengthStd: number;
  /** 后验不确定椭圆半轴（米） */
  sigmaX: number;
  sigmaY: number;
  confidence: "low" | "medium" | "high";
  obsCount: number;
}

/** 一个有效的 PCR 浓度观测点。 */
export interface ObservationPoint {
  x: number;
  y: number;
  /** copies/m³ */
  concentration: number;
  /** 观测质量权重 0-1（valid=1, doubtful=0.48） */
  quality: number;
}

export interface ParticleFilterConfig {
  /** 粒子数，默认 1000 */
  particleCount?: number;
  /** 观测噪声标准差（log10 数量级），默认 0.3 */
  sigmaObsLog?: number;
  /** log10(q) 先验均值，缺省取 log10(最大观测浓度) */
  priorStrengthLogMean?: number;
  /** log10(q) 先验标准差（数量级），默认 1.5 */
  priorStrengthLogStd?: number;
  /** 有效粒子数重采样阈值比例，默认 0.5 */
  resampleThreshold?: number;
  /** 随机种子，默认 42 */
  seed?: number;
}

export interface SourceBounds {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

/** 孢子命运参数（逐小时速率的参数化来源）。全部值须有文献依据。 */
export interface SporeFateParams {
  /** 沉降末速度 m/s（锈病夏孢子 25-30μm 约 0.005-0.01） */
  depositionVelocity: number;
  /** UV 存活衰减系数 per-hour */
  uvKillCoeff: number;
  /** 降雨冲刷系数 per-mm */
  rainWashoutRate: number;
  /** 再悬浮/再释放基础比例 per-hour */
  reEmissionBase: number;
  /** 孢子萌发适温 °C */
  temperatureOptimum: number;
  /** 适温高斯宽度 °C */
  temperatureSigma: number;
  /** 相对湿度下限（比例 0-1） */
  humidityMin: number;
  /** 相对湿度最适（比例 0-1） */
  humidityOpt: number;
  /** 基础小时增长率 */
  growthRateBase: number;
  citation: Citation;
}

/** 病害侵染窗口参数（植物病理学文献值）。 */
export interface InfectionWindowParams {
  diseaseId: string;
  diseaseName: string;
  /** 侵染适温下限 °C */
  tempMin: number;
  /** 侵染适温上限 °C */
  tempMax: number;
  /** 侵染最适温 °C */
  tempOpt: number;
  /** 所需叶面湿润持续小时数 */
  dewHoursMin: number;
  /** 相对湿度阈值 % */
  rhThreshold: number;
  /** 潜育期（天） */
  latentPeriodDays: number;
  citation: Citation;
}

/** runForecast 的可选扩展入参。全部缺省时行为与旧版逐位一致（回归锁保证）。 */
export interface ForecastOptions {
  windSeries?: WindSeries;
  source?: SourceEstimate;
  fate?: SporeFateParams;
}

/** 单小时气象（供侵染窗口判定）。 */
export interface HourlyWeather {
  hour: number;
  temperature: number;
  /** 相对湿度 % */
  humidity: number;
  /** 叶面湿润指示 0-1 */
  leafWetness: number;
}
export type WeatherSeries = HourlyWeather[];

/** 网格几何（FusionField / ForecastSlice 的公共子集，结构化兼容）。 */
export interface GridGeometry {
  grid: Point[];
  cols: number;
  rows: number;
  gridStep: number;
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
  inside: boolean[];
}

/** 某一预报期的逐格发病概率场。 */
export interface InfectionRiskField {
  grid: Point[];
  cols: number;
  rows: number;
  gridStep: number;
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
  inside: boolean[];
  /** 每格发病概率 0-1 */
  probabilities: number[];
  horizonDays: number;
  diseaseId: string;
  /** 该期内侵染窗口是否满足 */
  windowSatisfied: boolean;
  /** 窗口内累计叶面湿润小时数 */
  wetHours: number;
}

/** 单预报期的 A/B 对比指标（log10 空间，在观测点处计算）。 */
export interface AbComparisonSlice {
  horizonHours: number;
  obsCount: number;
  eulerRMSE: number;
  eulerBias: number;
  plumeRMSE: number;
  plumeBias: number;
}

export interface AbComparisonResult {
  source: SourceEstimate;
  plumeField: ForecastResult;
  slices: AbComparisonSlice[];
}

/** runDispersionForecast 编排入参。 */
export interface DispersionForecastOptions {
  /** 原始采样点（引擎内部提取有效 PCR 观测） */
  samples?: SamplingPoint[];
  hoursList?: number[];
  windSeries?: WindSeries;
  fate?: SporeFateParams;
  infection?: {
    diseaseId: string;
    horizons: number[];
  };
  compare?: boolean;
  pfConfig?: ParticleFilterConfig;
}

/** 统一编排输出包。 */
export interface DispersionForecastBundle {
  forecast: ForecastResult;
  sourceEstimate: SourceEstimate | null;
  infectionRisk: Record<number, InfectionRiskField>;
  comparison: AbComparisonResult | null;
  /** 实际参与同化的有效观测 */
  observations: ObservationPoint[];
}
