from pathlib import Path
from collections import deque
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "spore-vehicle-nav" / "results" / "real_single_ridge_20260912_195820"
OUT = ROOT / "report_assets" / "charts"
FONT_REGULAR = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
NAVY = (23, 54, 93)
BLUE = (50, 126, 184)
GREEN = (61, 142, 110)
ORANGE = (235, 155, 55)
GRAY = (100, 112, 124)
LIGHT = (224, 229, 234)
UNKNOWN = (205, 205, 205)


def font(size, bold=False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REGULAR, size)


def load_map(path):
    array = np.array(Image.open(path).convert("L"))
    rgb = np.empty((*array.shape, 3), dtype=np.uint8)
    rgb[:] = UNKNOWN
    rgb[array > 250] = (255, 255, 255)
    rgb[array < 65] = NAVY
    return array, Image.fromarray(rgb)


def largest_component(mask):
    height, width = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    best = []
    for y, x in zip(*np.nonzero(mask)):
        if seen[y, x]:
            continue
        seen[y, x] = True
        stack = [(y, x)]
        points = []
        while stack:
            cy, cx = stack.pop()
            points.append((cy, cx))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
        if len(points) > len(best):
            best = points
    return np.array([(x, y) for y, x in best], dtype=float)


def fitted_axis(array, resolution=0.05):
    pts = largest_component(array < 65)
    centered = pts - pts.mean(axis=0)
    values, vectors = np.linalg.eigh(np.cov(centered, rowvar=False))
    major = vectors[:, np.argmax(values)]
    projection = centered @ major
    a = pts.mean(axis=0) + major * projection.min()
    b = pts.mean(axis=0) + major * projection.max()
    return a, b, (projection.max() - projection.min() + 1) * resolution


def fit_image(image, box):
    x0, y0, x1, y1 = box
    width, height = x1 - x0, y1 - y0
    scale = min(width / image.width, height / image.height)
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    resized = image.resize(size, Image.Resampling.NEAREST)
    pos = (round(x0 + (width - size[0]) / 2), round(y0 + (height - size[1]) / 2))
    return resized, pos, scale


def centered(draw, xy, text, fnt, fill=(0, 0, 0)):
    box = draw.textbbox((0, 0), text, font=fnt)
    draw.text((xy[0] - (box[2] - box[0]) / 2, xy[1]), text, font=fnt, fill=fill)


def arrow(draw, p1, p2, fill, width=5):
    draw.line([p1, p2], fill=fill, width=width)
    angle = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
    for point, direction in ((p1, angle), (p2, angle + math.pi)):
        size = 16
        left = (point[0] + size * math.cos(direction + 0.55), point[1] + size * math.sin(direction + 0.55))
        right = (point[0] + size * math.cos(direction - 0.55), point[1] + size * math.sin(direction - 0.55))
        draw.polygon([point, left, right], fill=fill)


def draw_scale(draw, origin, pixels_per_meter):
    x, y = origin
    length = round(pixels_per_meter)
    draw.line((x, y, x + length, y), fill=(0, 0, 0), width=5)
    draw.line((x, y - 8, x, y + 8), fill=(0, 0, 0), width=3)
    draw.line((x + length, y - 8, x + length, y + 8), fill=(0, 0, 0), width=3)
    centered(draw, (x + length / 2, y + 10), "1 米", font(24), GRAY)


