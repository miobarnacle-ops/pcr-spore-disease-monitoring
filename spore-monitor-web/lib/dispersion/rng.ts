// 确定性随机数工具：粒子滤波的重采样与先验采样全部经由种子 RNG，
// 保证同一输入下结果完全可复现（测试与现场演示的前提）。

export type Rng = () => number;

/** mulberry32 — 32 位种子 PRNG，质量满足蒙特卡洛滤波用途，速度极快。 */
export function mulberry32(seed: number): Rng {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Box-Muller 变换：由均匀 RNG 生成标准正态样本。 */
export function standardNormal(rng: Rng): number {
  let u = 0;
  let v = 0;
  while (u === 0) u = rng();
  while (v === 0) v = rng();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

/** 均匀区间采样 [min, max)。 */
export function uniform(rng: Rng, min: number, max: number): number {
  return min + (max - min) * rng();
}
