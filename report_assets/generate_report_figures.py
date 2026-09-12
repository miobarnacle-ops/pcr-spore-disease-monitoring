#!/usr/bin/env python3
"""为三模块报告生成可复核的中文技术图表。"""

from pathlib import Path
import csv
import json
import textwrap

import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch, Rectangle, FancyArrowPatch, Circle
import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "report_assets" / "charts"
OUT.mkdir(parents=True, exist_ok=True)

CHINESE_FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
font_manager.fontManager.addfont(CHINESE_FONT)
plt.rcParams.update({
    "font.family": "Noto Sans CJK JP",
    "axes.unicode_minus": False,
    "figure.dpi": 160,
    "savefig.dpi": 220,
    "savefig.bbox": "tight",
    "savefig.facecolor": "white",
})

NAVY = "#15324B"
BLUE = "#2878B5"
CYAN = "#43A7B8"
GREEN = "#3B8C6E"
LIGHT = "#EEF5F7"
ORANGE = "#E99A3E"
RED = "#D75A4A"
GRAY = "#687782"


def _wrap_box_text(value, width_chars):
    """按流程框宽度换行，兼容中文且保留人工换行。"""
    lines = []
    for line in str(value).splitlines() or [""]:
        lines.extend(textwrap.wrap(line, width=max(4, width_chars),
                                   break_long_words=True,
                                   break_on_hyphens=False) or [""])
    return "\n".join(lines)


def box(ax, xy, wh, title, subtitle="", fc=LIGHT, ec=BLUE, title_size=13,
        subtitle_size=9.2):
    x, y = xy
    w, h = wh
    patch = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.012,rounding_size=0.025",
        linewidth=1.8, edgecolor=ec, facecolor=fc,
    )
    ax.add_patch(patch)
    title = _wrap_box_text(title, int(w * 72 * 13 / title_size))
    subtitle = _wrap_box_text(subtitle, int(w * 68 * 9.2 / subtitle_size))
    title_lines = title.count("\n") + 1
    subtitle_lines = subtitle.count("\n") + 1 if subtitle else 0
    title_y = 0.72 if subtitle and (title_lines > 1 or subtitle_lines > 2) else (0.62 if subtitle else 0.50)
    subtitle_y = 0.27 if subtitle_lines > 2 else 0.28
    title_artist = ax.text(x + w / 2, y + h * title_y, title,
                           ha="center", va="center", fontsize=title_size, weight="bold",
                           color=NAVY, linespacing=1.08)
    title_artist._flow_box_bounds = (x, y, w, h)
    if subtitle:
        subtitle_artist = ax.text(x + w / 2, y + h * subtitle_y, subtitle,
                                  ha="center", va="center", fontsize=subtitle_size,
                                  color=GRAY, linespacing=1.22)
        subtitle_artist._flow_box_bounds = (x, y, w, h)
    return patch


def arrow(ax, start, end, color=BLUE, width=1.8, style="-|>"):
    ax.add_patch(FancyArrowPatch(start, end, arrowstyle=style,
                                 mutation_scale=14, linewidth=width, color=color))


def save(fig, name):
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    overflow = []
    for ax in fig.axes:
        for artist in ax.texts:
            bounds = getattr(artist, "_flow_box_bounds", None)
            if not bounds:
                continue
            x, y, w, h = bounds
            (left, bottom), (right, top) = ax.transData.transform([(x, y), (x + w, y + h)])
            text_bounds = artist.get_window_extent(renderer=renderer)
            if (text_bounds.x0 < left - 2 or text_bounds.x1 > right + 2 or
                    text_bounds.y0 < bottom - 2 or text_bounds.y1 > top + 2):
                overflow.append(artist.get_text().replace("\n", " / "))
    if overflow:
        raise RuntimeError(f"{name} 流程框文字越界：{'；'.join(overflow)}")
    fig.savefig(OUT / name)
    plt.close(fig)


def navigation_architecture():
    fig, ax = plt.subplots(figsize=(12, 7))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.text(0.5, 0.965, "自主巡检导航的分层融合架构", ha="center", va="top",
            fontsize=20, weight="bold", color=NAVY)
    ax.text(0.5, 0.915, "局部连续性、地图一致性与全局约束各司其职，避免重复发布坐标变换",
            ha="center", va="top", fontsize=11, color=GRAY)

    box(ax, (0.055, 0.70), (0.20, 0.14), "车体感知", "轮速 · 惯性测量\n激光雷达", fc="#EAF4FA")
    box(ax, (0.305, 0.70), (0.20, 0.14), "局部连续定位", "轮速—惯性滤波\n输出连续里程计", fc="#EAF4FA")
    box(ax, (0.555, 0.70), (0.20, 0.14), "地图定位", "同步定位与建图\n约束地图漂移", fc="#E9F6F0", ec=GREEN)
    box(ax, (0.805, 0.70), (0.14, 0.14), "全局约束", "北斗差分\n质量门", fc="#FFF4E7", ec=ORANGE)
    for s, e in [((0.255, 0.77), (0.305, 0.77)), ((0.505, 0.77), (0.555, 0.77)), ((0.805, 0.77), (0.755, 0.77))]:
        arrow(ax, s, e)

    box(ax, (0.20, 0.43), (0.60, 0.15), "统一全局位姿与质量状态",
        "坐标、时间、协方差、定位模式和数据新鲜度统一输出", fc="#EFF2FA", ec="#5469A6", title_size=15)
    arrow(ax, (0.405, 0.70), (0.405, 0.58), color="#5469A6")
    arrow(ax, (0.655, 0.70), (0.655, 0.58), color="#5469A6")
    arrow(ax, (0.875, 0.70), (0.75, 0.58), color=ORANGE)

    box(ax, (0.08, 0.16), (0.24, 0.14), "覆盖路径规划", "边界分解 · 平行作业线\n地头转弯 · 采样点", fc="#E9F6F0", ec=GREEN)
    box(ax, (0.38, 0.16), (0.24, 0.14), "路径跟踪", "前视跟踪 · 速度约束\n偏差与进度反馈", fc="#EAF4FA")
    box(ax, (0.68, 0.16), (0.24, 0.14), "质量感知安全门", "障碍 · 断联 · 定位降级\n停车、暂停或人工接管", fc="#FFF0EE", ec=RED)
    arrow(ax, (0.50, 0.43), (0.20, 0.30), color="#5469A6")
    arrow(ax, (0.32, 0.23), (0.38, 0.23), color=GREEN)
    arrow(ax, (0.62, 0.23), (0.68, 0.23), color=RED)

    save(fig, "导航_分层融合架构.png")


