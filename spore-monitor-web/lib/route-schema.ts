import type {
  PlanParams,
  PlanningResult,
  Point,
  SamplingPoint,
} from "./inspection-engine";

export type RouteWaypointType = "start" | "transit" | "sampling" | "turn" | "return";

export interface RouteWaypoint {
  seq: number;
  x_m: number;
  y_m: number;
  yaw_rad: number | null;
  type: RouteWaypointType;
  round: number;
  sample_id: string | null;
  ridge_idx?: number;
  speed_limit_mps: number;
  tolerance_m: number;
}

export interface RouteDocument {
  schema_version: "1.0";
  generated_at: string;
  frame_id: "field";
  coordinate_type: "local_enu";
  unit: "m";
  meta: {
    field_id: string;
    map_id: string;
    map_version: number;
    route_id: string;
    y_axis_positive: "field_interior";
  };
  coordinate_system: {
    origin_definition: "first_boundary_point";
    x_axis_definition: "first_boundary_edge";
    y_axis_definition: "field_interior_side";
    interior_sign: 1 | -1;
  };
  vehicle: {
    max_linear_mps: number;
    max_angular_radps: number;
    minimum_turn_radius_m: number;
  };
  field_polygon_m: Point[];
  sampling_points: Array<{
    sample_id: string;
    x_m: number;
    y_m: number;
    round: number;
    ridge_idx: number;
  }>;
  rounds: Array<{
    round: number;
    waypoint_start: number;
    waypoint_end: number;
    distance_m: number;
  }>;
  path: RouteWaypoint[];
  statistics: {
    coverage_pct: number;
    average_confidence: number;
    planned_distance_m: number;
    planned_time_s: number;
  };
}

export interface RouteValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
  stats: {
    waypoint_count: number;
    sampling_waypoint_count: number;
    path_distance_m: number;
    max_segment_m: number;
    max_speed_mps: number;
    sharp_turn_count: number;
    outside_waypoint_count: number;
  };
}

export interface BuildRouteOptions {
  fieldId?: string;
  mapId?: string;
  mapVersion?: number;
  routeId?: string;
  maxLinearMps?: number;
  maxAngularRadps?: number;
  minimumTurnRadiusM?: number;
}

function round(value: number, digits = 4) {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

function finite(value: number, name: string) {
  if (!Number.isFinite(value)) throw new Error(`${name} 必须是有限数值。`);
  return value;
}

function transformPixelToField(
  point: Point,
  reference: Point,
  theta: number,
  scale: number,
  interiorSign: 1 | -1,
): Point {
  const dx = (point[0] - reference[0]) / scale;
  const dy = (point[1] - reference[1]) / scale;
  return [
    round(Math.cos(theta) * dx + Math.sin(theta) * dy),
    round(interiorSign * (-Math.sin(theta) * dx + Math.cos(theta) * dy)),
  ];
}

function averageInteriorSign(polygon: Point[], reference: Point, theta: number, scale: number): 1 | -1 {
  const raw = polygon.map((point) => transformPixelToField(point, reference, theta, scale, 1)[1]);
  const mean = raw.reduce((sum, value) => sum + value, 0) / Math.max(1, raw.length);
  return mean >= 0 ? 1 : -1;
}

function distance(a: Point, b: Point) {
  return Math.hypot(a[0] - b[0], a[1] - b[1]);
}

function pointToSegmentDistance(point: Point, a: Point, b: Point) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const lengthSquared = dx * dx + dy * dy;
  if (lengthSquared <= 1e-12) return distance(point, a);
  const t = Math.max(0, Math.min(1, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / lengthSquared));
  return distance(point, [a[0] + t * dx, a[1] + t * dy]);
}

function pointInPolygon(point: Point, polygon: Point[]) {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [xi, yi] = polygon[i], [xj, yj] = polygon[j];
    const intersects = yi > point[1] !== yj > point[1] && point[0] < ((xj - xi) * (point[1] - yi)) / (yj - yi) + xi;
    if (intersects) inside = !inside;
  }
  return inside;
}

function nearestSampleId(round: number, nodeIndex: number) {
  return `R${round + 1}-P${nodeIndex + 1}`;
}