def make_core_map():
    array, map_image = load_map(RESULT / "offline_masked_2m" / "masked_map.pgm")
    canvas = Image.new("RGB", (1800, 1120), "white")
    draw = ImageDraw.Draw(canvas)
    centered(draw, (900, 35), "真实单垄过滤后 SLAM 建图结果", font(48, True), NAVY)
    centered(draw, (900, 100), "地图分辨率 0.05 米  地图范围 6.60 米 × 5.90 米", font(27), GRAY)

    chart_box = (120, 175, 1280, 1010)
    rendered, pos, scale = fit_image(map_image, chart_box)
    canvas.paste(rendered, pos)
    draw.rectangle((pos[0], pos[1], pos[0] + rendered.width, pos[1] + rendered.height), outline=(70, 80, 90), width=3)

    a, b, _ = fitted_axis(array)
    p1 = (pos[0] + a[0] * scale, pos[1] + a[1] * scale)
    p2 = (pos[0] + b[0] * scale, pos[1] + b[1] * scale)
    arrow(draw, p1, p2, ORANGE, 6)
    mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
    label = "垄体主轴约 4.10 米"
    bbox = draw.textbbox((0, 0), label, font=font(27, True))
    draw.rounded_rectangle((mx - 150, my - 45, mx + 150, my - 5), 8, fill=(255, 255, 255), outline=ORANGE, width=2)
    centered(draw, (mx, my - 41), label, font(27, True), NAVY)
    draw_scale(draw, (pos[0] + 35, pos[1] + rendered.height - 40), scale / 0.05)

    panel_x = 1340
    draw.text((panel_x, 205), "实验与地图指标", font=font(32, True), fill=NAVY)
    metrics = [
        ("真实垄体尺寸", "4.80 米 × 0.40 米"),
        ("SLAM 轨迹长度", "33.35 米"),
        ("轨迹覆盖范围", "6.44 米 × 5.95 米"),
        ("起终点间距", "约 0.96 米"),
        ("最大单步坐标修正", "0.317 米"),
        ("大于 0.5 米修正", "0 次"),
        ("连续占据结构", "1 个主要结构"),
        ("地图测得主轴", "约 4.10 米 × 0.90 米"),
    ]
    y = 270
    for name, value in metrics:
        draw.line((panel_x, y - 12, 1715, y - 12), fill=LIGHT, width=2)
        draw.text((panel_x, y), name, font=font(22), fill=GRAY)
        draw.text((panel_x, y + 32), value, font=font(25, True), fill=NAVY)
        y += 88

    legend_y = 1010
    for x, color, text in ((1340, NAVY, "占据"), (1460, (255, 255, 255), "自由"), (1580, UNKNOWN, "未知")):
        draw.rectangle((x, legend_y, x + 28, legend_y + 28), fill=color, outline=(100, 100, 100))
        draw.text((x + 38, legend_y - 2), text, font=font(21), fill=GRAY)
    canvas.save(OUT / "导航_真实单垄过滤后SLAM地图.png", quality=95)


def make_comparison():
    entries = [
        ("原始在线建图", RESULT / "single_ridge_2laps.pgm", ["SLAM 轨迹 5.82 米", "占据连通区域 2532 个"]),
        ("里程计投图对照", RESULT / "offline_odom_projection" / "odom_map.pgm", ["里程计轨迹 38.42 米", "垄体主轴约 4.96 米"]),
        ("过滤后 SLAM 重建", RESULT / "offline_masked_2m" / "masked_map.pgm", ["SLAM 轨迹 33.35 米", "连续主要结构 1 个"]),
    ]
    canvas = Image.new("RGB", (1900, 1050), "white")
    draw = ImageDraw.Draw(canvas)
    centered(draw, (950, 30), "真实单垄数据的建图处理对比", font(48, True), NAVY)
    centered(draw, (950, 95), "原始在线结果  数据完整性对照  现场干扰过滤后的 SLAM 结果", font(27), GRAY)

    panel_w = 560
    starts = [70, 670, 1270]
    for index, ((title, path, metrics), x0) in enumerate(zip(entries, starts)):
        array, image = load_map(path)
        centered(draw, (x0 + panel_w / 2, 165), title, font(31, True), NAVY)
        rendered, pos, scale = fit_image(image, (x0 + 25, 225, x0 + panel_w - 25, 765))
        canvas.paste(rendered, pos)
        draw.rectangle((pos[0], pos[1], pos[0] + rendered.width, pos[1] + rendered.height), outline=(90, 100, 110), width=2)
        draw_scale(draw, (pos[0] + 25, pos[1] + rendered.height - 32), scale / 0.05)
        for j, metric in enumerate(metrics):
            centered(draw, (x0 + panel_w / 2, 805 + j * 45), metric, font(25, j == 1), NAVY if j == 1 else GRAY)
        if index < 2:
            draw.line((x0 + panel_w + 20, 190, x0 + panel_w + 20, 930), fill=LIGHT, width=3)

    legend_y = 965
    for x, color, text in ((650, NAVY, "占据栅格"), (870, (255, 255, 255), "自由栅格"), (1090, UNKNOWN, "未知栅格")):
        draw.rectangle((x, legend_y, x + 30, legend_y + 30), fill=color, outline=(100, 100, 100))
        draw.text((x + 42, legend_y - 2), text, font=font(23), fill=GRAY)
    canvas.save(OUT / "导航_真实单垄建图处理对比.png", quality=95)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    make_core_map()
    make_comparison()
    print(OUT / "导航_真实单垄过滤后SLAM地图.png")
    print(OUT / "导航_真实单垄建图处理对比.png")