def navigation_field_route():
    fig, ax = plt.subplots(figsize=(11, 7))
    ax.set_aspect("equal")
    ax.set_xlim(-4.6, 4.6)
    ax.set_ylim(-3.7, 3.7)
    ax.set_facecolor("#F7F4EA")
    ax.add_patch(Rectangle((-4, -3), 8, 6, fill=False, linewidth=2.2, edgecolor=NAVY))
    for y in [-1.42, 0, 1.42]:
        ax.add_patch(Rectangle((-2.4, y - 0.11), 4.8, 0.22,
                               facecolor="#77A95B", edgecolor="#4E783E", linewidth=1.2))
        for x in np.linspace(-2.3, 2.3, 24):
            ax.plot([x, x], [y - 0.08, y + 0.08], color="#356A39", linewidth=1)

    # 两条垄间通道及地头转弯，展示覆盖路径而非实测轨迹。
    x_left, x_right = -2.8, 2.8
    ys = [-0.71, 0.71]
    route_x = [x_left, x_right]
    route_y = [ys[0], ys[0]]
    theta = np.linspace(-np.pi / 2, np.pi / 2, 60)
    arc_x = x_right + 0.71 * np.cos(theta)
    arc_y = 0 + 0.71 * np.sin(theta)
    route_x += list(arc_x) + [x_left]
    route_y += list(arc_y) + [ys[1]]
    ax.plot(route_x, route_y, color="#1877C9", linewidth=4, solid_capstyle="round", label="规划覆盖路径")
    ax.scatter([x_left], [ys[0]], s=90, color=GREEN, zorder=5, label="起点")
    ax.scatter([-1.4, 0, 1.4], [ys[0], ys[0], ys[1]], s=70, color=ORANGE,
               edgecolor="white", linewidth=1.5, zorder=5, label="示意采样点")

    ax.annotate("地头转弯区", xy=(3.48, 0), xytext=(3.65, 1.3),
                arrowprops=dict(arrowstyle="->", color=RED), color=RED, fontsize=11, ha="center")
    ax.annotate("垄间净通道不小于1.20米", xy=(0, -0.71), xytext=(0, -2.45),
                arrowprops=dict(arrowstyle="->", color=BLUE), color=NAVY, fontsize=11, ha="center")
    ax.text(0, 3.28, "现有仿真配置：8米 × 6米、3条作物垄、目标地头1.60米",
            ha="center", va="center", fontsize=13, weight="bold", color=NAVY)
    ax.set_title("模拟农田结构与牛耕式覆盖路径示意", fontsize=19, weight="bold", color=NAVY, pad=18)
    ax.set_xlabel("田块长度方向（米）")
    ax.set_ylabel("田块宽度方向（米）")
    ax.grid(alpha=0.15)
    ax.legend(loc="lower right", frameon=True, ncol=3, fontsize=10)
    save(fig, "导航_仿真农田与覆盖路径.png")


def console_architecture():
    fig, ax = plt.subplots(figsize=(12, 7))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.text(0.5, 0.96, "一套业务核心支撑电脑端与手机端", ha="center", va="top",
            fontsize=20, weight="bold", color=NAVY)
    ax.text(0.5, 0.91, "界面随屏幕重排，任务、遥测、样本、预测和告警保持同一数据语义",
            ha="center", va="top", fontsize=11, color=GRAY)

    box(ax, (0.07, 0.68), (0.25, 0.15), "电脑端", "地图规划 · 参数配置\n统计分析 · 报告导出", fc="#EAF4FA")
    box(ax, (0.68, 0.68), (0.25, 0.15), "手机端", "状态总览 · 任务进度\n告警确认 · 受限操作", fc="#E9F6F0", ec=GREEN)
    box(ax, (0.25, 0.43), (0.50, 0.17), "统一业务核心", "七类业务页签 · 版本化数据契约 · 本地会话\n来源标记 · 响应式布局 · 文件导入导出", fc="#EFF2FA", ec="#5469A6", title_size=16)
    arrow(ax, (0.195, 0.68), (0.34, 0.60), color=BLUE)
    arrow(ax, (0.805, 0.68), (0.66, 0.60), color=GREEN)

    box(ax, (0.06, 0.15), (0.22, 0.14), "模拟数据", "固定种子与故障情景", fc="#F3F5F6", ec=GRAY)
    box(ax, (0.39, 0.15), (0.22, 0.14), "历史回放", "带版本的任务记录", fc="#F3F5F6", ec=GRAY)
    box(ax, (0.72, 0.15), (0.22, 0.14), "车辆实时数据", "机器人桥接与状态适配", fc="#FFF4E7", ec=ORANGE)
    for x in [0.17, 0.50, 0.83]:
        arrow(ax, (x, 0.29), (0.5, 0.43), color=GRAY)
    save(fig, "控制台_一核多端架构.png")


def algorithm_pipeline():
    fig, ax = plt.subplots(figsize=(13, 6.8))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.text(0.5, 0.965, "观测驱动的孢子扩散预测预警流程", ha="center", va="top",
            fontsize=20, weight="bold", color=NAVY)
    ax.text(0.5, 0.915, "从稀疏检测到疑似源、不确定性和分时风险，不把模型结果替代病原诊断",
            ha="center", va="top", fontsize=11, color=GRAY)
    xs = [0.035, 0.235, 0.435, 0.635, 0.835]
    titles = ["观测与环境输入", "粗测—检测融合", "疑似源反演", "动态传播计算", "分时风险输出"]
    subtitles = [
        "采样位置 · 定量检测\n逐时天气 · 冠层参数",
        "空间趋势 · 质量加权\n尺度校正 · 边界屏蔽",
        "粒子更新 · 源强估计\n置信区间 · 退化判断",
        "平流 · 扩散 · 失活\n沉降 · 雨洗 · 再释放",
        "3天 / 5天 / 7天\n热点 · 侵染窗口 · 建议",
    ]
    colors = ["#EAF4FA", "#E9F6F0", "#FFF4E7", "#EFF2FA", "#FFF0EE"]
    edges = [BLUE, GREEN, ORANGE, "#5469A6", RED]
    for i, x in enumerate(xs):
        box(ax, (x, 0.56), (0.15, 0.22), titles[i], subtitles[i], fc=colors[i], ec=edges[i], title_size=12)
        if i < len(xs) - 1:
            arrow(ax, (x + 0.15, 0.67), (xs[i + 1], 0.67), color=GRAY)

    box(ax, (0.11, 0.22), (0.22, 0.15), "稳态快速基线", "用于稳定风场对照\n及快速前向计算", fc="#F3F5F6", ec=GRAY)
    box(ax, (0.39, 0.22), (0.22, 0.15), "质量与版本控制", "区分模拟、回放与实测\n保存参数、种子和时间戳", fc="#F3F5F6", ec=GRAY)
    box(ax, (0.67, 0.22), (0.22, 0.15), "人工复核闭环", "预警指导复检与防控\n检测结果仍由专业人员确认", fc="#F3F5F6", ec=GRAY)
    arrow(ax, (0.22, 0.37), (0.31, 0.56), color=GRAY)
    arrow(ax, (0.50, 0.37), (0.50, 0.56), color=GRAY)
    arrow(ax, (0.78, 0.37), (0.91, 0.56), color=GRAY)
    save(fig, "孢子算法_观测到预警流程.png")


