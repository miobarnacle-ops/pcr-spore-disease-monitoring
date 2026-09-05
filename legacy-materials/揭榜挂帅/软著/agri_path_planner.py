import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import math
import csv
import json

try:
    from PIL import Image, ImageTk, ImageDraw
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False


# =========================================================
# 几何基础算子 (模块级，避免类内耦合)
# =========================================================

def _rotate_pt(x, y, cx, cy, theta):
    """点绕(cx,cy)旋转theta弧度，返回旋转后坐标"""
    dx, dy = x - cx, y - cy
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    return dx * cos_t - dy * sin_t + cx, dx * sin_t + dy * cos_t + cy


def _point_in_poly(x, y, poly):
    """射线法判点在多边形内，poly为[(x,y),...]顶点序列"""
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _seg_intersections(scan_y, poly):
    """求水平线y=scan_y与多边形poly的交点x列表，已排序"""
    pts = []
    j = len(poly) - 1
    for i in range(len(poly)):
        px1, py1 = poly[i]
        px2, py2 = poly[j]
        if (py1 <= scan_y < py2) or (py2 <= scan_y < py1):
            if abs(py2 - py1) > 1e-9:
                ix = px1 + (scan_y - py1) * (px2 - px1) / (py2 - py1)
                pts.append(ix)
        j = i
    pts.sort()
    return pts


# =========================================================
# 覆盖评估子模块
# [UPDATED 2026-07-12] 引入空间分箱加速候选点增益评估，
# 将原来的 O(P*C*G) 降到近似 O(P*C*局部格点数)
# =========================================================

class CoverageEvaluator:
    """管理评估格网、候选点池、累积置信度，提供贪心选址接口"""

    def __init__(self, eval_grid, candidate_pool, radius_px):
        self.eval_grid = eval_grid          # [(gx, gy), ...] 画布坐标
        self.candidates = candidate_pool    # [dict, ...] 候选采样点
        self.radius_px = radius_px
        self.n_grid = len(eval_grid)
        self.n_cand = len(candidate_pool)

        # 构建空间分箱：将格网按 cell_size 分桶，加速邻域查询
        self.cell_size = max(radius_px, 20.0)
        self._build_spatial_index()

    def _build_spatial_index(self):
        """将格网点按空间栅格分箱，存每个cell内的格点下标列表"""
        self.grid_bins = {}
        for g_idx, (gx, gy) in enumerate(self.eval_grid):
            cx_bin = int(gx / self.cell_size)
            cy_bin = int(gy / self.cell_size)
            key = (cx_bin, cy_bin)
            if key not in self.grid_bins:
                self.grid_bins[key] = []
            self.grid_bins[key].append(g_idx)

        # 候选点也做同样分箱
        self.cand_bins = {}
        for c_idx, cand in enumerate(self.candidates):
            cx, cy = cand['real_xy']
            bx = int(cx / self.cell_size)
            by = int(cy / self.cell_size)
            key = (bx, by)
            if key not in self.cand_bins:
                self.cand_bins[key] = []
            self.cand_bins[key].append(c_idx)

    def _neighbor_grid_indices(self, cand_x, cand_y):
        """返回候选点可能覆盖到的格网下标 (只查相邻分箱)"""
        cx_bin = int(cand_x / self.cell_size)
        cy_bin = int(cand_y / self.cell_size)
        indices = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                key = (cx_bin + dx, cy_bin + dy)
                if key in self.grid_bins:
                    indices.extend(self.grid_bins[key])
        return indices

    def evaluate_candidate(self, cand, base_confidence):
        """评估单个候选点相对base_confidence的覆盖增益"""
        cx, cy = cand['real_xy']
        r2 = self.radius_px ** 2
        total_gain = 0.0
        new_confs = list(base_confidence)

        for g_idx in self._neighbor_grid_indices(cx, cy):
            gx, gy = self.eval_grid[g_idx]
            dx, dy = gx - cx, gy - cy
            dist2 = dx * dx + dy * dy
            if dist2 < r2:
                confidence = 1.0 - dist2 / r2  # 二次衰减模型
                if confidence > base_confidence[g_idx]:
                    delta = confidence - base_confidence[g_idx]
                    total_gain += delta
                    new_confs[g_idx] = confidence

        return total_gain, new_confs

    def greedy_select_round(self, base_confidence, num_select):
        """从base_confidence出发贪心选num_select个点，返回(list[dict], list[float])"""
        selected = []
        cur_conf = list(base_confidence)
        # 维护候选池的可用标记
        available = [True] * self.n_cand

        for _ in range(num_select):
            best_cand = None
            best_gain = -1.0
            best_confs = None
            best_cidx = -1

            for c_idx, cand in enumerate(self.candidates):
                if not available[c_idx]:
                    continue
                gain, new_confs = self.evaluate_candidate(cand, cur_conf)
                if gain > best_gain:
                    best_gain = gain
                    best_cand = cand
                    best_confs = new_confs
                    best_cidx = c_idx

            if best_cand is None or best_gain < 0.001:
                break  # 增益过低，提前终止
            selected.append(best_cand)
            cur_conf = best_confs
            available[best_cidx] = False

        return selected, cur_conf


