// 贝叶斯源项估计（SIR 粒子滤波）—— "孢子数字孪生" 同化层。
//
// 方法论：
// - 状态 θ = [x, y, log10(q)]（对数强度保证正值且先验取对数正态）。
// - 前向模型：解析高斯烟羽（闭式），单粒子单观测 O(1)；
//   与欧拉预报引擎同属高斯扩散族（稳态极限），后验自洽。2000 粒子 × 6 观测 < 50ms。
// - 似然：log10 空间高斯，σ_obs = 0.3 个数量级（对应 PCR 约 2 倍定量误差），
//   quality<1（doubtful）的观测 σ 加倍。
// - 静态状态单批后验：一次重要性加权即后验分布，随后计算加权矩。
//   不做无运动的重采样（静态参数重采样只会损失多样性，Doucet & Johansen 2011）；
//   N_eff 作为诊断量参与置信度评级。
import { gaussianPlume, qualityWeight } from "../inspection-engine";
import type { SamplingPoint, StabilityClass } from "../inspection-engine";
import type { ObservationPoint, ParticleFilterConfig, SourceBounds, SourceEstimate } from "./types";
import { mulberry32, standardNormal, uniform } from "./rng";

/** 从采样点提取有效 PCR 观测（排除无浓度/无效质量/非正值）。 */
export function extractObservations(samples: SamplingPoint[]): ObservationPoint[] {
  const valid = samples.filter(
    (sample): sample is SamplingPoint & { pcr_conc: number } =>
      sample.pcr_conc != null && sample.pcr_conc > 0 && qualityWeight(sample.pcr_qual) > 0,
  );
  return valid.map((sample) => ({
    x: sample.x_m,
    y: sample.y_m,
    concentration: sample.pcr_conc,
    quality: qualityWeight(sample.pcr_qual),
  }));
}

interface Particle {
  x: number;
  y: number;
  logQ: number;
  weight: number;
}

/**
 * 估计孢子源位置 (x, y) 与释放强度 q（copies/s）的后验分布。
 * 调用方保证 observations.length >= 2（单观测径向退化，逆问题病态）。
 */
export function estimateSource(
  observations: ObservationPoint[],
  bounds: SourceBounds,
  wind: number,
  direction: number,
  stability: StabilityClass,
  config: ParticleFilterConfig = {},
): SourceEstimate {
  if (observations.length < 2) throw new Error("源项估计需要至少 2 个有效 PCR 观测点（单观测径向退化）。");
  if (bounds.maxX <= bounds.minX || bounds.maxY <= bounds.minY) throw new Error("源搜索区域为空。");

  const particleCount = config.particleCount ?? 1000;
  const sigmaObsLog = config.sigmaObsLog ?? 0.3;
  const priorStrengthLogStd = config.priorStrengthLogStd ?? 1.5;
  const seed = config.seed ?? 42;
  const rng = mulberry32(seed);

  const obsLog = observations.map((obs) => Math.log10(Math.max(1, obs.concentration)));
  const priorStrengthLogMean = config.priorStrengthLogMean ?? Math.max(...obsLog);

  // 先验采样：位置均匀分布于搜索框，强度对数正态
  const particles: Particle[] = [];
  for (let index = 0; index < particleCount; index++) {
    particles.push({
      x: uniform(rng, bounds.minX, bounds.maxX),
      y: uniform(rng, bounds.minY, bounds.maxY),
      logQ: priorStrengthLogMean + standardNormal(rng) * priorStrengthLogStd,
      weight: 1 / particleCount,
    });
  }

  // 重要性加权（对数域防下溢，max-log 归一化）
  const logWeights: number[] = [];
  let maxLogWeight = -Infinity;
  for (const particle of particles) {
    let logWeight = 0;
    for (let obsIndex = 0; obsIndex < observations.length; obsIndex++) {
      const obs = observations[obsIndex];
      const predicted = Math.max(1, gaussianPlume(particle.x, particle.y, 10 ** particle.logQ, wind, direction, stability, obs.x, obs.y));
      const residual = obsLog[obsIndex] - Math.log10(predicted);
      const sigma = sigmaObsLog * (obs.quality < 1 ? 2 : 1);
      logWeight += -0.5 * (residual / sigma) ** 2;
    }
    logWeights.push(logWeight);
    if (logWeight > maxLogWeight) maxLogWeight = logWeight;
  }
  let weightSum = 0;
  for (let index = 0; index < particles.length; index++) {
    particles[index].weight = Math.exp(logWeights[index] - maxLogWeight);
    weightSum += particles[index].weight;
  }
  for (const particle of particles) particle.weight /= weightSum;

  // 有效粒子数（诊断量）
  let squareSum = 0;
  for (const particle of particles) squareSum += particle.weight ** 2;
  const effectiveCount = 1 / Math.max(squareSum, Number.EPSILON);

  // 加权后验矩
  let meanX = 0, meanY = 0, meanLogQ = 0;
  for (const particle of particles) {
    meanX += particle.weight * particle.x;
    meanY += particle.weight * particle.y;
    meanLogQ += particle.weight * particle.logQ;
  }
  let varianceX = 0, varianceY = 0, varianceLogQ = 0;
  for (const particle of particles) {
    varianceX += particle.weight * (particle.x - meanX) ** 2;
    varianceY += particle.weight * (particle.y - meanY) ** 2;
    varianceLogQ += particle.weight * (particle.logQ - meanLogQ) ** 2;
  }

  const obsCount = observations.length;
  const confidence: SourceEstimate["confidence"] =
    obsCount >= 4 && effectiveCount >= 0.5 * particleCount ? "high"
    : obsCount >= 3 && effectiveCount >= 0.25 * particleCount ? "medium"
    : "low";

  return {
    x: meanX,
    y: meanY,
    strength: 10 ** meanLogQ,
    logStrengthMean: meanLogQ,
    logStrengthStd: Math.sqrt(varianceLogQ),
    sigmaX: Math.sqrt(varianceX),
    sigmaY: Math.sqrt(varianceY),
    confidence,
    obsCount,
  };
}