def metric_comparison():
    csv_path = ROOT / "spore-monitor-web" / "python-pipeline" / "artifacts" / "report-comparison-v1" / "scenario_metrics.csv"
    with csv_path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    scenes = [r["scenario_name"] for r in rows]
    dyn_rmse = np.array([float(r["reworked_rmse_log10"]) for r in rows])
    gau_rmse = np.array([float(r["gaussian_rmse_log10"]) for r in rows])
    dyn_iou = np.array([float(r["reworked_hotspot_iou"]) for r in rows])
    gau_iou = np.array([float(r["gaussian_hotspot_iou"]) for r in rows])
    x = np.arange(len(scenes))
    width = 0.34

    fig, axes = plt.subplots(1, 2, figsize=(14, 6.2))
    fig.suptitle("合成留出点上的阶段性模型对比", fontsize=20, weight="bold", color=NAVY, y=0.98)
    fig.text(0.5, 0.925, "每个场景20个校准点、60个独立留出点；结果用于验证方法潜力，不代表田间准确率",
             ha="center", fontsize=10.5, color=GRAY)

    ax = axes[0]
    b1 = ax.bar(x - width/2, dyn_rmse, width, label="动态离线代理", color=BLUE)
    b2 = ax.bar(x + width/2, gau_rmse, width, label="高斯烟羽基线", color=ORANGE)
    ax.set_title("留出点对数均方根误差（越低越好）", fontsize=13, weight="bold")
    ax.set_xticks(x, scenes, rotation=10)
    ax.set_ylabel("误差")
    ax.set_ylim(0, 4.05)
    ax.grid(axis="y", alpha=0.2)
    ax.legend(loc="upper left")
    ax.bar_label(b1, fmt="%.2f", padding=3, fontsize=9)
    ax.bar_label(b2, fmt="%.2f", padding=3, fontsize=9)
    ax.text(0, 1.05, "高斯更优", ha="center", color=ORANGE, weight="bold")
    ax.text(1, 3.72, "动态方法降低57.8%", ha="center", color=BLUE, weight="bold", fontsize=9)
    ax.text(2, 3.43, "动态方法降低60.4%", ha="center", color=BLUE, weight="bold", fontsize=9)

    ax = axes[1]
    b3 = ax.bar(x - width/2, dyn_iou, width, label="动态离线代理", color=GREEN)
    b4 = ax.bar(x + width/2, gau_iou, width, label="高斯烟羽基线", color="#9C7B4F")
    ax.set_title("热点交并比（越高越好）", fontsize=13, weight="bold")
    ax.set_xticks(x, scenes, rotation=10)
    ax.set_ylabel("交并比")
    ax.set_ylim(0, 1.08)
    ax.grid(axis="y", alpha=0.2)
    ax.legend(loc="upper right")
    ax.bar_label(b3, fmt="%.2f", padding=3, fontsize=9)
    ax.bar_label(b4, fmt="%.2f", padding=3, fontsize=9)
    fig.subplots_adjust(top=0.84, bottom=0.12, wspace=0.25)
    save(fig, "孢子算法_阶段性精度对比.png")


def applicability_matrix():
    fig, ax = plt.subplots(figsize=(13, 6.5))
    ax.axis("off")
    ax.set_title("高斯烟羽基线与动态方案的适用性对比", fontsize=20, weight="bold", color=NAVY, pad=20)
    rows = [
        ["时间表达", "稳定、连续释放", "逐时演化与历史记忆", "动态方案"],
        ["风场变化", "固定平均风", "支持风向转折与风速变化", "动态方案"],
        ["孢子命运", "简化沉降衰减", "失活、沉降、雨洗、再释放", "动态方案"],
        ["观测利用", "可用于快速前向计算", "融合粗测与检测并反演疑似源", "动态方案"],
        ["稳定场景", "精度高、解释直观", "计算量较高", "高斯基线"],
        ["计算成本", "低", "可按网格与时步分级", "高斯基线"],
        ["主要输出", "稳态浓度梯度", "分时风险、热点与置信度", "动态方案"],
    ]
    columns = ["比较维度", "高斯烟羽基线", "观测驱动动态方案", "更具优势"]
    table = ax.table(cellText=rows, colLabels=columns, loc="center", cellLoc="center",
                     colWidths=[0.16, 0.28, 0.38, 0.16])
    table.auto_set_font_size(False)
    table.set_fontsize(10.5)
    table.scale(1, 2.05)
    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor("#CAD5DC")
        if r == 0:
            cell.set_facecolor(NAVY)
            cell.get_text().set_color("white")
            cell.get_text().set_weight("bold")
        else:
            cell.set_facecolor("#F7FAFB" if r % 2 else "#EDF4F6")
            if c == 3:
                value = rows[r-1][3]
                cell.get_text().set_color(GREEN if value == "动态方案" else ORANGE)
                cell.get_text().set_weight("bold")
    save(fig, "孢子算法_模型适用性对比.png")


def coordinate_frames():
    fig, ax = plt.subplots(figsize=(12, 7.2))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.text(0.5, 0.955, "农田巡检坐标体系与唯一发布者原则", ha="center", va="top", fontsize=20, weight="bold", color=NAVY)
    ax.text(0.5, 0.908, "路线、地图、里程计与传感器外参在各自坐标层中承担唯一职责", ha="center", va="top", fontsize=11, color=GRAY)
    levels = [
        (0.10, 0.69, 0.80, 0.13, "田块坐标", "保存边界、路线与采样点；北斗观测转换后的局部东—北—天坐标", "#FFF4E7", ORANGE),
        (0.18, 0.50, 0.64, 0.13, "地图坐标", "同步定位与建图维护局部几何一致性", "#E9F6F0", GREEN),
        (0.27, 0.31, 0.46, 0.13, "里程计坐标", "轮速—惯性滤波提供连续的局部运动估计", "#EAF4FA", BLUE),
        (0.36, 0.12, 0.28, 0.13, "车体与传感器坐标", "车体平面基准、车体中心、雷达、惯性测量与卫星天线外参", "#EFF2FA", "#5469A6"),
    ]
    for x, y, w, h, title, sub, fc, ec in levels:
        box(ax, (x, y), (w, h), title, sub, fc=fc, ec=ec, title_size=14)
    arrow(ax, (0.50, 0.69), (0.50, 0.63), color=ORANGE)
    arrow(ax, (0.50, 0.50), (0.50, 0.44), color=GREEN)
    arrow(ax, (0.50, 0.31), (0.50, 0.25), color=BLUE)
    save(fig, "导航_坐标体系与唯一发布者原则.png")


def fusion_quality_gate():
    fig, ax = plt.subplots(figsize=(13, 7))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.text(0.5, 0.955, "北斗差分与同步定位建图的分层融合及质量门", ha="center", va="top", fontsize=20, weight="bold", color=NAVY)
    box(ax, (0.04, 0.67), (0.22, 0.14), "北斗差分观测", "坐标 · 解状态 · 协方差\n差分龄期 · 时间戳", fc="#FFF4E7", ec=ORANGE)
    box(ax, (0.39, 0.67), (0.22, 0.14), "局部定位与建图", "连续里程计 · 地图约束\n扫描匹配质量", fc="#E9F6F0", ec=GREEN)
    box(ax, (0.74, 0.67), (0.22, 0.14), "车辆任务状态机", "速度上限 · 暂停\n人工处置", fc="#FFF0EE", ec=RED)
    box(ax, (0.30, 0.41), (0.40, 0.16), "北斗质量门", "固定解：强约束；浮点解：低权重；单点、过期或突跳：拒绝校正并发布降级状态", fc="#EFF2FA", ec="#5469A6", title_size=15)
    arrow(ax, (0.26, 0.74), (0.39, 0.74), color=ORANGE)
    arrow(ax, (0.50, 0.67), (0.50, 0.57), color="#5469A6")
    box(ax, (0.30, 0.16), (0.40, 0.14), "田块至地图全局对齐", "将通过质量门的北斗观测与同时刻局部位姿配对；渐进估计平移和航向，抑制坐标跳变", fc="#EAF4FA", ec=BLUE, title_size=14)
    arrow(ax, (0.50, 0.41), (0.50, 0.30), color=BLUE)
    arrow(ax, (0.70, 0.23), (0.78, 0.67), color=RED)
    save(fig, "导航_融合质量门与全局对齐.png")