# =========================================================
# 地头路径计算
# =========================================================

def _compute_headland_path(node_a, node_b, ridge_db, cx, cy, theta):
    """计算两采样点间的地头转弯路径。
    同垄：直接横向平移。
    跨垄：比较左端绕行与右端绕行距离，取短者。
    返回 (距离, [途经点画布坐标列表])
    """
    ra, rb = node_a['ridge_idx'], node_b['ridge_idx']
    xa, ya = node_a['rot_xy']
    xb, yb = node_b['rot_xy']

    if ra == rb:
        return abs(xa - xb), [node_a['real_xy'], node_b['real_xy']]

    la, lb = ridge_db[ra]['left_rot'], ridge_db[rb]['left_rot']
    ra_, rb_ = ridge_db[ra]['right_rot'], ridge_db[rb]['right_rot']

    dist_left = (xa - la) + abs(ya - yb) + (xb - lb)
    dist_right = (ra_ - xa) + abs(ya - yb) + (rb_ - xb)

    if dist_left < dist_right:
        waypoints = [
            node_a['real_xy'],
            _rotate_pt(la, ya, cx, cy, theta),
            _rotate_pt(lb, yb, cx, cy, theta),
            node_b['real_xy']
        ]
        return dist_left, waypoints
    else:
        waypoints = [
            node_a['real_xy'],
            _rotate_pt(ra_, ya, cx, cy, theta),
            _rotate_pt(rb_, yb, cx, cy, theta),
            node_b['real_xy']
        ]
        return dist_right, waypoints


# =========================================================
# TSP 路径优化 (最近邻构造 + 2-opt 局部搜索)
# =========================================================

def _nn_tour(nodes, cx, cy, theta, ridge_db):
    """最近邻贪心构造初始回路，返回访问顺序列表"""
    n = len(nodes)
    if n <= 2:
        return list(range(n))

    visited = [False] * n
    tour = [0]
    visited[0] = True

    for _ in range(n - 1):
        last = tour[-1]
        best_j, best_d = -1, float('inf')
        for j in range(n):
            if visited[j]:
                continue
            d, _ = _compute_headland_path(nodes[last], nodes[j], ridge_db, cx, cy, theta)
            if d < best_d:
                best_d = d
                best_j = j
        tour.append(best_j)
        visited[best_j] = True

    return tour


def _two_opt(tour, nodes, cx, cy, theta, ridge_db, max_iter=50):
    """2-opt 局部搜索改进回路"""
    n = len(nodes)
    if n < 3:
        return tour

    best_tour = list(tour)
    improved = True
    iteration = 0

    while improved and iteration < max_iter:
        improved = False
        iteration += 1
        for i in range(1, n - 2):
            for j in range(i + 1, n):
                if j - i == 1:
                    continue
                # 计算交换前两条边的距离
                a, b = best_tour[i - 1], best_tour[i]
                c, d = best_tour[j], best_tour[(j + 1) % n]
                d_ab, _ = _compute_headland_path(nodes[a], nodes[b], ridge_db, cx, cy, theta)
                d_cd, _ = _compute_headland_path(nodes[c], nodes[d], ridge_db, cx, cy, theta)
                # 计算交换后两条边的距离
                d_ac, _ = _compute_headland_path(nodes[a], nodes[c], ridge_db, cx, cy, theta)
                d_bd, _ = _compute_headland_path(nodes[b], nodes[d], ridge_db, cx, cy, theta)

                if (d_ac + d_bd) < (d_ab + d_cd):
                    best_tour[i:j + 1] = reversed(best_tour[i:j + 1])
                    improved = True

    return best_tour


# =========================================================
# 热力图伪彩色映射
# =========================================================

def _conf_to_rgba(conf):
    """置信度 [0,1] 映射到 RGBA 伪彩色。
    红(低) -> 橙 -> 黄 -> 黄绿 -> 绿(高)，alpha随置信度升高。
    """
    if conf < 0.001:
        return (0, 0, 0, 0)

    if conf < 0.25:
        t = conf / 0.25
        r, g, b = 220, int(30 + 80 * t), 30
    elif conf < 0.5:
        t = (conf - 0.25) / 0.25
        r, g, b = 220, int(110 + 100 * t), 30
    elif conf < 0.75:
        t = (conf - 0.5) / 0.25
        r, g, b = int(220 - 150 * t), int(210 + 40 * t), 30
    else:
        t = (conf - 0.75) / 0.25
        r, g, b = int(70 - 30 * t), int(250 - 50 * t), 30

    alpha = int(50 + 110 * conf)
    return (r, g, b, alpha)


# =========================================================
# 主界面与控制逻辑
# [UPDATED 2026-07-12] 拆分几何函数、覆盖求解器；加入输入校验；
# 使用空间分箱加速贪心选址；修正 2-opt 迭代边界
# =========================================================

