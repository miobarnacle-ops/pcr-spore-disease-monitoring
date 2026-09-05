// 风场时序解析与日变化气象合成。
// 无实测序列时，所有函数与旧版引擎的正弦摆动公式逐位一致（回归锁）。
import type { WeatherParams } from "../inspection-engine";
import type { WeatherSeries, WindReading, WindSeries } from "./types";

/** 旧版日变化摆动公式（缺省风向）。与旧引擎逐位一致。 */
export function syntheticDirection(baseDirection: number, hour: number): number {
  return (baseDirection + 13 * Math.sin(2 * Math.PI * hour / 24) + 5 * Math.sin(2 * Math.PI * hour / 8) + 360) % 360;
}

/** 最短角路径线性插值（350°→10° 经 0° 而非 180°）。 */
function lerpAngle(a: number, b: number, t: number): number {
  const delta = ((b - a + 540) % 360) - 180;
  return (a + delta * t + 360) % 360;
}

/** 在风序列上线性插值出第 hour 小时的风；越界取最近端点（不外推）。 */
export function interpolateWind(series: WindSeries | undefined, hour: number): WindReading | null {
  if (!series || !series.length) return null;
  const first = series[0], last = series[series.length - 1];
  if (hour <= first.hour) return { hour, speed: first.speed, direction: first.direction };
  if (hour >= last.hour) return { hour, speed: last.speed, direction: last.direction };
  for (let index = 0; index < series.length - 1; index++) {
    const a = series[index], b = series[index + 1];
    if (hour >= a.hour && hour <= b.hour) {
      const t = b.hour === a.hour ? 0 : (hour - a.hour) / (b.hour - a.hour);
      return { hour, speed: a.speed + (b.speed - a.speed) * t, direction: lerpAngle(a.direction, b.direction, t) };
    }
  }
  return null;
}

/** 解析第 hour 小时风向：有序列用序列（角度插值），否则用旧版摆动。 */
export function resolveWindDirection(baseDirection: number, hour: number, series?: WindSeries): number {
  if (!series || !series.length) return syntheticDirection(baseDirection, hour);
  return interpolateWind(series, hour)?.direction ?? syntheticDirection(baseDirection, hour);
}

/** 解析第 hour 小时风速：有序列用序列，否则恒定（与旧版一致：旧版只摆动方向不摆动风速）。 */
export function resolveWindSpeed(baseSpeed: number, hour: number, series?: WindSeries): number {
  if (!series || !series.length) return baseSpeed;
  return interpolateWind(series, hour)?.speed ?? baseSpeed;
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

/**
 * 由天气快照合成日变化气象序列（快照值按当日日均值解释）。
 * - 温度峰值取 14 时（sin 相位），日较差随云量减小而增大（3-7°C）；
 * - 湿度与温度反相（约 3.5%/°C），限制在 10-100%；
 * - 叶面湿润：夜间 20 时-次日 7 时结露底值 0.45，其余时段由湿度 (>87% 起露) 推算。
 * 白天窗口取 6-19 时的通用近似；该序列供侵染窗口（结露时长）判定使用。
 */
export function buildDiurnalWeather(weather: WeatherParams, hours: number): WeatherSeries {
  const cloudFactor = clamp((weather.cloud ?? 40) / 100, 0, 1);
  const amplitude = 3 + 4 * (1 - cloudFactor);
  const series: WeatherSeries = [];
  for (let hour = 0; hour < hours; hour++) {
    const phase = Math.sin(2 * Math.PI * (hour - 8) / 24);
    const temperature = weather.temperature + amplitude * phase;
    const humidity = clamp(weather.humidity - 3.5 * amplitude * phase, 10, 100);
    const nightDew = hour < 7 || hour >= 19 ? .45 : 0;
    const leafWetness = clamp(Math.max(nightDew, (humidity - 87) / 10), 0, 1);
    series.push({ hour, temperature, humidity, leafWetness });
  }
  return series;
}