def navigation_integrated_chain():
    fig, ax = plt.subplots(figsize=(13.5, 7.4))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.text(0.5, 0.965, "自主巡检导航的三模块协同闭环", ha="center", va="top",
            fontsize=20, weight="bold", color=NAVY)
    ax.text(0.5, 0.915, "定位与建图形成统一位姿，覆盖规划生成任务几何，车辆执行层完成跟踪与安全约束",
            ha="center", va="top", fontsize=11, color=GRAY)

    box(ax, (0.035, 0.68), (0.20, 0.15), "车载感知与运动", "轮式里程计 · 惯性测量\n二维激光扫描 · 北斗差分", fc="#F3F5F6", ec=GRAY)
    box(ax, (0.285, 0.68), (0.20, 0.15), "SLAM 与局部里程计", "局部 EKF · 扫描匹配\n回环优化 · 地图保存", fc="#EAF4FA", ec=BLUE)
    box(ax, (0.535, 0.68), (0.20, 0.15), "北斗 RTK 全局约束", "经纬高转局部 ENU\n解状态 · 质量门\n田块地图对齐", fc="#FFF4E7", ec=ORANGE, subtitle_size=8.5)
    box(ax, (0.785, 0.68), (0.18, 0.15), "统一位姿与质量", "map · odom · field\n协方差与新鲜度", fc="#E9F6F0", ec=GREEN)
    arrow(ax, (0.235, 0.755), (0.285, 0.755), color=GRAY)
    arrow(ax, (0.485, 0.755), (0.535, 0.755), color=BLUE)
    arrow(ax, (0.755, 0.755), (0.785, 0.755), color=ORANGE)

    box(ax, (0.08, 0.40), (0.25, 0.15), "覆盖与采样点规划", "田块边界 · 平行垄线\n覆盖置信度 · 多轮互补选点", fc="#E9F6F0", ec=GREEN)
    box(ax, (0.375, 0.40), (0.25, 0.15), "访问顺序与任务文件", "地头距离 · 最近邻\n2-opt 优化 · route_v1 航点", fc="#EFF2FA", ec="#5469A6", subtitle_size=8.7)
    box(ax, (0.67, 0.40), (0.25, 0.15), "车辆执行与动态安全", "坐标对准 · 平滑 · 跟踪\n到点采样 · 障碍停车\n状态反馈", fc="#FFF0EE", ec=RED, subtitle_size=8.5)
    arrow(ax, (0.205, 0.68), (0.205, 0.55), color=GREEN)
    arrow(ax, (0.33, 0.475), (0.375, 0.475), color=GREEN)
    arrow(ax, (0.625, 0.475), (0.67, 0.475), color="#5469A6")
    arrow(ax, (0.875, 0.68), (0.795, 0.55), color=GREEN)

    box(ax, (0.19, 0.14), (0.62, 0.14), "任务结果与可追溯记录",
        "地图与位姿图 · 规划参数与路线版本\nRTK 状态 · 实驶轨迹 · 采样事件 · 安全事件",
        fc="#F3F5F6", ec=GRAY, title_size=15)
    arrow(ax, (0.795, 0.40), (0.68, 0.28), color=RED)
    save(fig, "导航_三模块协同闭环.png")


def rtk_stage_metrics():
    labels = ["平均绝对误差", "均方根误差", "95%分位误差", "最大误差"]
    values = np.array([0.044, 0.049, 0.082, 0.117])
    fig, ax = plt.subplots(figsize=(11.5, 6.6))
    bars = ax.bar(labels, values, color=[BLUE, BLUE, GREEN, ORANGE], width=0.58)
    ax.axhline(0.5, color=RED, linestyle="--", linewidth=2, label="项目总体定位目标 0.5 米")
    ax.set_ylim(0, 0.56)
    ax.set_ylabel("二维位置差值（米）")
    ax.set_title("固定解参考区间内的融合轨迹一致性指标", fontsize=19, weight="bold", color=NAVY, pad=18)
    ax.text(0.5, 1.01, "区间 312.6 至 376.4 秒，共 63.8 秒；融合轨迹经二维刚体对齐后与 RTK ENU 比较",
            transform=ax.transAxes, ha="center", fontsize=10.5, color=GRAY)
    ax.grid(axis="y", alpha=0.2)
    ax.legend(loc="upper right")
    ax.bar_label(bars, labels=[f"{v:.3f}" for v in values], padding=4, fontsize=10)
    fig.subplots_adjust(bottom=0.15, top=0.82)
    save(fig, "导航_北斗融合阶段误差指标.png")


def console_dataflow():
    fig, ax = plt.subplots(figsize=(12.5, 7.0))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.text(0.5, 0.955, "多端控制台的数据链与弱网降级边界", ha="center", va="top", fontsize=20, weight="bold", color=NAVY)
    box(ax, (0.04, 0.68), (0.20, 0.13), "模拟数据", "固定种子故障情景", fc="#F3F5F6", ec=GRAY)
    box(ax, (0.04, 0.46), (0.20, 0.13), "历史回放", "带版本的任务记录", fc="#F3F5F6", ec=GRAY)
    box(ax, (0.04, 0.24), (0.20, 0.13), "车辆实时数据", "里程计 · 雷达 · 电池\n诊断 · 任务状态", fc="#FFF4E7", ec=ORANGE)
    box(ax, (0.38, 0.42), (0.25, 0.18), "数据适配与版本契约", "来源标签 · 时间戳\n新鲜度门限 · 统一业务语义", fc="#EFF2FA", ec="#5469A6", title_size=14)
    box(ax, (0.76, 0.64), (0.18, 0.13), "电脑端", "地图、参数、分析\n报告与导出", fc="#EAF4FA", ec=BLUE)
    box(ax, (0.76, 0.40), (0.18, 0.13), "手机端", "状态、进度、告警\n受限任务操作", fc="#E9F6F0", ec=GREEN)
    box(ax, (0.76, 0.16), (0.18, 0.13), "车端安全门", "看门狗与障碍停车\n独立于网络", fc="#FFF0EE", ec=RED)
    for y in [0.745, 0.525, 0.305]: arrow(ax, (0.24, y), (0.38, 0.51), color=GRAY)
    arrow(ax, (0.63, 0.53), (0.76, 0.705), color=BLUE)
    arrow(ax, (0.63, 0.51), (0.76, 0.465), color=GREEN)
    arrow(ax, (0.63, 0.48), (0.76, 0.225), color=RED)
    save(fig, "控制台_数据链与弱网降级.png")