class AgriAdvancedPlanner:
    """多模态智能巡检系统 - 孢子最优网格覆盖与地头路由规划模块 V1.0"""

    def __init__(self, root):
        self.root = root
        self.root.title("多模态智能巡检系统 - 孢子最优网格覆盖与地头路由规划模块 V1.0")
        self.root.geometry("1400x850")

        # 配色方案
        self.COLOR_BG = "#161a1d"
        self.COLOR_GRID = "#1f2d3d"
        self.COLOR_RIDGE = "#282e38"
        self.COLOR_BORDER = "#00a8ff"
        self.COLOR_PATH = "#00ecc6"
        self.COLOR_BADGE_BG = "#1e272e"

        # 多轮次独立配色
        self.ROUND_COLORS = [
            "#ff9f43", "#00a8ff", "#e056a0", "#f1c40f", "#9b59b6"
        ]

        # 图像缓存
        self.photo_image = None
        self.circle_photo = None
        self.pil_image = None

        # 标定状态
        self.field_polygon = []
        self.is_drawing = False

        # 规划结果
        self.all_rounds_selected = []
        self.all_rounds_tours = []
        self.cumulative_confidence = []
        self.heatmap_photo = None
        self.eval_grid = []
        self.ridge_db = {}
        self.grid_step = 1.0

        # 缓存最近一次规划的比例尺参数，供导出复用
        self._cached_scale = 1.0
        self._cached_ref_x1 = 0.0
        self._cached_ref_y1 = 0.0
        self._cached_radius_m = 20.0
        self._cached_speed = 0.5
        # [UPDATED 2026-07-13] 缓存逐轮路径段距离与行驶时间，供导出和统计
        self._cached_round_segments = []  # list[list[dict]] 每轮每段 {from, to, dist_m, time_s}

        self.setup_ui()

    # =========================================================
    # UI 布局
    # =========================================================

    def setup_ui(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TLabel", foreground="#dcdde1", background="#2f3640")

        control_frame = tk.Frame(self.root, bg="#212529", width=350)
        control_frame.pack(side="left", fill="y")

        title_lbl = tk.Label(control_frame, text="AUTONOMOUS NAVIGATION CONTROL",
                             fg="#718093", bg="#212529", font=("Consolas", 9, "bold"))
        title_lbl.pack(pady=(20, 2))

        ttk.Button(control_frame, text="1. 导入空地多光谱卫星图",
                   command=self.load_image).pack(pady=10, fill="x", padx=20)
        ttk.Button(control_frame, text="2. 标定不规则边界(首边为垄向)",
                   command=self.start_drawing).pack(pady=10, fill="x", padx=20)
        ttk.Button(control_frame, text="闭合农田拓扑空间",
                   command=self.close_polygon).pack(pady=5, fill="x", padx=20)

        # 参数面板
        param_bg = tk.Frame(control_frame, bg="#2c313c", bd=1, relief="solid")
        param_bg.pack(pady=20, fill="x", padx=20)

        def _make_entry(label, default, row):
            tk.Label(param_bg, text=label, fg="#dcdde1", bg="#2c313c",
                     font=("微软雅黑", 10)).grid(row=row, column=0, pady=10, padx=15, sticky="w")
            ent = tk.Entry(param_bg, width=8, bg="#161a1d", fg="#00ecc6", bd=0,
                           insertbackground="white", font=("Consolas", 11, "bold"))
            ent.insert(0, default)
            ent.grid(row=row, column=1, pady=10, padx=15, sticky="e")
            return ent

        self.entry_ref_len = _make_entry("基准首边长度 (m)", "100.0", 0)
        self.entry_ridge_dist = _make_entry("作物种植垄距 (m)", "4.0", 1)
        self.entry_sample_count = _make_entry("每轮采样点数 (P)", "8", 2)
        self.entry_radius = _make_entry("孢子有效半径 (R)", "20.0", 3)
        self.entry_num_rounds = _make_entry("采集轮次 (K)", "2", 4)
        self.entry_speed = _make_entry("小车行驶速度 (m/s)", "0.5", 5)

        ttk.Button(control_frame, text="3. 求解全覆盖路由方案",
                   command=self.solve_planning_pipeline).pack(pady=20, fill="x", padx=20)
        ttk.Button(control_frame, text="导出采样点坐标 (CSV)",
                   command=self.export_csv).pack(pady=5, fill="x", padx=20)
        ttk.Button(control_frame, text="导出路径规划结果 (JSON)",
                   command=self.export_json).pack(pady=5, fill="x", padx=20)
        ttk.Button(control_frame, text="清空解算画布",
                   command=self.clear_canvas).pack(pady=5, fill="x", padx=20)

        self.status_var = tk.StringVar()
        self.status_var.set("SYS READY: 等待标定区域坐标系...")
        status_lbl = tk.Label(control_frame, textvariable=self.status_var, wraplength=300,
                              fg="#e1b12c", bg="#212529", font=("微软雅黑", 10, "bold"))
        status_lbl.pack(side="bottom", pady=30)

        self.canvas_frame = ttk.Frame(self.root)
        self.canvas_frame.pack(side="right", fill="both", expand=True)
        self.canvas = tk.Canvas(self.canvas_frame, bg=self.COLOR_BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Button-1>", self.on_canvas_click)

    # =========================================================
    # [UPDATED 2026-07-12] 参数解析加入 try/except 防崩溃
    # =========================================================

    def _parse_params(self):
        """解析用户输入参数，转换失败时弹出警告并返回 None"""
        try:
            ref_len = float(self.entry_ref_len.get())
            ridge_dist = float(self.entry_ridge_dist.get())
            n_samples = int(self.entry_sample_count.get())
            radius = float(self.entry_radius.get())
            n_rounds = int(self.entry_num_rounds.get())
            speed = float(self.entry_speed.get())
        except ValueError:
            messagebox.showerror("参数错误", "请输入合法的数值参数。")
            return None
        if ref_len <= 0 or ridge_dist <= 0 or radius <= 0 or n_samples < 1 or n_rounds < 1 or speed <= 0:
            messagebox.showerror("参数错误", "参数值必须为正数。")
            return None
        return ref_len, ridge_dist, n_samples, radius, n_rounds, speed

    # =========================================================
    # 图像加载与多边形标定
    # =========================================================

    def load_image(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif")])
        if file_path and HAS_PILLOW:
            try:
                self.pil_image = Image.open(file_path)
                cw = self.canvas.winfo_width()
                ch = self.canvas.winfo_height()
                if cw < 10:
                    cw, ch = 1000, 800
                self.pil_image.thumbnail((cw, ch))
                self.photo_image = ImageTk.PhotoImage(self.pil_image)
                self.canvas.delete("all")
                # [UPDATED 2026-07-13] 小图居中放置，避免缩在边角不便框选
                iw, ih = self.pil_image.size
                ox = (cw - iw) // 2
                oy = (ch - ih) // 2
                self.canvas.create_image(ox, oy, anchor="nw", image=self.photo_image)
                self.status_var.set("MAP LOADED: 卫星影像注入完成，尺度自适应就绪。")
            except Exception as e:
                messagebox.showerror("Error", f"图像解析异常: {e}")

    def start_drawing(self):
        self.is_drawing = True
        self.field_polygon = []
        self.canvas.delete("ridge", "path", "point", "circle", "grid", "heatmap")
        self.status_var.set("DIGITIZING: 正在标定空间拓扑边界线...")

    def on_canvas_click(self, event):
        if not self.is_drawing:
            return
        x, y = event.x, event.y
        self.field_polygon.append((x, y))
        self.canvas.create_oval(x - 3, y - 3, x + 3, y + 3,
                                fill="#ffffff", outline=self.COLOR_BORDER,
                                width=1, tags="polygon")
        if len(self.field_polygon) > 1:
            x1, y1 = self.field_polygon[-2]
            color = self.COLOR_BORDER if len(self.field_polygon) == 2 else "#ffffff"
            width = 3 if len(self.field_polygon) == 2 else 1.5
            self.canvas.create_line(x1, y1, x, y, fill=color, width=width, tags="polygon")

    def close_polygon(self):
        if len(self.field_polygon) > 2:
            self.canvas.create_line(
                self.field_polygon[-1][0], self.field_polygon[-1][1],
                self.field_polygon[0][0], self.field_polygon[0][1],
                fill="#ffffff", width=1.5, tags="polygon")
            self.is_drawing = False
            self.status_var.set("TOPOLOGY CLOSED: 多边形闭合，进入数理网格解算态。")
        else:
            messagebox.showwarning("Warning", "多边形边界闭合需要至少3个空间离散点。")

    # =========================================================
    # 路径箭头的画布绘制
    # =========================================================

    def _draw_arrow(self, x1, y1, x2, y2, color):
        """在线段 75% 处绘制流向箭头"""
        mx = x1 + 0.75 * (x2 - x1)
        my = y1 + 0.75 * (y2 - y1)
        angle = math.atan2(y2 - y1, x2 - x1)
        alen, awid = 10, 5
        p1 = (mx + alen * math.cos(angle), my + alen * math.sin(angle))
        p2 = (mx + awid * math.cos(angle + math.pi * 0.85),
              my + awid * math.sin(angle + math.pi * 0.85))
        p3 = (mx + awid * math.cos(angle - math.pi * 0.85),
              my + awid * math.sin(angle - math.pi * 0.85))
        self.canvas.create_polygon(p1[0], p1[1], p2[0], p2[1], p3[0], p3[1],
                                   fill=color, outline="", tags="path")

    # =========================================================
    # PIL 热力图与覆盖圆渲染
    # =========================================================

    def _render_heatmap(self, canvas_w, canvas_h):
        """逐格点填色生成热力图 overlay，压入 Canvas"""
        if not HAS_PILLOW or not self.eval_grid or not self.cumulative_confidence:
            return
        overlay = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        half = self.grid_step / 2.0

        for g_idx, (gx, gy) in enumerate(self.eval_grid):
            color = _conf_to_rgba(self.cumulative_confidence[g_idx])
            if color[3] == 0:
                continue
            draw.rectangle(
                [gx - half, gy - half, gx + half, gy + half], fill=color)

        self.heatmap_photo = ImageTk.PhotoImage(overlay)
        self.canvas.create_image(0, 0, anchor="nw",
                                 image=self.heatmap_photo, tags="heatmap")

    def _render_coverage_circles(self, canvas_w, canvas_h, radius_px):
        """三层同心半透明圆表示孢子有效覆盖半径"""
        if not HAS_PILLOW:
            return
        overlay = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        for round_nodes in self.all_rounds_selected:
            for node in round_nodes:
                nx, ny = node['real_xy']
                r = radius_px
                draw.ellipse([nx - r, ny - r, nx + r, ny + r],
                             fill=(27, 42, 36, 25), outline=(76, 209, 55, 60), width=1)
                draw.ellipse([nx - r * 0.6, ny - r * 0.6, nx + r * 0.6, ny + r * 0.6],
                             fill=(34, 62, 50, 45), outline=(76, 209, 55, 90), width=1)
                draw.ellipse([nx - r * 0.3, ny - r * 0.3, nx + r * 0.3, ny + r * 0.3],
                             fill=(46, 91, 70, 75), outline=(186, 220, 88, 130), width=1)
        self.circle_photo = ImageTk.PhotoImage(overlay)
        self.canvas.create_image(0, 0, anchor="nw",
                                 image=self.circle_photo, tags="circle")

    # =========================================================
    # [UPDATED 2026-07-12] 核心规划管线
    # 阶段一：垄线扫描 + 候选点撒布 + 评估格网建立
    # 阶段二：多轮互补贪心覆盖选址（使用空间分箱加速）
    # 阶段三：逐轮最近邻 + 2-opt 路径优化
    # 阶段四：分层可视化渲染
    # =========================================================

    def solve_planning_pipeline(self):
        if len(self.field_polygon) < 3:
            messagebox.showerror("Error", "执行覆盖图论路由前请先闭合农田拓扑空间！")
            return

        params = self._parse_params()
        if params is None:
            return
        actual_ref_len, ridge_dist_m, num_samples, radius_m, num_rounds, speed_ms = params

        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        if canvas_w < 10:
            canvas_w, canvas_h = 1000, 800

        # 清除上轮叠加图层 (含编号徽章text，否则改轮次后旧标签残留)
        self.canvas.delete("ridge", "path", "point", "circle", "grid", "heatmap", "text")
        self.heatmap_photo = None
        self.circle_photo = None
        self.status_var.set("CALCULATING: 覆盖矩阵收敛中...")
        self.root.update()

        # ---- 尺度标定 ----
        ref_x1, ref_y1 = self.field_polygon[0]
        ref_x2, ref_y2 = self.field_polygon[1]
        px_ref_len = math.hypot(ref_x2 - ref_x1, ref_y2 - ref_y1)
        if px_ref_len < 1.0:
            messagebox.showerror("Error", "基准边长度过短，请重新标定边界。")
            return
        scale = px_ref_len / actual_ref_len  # 像素/米

        ridge_dist_px = ridge_dist_m * scale
        radius_px = radius_m * scale
        theta = math.atan2(ref_y2 - ref_y1, ref_x2 - ref_x1)

        # 缓存供导出使用
        self._cached_scale = scale
        self._cached_ref_x1 = ref_x1
        self._cached_ref_y1 = ref_y1
        self._cached_radius_m = radius_m
        self._cached_speed = speed_ms

        # ---- 旋转至垄向对齐坐标系 ----
        cx, cy = ref_x1, ref_y1
        rot_poly = [_rotate_pt(x, y, cx, cy, -theta) for x, y in self.field_polygon]
        min_x = min(p[0] for p in rot_poly)
        max_x = max(p[0] for p in rot_poly)
        min_y = min(p[1] for p in rot_poly)
        max_y = max(p[1] for p in rot_poly)
        box_w, box_h = max_x - min_x, max_y - min_y

        # ---- 自适应步长 ----
        # 格网评估步长：控制评估单元数在一个合理范围
        self.grid_step = max(4.0 * scale,
                             math.sqrt((box_w * box_h) / 1200.0))
        approx_ridges = max(1, box_h / ridge_dist_px)
        step_px = max(1.5 * scale, (box_w * approx_ridges) / 800.0)

        # ========== 阶段一：垄线扫描与候选点生成 ==========
        candidate_pool = []
        self.ridge_db = {}
        scan_y = min_y + ridge_dist_px / 2.0
        ridge_index = 0

        while scan_y <= max_y:
            pts = _seg_intersections(scan_y, rot_poly)
            for i in range(0, len(pts) - 1, 2):
                sx, ex = pts[i], pts[i + 1]
                self.ridge_db[ridge_index] = {
                    'y_rot': scan_y, 'left_rot': sx, 'right_rot': ex}

                cur_x = sx + step_px
                while cur_x <= ex - step_px:
                    candidate_pool.append({
                        'real_xy': _rotate_pt(cur_x, scan_y, cx, cy, theta),
                        'rot_xy': (cur_x, scan_y),
                        'ridge_idx': ridge_index
                    })
                    cur_x += step_px
            if pts:
                ridge_index += 1
            scan_y += ridge_dist_px

        # 评估格网
        self.eval_grid = []
        gx = min_x
        while gx <= max_x:
            gy = min_y
            while gy <= max_y:
                rx, ry = _rotate_pt(gx, gy, cx, cy, theta)
                if _point_in_poly(rx, ry, self.field_polygon):
                    self.eval_grid.append((rx, ry))
                gy += self.grid_step
            gx += self.grid_step

        if not self.eval_grid or not candidate_pool:
            messagebox.showerror("Error", "算子空间结构异常，请检查标定范围或放宽参数。")
            return

        # ========== 阶段二：多轮互补贪心覆盖选址 ==========
        self.all_rounds_selected = []
        self.cumulative_confidence = [0.0] * len(self.eval_grid)
        evaluator = CoverageEvaluator(self.eval_grid, candidate_pool, radius_px)

        for rnd in range(num_rounds):
            self.status_var.set(
                f"OPTIMIZING: 第 {rnd + 1} 轮互补覆盖选址 ({rnd + 1}/{num_rounds})...")
            self.root.update()

            selected, new_conf = evaluator.greedy_select_round(
                self.cumulative_confidence, num_samples)
            self.all_rounds_selected.append(selected)
            self.cumulative_confidence = new_conf

        # ========== 阶段三：逐轮路径规划 ==========
        self.all_rounds_tours = []
        for rnd, nodes in enumerate(self.all_rounds_selected):
            n = len(nodes)
            if n < 2:
                self.all_rounds_tours.append(list(range(n)))
                continue
            self.status_var.set(f"ROUTING: 第 {rnd + 1} 轮地头路径优化中...")
            self.root.update()

            init_tour = _nn_tour(nodes, cx, cy, theta, self.ridge_db)
            opt_tour = _two_opt(init_tour, nodes, cx, cy, theta, self.ridge_db)
            self.all_rounds_tours.append(opt_tour)

        # ========== 阶段四：可视化渲染 ==========

        # 图层1: 评估格网
        for (gx_e, gy_e) in self.eval_grid:
            self.canvas.create_rectangle(
                gx_e - 0.5, gy_e - 0.5, gx_e + 0.5, gy_e + 0.5,
                fill=self.COLOR_GRID, outline="", tags="grid")

        # 图层2: 置信度热力图
        self._render_heatmap(canvas_w, canvas_h)

        # 图层3: 垄沟导引线
        for rinfo in self.ridge_db.values():
            y_rot = rinfo['y_rot']
            lr, rr = rinfo['left_rot'], rinfo['right_rot']
            rs = _rotate_pt(lr, y_rot, cx, cy, theta)
            re = _rotate_pt(rr, y_rot, cx, cy, theta)
            self.canvas.create_line(rs[0], rs[1], re[0], re[1],
                                    fill=self.COLOR_RIDGE, width=1, tags="ridge")

        # 图层4: 覆盖圆
        self._render_coverage_circles(canvas_w, canvas_h, radius_px)

        # 图层5: 巡游路径与箭头 (同时缓存段距离与行驶时间)
        self._cached_round_segments = []
        for rnd, (nodes, tour) in enumerate(
                zip(self.all_rounds_selected, self.all_rounds_tours)):
            color = self.ROUND_COLORS[rnd % len(self.ROUND_COLORS)]
            n_nodes = len(nodes)
            round_segs = []
            if n_nodes < 2:
                self._cached_round_segments.append(round_segs)
                continue
            for idx in range(n_nodes):
                na = nodes[tour[idx]]
                nb = nodes[tour[(idx + 1) % n_nodes]]
                dist_px, waypoints = _compute_headland_path(
                    na, nb, self.ridge_db, cx, cy, theta)
                dist_m = dist_px / scale
                time_s = dist_m / speed_ms
                round_segs.append({
                    'from_idx': tour[idx],
                    'to_idx': tour[(idx + 1) % n_nodes],
                    'dist_px': round(dist_px, 1),
                    'dist_m': round(dist_m, 2),
                    'time_s': round(time_s, 1)
                })
                for k in range(len(waypoints) - 1):
                    x1, y1 = waypoints[k]
                    x2, y2 = waypoints[k + 1]
                    self.canvas.create_line(x1, y1, x2, y2, fill=color,
                                            width=1.8, dash=(6, 4), tags="path")
                    self._draw_arrow(x1, y1, x2, y2, color)
            self._cached_round_segments.append(round_segs)

        # 图层6: 采样点准星圈与编号
        for rnd, nodes in enumerate(self.all_rounds_selected):
            color = self.ROUND_COLORS[rnd % len(self.ROUND_COLORS)]
            for li, node in enumerate(nodes):
                nx, ny = node['real_xy']
                self.canvas.create_oval(nx - 7, ny - 7, nx + 7, ny + 7,
                                        fill="", outline=color, width=1.5, tags="point")
                self.canvas.create_oval(nx - 2, ny - 2, nx + 2, ny + 2,
                                        fill="#ffffff", outline="", tags="point")
                # 编号徽章
                bw, bh = 44, 16
                bx1, by1 = nx + 12, ny - 22
                bx2, by2 = bx1 + bw, by1 + bh
                self.canvas.create_rectangle(bx1, by1, bx2, by2,
                                             fill=self.COLOR_BADGE_BG,
                                             outline=color, width=1, tags="text")
                self.canvas.create_text((bx1 + bx2) / 2, (by1 + by2) / 2,
                                        text=f"R{rnd + 1}-P{li + 1}",
                                        fill="#ffffff",
                                        font=("Consolas", 7, "bold"), tags="text")

        # ---- 统计摘要 ----
        covered = sum(1 for c in self.cumulative_confidence if c > 0.5)
        total = len(self.cumulative_confidence)
        cov_pct = (covered / total * 100) if total > 0 else 0
        avg_c = sum(self.cumulative_confidence) / total if total > 0 else 0
        # [UPDATED 2026-07-13] 累计各轮预估行驶时间
        total_times = []
        for segs in self._cached_round_segments:
            t = sum(s['time_s'] for s in segs)
            total_times.append(t)
        time_str = " | ".join(
            f"R{i + 1}: {t:.0f}s" for i, t in enumerate(total_times))
        self.status_var.set(
            f"ROUTING COMPILED: {num_rounds}轮x~{num_samples}点 | "
            f"半高覆盖达标率: {cov_pct:.1f}% | "
            f"全域均置信度: {avg_c:.3f} | "
            f"预估行驶: {time_str}")

    # =========================================================
    # CSV 导出
    # [UPDATED 2026-07-13] 增加段行驶时间列
    # =========================================================

    def export_csv(self):
        if not self.all_rounds_selected:
            messagebox.showwarning("Warning", "尚无规划结果，请先执行全覆盖路由方案。")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")],
            title="导出采样点坐标与路径")
        if not file_path:
            return

        scale = self._cached_scale
        ref_x1 = self._cached_ref_x1
        ref_y1 = self._cached_ref_y1
        radius_m = self._cached_radius_m
        speed_ms = self._cached_speed

        try:
            with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                # 分为两段：采样点清单 + 路径段时间预估
                writer.writerow(['=== 采样点坐标清单 ==='])
                writer.writerow([
                    '采集轮次', '轮内编号', '全局序号',
                    '像素X', '像素Y',
                    '相对X(m)', '相对Y(m)',
                    '所在垄索引', '覆盖半径(m)'])

                gseq = 0
                for rnd, nodes in enumerate(self.all_rounds_selected):
                    for li, node in enumerate(nodes):
                        px, py = node['real_xy']
                        rel_x = (px - ref_x1) / scale
                        rel_y = (py - ref_y1) / scale
                        gseq += 1
                        writer.writerow([
                            rnd + 1,
                            f"R{rnd + 1}-P{li + 1}",
                            gseq,
                            f"{px:.1f}", f"{py:.1f}",
                            f"{rel_x:.2f}", f"{rel_y:.2f}",
                            node['ridge_idx'],
                            f"{radius_m:.1f}"])

                writer.writerow([])
                writer.writerow(['=== 路径段时间预估 (车速={}m/s) ==='.format(speed_ms)])
                writer.writerow(['采集轮次', '起点编号', '终点编号',
                                 '距离(像素)', '距离(m)', '行驶时间(s)'])

                for rnd, segs in enumerate(self._cached_round_segments):
                    for seg in segs:
                        writer.writerow([
                            rnd + 1,
                            f"R{rnd + 1}-P{seg['from_idx'] + 1}",
                            f"R{rnd + 1}-P{seg['to_idx'] + 1}",
                            f"{seg['dist_px']:.1f}",
                            f"{seg['dist_m']:.2f}",
                            f"{seg['time_s']:.1f}"])

            fname = file_path.replace('\\', '/').split('/')[-1]
            self.status_var.set(f"EXPORTED: CSV 数据已写入 {fname}")
            messagebox.showinfo("导出成功",
                                f"已导出 {gseq} 个采样点及路径时间至:\n{file_path}")
        except Exception as e:
            messagebox.showerror("导出失败", f"文件写入异常: {e}")

    # =========================================================
    # JSON 导出
    # [UPDATED 2026-07-13] 结构化导出路径规划结果，便于下位机(MCU/嵌入式)直接解析
    # JSON 格式包含坐标(m)、路径顺序、段行驶时间、覆盖置信度摘要
    # =========================================================

    def export_json(self):
        if not self.all_rounds_selected:
            messagebox.showwarning("Warning", "尚无规划结果，请先执行全覆盖路由方案。")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
            title="导出路径规划 JSON")
        if not file_path:
            return

        scale = self._cached_scale
        ref_x1 = self._cached_ref_x1
        ref_y1 = self._cached_ref_y1
        radius_m = self._cached_radius_m
        speed_ms = self._cached_speed

        # 构建 JSON 结构
        covered = sum(1 for c in self.cumulative_confidence if c > 0.5)
        total = len(self.cumulative_confidence)

        data = {
            "meta": {
                "version": "1.0",
                "generated": "2026-07-13",
                "scale_px_per_m": round(scale, 2),
                "reference_point": {
                    "pixel": [round(ref_x1, 1), round(ref_y1, 1)],
                    "description": "多边形第一标定点，作为相对坐标原点"
                },
                "field_params": {
                    "reference_edge_length_m": round(self._cached_scale * 100 / scale, 2) if scale > 0 else 0,
                    "ridge_distance_m": round(float(self.entry_ridge_dist.get()), 2),
                    "spore_radius_m": radius_m,
                    "vehicle_speed_ms": speed_ms
                },
                "coverage_summary": {
                    "covered_cells_half_threshold": covered,
                    "total_eval_cells": total,
                    "coverage_rate_pct": round((covered / total * 100) if total > 0 else 0, 1),
                    "mean_confidence": round(sum(self.cumulative_confidence) / total if total > 0 else 0, 4)
                },
                "num_rounds": len(self.all_rounds_selected)
            },
            # [UPDATED 2026-07-13] 导出农田多边形(米制)，供传感模块裁剪热力图
            "field_polygon": {
                "vertices_m": [
                    [round((px - ref_x1) / scale, 2), round((py - ref_y1) / scale, 2)]
                    for px, py in self.field_polygon
                ],
                "vertices_px": [[round(px, 1), round(py, 1)] for px, py in self.field_polygon],
                "description": "农田边界多边形，顶点按标定顺序排列"
            },
            "rounds": []
        }

        for rnd, (nodes, tour, segs) in enumerate(zip(
                self.all_rounds_selected, self.all_rounds_tours,
                self._cached_round_segments)):
            waypoints = []
            for li, node in enumerate(nodes):
                px, py = node['real_xy']
                rel_x = (px - ref_x1) / scale
                rel_y = (py - ref_y1) / scale
                waypoints.append({
                    "id": f"R{rnd + 1}-P{li + 1}",
                    "global_seq": li + 1,
                    "pixel": [round(px, 1), round(py, 1)],
                    "relative_m": [round(rel_x, 2), round(rel_y, 2)],
                    "ridge_index": node['ridge_idx']
                })

            # 按巡回顺序重排
            ordered_waypoints = [waypoints[i] for i in tour]

            total_time = round(sum(s['time_s'] for s in segs), 1)
            total_dist = round(sum(s['dist_m'] for s in segs), 2)

            round_data = {
                "round_id": rnd + 1,
                "num_points": len(nodes),
                "total_distance_m": total_dist,
                "total_time_s": total_time,
                "visit_order": tour,
                "waypoints": ordered_waypoints,
                "segments": [
                    {
                        "from": f"R{rnd + 1}-P{seg['from_idx'] + 1}",
                        "to": f"R{rnd + 1}-P{seg['to_idx'] + 1}",
                        "distance_m": seg['dist_m'],
                        "time_s": seg['time_s']
                    }
                    for seg in segs
                ]
            }
            data["rounds"].append(round_data)

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            fname = file_path.replace('\\', '/').split('/')[-1]
            self.status_var.set(f"EXPORTED: JSON 数据已写入 {fname}")
            messagebox.showinfo("导出成功",
                                f"已导出 {len(data['rounds'])} 轮路径规划结果至:\n{file_path}")
        except Exception as e:
            messagebox.showerror("导出失败", f"JSON 写入异常: {e}")

    # =========================================================
    # 重置
    # =========================================================

    def clear_canvas(self):
        self.canvas.delete("all")
        self.photo_image = None
        self.circle_photo = None
        self.heatmap_photo = None
        self.pil_image = None
        self.field_polygon = []
        self.is_drawing = False
        self.all_rounds_selected = []
        self.all_rounds_tours = []
        self.cumulative_confidence = []
        self.eval_grid = []
        self.ridge_db = {}
        self._cached_scale = 1.0
        self._cached_ref_x1 = 0.0
        self._cached_ref_y1 = 0.0
        self._cached_radius_m = 20.0
        self._cached_speed = 0.5
        self._cached_round_segments = []
        self.status_var.set("SYS READY: 解算数据归零，等待重载坐标边界。")


if __name__ == "__main__":
    root = tk.Tk()
    app = AgriAdvancedPlanner(root)
    root.mainloop()