/** 将现有网页规划结果转换为 ROS/仿真可消费的米制路线文件。 */
export function buildRouteDocument(
  polygonPixels: Point[],
  planning: PlanningResult,
  samples: SamplingPoint[],
  params: PlanParams,
  options: BuildRouteOptions = {},
): RouteDocument {
  if (polygonPixels.length < 3) throw new Error("路线导出至少需要 3 个边界顶点。");
  finite(planning.scale, "规划比例尺");
  if (planning.scale <= 0) throw new Error("规划比例尺必须大于 0。");
  const interiorSign = averageInteriorSign(polygonPixels, planning.reference, planning.rotationTheta, planning.scale);
  const transform = (point: Point) => transformPixelToField(point, planning.reference, planning.rotationTheta, planning.scale, interiorSign);
  const fieldPolygon = polygonPixels.map(transform);
  const path: RouteWaypoint[] = [];
  const rounds: RouteDocument["rounds"] = [];

  const pushWaypoint = (point: Point, round: number, type: RouteWaypointType, sampleId?: string, ridgeIdx?: number) => {
    const previous = path.at(-1);
    const same = previous && Math.hypot(previous.x_m - point[0], previous.y_m - point[1]) < 0.001;
    if (same) {
      if (sampleId && previous) {
        previous.type = type;
        previous.sample_id = sampleId;
        previous.ridge_idx = ridgeIdx;
      }
      return previous;
    }
    const waypoint: RouteWaypoint = {
      seq: path.length,
      x_m: point[0],
      y_m: point[1],
      yaw_rad: null,
      type: path.length === 0 ? "start" : type,
      round,
      sample_id: sampleId ?? null,
      ...(ridgeIdx == null ? {} : { ridge_idx: ridgeIdx }),
      speed_limit_mps: round > 0 && type === "turn" ? Math.min(params.vehicleSpeed, options.maxLinearMps ?? 0.12) : Math.min(params.vehicleSpeed, options.maxLinearMps ?? 0.12),
      tolerance_m: type === "sampling" ? 0.2 : 0.3,
    };
    path.push(waypoint);
    return waypoint;
  };

  planning.roundSegments.forEach((segments, roundIndex) => {
    const start = path.length;
    segments.forEach((segment, segmentIndex) => {
      const nodes = planning.roundNodes[roundIndex] ?? [];
      const target = nodes[segment.to];
      const targetSample = nearestSampleId(roundIndex, segment.to);
      const fromSample = nearestSampleId(roundIndex, segment.from);
      const converted = segment.waypoints.map(transform);
      converted.forEach((point, pointIndex) => {
        const isLast = pointIndex === converted.length - 1;
        const isTurn = pointIndex > 0 && !isLast && converted.length > 2;
        const isSegmentStart = pointIndex === 0;
        pushWaypoint(
          point,
          roundIndex + 1,
          isLast ? "sampling" : isTurn ? "turn" : isSegmentStart ? (path.length === 0 ? "start" : "sampling") : "transit",
          isLast ? targetSample : isSegmentStart ? fromSample : undefined,
          isLast ? target?.ridge_idx : segmentIndex === 0 ? nodes[segment.from]?.ridge_idx : undefined,
        );
      });
    });
    rounds.push({
      round: roundIndex + 1,
      waypoint_start: start,
      waypoint_end: Math.max(start, path.length - 1),
      distance_m: round(segments.reduce((sum, segment) => sum + segment.dist_m, 0), 3),
    });
  });

  const sampleById = new Map(samples.map((sample) => [sample.point_id, sample]));
  const samplingPoints = samples.map((sample) => {
    const transformed = transform(sample.real_xy);
    return {
      sample_id: sample.point_id,
      x_m: transformed[0],
      y_m: transformed[1],
      round: sample.round,
      ridge_idx: sample.ridge_idx,
    };
  });
  // Keep the imported sample table relevant: an inconsistent planner result should be visible in validation.
  for (const waypoint of path) {
    if (waypoint.sample_id && !sampleById.has(waypoint.sample_id)) waypoint.sample_id = null;
  }

  return {
    schema_version: "1.0",
    generated_at: new Date().toISOString(),
    frame_id: "field",
    coordinate_type: "local_enu",
    unit: "m",
    meta: {
      field_id: options.fieldId ?? "field-local",
      map_id: options.mapId ?? "map-local",
      map_version: options.mapVersion ?? 1,
      route_id: options.routeId ?? `route-${Date.now()}`,
      y_axis_positive: "field_interior",
    },
    coordinate_system: {
      origin_definition: "first_boundary_point",
      x_axis_definition: "first_boundary_edge",
      y_axis_definition: "field_interior_side",
      interior_sign: interiorSign,
    },
    vehicle: {
      max_linear_mps: options.maxLinearMps ?? 0.12,
      max_angular_radps: options.maxAngularRadps ?? 0.25,
      minimum_turn_radius_m: options.minimumTurnRadiusM ?? 0.5,
    },
    field_polygon_m: fieldPolygon,
    sampling_points: samplingPoints,
    rounds,
    path,
    statistics: {
      coverage_pct: round(planning.coveragePct, 3),
      average_confidence: round(planning.averageConfidence, 5),
      planned_distance_m: round(planning.totalDistance, 3),
      planned_time_s: round(planning.totalTime, 3),
    },
  };
}