def console_safety_permissions():
    fig, ax = plt.subplots(figsize=(12.5, 6.7))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.text(0.5, 0.95, "双端控制的权限与安全边界", ha="center", va="top", fontsize=20, weight="bold", color=NAVY)
    roles = [
        (0.025, "观察员", "查看状态与历史记录", "#F3F5F6", GRAY),
        (0.225, "农技人员", "确认检测与处置建议", "#E9F6F0", GREEN),
        (0.425, "任务管理员", "创建路线与管理任务", "#EAF4FA", BLUE),
        (0.625, "现场安全员", "运动授权与物理急停", "#FFF4E7", ORANGE),
        (0.825, "系统管理员", "维护设备、账户与审计", "#EFF2FA", "#5469A6"),
    ]
    for x, title, sub, fc, ec in roles:
        box(ax, (x, 0.65), (0.15, 0.14), title, sub, fc=fc, ec=ec, title_size=11)
    box(ax, (0.18, 0.39), (0.64, 0.14), "高风险操作的四项约束", "身份认证 · 角色授权 · 二次确认 · 事件记录；手机端默认不开放连续速度控制", fc="#EFF2FA", ec="#5469A6", title_size=15)
    box(ax, (0.18, 0.16), (0.28, 0.13), "网络与界面层", "断开后自动重新锁定；模拟与回放模式不发布真实运动指令", fc="#EAF4FA", ec=BLUE)
    box(ax, (0.54, 0.16), (0.28, 0.13), "车辆与现场层", "车端看门狗、障碍停车、速度限制、物理急停与断电相互独立", fc="#FFF0EE", ec=RED)
    arrow(ax, (0.50, 0.65), (0.50, 0.53), color="#5469A6")
    arrow(ax, (0.38, 0.39), (0.32, 0.29), color=BLUE)
    arrow(ax, (0.62, 0.39), (0.68, 0.29), color=RED)
    save(fig, "控制台_权限与安全边界.png")


def source_inversion():
    fig, ax = plt.subplots(figsize=(12.5, 6.8))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.text(0.5, 0.955, "PCR 观测驱动的疑似源项反演与不确定性表达", ha="center", va="top", fontsize=20, weight="bold", color=NAVY)
    box(ax, (0.05, 0.62), (0.21, 0.15), "质量控制后的观测", "坐标、时间、定量检测\n质量标记与观测方差", fc="#EAF4FA", ec=BLUE)
    box(ax, (0.39, 0.62), (0.22, 0.15), "候选源粒子集合", "源位置、相对源强\n先验范围与田块边界", fc="#FFF4E7", ec=ORANGE)
    box(ax, (0.74, 0.62), (0.21, 0.15), "快速前向计算", "稳态基线计算观测点\n预测浓度", fc="#E9F6F0", ec=GREEN)
    box(ax, (0.27, 0.34), (0.46, 0.17), "对数空间似然与权重更新", "比较预测与观测\n更新粒子权重 · 监测有效粒子数\n退化时降低置信度", fc="#EFF2FA", ec="#5469A6", title_size=15)
    box(ax, (0.12, 0.10), (0.26, 0.14), "疑似源估计", "位置、相对强度与不确定椭圆", fc="#FFF0EE", ec=RED)
    box(ax, (0.62, 0.10), (0.26, 0.14), "复检建议", "将有限采样资源投向\n信息增益较高的位置", fc="#F3F5F6", ec=GRAY)
    arrow(ax, (0.26, 0.695), (0.39, 0.695), color=BLUE)
    arrow(ax, (0.61, 0.695), (0.74, 0.695), color=GREEN)
    arrow(ax, (0.50, 0.62), (0.50, 0.49), color="#5469A6")
    arrow(ax, (0.43, 0.34), (0.25, 0.24), color=RED)
    arrow(ax, (0.57, 0.34), (0.75, 0.24), color=GRAY)
    save(fig, "孢子算法_疑似源反演与不确定性.png")


def lightweight_benchmark():
    csv_path = ROOT / "spore-monitor-web" / "python-pipeline" / "artifacts" / "benchmark" / "lightweight_ab_summary.csv"
    with csv_path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    h = np.array([int(r["horizon_hours"]) for r in rows])
    e_rmse = np.array([float(r["reworked_euler_rmse_log10"]) for r in rows])
    g_rmse = np.array([float(r["gaussian_rmse_log10"]) for r in rows])
    e_bias = np.array([float(r["reworked_euler_bias_log10"]) for r in rows])
    g_bias = np.array([float(r["gaussian_bias_log10"]) for r in rows])
    improve = np.array([float(r["rmse_improvement_pct"]) for r in rows])
    x = np.arange(len(h)); w = 0.34
    fig, axes = plt.subplots(1, 2, figsize=(14, 6.4))
    fig.suptitle("轻量化数值基准中的扩散算法对比", fontsize=20, weight="bold", color=NAVY, y=0.985)
    fig.text(0.5, 0.925, "细网格数值解为参考场；每个预测期在30个固定随机采样点上比较，结果仅反映受控合成环境", ha="center", fontsize=10.5, color=GRAY)
    ax = axes[0]
    a = ax.bar(x-w/2, e_rmse, w, label="重构扩散核心", color=BLUE)
    b = ax.bar(x+w/2, g_rmse, w, label="高斯烟羽基线", color=ORANGE)
    ax.set_xticks(x, [f"{v}小时" for v in h])
    ax.set_title("对数浓度均方根误差（越低越好）", fontsize=13, weight="bold")
    ax.set_ylabel("误差")
    ax.set_ylim(0, 1.15); ax.grid(axis="y", alpha=.2); ax.legend(loc="upper left")
    ax.bar_label(a, fmt="%.3f", padding=3, fontsize=9); ax.bar_label(b, fmt="%.3f", padding=3, fontsize=9)
    for i, value in enumerate(improve): ax.text(i, 1.04, f"降低{value:.1f}%", ha="center", color=BLUE, weight="bold", fontsize=10)
    ax = axes[1]
    a = ax.bar(x-w/2, e_bias, w, label="重构扩散核心", color=GREEN)
    b = ax.bar(x+w/2, g_bias, w, label="高斯烟羽基线", color="#9C7B4F")
    ax.axhline(0, color=GRAY, linewidth=1)
    ax.set_xticks(x, [f"{v}小时" for v in h])
    ax.set_title("对数浓度偏差（接近零更好）", fontsize=13, weight="bold")
    ax.set_ylabel("偏差")
    ax.set_ylim(-1.0, .7); ax.grid(axis="y", alpha=.2); ax.legend(loc="upper left")
    ax.bar_label(a, fmt="%+.3f", padding=3, fontsize=9); ax.bar_label(b, fmt="%+.3f", padding=3, fontsize=9)
    fig.subplots_adjust(top=.84, bottom=.12, wspace=.25)
    save(fig, "孢子算法_轻量化数值基准对比.png")


