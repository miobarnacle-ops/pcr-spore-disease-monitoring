// 引擎测试共享夹具：田块、规划结果、采样点、天气场景。
import type { PlanningResult, SamplingPoint, WeatherParams, Point } from "../../lib/inspection-engine";

export const FIELD_POLYGON: Point[] = [[0, 0], [80, 0], [80, 50], [0, 50]];

export function makePlanning(): PlanningResult {
  return {
    scale: 1,
    reference: [0, 0],
    rotationTheta: 0,
    rotationCenter: [0, 0],
    fieldPolygonMeters: FIELD_POLYGON,
    ridgeDatabase: {},
    roundNodes: [],
    roundTours: [],
    roundSegments: [],
    evaluationGrid: [],
    cumulativeConfidence: [],
    gridStepPx: 1,
    samplingPoints: [],
    coveragePct: 0,
    averageConfidence: 0,
    totalDistance: 0,
    totalTime: 0,
    candidateCount: 0,
  };
}

export function makeSamples(): SamplingPoint[] {
  return [
    { point_id: "s1", real_xy: [0, 0], x_m: 20, y_m: 25, ridge_idx: 0, round: 1, turbidity: 40, risk: "medium", read_time: "2026-08-27T10:00:00Z", pcr_ct: 28.5, pcr_conc: 4200, pcr_qual: "valid", pcr_gene: "ITS1-F/ITS4-R", pcr_verdict: "阳性" },
    { point_id: "s2", real_xy: [0, 0], x_m: 60, y_m: 30, ridge_idx: 1, round: 1, turbidity: 70, risk: "high", read_time: "2026-08-27T10:10:00Z", pcr_ct: 24.2, pcr_conc: 15000, pcr_qual: "valid", pcr_gene: "ITS1-F/ITS4-R", pcr_verdict: "阳性" },
    { point_id: "s3", real_xy: [0, 0], x_m: 40, y_m: 10, ridge_idx: 0, round: 1, turbidity: 22, risk: "low", read_time: "2026-08-27T10:20:00Z", pcr_ct: 33.8, pcr_conc: 900, pcr_qual: "doubtful", pcr_gene: "ITS1-F/ITS4-R", pcr_verdict: "阳性" },
    { point_id: "s4", real_xy: [0, 0], x_m: 55, y_m: 12, ridge_idx: 1, round: 2, turbidity: 55, risk: "medium", read_time: "2026-08-28T09:00:00Z", pcr_ct: 26.1, pcr_conc: 8200, pcr_qual: "valid", pcr_gene: "ITS1-F/ITS4-R", pcr_verdict: "阳性" },
    { point_id: "s5", real_xy: [0, 0], x_m: 12, y_m: 40, ridge_idx: 0, round: 2, turbidity: 18, risk: "low", read_time: "2026-08-28T09:10:00Z", pcr_ct: null, pcr_conc: null, pcr_qual: "pending", pcr_gene: null, pcr_verdict: "待定" },
  ];
}

/** 回归场景刻意带降雨 12mm，覆盖 rainWashout 参数化路径。 */
export function makeWeather(overrides: Partial<WeatherParams> = {}): WeatherParams {
  return {
    windSpeed: 3.5,
    windDirection: 135,
    temperature: 25,
    humidity: 75,
    cloud: 40,
    daytime: true,
    diseaseIndex: 45,
    lai: 3,
    plantHeight: 0.8,
    soilMoisture: 55,
    soilTemperature: 22,
    lightIntensity: 30000,
    rainfall: 12,
    leafWetness: 70,
    ...overrides,
  };
}