export function validateRouteDocument(route: RouteDocument): RouteValidationResult {
  const errors: string[] = [];
  const warnings: string[] = [];
  const polygon = route.field_polygon_m;
  if (route.schema_version !== "1.0") errors.push("不支持的路线 schema_version。");
  if (route.frame_id !== "field" || route.coordinate_type !== "local_enu" || route.unit !== "m") errors.push("路线必须使用 field/local_enu 坐标系和米制单位。");
  if (polygon.length < 3) errors.push("field_polygon_m 至少需要 3 个顶点。");
  if (!route.path.length) errors.push("路线没有可执行航点。");
  if (route.vehicle.max_linear_mps <= 0 || route.vehicle.max_angular_radps <= 0) errors.push("车辆速度限制必须为正数。");
  if (route.vehicle.minimum_turn_radius_m <= 0) errors.push("最小转弯半径必须为正数。");

  let pathDistance = 0;
  let maxSegment = 0;
  let maxSpeed = 0;
  let sharpTurns = 0;
  let outside = 0;
  let sampling = 0;
  const fieldXs = polygon.map(([x]) => x), fieldYs = polygon.map(([, y]) => y);
  const fieldDiagonal = polygon.length >= 3
    ? Math.hypot(Math.max(...fieldXs) - Math.min(...fieldXs), Math.max(...fieldYs) - Math.min(...fieldYs))
    : 0;
  const suspiciousSegmentLength = Math.max(5, fieldDiagonal * 1.25);
  for (let i = 0; i < route.path.length; i++) {
    const waypoint = route.path[i];
    if (![waypoint.x_m, waypoint.y_m, waypoint.speed_limit_mps, waypoint.tolerance_m].every(Number.isFinite)) errors.push(`航点 ${i} 含有非法数值。`);
    if (waypoint.speed_limit_mps > route.vehicle.max_linear_mps + 1e-6) errors.push(`航点 ${i} 的速度超过车辆限制。`);
    maxSpeed = Math.max(maxSpeed, waypoint.speed_limit_mps);
    if (waypoint.type === "sampling" || waypoint.sample_id) sampling++;
    if (polygon.length >= 3 && !pointInPolygon([waypoint.x_m, waypoint.y_m], polygon)) {
      const boundaryDistance = Math.min(...polygon.map((point, index) => pointToSegmentDistance([waypoint.x_m, waypoint.y_m], point, polygon[(index + 1) % polygon.length])));
      if (boundaryDistance > 0.15) outside++;
    }
    if (i > 0) {
      const previous = route.path[i - 1];
      const segment = distance([previous.x_m, previous.y_m], [waypoint.x_m, waypoint.y_m]);
      pathDistance += segment;
      maxSegment = Math.max(maxSegment, segment);
      if (segment < 0.001) warnings.push(`航点 ${i - 1} 与 ${i} 几乎重合。`);
      if (segment > suspiciousSegmentLength) warnings.push(`航点 ${i - 1}→${i} 长度 ${segment.toFixed(2)}m，超过田块尺度，建议检查是否存在坐标尺度错误。`);
    }
    if (i > 1) {
      const a = route.path[i - 2], b = route.path[i - 1], c = waypoint;
      const v1: Point = [b.x_m - a.x_m, b.y_m - a.y_m], v2: Point = [c.x_m - b.x_m, c.y_m - b.y_m];
      const n1 = Math.hypot(...v1), n2 = Math.hypot(...v2);
      if (n1 > 0.001 && n2 > 0.001) {
        const cosine = Math.max(-1, Math.min(1, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)));
        if (Math.acos(cosine) > Math.PI / 3) sharpTurns++;
      }
    }
  }
  if (outside) errors.push(`${outside} 个航点明显位于田块边界外。`);
  if (sharpTurns) warnings.push(`检测到 ${sharpTurns} 个急转折点；实车执行前需要圆弧或样条平滑。`);
  if (!route.path.some((waypoint) => waypoint.type === "start")) warnings.push("路线没有 start 航点，将使用车辆当前位姿作为起点。");
  if (!route.path.some((waypoint) => waypoint.type === "sampling" || waypoint.sample_id)) warnings.push("路线没有 sampling 航点，无法验证到点停车流程。");
  return {
    valid: errors.length === 0,
    errors,
    warnings,
    stats: {
      waypoint_count: route.path.length,
      sampling_waypoint_count: sampling,
      path_distance_m: round(pathDistance, 3),
      max_segment_m: round(maxSegment, 3),
      max_speed_mps: round(maxSpeed, 3),
      sharp_turn_count: sharpTurns,
      outside_waypoint_count: outside,
    },
  };
}