def navigation_route_evidence():
    """用本地 route_v1 文件展示已经进入车端执行链的代表路线。"""
    cases = [
        ("trial2_3m_straight.json", "3米直线", "终点差0.08米"),
        ("trial3_square_loop.json", "方形回环", "闭合误差0.22米"),
        ("trial5_double_ridge.json", "双垄往复", "终点差0.18米"),
        ("trial6_full_route.json", "多点采样", "状态机完整结束"),
    ]
    base = ROOT / "spore-vehicle-nav" / "results"
    fig, axes = plt.subplots(2, 2, figsize=(13.2, 8.7))
    fig.suptitle("本地路线文件与实车分级试验结果", fontsize=21, weight="bold", color=NAVY, y=0.975)
    fig.text(0.5, 0.925, "路线几何来自已归档的 route_v1 JSON；结果摘自2026年8月26日实车试验记录",
             ha="center", fontsize=10.5, color=GRAY)
    for ax, (filename, title, result) in zip(axes.flat, cases):
        data = json.loads((base / filename).read_text(encoding="utf-8"))
        polygon = np.asarray(data["field_polygon_m"], dtype=float)
        polygon = np.vstack([polygon, polygon[0]])
        path = np.asarray([[p["x_m"], p["y_m"]] for p in data["path"]], dtype=float)
        ax.fill(polygon[:, 0], polygon[:, 1], color="#F4F2E7", alpha=0.8)
        ax.plot(polygon[:, 0], polygon[:, 1], color=NAVY, linewidth=1.6)
        ax.plot(path[:, 0], path[:, 1], color=BLUE, linewidth=3, marker="o", markersize=5)
        for i in range(len(path) - 1):
            p0, p1 = path[i], path[i + 1]
            midpoint = p0 * 0.55 + p1 * 0.45
            ax.annotate("", xy=midpoint + (p1 - p0) * 0.06, xytext=midpoint,
                        arrowprops=dict(arrowstyle="-|>", color=BLUE, lw=1.4))
        samples = [p for p in data["path"] if p.get("type") == "sampling"]
        if samples:
            sx = [p["x_m"] for p in samples]
            sy = [p["y_m"] for p in samples]
            ax.scatter(sx, sy, s=120, color=ORANGE, edgecolor="white", linewidth=1.5,
                       zorder=5, label="采样点")
        ax.scatter(path[0, 0], path[0, 1], s=80, color=GREEN, edgecolor="white",
                   linewidth=1.2, zorder=5, label="起点")
        ax.set_title(f"{title}  |  {result}", fontsize=13, weight="bold", color=NAVY)
        ax.set_xlabel("field x（米）")
        ax.set_ylabel("field y（米）")
        ax.set_aspect("equal", adjustable="datalim")
        ax.grid(alpha=0.18)
        ax.legend(loc="best", fontsize=8)
    fig.subplots_adjust(top=0.86, bottom=0.07, hspace=0.42, wspace=0.26)
    save(fig, "导航_本地路线与实车分级结果.png")


def navigation_mission_timeline():
    """从本地 r5_status.log 提取多点路线的到点和采样事件。"""
    log_path = ROOT / "spore-vehicle-nav" / "results" / "pi_logs_20260826" / "r5_status.log"
    records = []
    for raw in log_path.read_text(encoding="utf-8").splitlines():
        try:
            records.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    start = min(r["timestamp"] for r in records if "timestamp" in r)
    events = []
    seen = set()
    for r in records:
        event = r.get("event")
        state = r.get("state")
        seq = r.get("waypoint_seq")
        key = None
        label = None
        color = BLUE
        if event == "waypoint_arrived" and seq is not None:
            key = ("arrived", seq)
            label = f"到达航点{seq}"
            color = GREEN
        elif event == "sample_requested":
            key = ("sample", seq)
            label = f"到达采样点并触发采样 {r.get('sample_id') or ''}".strip()
            color = ORANGE
        elif event == "task_finished":
            key = ("finish", 0)
            label = "任务完成"
            color = NAVY
        if key and key not in seen:
            seen.add(key)
            events.append((r["timestamp"] - start, label, color))
    # 采样请求与最后一个航点到达使用同一时间戳，合并表达以避免重复标签。
    events = [event for event in events if event[1] != "到达航点5"]

    fig, ax = plt.subplots(figsize=(13.0, 5.8))
    ax.set_xlim(-3, 75)
    ax.set_ylim(-0.8, 2.3)
    ax.axis("off")
    ax.text(36, 2.08, "多点路线的车端任务状态证据链", ha="center", fontsize=21,
            weight="bold", color=NAVY)
    ax.text(36, 1.73, "根据 r5_status.log 自动提取；任务包含6个航点和采样点 S4",
            ha="center", fontsize=10.5, color=GRAY)
    ax.plot([0, 70], [0.55, 0.55], color="#AAB6BE", linewidth=3, solid_capstyle="round")
    ax.scatter([0], [0.55], s=130, color=BLUE, zorder=3)
    ax.text(0, 0.05, "开始导航\n0.0秒", ha="center", va="top", fontsize=9.5, color=NAVY)
    for idx, (t, label, color) in enumerate(events):
        ytext = 1.05 if idx % 2 == 0 else -0.05
        va = "bottom" if ytext > 0.5 else "top"
        ax.scatter([t], [0.55], s=135, color=color, edgecolor="white", linewidth=1.3, zorder=4)
        ax.plot([t, t], [0.55, ytext - (0.08 if va == "bottom" else -0.08)], color=color, linewidth=1.3)
        ax.text(t, ytext, f"{label}\n{t:.1f}秒", ha="center", va=va, fontsize=9.3,
                color=NAVY, weight="bold" if color in (ORANGE, NAVY) else None)
    save(fig, "导航_实车任务状态证据链.png")


def slam_repeatability_evidence():
    """直接读取两次保存的PGM地图，形成重复地图叠加与栅格组成图。"""
    first_path = ROOT / "spore-vehicle-nav" / "results" / "sim_farmland_8x6_20260831" / "sim_farmland_8x6.pgm"
    second_path = ROOT / "spore-vehicle-nav" / "results" / "sim_farmland_8x6_repeat_20260831" / "sim_farmland_8x6.pgm"
    first = np.asarray(Image.open(first_path).convert("L"))
    second = np.asarray(Image.open(second_path).convert("L"))
    occ1 = first < 80
    occ2 = second < 80
    overlay = np.ones((*first.shape, 3), dtype=float)
    overlay[occ1 & ~occ2] = np.array([40, 120, 181]) / 255
    overlay[occ2 & ~occ1] = np.array([233, 154, 62]) / 255
    overlay[occ1 & occ2] = np.array([21, 50, 75]) / 255
    unknown = (first >= 80) & (first < 240)
    overlay[unknown & ~(occ1 | occ2)] = np.array([0.82, 0.84, 0.85])

    fig, axes = plt.subplots(1, 2, figsize=(14, 6.8), gridspec_kw={"width_ratios": [1.35, 0.85]})
    fig.suptitle("两次仿真建图的一致性与栅格组成", fontsize=21, weight="bold", color=NAVY, y=0.98)
    ax = axes[0]
    ax.imshow(overlay, origin="upper", extent=[-3.92, 3.93, -2.93, 2.92])
    ax.set_title("相同坐标下的占据栅格叠加", fontsize=13, weight="bold")
    ax.set_xlabel("map x（米）")
    ax.set_ylabel("map y（米）")
    ax.grid(alpha=0.12)
    legend_handles = [
        Rectangle((0, 0), 1, 1, color=NAVY, label="两次重合"),
        Rectangle((0, 0), 1, 1, color=BLUE, label="仅第一轮"),
        Rectangle((0, 0), 1, 1, color=ORANGE, label="仅第二轮"),
    ]
    ax.legend(handles=legend_handles, loc="lower right", fontsize=9)
    ax.text(0.02, 0.97, "三条垄中心偏移均为0.050米\n项目重复性门槛为0.150米",
            transform=ax.transAxes, va="top", fontsize=10.5, color=NAVY,
            bbox=dict(facecolor="white", edgecolor="#CAD4DA", alpha=0.92, boxstyle="round,pad=0.45"))

    ax = axes[1]
    labels = ["占据栅格", "自由栅格", "未知栅格"]
    counts = np.array([1653, 15871, 845])
    colors = [NAVY, "#DDEAF2", "#AAB6BE"]
    wedges, _ = ax.pie(counts, colors=colors, startangle=90,
                       wedgeprops=dict(width=0.38, edgecolor="white"))
    ax.text(0, 0.10, "157 × 117", ha="center", fontsize=18, weight="bold", color=NAVY)
    ax.text(0, -0.12, "0.05米每栅格", ha="center", fontsize=10.5, color=GRAY)
    legend_labels = [f"{name}  {value}（{value/counts.sum():.1%}）" for name, value in zip(labels, counts)]
    ax.legend(wedges, legend_labels, loc="lower center", bbox_to_anchor=(0.5, -0.10),
              frameon=False, fontsize=10)
    ax.set_title("首轮地图栅格组成", fontsize=13, weight="bold")
    fig.subplots_adjust(top=0.86, bottom=0.11, wspace=0.18)
    save(fig, "导航_SLAM重复性与栅格统计.png")


def slam_sensor_architecture():
    """统一重绘成员稿中的SLAM软硬件数据流，避免框外文字与风格割裂。"""
    fig, ax = plt.subplots(figsize=(13, 6.6))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    ax.text(0.5, 0.95, "SLAM 多传感器系统架构", ha="center", va="top",
            fontsize=20, weight="bold", color=NAVY)
    box(ax, (0.04, 0.66), (0.18, 0.14), "轮式里程计", "车轮增量里程", fc="#F3F5F6", ec=GRAY)
    box(ax, (0.04, 0.39), (0.18, 0.14), "惯性测量", "角速度与线加速度", fc="#F3F5F6", ec=GRAY)
    box(ax, (0.04, 0.12), (0.18, 0.14), "二维激光雷达", "扫描距离序列", fc="#F3F5F6", ec=GRAY)
    box(ax, (0.31, 0.53), (0.20, 0.17), "局部扩展卡尔曼滤波", "轮速与惯性融合\n输出连续里程计", fc="#EAF4FA", ec=BLUE)
    box(ax, (0.60, 0.38), (0.22, 0.20), "SLAM Toolbox", "扫描匹配 · 回环检测\n位姿图优化", fc="#EFF2FA", ec="#5469A6", title_size=15)
    box(ax, (0.86, 0.65), (0.11, 0.14), "占据栅格地图", "map", fc="#E9F6F0", ec=GREEN, title_size=11)
    box(ax, (0.86, 0.39), (0.11, 0.14), "融合里程计", "odom", fc="#E9F6F0", ec=GREEN, title_size=11)
    box(ax, (0.86, 0.13), (0.11, 0.14), "序列化位姿图", "posegraph\ndata", fc="#E9F6F0", ec=GREEN, title_size=11, subtitle_size=8.2)
    arrow(ax, (0.22, 0.73), (0.31, 0.64), color=GRAY)
    arrow(ax, (0.22, 0.46), (0.31, 0.59), color=GRAY)
    arrow(ax, (0.51, 0.615), (0.60, 0.51), color=BLUE)
    arrow(ax, (0.22, 0.19), (0.60, 0.43), color=GRAY)
    arrow(ax, (0.82, 0.53), (0.86, 0.72), color=GREEN)
    arrow(ax, (0.82, 0.48), (0.86, 0.46), color=GREEN)
    arrow(ax, (0.82, 0.43), (0.86, 0.20), color=GREEN)
    save(fig, "导航_SLAM多传感器架构.png")


def slam_mapping_process():
    fig, ax = plt.subplots(figsize=(13.5, 5.6))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    ax.text(0.5, 0.94, "二维激光 SLAM 建图处理流程", ha="center", va="top",
            fontsize=20, weight="bold", color=NAVY)
    xs = [0.035, 0.195, 0.355, 0.515, 0.675, 0.835]
    titles = ["采集与时间同步", "局部运动估计", "二维扫描匹配", "位姿图与回环", "全局图优化", "地图与位姿图保存"]
    subtitles = ["激光 · 里程计\n惯性测量", "轮速—惯性融合\n提供初值", "当前扫描对齐\n形成局部约束", "关键帧节点\n可信回环边", "联合优化节点\n与约束", "PGM · YAML\n位姿图数据"]
    colors = ["#F3F5F6", "#EAF4FA", "#EAF4FA", "#FFF4E7", "#EFF2FA", "#E9F6F0"]
    edges = [GRAY, BLUE, BLUE, ORANGE, "#5469A6", GREEN]
    for i, x in enumerate(xs):
        box(ax, (x, 0.48), (0.13, 0.24), titles[i], subtitles[i],
            fc=colors[i], ec=edges[i], title_size=11.5, subtitle_size=8.7)
        if i < len(xs) - 1:
            arrow(ax, (x + 0.13, 0.60), (xs[i + 1], 0.60), color=GRAY)
    box(ax, (0.43, 0.16), (0.22, 0.14), "回环质量判定", "几何一致性 · 残差门限\n不可信约束不入图", fc="#FFF0EE", ec=RED)
    arrow(ax, (0.58, 0.48), (0.54, 0.30), color=ORANGE)
    arrow(ax, (0.65, 0.23), (0.74, 0.48), color=ORANGE)
    save(fig, "导航_SLAM建图处理流程.png")


def slam_map_summary():
    pgm = ROOT / "spore-vehicle-nav" / "results" / "sim_farmland_8x6_20260831" / "sim_farmland_8x6.pgm"
    image = np.asarray(Image.open(pgm).convert("L"))
    fig, (ax, meta) = plt.subplots(1, 2, figsize=(12.8, 6.8),
                                   gridspec_kw={"width_ratios": [1.55, 0.75]})
    fig.suptitle("6米 × 8米模拟垄占据栅格地图", fontsize=20, weight="bold", color=NAVY, y=0.97)
    ax.imshow(image, cmap="gray", vmin=0, vmax=255, origin="upper",
              extent=[-3.92, 3.93, -2.93, 2.92])
    ax.set_xlabel("map x（米）"); ax.set_ylabel("map y（米）")
    ax.set_aspect("equal"); ax.grid(alpha=0.10)
    meta.axis("off")
    meta.text(0.02, 0.86, "地图元数据", fontsize=16, weight="bold", color=NAVY)
    items = ["栅格：157 × 117", "分辨率：0.050 米/栅格", "覆盖范围：7.85 × 5.85 米",
             "原点：(-3.92, -2.93)", "占据栅格：9.0%", "自由栅格：86.4%", "未知栅格：4.6%"]
    for i, item in enumerate(items):
        meta.text(0.02, 0.75 - i * 0.085, item, fontsize=11.5, color=NAVY)
    handles = [Rectangle((0, 0), 1, 1, color="black", label="占据栅格"),
               Rectangle((0, 0), 1, 1, facecolor="white", edgecolor=GRAY, label="自由空间"),
               Rectangle((0, 0), 1, 1, color="#AAB6BE", label="未知区域")]
    meta.legend(handles=handles, loc="lower left", frameon=False, fontsize=11,
                handlelength=1.5, handleheight=1.2)
    fig.subplots_adjust(top=0.87, bottom=0.10, wspace=0.12)
    save(fig, "导航_模拟垄占据栅格地图.png")


def sampling_planning_chain():
    fig, ax = plt.subplots(figsize=(13, 6.8))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    ax.text(0.5, 0.95, "农田采样点与小车路径规划处理链", ha="center", va="top",
            fontsize=20, weight="bold", color=NAVY)
    top = [
        (0.04, "田块边界与地图", "人工闭合边界\n或SLAM地图"),
        (0.28, "作业方向确定", "首边标定\n主方向估计"),
        (0.52, "平行作业线生成", "按垄距扫描\n裁剪可达线段"),
        (0.76, "覆盖置信度更新", "距离衰减模型\n形成置信度矩阵"),
    ]
    for i, (x, title, sub) in enumerate(top):
        box(ax, (x, 0.64), (0.18, 0.16), title, sub,
            fc=["#F3F5F6", "#EAF4FA", "#E9F6F0", "#FFF4E7"][i],
            ec=[GRAY, BLUE, GREEN, ORANGE][i])
        if i < len(top)-1: arrow(ax, (x+0.18, 0.72), (top[i+1][0], 0.72), color=GRAY)
    box(ax, (0.12, 0.27), (0.22, 0.16), "多轮互补采样点", "选择边际覆盖增益\n最大的候选点", fc="#FFF4E7", ec=ORANGE)
    box(ax, (0.39, 0.27), (0.22, 0.16), "访问顺序优化", "最近邻初始化\n2-opt 路径改进", fc="#EAF4FA", ec=BLUE)
    box(ax, (0.66, 0.27), (0.22, 0.16), "任务路线输出", "同垄直达 · 跨垄走地头\nroute_v1.json 米制航点", fc="#E9F6F0", ec=GREEN)
    arrow(ax, (0.85, 0.64), (0.23, 0.43), color=GRAY)
    arrow(ax, (0.34, 0.35), (0.39, 0.35), color=GRAY)
    arrow(ax, (0.61, 0.35), (0.66, 0.35), color=GRAY)
    save(fig, "导航_采样路径规划处理链.png")


def coverage_confidence_selection():
    fig, axes = plt.subplots(1, 2, figsize=(13, 6.2))
    fig.suptitle("覆盖置信度模型与贪心选点机制", fontsize=20, weight="bold", color=NAVY, y=0.97)
    ax = axes[0]
    distance = np.linspace(0, 22, 300); radius = 20.0
    confidence = np.maximum(0, 1 - (distance / radius) ** 2)
    ax.plot(distance, confidence, color=BLUE, linewidth=3, label="覆盖置信度")
    ax.fill_between(distance, confidence, alpha=0.12, color=BLUE)
    ax.axvline(radius / np.sqrt(2), color=ORANGE, linestyle="--", label="半高覆盖距离")
    ax.axvline(radius, color=GRAY, linestyle=":", label="有效半径")
    ax.set(xlabel="距采样点距离 d（米）", ylabel="覆盖置信度 c(d)", ylim=(0, 1.08), xlim=(0, 22))
    ax.set_title("单点覆盖置信度随距离衰减", fontsize=13, weight="bold")
    ax.grid(alpha=0.2); ax.legend(loc="upper right", fontsize=9)
    ax = axes[1]
    ax.set_title("按边际增益选择候选点", fontsize=13, weight="bold")
    ax.set_xlim(0, 10); ax.set_ylim(0, 7); ax.set_aspect("equal"); ax.axis("off")
    field = Rectangle((0.7, 0.8), 8.6, 5.3, angle=-4, facecolor="#F5F4D8", edgecolor=NAVY, linewidth=1.6)
    ax.add_patch(field)
    for x, y in [(2.3, 2.4), (5.1, 4.6)]:
        ax.add_patch(Circle((x, y), 1.45, color=BLUE, alpha=0.12)); ax.scatter(x, y, s=55, color=BLUE, edgecolor="white", zorder=3)
    chosen=(7.4, 2.5)
    ax.add_patch(Circle(chosen, 1.45, color=ORANGE, alpha=0.18)); ax.scatter(*chosen, s=70, color=ORANGE, edgecolor="white", zorder=3)
    ax.annotate("本轮新增点", xy=chosen, xytext=(8.9, 4.3), color=ORANGE, ha="center",
                arrowprops=dict(arrowstyle="->", color=ORANGE), fontsize=11, weight="bold")
    fig.subplots_adjust(top=0.84, bottom=0.11, wspace=0.22)
    save(fig, "导航_覆盖置信度与贪心选点.png")


def planning_execution_chain():
    fig, ax = plt.subplots(figsize=(13.5, 6.3))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    ax.text(0.5, 0.95, "规划结果到车辆执行的坐标与控制链", ha="center", va="top",
            fontsize=20, weight="bold", color=NAVY)
    top = [(0.06, "网页规划器", "田块边界与采样点", BLUE),
           (0.39, "路线任务文件", "route_v1.json\nfield 米制坐标", "#5469A6"),
           (0.72, "坐标对准", "field 到 map\n起点位姿与航向", GREEN)]
    for i, (x, title, sub, ec) in enumerate(top):
        box(ax, (x, 0.64), (0.22, 0.16), title, sub, fc=LIGHT, ec=ec)
        if i < 2: arrow(ax, (x+0.22, 0.72), (top[i+1][0], 0.72), color=ec)
    bottom = [(0.04, "曲线平滑与等弧长重采样", "生成连续参考轨迹", GRAY),
              (0.285, "前视路径跟踪", "计算线速度与角速度", BLUE),
              (0.53, "激光雷达安全判定", "减速 · 停车 · 局部处置", ORANGE),
              (0.775, "底盘与采样状态机", "速度指令 · 到点触发", GREEN)]
    for i, (x, title, sub, ec) in enumerate(bottom):
        box(ax, (x, 0.25), (0.19, 0.17), title, sub, fc=LIGHT, ec=ec, title_size=11.5)
        if i < 3: arrow(ax, (x+0.19, 0.335), (bottom[i+1][0], 0.335), color=ec)
    arrow(ax, (0.83, 0.64), (0.135, 0.42), color=GRAY)
    save(fig, "导航_规划到车辆执行链.png")


if __name__ == "__main__":
    navigation_architecture()
    navigation_field_route()
    console_architecture()
    algorithm_pipeline()
    metric_comparison()
    applicability_matrix()
    coordinate_frames()
    fusion_quality_gate()
    navigation_integrated_chain()
    rtk_stage_metrics()
    console_dataflow()
    console_safety_permissions()
    source_inversion()
    lightweight_benchmark()
    navigation_route_evidence()
    navigation_mission_timeline()
    slam_repeatability_evidence()
    slam_sensor_architecture()
    slam_mapping_process()
    slam_map_summary()
    sampling_planning_chain()
    coverage_confidence_selection()
    planning_execution_chain()
    print("已生成：")
    for path in sorted(OUT.glob("*.png")):
        print(path.relative_to(ROOT))
