# -*- coding: utf-8 -*-
"""
多模态智能巡检系统 V2.0
路径规划(覆盖选址+TSP优化) + 田间检测(浊度粗定+IDW热力图)
双页签共享画布架构，坐标系天然一致。
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import math, csv, json, random, os, sys
from datetime import datetime

try:
    from PIL import Image, ImageTk, ImageDraw
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

# =========================================================
# 基础几何工具
# =========================================================

def _rot(x, y, cx, cy, th):
    """点(x,y)绕(cx,cy)旋转th弧度"""
    dx, dy = x - cx, y - cy
    c, s = math.cos(th), math.sin(th)
    return dx * c - dy * s + cx, dx * s + dy * c + cy

def _in_poly(x, y, poly):
    """射线法——点是否在多边形内"""
    inside, j = False, len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]; xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside

def _scan_x(scan_y, poly):
    """水平扫描线y=scan_y与多边形交点x列表，已排序"""
    pts, j = [], len(poly) - 1
    for i in range(len(poly)):
        px1, py1 = poly[i]; px2, py2 = poly[j]
        if (py1 <= scan_y < py2) or (py2 <= scan_y < py1):
            if abs(py2 - py1) > 1e-9:
                pts.append(px1 + (scan_y - py1) * (px2 - px1) / (py2 - py1))
        j = i
    pts.sort()
    return pts

def _area(poly):
    """多边形面积(顶点按序，自动取绝对值)"""
    a, j = 0.0, len(poly) - 1
    for i in range(len(poly)):
        a += poly[i][0] * poly[j][1] - poly[j][0] * poly[i][1]
        j = i
    return abs(a) / 2.0

def _centroid(poly):
    """多边形质心"""
    cx, cy, j = 0.0, 0.0, len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]; xj, yj = poly[j]
        cross = xi * yj - xj * yi
        cx += (xi + xj) * cross
        cy += (yi + yj) * cross
        j = i
    a6 = 6.0 * _area(poly)
    if a6 == 0:
        return (poly[0][0], poly[0][1])
    return (cx / a6, cy / a6)

def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])

def _bbox(pts):
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return min(xs), max(xs), min(ys), max(ys)

# =========================================================
# 伪彩色映射
# =========================================================

def _conf_rgba(c):
    """置信度[0,1]→RGBA，红(低)→橙→黄→绿(高)"""
    if c < 0.001:
        return (0, 0, 0, 0)
    if c < 0.25:
        t = c / 0.25; r, g, b = 220, int(30 + 80 * t), 30
    elif c < 0.5:
        t = (c - 0.25) / 0.25; r, g, b = 220, int(110 + 100 * t), 30
    elif c < 0.75:
        t = (c - 0.5) / 0.25; r, g, b = int(220 - 150 * t), int(210 + 40 * t), 30
    else:
        t = (c - 0.75) / 0.25; r, g, b = int(70 - 30 * t), int(250 - 50 * t), 30
    return (r, g, b, int(50 + 110 * c))

def _turb_rgba(turb):
    """浊度(NTU)→RGBA，绿(低)→黄→橙→红(高)"""
    turb = max(0, min(600, turb))
    segs = [(0, (39, 174, 96)), (150, (241, 196, 15)),
            (400, (230, 126, 34)), (600, (231, 76, 60))]
    for i in range(len(segs) - 1):
        v0, (r0, g0, b0) = segs[i]; v1, (r1, g1, b1) = segs[i + 1]
        if turb <= v1:
            t = (turb - v0) / (v1 - v0) if v1 != v0 else 0
            return (int(r0 + (r1 - r0) * t), int(g0 + (g1 - g0) * t),
                    int(b0 + (b1 - b0) * t), int(60 + 100 * (turb / 600)))
    r, g, b = segs[-1][1]
    return (r, g, b, int(60 + 100 * (turb / 600)))

# =========================================================
# 覆盖选址——空间分箱加速版
# =========================================================

class CoverEval:
    """候选点贪心选址器。
    栅格分箱将距离查询从O(G)压缩到近似O(局部格点数)，
    对大面积农田效果尤为显著。"""

    def __init__(self, grid, cands, r_px):
        self.grid = grid
        self.cands = cands
        self.r2 = r_px ** 2
        self.cell_sz = max(r_px, 20.0)
        # 建索引
        self.bins = {}
        for i, (gx, gy) in enumerate(grid):
            k = (int(gx / self.cell_sz), int(gy / self.cell_sz))
            self.bins.setdefault(k, []).append(i)

    def _nearby(self, cx, cy):
        """返回候选点可能影响的格网下标(9邻域分箱)"""
        bx, by = int(cx / self.cell_sz), int(cy / self.cell_sz)
        out = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                k = (bx + dx, by + dy)
                if k in self.bins:
                    out.extend(self.bins[k])
        return out

    def _eval_one(self, cand, base):
        """评估单个候选点带来的覆盖增益"""
        cx, cy = cand['real_xy']
        gain, newconf = 0.0, list(base)
        for gi in self._nearby(cx, cy):
            gx, gy = self.grid[gi]
            d2 = (gx - cx) ** 2 + (gy - cy) ** 2
            if d2 < self.r2:
                cv = 1.0 - d2 / self.r2       # 二次衰减模型
                if cv > base[gi]:
                    gain += cv - base[gi]
                    newconf[gi] = cv
        return gain, newconf

    def select(self, base, n, cb=None):
        """贪心选n个点，可选进度回调cb(step,total)"""
        sel, cur, avail = [], list(base), [True] * len(self.cands)
        for step in range(n):
            best_cand, best_gain, best_nc, best_ci = None, -1.0, None, -1
            for ci, cand in enumerate(self.cands):
                if not avail[ci]:
                    continue
                g, nc_ = self._eval_one(cand, cur)
                if g > best_gain:
                    best_gain, best_cand, best_nc, best_ci = g, cand, nc_, ci
            if best_cand is None or best_gain < 0.001:
                break       # 饱和，停止
            sel.append(best_cand)
            cur = best_nc
            avail[best_ci] = False
            if cb:
                cb(step + 1, n)
        return sel, cur

# =========================================================
# 地头路径 & TSP
# =========================================================

def _hpath(na, nb, rdb, cx, cy, th):
    """两采样点间的地头转弯路径。
    同垄直连；跨垄比较左端绕行/右端绕行，取短者。"""
    ra, rb = na['ridge_idx'], nb['ridge_idx']
    xa, ya = na['rot_xy']; xb, yb = nb['rot_xy']
    if ra == rb:
        return abs(xa - xb), [na['real_xy'], nb['real_xy']]
    la, lb = rdb[ra]['left_rot'], rdb[rb]['left_rot']
    ra_, rb_ = rdb[ra]['right_rot'], rdb[rb]['right_rot']
    dl = (xa - la) + abs(ya - yb) + (xb - lb)
    dr = (ra_ - xa) + abs(ya - yb) + (rb_ - xb)
    if dl < dr:
        return dl, [na['real_xy'], _rot(la, ya, cx, cy, th),
                    _rot(lb, yb, cx, cy, th), nb['real_xy']]
    return dr, [na['real_xy'], _rot(ra_, ya, cx, cy, th),
                _rot(rb_, yb, cx, cy, th), nb['real_xy']]

def _nnt(nds, rdb, cx, cy, th):
    """最近邻贪心——构造TSP初始回路"""
    n = len(nds)
    if n <= 2:
        return list(range(n))
    vis = [False] * n
    tour = [0]; vis[0] = True
    for _ in range(n - 1):
        last = tour[-1]; bj, bd = -1, float('inf')
        for j in range(n):
            if vis[j]:
                continue
            d, _ = _hpath(nds[last], nds[j], rdb, cx, cy, th)
            if d < bd:
                bd, bj = d, j
        tour.append(bj); vis[bj] = True
    return tour

def _2opt(tour, nds, rdb, cx, cy, th, max_iter=50):
    """2-opt边交换改进TSP回路"""
    n = len(nds)
    if n < 3:
        return tour
    best, improved, it = list(tour), True, 0
    while improved and it < max_iter:
        improved = False; it += 1
        for i in range(1, n - 2):
            for j in range(i + 1, n):
                if j - i == 1:
                    continue
                a, b = best[i - 1], best[i]
                c, d = best[j], best[(j + 1) % n]
                dab, _ = _hpath(nds[a], nds[b], rdb, cx, cy, th)
                dcd, _ = _hpath(nds[c], nds[d], rdb, cx, cy, th)
                dac, _ = _hpath(nds[a], nds[c], rdb, cx, cy, th)
                dbd, _ = _hpath(nds[b], nds[d], rdb, cx, cy, th)
                if (dac + dbd) < (dab + dcd):
                    best[i:j + 1] = reversed(best[i:j + 1])
                    improved = True
    return best

# =========================================================
# 参数预设 — 覆盖常见农田场景
# =========================================================

PRESETS = {
    "小麦试验田(小)":  {"ref": "50.0",  "ridge": "2.5", "samp": "6",  "r": "15.0", "K": "2", "spd": "0.4"},
    "玉米大田(中)":    {"ref": "100.0", "ridge": "4.0", "samp": "8",  "r": "20.0", "K": "2", "spd": "0.5"},
    "水稻连片(大)":    {"ref": "200.0", "ridge": "3.0", "samp": "12", "r": "25.0", "K": "3", "spd": "0.6"},
    "果园稀疏(宽垄)":  {"ref": "80.0",  "ridge": "5.0", "samp": "5",  "r": "30.0", "K": "1", "spd": "0.4"},
    "菜地密植(窄垄)":  {"ref": "60.0",  "ridge": "1.5", "samp": "10", "r": "12.0", "K": "2", "spd": "0.3"},
    "人工密集采样":    {"ref": "100.0", "ridge": "2.0", "samp": "16", "r": "10.0", "K": "3", "spd": "0.3"},
}

# =========================================================
# 主系统类
# =========================================================

class InspectionSystem:
    """多模态智能巡检系统 V2.0
    路径规划：覆盖选址 + 2-opt路径优化
    田间检测：浊度粗定 + IDW热力图 + 即时预警"""

    def __init__(self, root):
        self.root = root
        self.root.title("多模态智能巡检系统 V2.0")
        self.root.geometry("1400x850")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # ====== 配色(与所有子模块风格统一) ======
        self.cbg = "#161a1d"      # 主背景
        self.cpn = "#212529"      # 面板背景
        self.ccd = "#2c313c"      # 卡片背景
        self.cac = "#00ecc6"      # 强调色
        self.cal = "#e1b12c"      # 警告色
        self.cdg = "#e74c3c"      # 危险色
        self.cif = "#00a8ff"      # 信息色
        self.csf = "#27ae60"      # 安全色
        self.crk = "#282e38"      # 垄线色
        self.ctx = "#dcdde1"      # 文字色
        self.cdm = "#718093"      # 暗文字色
        self.rcs = ["#ff9f43", "#00a8ff", "#e056a0", "#f1c40f", "#9b59b6"]  # 轮次配色
        self.rsk_c = {
            'low': self.csf, 'medium': self.cal,
            'high': self.cdg, 'pending': self.cdm
        }

        # ====== 共享数据——规划产出供传感直接复用 ======
        self.pimg = None            # PIL Image
        self.pimg_tk = None         # tk PhotoImage 引用(必须保持)
        self.poly = []              # 农田边界(画布像素坐标)
        self.poly_m = []            # 农田边界(米制坐标)
        self.scale = 1.0            # px/m 比例尺
        self.rx1, self.ry1 = 0.0, 0.0   # 参考点(第一标定点，像素坐标)
        self.rad_m = 20.0           # 孢子有效半径(m)
        self.spd = 0.5              # 小车行驶速度(m/s)

        # 规划产出
        self.rdb = {}               # 垄数据库 {idx: {y_rot, left_rot, right_rot}}
        self._rnds = []             # 每轮原始节点 list[list[dict]]
        self._tours = []            # 每轮访问顺序 list[list[int]]
        self._segs = []             # 每轮路径段 list[list[dict]]
        self._cconf = []            # 累积覆盖置信度
        self._egrid = []            # 评估格网点
        self._gstep = 1.0           # 格网步长

        # 传感数据(直接挂载在采样点dict上)
        self.spts = []

        # ====== UI 状态 ======
        self.drawing = False
        self.sel = -1               # 当前选中采样点索引
        self.scanning = False
        self.sjob = None            # after id
        self.th_mid = 150.0         # 中风险阈值(NTU)
        self.th_hi = 400.0          # 高风险阈值(NTU)
        self.cov_r = 20.0           # 传感覆盖半径(m)
        self._grid_on = True        # 格网可见
        self._leg_on = True         # 图例可见
        self._ustk = []             # 撤销栈

        # 图像缓存(必须保持Python引用防止被GC)
        self._hmp = None            # heatmap photo
        self._crp = None            # circles photo
        self._cfp = None            # confidence photo
        self._lgp = None            # legend photo
        self._iox, self._ioy = 0, 0 # 图像在画布上的偏移
        self._cw, self._ch = 1000, 800  # 画布尺寸缓存

        # 快捷键
        self.root.bind('<Control-z>', lambda e: self._undo_v())
        self.root.bind('<Control-s>', lambda e: self.export_json())
        self.root.bind('<Escape>', lambda e: self._stop_scan())

        self._mk_ui()

    # =========================================================
    # 界面搭建
    # =========================================================

    def _mk_ui(self):
        s = ttk.Style(); s.theme_use('clam')
        s.configure("TLabel", foreground=self.ctx, background=self.cpn)
        s.configure("TNotebook", background=self.cpn, borderwidth=0)
        s.configure("TNotebook.Tab", padding=[18, 4], font=("微软雅黑", 11))

        # 右侧——共享画布
        rf = tk.Frame(self.root, bg=self.cbg)
        rf.pack(side="right", fill="both", expand=True)

        self.canv = tk.Canvas(rf, bg=self.cbg, highlightthickness=0)
        self.canv.pack(fill="both", expand=True)
        self.canv.bind("<Motion>", self._on_move)

        self._clbl = tk.Label(rf, text="", fg=self.cdm, bg=self.cbg, font=("Consolas", 9))
        self._clbl.place(x=8, y=8)

        self.stvar = tk.StringVar()
        self.stvar.set("SYS READY: 在「路径规划」页导入卫星图并标定边界。")
        tk.Label(rf, textvariable=self.stvar, fg=self.cal, bg=self.cbg,
                 font=("微软雅黑", 10, "bold")).pack(side="bottom", pady=6)

        # 左侧双页签
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(side="left", fill="y")
        self.ptab = tk.Frame(self.nb, bg=self.cpn, width=360)
        self.stab = tk.Frame(self.nb, bg=self.cpn, width=360)
        self.nb.add(self.ptab, text=" 路径规划 ")
        self.nb.add(self.stab, text=" 田间检测 ")
        self._mk_plan()
        self._mk_sens()
        self.nb.bind("<<NotebookTabChanged>>", self._on_tab)
        self.canv.bind("<Button-1>", self._clk)
        self.canv.bind("<Button-3>", self._rclk)

    # =========================================================
    # 规划页控制面板
    # =========================================================

    def _mk_plan(self):
        """路径规划Tab——可滚动控制面板"""
        t = self.ptab; t.pack_propagate(False)
        # 滚动容器
        cvs = tk.Canvas(t, bg=self.cpn, highlightthickness=0, width=360)
        sbar = ttk.Scrollbar(t, orient="vertical", command=cvs.yview)
        inner = tk.Frame(cvs, bg=self.cpn)
        inner.bind("<Configure>", lambda e: cvs.configure(scrollregion=cvs.bbox("all")))
        cvs.create_window((0, 0), window=inner, anchor="nw", width=344)
        cvs.configure(yscrollcommand=sbar.set)
        cvs.pack(side="left", fill="both", expand=True)
        sbar.pack(side="right", fill="y")
        # 滚轮绑定
        def _on_mw(event):
            cvs.yview_scroll(int(-1 * (event.delta / 120)), "units")
        cvs.bind("<Enter>", lambda e: cvs.bind_all("<MouseWheel>", _on_mw))
        cvs.bind("<Leave>", lambda e: cvs.unbind_all("<MouseWheel>"))

        # 按钮快捷生成器——所有widget挂到inner上
        def btn(tx, cmd, py=8):
            tk.Button(inner, text=tx, bg=self.ccd, fg=self.ctx, bd=0, padx=15, pady=4,
                      cursor="hand2", font=("微软雅黑", 10), command=cmd).pack(
                          pady=py, fill="x", padx=14)

        tk.Label(inner, text="PATH PLANNING CONTROL", fg=self.cdm, bg=self.cpn,
                 font=("Consolas", 9, "bold")).pack(pady=(10, 2))

        btn("1. 导入空地多光谱卫星图", self._load_img, 8)
        btn("底图适配检查", self._check_image_fit, 2)
        btn("2. 标定不规则边界 (首边为垄向)", self._start_draw, 6)
        btn("闭合农田拓扑空间", self._close_poly, 2)
        btn("撤销上一个顶点 (Ctrl+Z / 右键)", self._undo_v, 2)

        # 参数预设下拉框
        pf0 = tk.Frame(inner, bg=self.ccd, bd=1, relief="solid")
        pf0.pack(pady=8, fill="x", padx=14)
        tk.Label(pf0, text="参数预设", fg=self.cif, bg=self.ccd,
                 font=("微软雅黑", 10, "bold")).pack(pady=(6, 2))
        self._preset_var = tk.StringVar(value="玉米大田(中)")
        self._preset_combo = ttk.Combobox(pf0, textvariable=self._preset_var,
                          values=list(PRESETS.keys()), state="readonly", width=20)
        self._preset_combo.pack(pady=3)
        prb = tk.Frame(pf0, bg=self.ccd); prb.pack(pady=(3, 2))
        tk.Button(prb, text="应用", bg=self.cif, fg="white", bd=0, padx=8, pady=2,
                  font=("微软雅黑", 9), command=self._apply_preset).pack(side="left", padx=3)
        tk.Button(prb, text="保存当前", bg="#5f6368", fg=self.ctx, bd=0, padx=8, pady=2,
                  font=("微软雅黑", 9), command=self._save_preset).pack(side="left", padx=3)
        tk.Button(prb, text="载入文件", bg="#5f6368", fg=self.ctx, bd=0, padx=8, pady=2,
                  font=("微软雅黑", 9), command=self._load_presets).pack(side="left", padx=3)

        # 参数面板
        pf = tk.Frame(inner, bg=self.ccd, bd=1, relief="solid")
        pf.pack(pady=8, fill="x", padx=14)
        tk.Label(pf, text="规划参数设定", fg=self.cif, bg=self.ccd,
                 font=("微软雅黑", 10, "bold")).pack(pady=(6, 4))

        gi = tk.Frame(pf, bg=self.ccd); gi.pack()
        def _e(label, default, r, unit=""):
            tk.Label(gi, text=label, fg=self.ctx, bg=self.ccd,
                     font=("微软雅黑", 9)).grid(row=r, column=0, pady=3, padx=(10, 4), sticky="w")
            ent = tk.Entry(gi, width=7, bg=self.cbg, fg=self.cac, bd=0,
                           insertbackground="white", font=("Consolas", 10, "bold"))
            ent.insert(0, default)
            ent.grid(row=r, column=1, pady=3, padx=2, sticky="e")
            if unit:
                tk.Label(gi, text=unit, fg=self.cdm, bg=self.ccd,
                         font=("微软雅黑", 8)).grid(row=r, column=2, pady=3, padx=(0, 8), sticky="w")
            return ent

        self._erl = _e("基准首边长度", "100.0", 0, "m")
        self._erd = _e("作物种植垄距", "4.0", 1, "m")
        self._esn = _e("每轮采样点数P", "8", 2)
        self._esr = _e("孢子有效半径R", "20.0", 3, "m")
        self._ek  = _e("采集轮次K", "2", 4)
        self._esp = _e("小车行驶速度", "0.5", 5, "m/s")

        # 显示选项
        sf = tk.Frame(pf, bg=self.ccd); sf.pack(pady=(4, 6))
        self._gv = tk.BooleanVar(value=True)
        tk.Checkbutton(sf, text="评估格网", variable=self._gv, fg=self.ctx, bg=self.ccd,
                       selectcolor=self.cbg, activebackground=self.ccd, activeforeground=self.ctx,
                       font=("微软雅黑", 9), command=self._redraw).pack(side="left", padx=6)
        self._lv = tk.BooleanVar(value=True)
        tk.Checkbutton(sf, text="图例", variable=self._lv, fg=self.ctx, bg=self.ccd,
                       selectcolor=self.cbg, activebackground=self.ccd, activeforeground=self.ctx,
                       font=("微软雅黑", 9), command=self._redraw).pack(side="left", padx=6)

        btn("推荐采样密度", self._show_density, 3)
        btn("3. 求解全覆盖路由方案", self._solve, 10)
        btn("导出路径规划 JSON", self.export_json, 4)
        btn("导出规划报告 TXT", self._export_report, 4)
        btn("综合统计摘要", self._show_stats, 4)
        btn("快速摘要(状态栏)", self._quick_summary, 2)
        btn("坐标验证", self._validate_coords_btn, 2)
        btn("保存工作会话", self._save_ses, 2)
        btn("恢复工作会话", self._load_ses, 2)
        btn("一键批量导出(JSON+CSV+TXT)", self._batch_export, 4)
        btn("清空画布", self._clear, 4)

    # =========================================================
    # 检测页控制面板
    # =========================================================

    def _mk_sens(self):
        """田间检测Tab——可滚动控制面板"""
        t = self.stab; t.pack_propagate(False)
        cvs = tk.Canvas(t, bg=self.cpn, highlightthickness=0, width=360)
        sbar = ttk.Scrollbar(t, orient="vertical", command=cvs.yview)
        inner = tk.Frame(cvs, bg=self.cpn)
        inner.bind("<Configure>", lambda e: cvs.configure(scrollregion=cvs.bbox("all")))
        cvs.create_window((0, 0), window=inner, anchor="nw", width=344)
        cvs.configure(yscrollcommand=sbar.set)
        cvs.pack(side="left", fill="both", expand=True)
        sbar.pack(side="right", fill="y")
        def _on_mw(event):
            cvs.yview_scroll(int(-1 * (event.delta / 120)), "units")
        cvs.bind("<Enter>", lambda e: cvs.bind_all("<MouseWheel>", _on_mw))
        cvs.bind("<Leave>", lambda e: cvs.unbind_all("<MouseWheel>"))

        tk.Label(inner, text="SPORE DETECTION CONTROL", fg=self.cdm, bg=self.cpn,
                 font=("Consolas", 9, "bold")).pack(pady=(10, 2))

        # 阈值面板
        tf = tk.Frame(inner, bg=self.ccd, bd=1, relief="solid")
        tf.pack(pady=8, fill="x", padx=14)
        tk.Label(tf, text="浊度预警阈值设定", fg=self.cif, bg=self.ccd,
                 font=("微软雅黑", 10, "bold")).pack(pady=(6, 3))
        gi = tk.Frame(tf, bg=self.ccd); gi.pack()
        def _tr(label, default, r, unit=""):
            tk.Label(gi, text=label, fg=self.ctx, bg=self.ccd,
                     font=("微软雅黑", 9)).grid(row=r, column=0, pady=2, padx=10, sticky="w")
            e = tk.Entry(gi, width=6, bg=self.cbg, fg=self.cac, bd=0,
                         insertbackground="white", font=("Consolas", 10, "bold"))
            e.insert(0, default)
            e.grid(row=r, column=1, pady=2, padx=2, sticky="e")
            if unit:
                tk.Label(gi, text=unit, fg=self.cdm, bg=self.ccd,
                         font=("微软雅黑", 8)).grid(row=r, column=2, pady=2, padx=(0, 8), sticky="w")
            return e
        self._sm = _tr("中风险阈值", "150", 0, "NTU")
        self._sh = _tr("高风险阈值", "400", 1, "NTU")
        self._sd = _tr("全检间隔", "0.8", 2, "s")
        self._sr = _tr("覆盖半径", "20", 3, "m")

        # 模拟分布模式
        sf0 = tk.Frame(tf, bg=self.ccd); sf0.pack(pady=(3, 2))
        tk.Label(sf0, text="模拟分布:", fg=self.cdm, bg=self.ccd,
                 font=("微软雅黑", 8)).pack(side="left", padx=(10, 3))
        self._sim = tk.StringVar(value="uniform")
        for m, lb in [("uniform", "均匀"), ("hotspot", "热点"),
                       ("gradient", "渐变"), ("twozone", "双区")]:
            tk.Radiobutton(sf0, text=lb, variable=self._sim, value=m, fg=self.ctx,
                           bg=self.ccd, selectcolor=self.cbg, activebackground=self.ccd,
                           activeforeground=self.ctx, font=("微软雅黑", 8)).pack(side="left", padx=2)
        tk.Button(tf, text="应用阈值", bg="#5f6368", fg=self.ctx, bd=0,
                  padx=10, pady=2, font=("微软雅黑", 9),
                  command=self._apply_th).pack(pady=(6, 8))

        # 传感器读数
        sf = tk.Frame(inner, bg=self.ccd, bd=1, relief="solid")
        sf.pack(pady=6, fill="x", padx=14)
        tk.Label(sf, text="光敏传感器读数", fg=self.cif, bg=self.ccd,
                 font=("微软雅黑", 10, "bold")).pack(pady=(6, 3))
        self._lpt = tk.Label(sf, text="当前采样点: 未选中", fg=self.cdm,
                             bg=self.ccd, font=("微软雅黑", 10))
        self._lpt.pack(pady=2)
        self._lrd = tk.Label(sf, text="-- NTU", fg=self.cac, bg=self.ccd,
                             font=("Consolas", 24, "bold"))
        self._lrd.pack(pady=4)
        self._lrs = tk.Label(sf, text="风险: 等待检测", fg=self.cdm,
                             bg=self.ccd, font=("微软雅黑", 10, "bold"))
        self._lrs.pack(pady=2)

        br = tk.Frame(sf, bg=self.ccd); br.pack(pady=(4, 3))
        tk.Button(br, text="读取传感器(单点)", bg=self.cif, fg="white", bd=0,
                  padx=8, pady=2, font=("微软雅黑", 9),
                  command=self._sd_single).pack(fill="x", padx=5)
        tk.Button(br, text="一键全检(顺序巡检)", bg=self.cac, fg=self.cbg, bd=0,
                  padx=8, pady=2, font=("微软雅黑", 9),
                  command=self._sd_scan).pack(fill="x", padx=5, pady=2)
        tk.Button(br, text="停止全检(Esc)", bg=self.cdg, fg="white", bd=0,
                  padx=8, pady=2, font=("微软雅黑", 9),
                  command=self._stop_scan).pack(fill="x", padx=5)
        tk.Button(br, text="重置全部读数", bg="#5f6368", fg=self.ctx, bd=0,
                  padx=8, pady=2, font=("微软雅黑", 9),
                  command=self._sd_reset).pack(fill="x", padx=5, pady=2)
        self._lpg = tk.Label(sf, text="", fg=self.cal, bg=self.ccd,
                             font=("微软雅黑", 9))
        self._lpg.pack(pady=(1, 6))

        # 农技建议 / 导出
        tk.Button(inner, text="查看农技建议", bg=self.cif, fg="white", bd=0,
                  padx=12, pady=3, font=("微软雅黑", 10),
                  command=self._show_recommend).pack(pady=4, fill="x", padx=14)

        tk.Button(inner, text="导出粗定检测数据 (CSV)", bg=self.ccd, fg=self.ctx, bd=0,
                  padx=12, pady=3, font=("微软雅黑", 10),
                  command=self._sd_export).pack(pady=2, fill="x", padx=14)

        # 统计栏
        ss = tk.Frame(inner, bg=self.cpn); ss.pack(fill="x", padx=14, pady=(3, 0))
        self._sst = tk.Label(ss, text="总计:0", fg=self.ctx, bg=self.cpn, font=("微软雅黑", 9))
        self._sst.pack(side="left", padx=4)
        self._ssd = tk.Label(ss, text="已测:0", fg=self.cif, bg=self.cpn, font=("微软雅黑", 9))
        self._ssd.pack(side="left", padx=4)
        self._ssh = tk.Label(ss, text="高风险:0", fg=self.cdg, bg=self.cpn,
                             font=("微软雅黑", 9, "bold"))
        self._ssh.pack(side="left", padx=4)
        self._ssa = tk.Label(ss, text="均值:--", fg=self.cdm, bg=self.cpn, font=("微软雅黑", 9))
        self._ssa.pack(side="left", padx=4)

        # 表格
        tf2 = tk.Frame(inner, bg=self.cbg)
        tf2.pack(fill="both", expand=True, padx=14, pady=4)
        self._stv = ttk.Treeview(tf2, columns=('seq', 'pid', 'turb', 'risk', 'time'),
                                 show='headings', height=8)
        for cid, cn, cw in [('seq', '#', 30), ('pid', '采样点', 90),
                              ('turb', '浊度(NTU)', 80), ('risk', '风险', 65),
                              ('time', '检测时间', 125)]:
            self._stv.heading(cid, text=cn)
            self._stv.column(cid, width=cw, anchor='center')
        self._stv.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(tf2, orient="vertical", command=self._stv.yview)
        self._stv.configure(yscrollcommand=sb.set); sb.pack(side="right", fill="y")
        self._stv.bind('<<TreeviewSelect>>', self._on_tv_sel)

    # =========================================================
    # 坐标/预设/鼠标
    # =========================================================

    def _apply_preset(self):
        key = self._preset_var.get()
        if key not in PRESETS:
            return
        p = PRESETS[key]
        for ent, k in [(self._erl, 'ref'), (self._erd, 'ridge'), (self._esn, 'samp'),
                        (self._esr, 'r'), (self._ek, 'K'), (self._esp, 'spd')]:
            ent.delete(0, "end"); ent.insert(0, p[k])
        self.stvar.set(f"PRESET APPLIED: {key}")

    def _save_preset(self):
        """将当前参数保存为自定义预设，写入JSON文件"""
        name = tk.simpledialog.askstring(
            "保存预设", "请输入预设名称:", parent=self.root)
        if not name:
            return
        cur = {
            "ref": self._erl.get(), "ridge": self._erd.get(),
            "samp": self._esn.get(), "r": self._esr.get(),
            "K": self._ek.get(), "spd": self._esp.get()
        }
        PRESETS[name] = cur
        self._preset_combo['values'] = list(PRESETS.keys())
        self._preset_var.set(name)
        # 同时保存到文件
        fp = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON 文件", "*.json")],
            title="导出预设文件")
        if fp:
            try:
                export = {name: cur}
                with open(fp, 'w', encoding='utf-8') as f:
                    json.dump(export, f, ensure_ascii=False, indent=2)
                self.stvar.set(f"PRESET SAVED: {name} -> {os.path.basename(fp)}")
            except Exception as e:
                messagebox.showerror("保存失败", f"{e}")
        else:
            self.stvar.set(f"PRESET SAVED: {name} (仅内存)")

    def _load_presets(self):
        """从JSON文件载入自定义预设，合并到现有预设列表"""
        fp = filedialog.askopenfilename(
            filetypes=[("JSON 文件", "*.json")], title="载入预设文件")
        if not fp:
            return
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
        except Exception as e:
            messagebox.showerror("载入失败", f"JSON解析异常: {e}"); return
        added = 0
        for name, vals in loaded.items():
            if not isinstance(vals, dict):
                continue
            # 校验必要字段
            if all(k in vals for k in ['ref', 'ridge', 'samp', 'r', 'K', 'spd']):
                PRESETS[name] = vals
                added += 1
        if added > 0:
            self._preset_combo['values'] = list(PRESETS.keys())
            self._preset_var.set(list(loaded.keys())[0])
            self.stvar.set(f"PRESETS LOADED: 从 {os.path.basename(fp)} 导入{added}个预设。")
        else:
            messagebox.showwarning("载入失败", "未找到合法的预设定义。\n"
                                   "格式: {\"名称\": {\"ref\":\"100\", \"ridge\":\"4\", "
                                   "\"samp\":\"8\", \"r\":\"20\", \"K\":\"2\", \"spd\":\"0.5\"}}")

    def _on_move(self, e):
        tab = self.nb.index(self.nb.select())
        if tab == 0 and self.poly:
            mx = (e.x - self.rx1) / self.scale if self.scale > 0 else 0
            my = (e.y - self.ry1) / self.scale if self.scale > 0 else 0
            self._clbl.config(text=f"px({e.x},{e.y})  m({mx:.1f},{my:.1f})")
        elif tab == 1 and self.spts:
            self._clbl.config(text=f"px({e.x},{e.y})")
        else:
            self._clbl.config(text="")

    def _clk(self, e):
        tab = self.nb.index(self.nb.select())
        if tab == 1:
            self._s_clk(e); return
        if not self.drawing:
            return
        self.poly.append((e.x, e.y))
        self._ustk.append((e.x, e.y))
        self.canv.create_oval(e.x - 3, e.y - 3, e.x + 3, e.y + 3,
                              fill="#ffffff", outline=self.cif, width=1)
        if len(self.poly) > 1:
            px, py = self.poly[-2]
            c = self.cif if len(self.poly) == 2 else "#ffffff"
            w = 3 if len(self.poly) == 2 else 1.5
            self.canv.create_line(px, py, e.x, e.y, fill=c, width=w)

    def _rclk(self, e):
        if self.drawing:
            self._undo_v()

    def _undo_v(self):
        if not self.drawing or not self.poly:
            return
        self.poly.pop()
        if self._ustk:
            self._ustk.pop()
        self._draw_plan()
        # 重绘剩下的顶点
        for i, (x, y) in enumerate(self.poly):
            self.canv.create_oval(x - 3, y - 3, x + 3, y + 3,
                                  fill="#ffffff", outline=self.cif, width=1)
            if i > 0:
                px, py = self.poly[i - 1]
                c = self.cif if i == 1 else "#ffffff"
                w = 3 if i == 1 else 1.5
                self.canv.create_line(px, py, x, y, fill=c, width=w)
        self.stvar.set(f"DIGITIZING: 已绘{len(self.poly)}顶点，右键撤销。")

    # =========================================================
    # 画布调度
    # =========================================================

    def _on_tab(self, e):
        self._cdims(); self._redraw()

    def _cdims(self):
        cw = self.canv.winfo_width(); ch = self.canv.winfo_height()
        if cw < 10:
            cw, ch = 1000, 800
        self._cw, self._ch = cw, ch
        if self.pimg:
            iw, ih = self.pimg.size
            self._iox = (cw - iw) // 2
            self._ioy = (ch - ih) // 2
        else:
            self._iox, self._ioy = 0, 0

    def _redraw(self):
        self._cdims()
        if self.nb.index(self.nb.select()) == 0:
            self._draw_plan()
        else:
            self._draw_sens()

    # =========================================================
    # 规划视图绘制
    # =========================================================

    def _draw_plan(self):
        self.canv.delete("all")
        self._cfp = None; self._crp = None; self._lgp = None
        cw, ch = self._cw, self._ch

        # 图层0: 卫星底图
        if self.pimg_tk:
            self.canv.create_image(self._iox, self._ioy, anchor="nw", image=self.pimg_tk)

        poly = self.poly

        # 图层1: 评估格网(可选)
        if self._grid_on and self._egrid and self._gv.get():
            for (gx, gy) in self._egrid:
                h = self._gstep / 2.0
                self.canv.create_rectangle(gx - h, gy - h, gx + h, gy + h,
                                           fill="#1a2332", outline="")

        # 图层2: 置信度热力图
        if HAS_PILLOW and self._cconf and self._egrid:
            self._draw_conf_heatmap(cw, ch)

        # 图层3: 多边形边界
        if len(poly) >= 2:
            for i in range(len(poly)):
                x1, y1 = poly[i]; x2, y2 = poly[(i + 1) % len(poly)]
                color = self.cif if i == 0 else "#ffffff"
                w = 3 if i == 0 else 1.5
                self.canv.create_line(x1, y1, x2, y2, fill=color, width=w)
            for x, y in poly:
                self.canv.create_oval(x - 3, y - 3, x + 3, y + 3,
                                      fill="#ffffff", outline=self.cif, width=1)

        if not self._rnds:
            if self._leg_on and self._lv.get():
                self._draw_plan_legend(cw, ch)
            return

        th = math.atan2(poly[1][1] - poly[0][1], poly[1][0] - poly[0][0])
        cx, cy = self.rx1, self.ry1

        # 图层4: 垄沟导引线
        for r in self.rdb.values():
            y_rot, lr, rr = r['y_rot'], r['left_rot'], r['right_rot']
            rs = _rot(lr, y_rot, cx, cy, th)
            re = _rot(rr, y_rot, cx, cy, th)
            self.canv.create_line(rs[0], rs[1], re[0], re[1], fill=self.crk, width=1)

        # 图层5: 覆盖圆(三层同心半透明)
        if HAS_PILLOW:
            self._draw_plan_circles(cw, ch)

        # 图层6: 路径+采样点标记
        for rnd, (nds, tour) in enumerate(zip(self._rnds, self._tours)):
            color = self.rcs[rnd % 5]
            nn = len(nds)
            if nn < 2:
                continue
            for idx in range(nn):
                na = nds[tour[idx]]; nb = nds[tour[(idx + 1) % nn]]
                _, wpts = _hpath(na, nb, self.rdb, cx, cy, th)
                for k in range(len(wpts) - 1):
                    self.canv.create_line(wpts[k][0], wpts[k][1],
                                          wpts[k + 1][0], wpts[k + 1][1],
                                          fill=color, width=2, dash=(6, 4))
                    self._arrow(wpts[k][0], wpts[k][1],
                                wpts[k + 1][0], wpts[k + 1][1], color)
            for li, node in enumerate(nds):
                nx, ny = node['real_xy']
                self.canv.create_oval(nx - 7, ny - 7, nx + 7, ny + 7,
                                      fill=self.cbg, outline=color, width=2)
                self.canv.create_oval(nx - 2.5, ny - 2.5, nx + 2.5, ny + 2.5,
                                      fill="#ffffff", outline="")
                self.canv.create_text(nx + 11, ny - 17,
                                      text=f"R{rnd + 1}-P{li + 1}",
                                      fill=color, font=("Consolas", 7, "bold"), anchor="w")

        # 图层7: 图例
        if self._leg_on and self._lv.get():
            self._draw_plan_legend(cw, ch)

    def _draw_conf_heatmap(self, cw, ch):
        overlay = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        half = self._gstep / 2.0
        for i, (gx, gy) in enumerate(self._egrid):
            if i >= len(self._cconf):
                break
            c = _conf_rgba(self._cconf[i])
            if c[3] == 0:
                continue
            draw.rectangle([gx - half, gy - half, gx + half, gy + half], fill=c)
        self._cfp = ImageTk.PhotoImage(overlay)
        self.canv.create_image(0, 0, anchor="nw", image=self._cfp)

    def _draw_plan_circles(self, cw, ch):
        if not self._rnds:
            return
        r_px = self.rad_m * self.scale
        overlay = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        for nds in self._rnds:
            for node in nds:
                nx, ny, r = node['real_xy'][0], node['real_xy'][1], r_px
                # 三层同心圆：外圈弱信、中圈中置信、内圈高信
                draw.ellipse([nx - r, ny - r, nx + r, ny + r],
                             fill=(27, 42, 36, 22), outline=(76, 209, 55, 55), width=1)
                draw.ellipse([nx - r * 0.6, ny - r * 0.6, nx + r * 0.6, ny + r * 0.6],
                             fill=(34, 62, 50, 40), outline=(76, 209, 55, 80), width=1)
                draw.ellipse([nx - r * 0.3, ny - r * 0.3, nx + r * 0.3, ny + r * 0.3],
                             fill=(46, 91, 70, 70), outline=(186, 220, 88, 120), width=1)
        self._crp = ImageTk.PhotoImage(overlay)
        self.canv.create_image(0, 0, anchor="nw", image=self._crp)

    def _draw_plan_legend(self, cw, ch):
        lw, lh = 140, 26
        lx, ly = cw - lw - 20, ch - lh - 20
        self.canv.create_rectangle(lx, ly, lx + lw, ly + lh,
                                   fill=self.cbg, outline=self.cdm, width=1)
        by, bh, bx, bw = ly + 5, lh - 10, lx + 8, 80
        for i in range(bw):
            c = _conf_rgba(i / bw)
            self.canv.create_line(bx + i, by, bx + i, by + bh,
                                  fill=f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}")
        self.canv.create_text(bx, by + bh + 2, text="0", fill=self.cdm,
                              font=("Consolas", 6), anchor="n")
        self.canv.create_text(bx + bw, by + bh + 2, text="1", fill=self.cdm,
                              font=("Consolas", 6), anchor="n")
        self.canv.create_text(bx + bw + 24, by + bh / 2, text="置信度",
                              fill=self.cdm, font=("微软雅黑", 7))

    def _arrow(self, x1, y1, x2, y2, color):
        """在路径段75%处绘制方向三角箭头"""
        mx = x1 + 0.75 * (x2 - x1); my = y1 + 0.75 * (y2 - y1)
        a = math.atan2(y2 - y1, x2 - x1)
        al, aw = 10, 5
        p1 = (mx + al * math.cos(a), my + al * math.sin(a))
        p2 = (mx + aw * math.cos(a + math.pi * 0.85), my + aw * math.sin(a + math.pi * 0.85))
        p3 = (mx + aw * math.cos(a - math.pi * 0.85), my + aw * math.sin(a - math.pi * 0.85))
        self.canv.create_polygon(p1[0], p1[1], p2[0], p2[1], p3[0], p3[1],
                                 fill=color, outline="")

    # =========================================================
    # 传感视图绘制
    # =========================================================

    def _draw_sens(self):
        self.canv.delete("all")
        self._hmp = None; self._crp = None; self._lgp = None
        cw, ch = self._cw, self._ch

        if self.pimg_tk:
            self.canv.create_image(self._iox, self._ioy, anchor="nw", image=self.pimg_tk)
        if not self.poly:
            return

        poly = self.poly
        # 多边形虚线边界
        for i in range(len(poly)):
            self.canv.create_line(poly[i][0], poly[i][1],
                                  poly[(i + 1) % len(poly)][0],
                                  poly[(i + 1) % len(poly)][1],
                                  fill=self.cif, width=2, dash=(8, 3))
        if not self.spts:
            return

        measured = [p for p in self.spts if p.get('turbidity') is not None]

        # IDW热力图(多边形mask裁剪)
        if HAS_PILLOW and len(measured) >= 3:
            self._draw_masked_heatmap(cw, ch, measured, poly)

        # 传感覆盖圆
        if HAS_PILLOW:
            self._draw_sens_circles(cw, ch)

        # 采样点标记
        for i, pt in enumerate(self.spts):
            px, py = pt['real_xy']
            risk = pt.get('risk', 'pending')
            color = self.rsk_c.get(risk, self.cdm)
            is_sel = (i == self.sel)
            r, w = (9, 3) if is_sel else (6, 1.5)
            self.canv.create_oval(px - r, py - r, px + r, py + r,
                                  fill=self.cbg, outline=color, width=w)
            inner_r = 4 if is_sel else 2.5
            fill_c = color if pt.get('turbidity') is not None else ""
            self.canv.create_oval(px - inner_r, py - inner_r,
                                  px + inner_r, py + inner_r, fill=fill_c, outline="")
            label = pt['point_id'].replace('R', '').replace('-P', '.')
            self.canv.create_text(px + 12, py - 10, text=label,
                                  fill=color, font=("Consolas", 7, "bold"), anchor="w")

        # 浊度图例
        if self._leg_on and self._lv.get():
            self._draw_sens_legend(cw, ch)

    def _draw_masked_heatmap(self, cw, ch, measured, poly):
        """IDW热力图 + 多边形mask = 平滑边界，完美贴合农田轮廓"""
        gs = max(14, min(cw, ch) // 50)
        r2_limit = (max(cw, ch) * 0.4) ** 2
        half = gs / 2.0

        raw = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        draw = ImageDraw.Draw(raw)
        mpts = [(p['real_xy'][0], p['real_xy'][1], p['turbidity']) for p in measured]
        if not mpts:
            return

        pxs = [p[0] for p in poly]; pys = [p[1] for p in poly]
        pad = gs * 2
        gx0 = max(0, int(min(pxs)) - pad); gx1 = min(cw, int(max(pxs)) + pad)
        gy0 = max(0, int(min(pys)) - pad); gy1 = min(ch, int(max(pys)) + pad)

        gx = gx0
        while gx <= gx1:
            gy = gy0
            while gy <= gy1:
                ws, vs = 0.0, 0.0
                for mx, my, mt in mpts:
                    d2 = (gx - mx) ** 2 + (gy - my) ** 2
                    if d2 < 1.0: d2 = 1.0
                    if d2 > r2_limit: continue
                    w = 1.0 / d2; ws += w; vs += w * mt
                if ws > 0:
                    draw.rectangle([gx - half, gy - half, gx + half, gy + half],
                                   fill=_turb_rgba(vs / ws))
                gy += gs
            gx += gs

        # 蒙版裁剪
        mask = Image.new("L", (cw, ch), 0)
        ImageDraw.Draw(mask).polygon([(int(x), int(y)) for x, y in poly], fill=255)
        clipped = Image.composite(raw, Image.new("RGBA", (cw, ch), (0, 0, 0, 0)), mask)
        self._hmp = ImageTk.PhotoImage(clipped)
        self.canv.create_image(0, 0, anchor="nw", image=self._hmp)

    def _draw_sens_circles(self, cw, ch):
        if len(self.spts) < 2:
            scale_pm = 1.0
        else:
            a, b = self.spts[0], self.spts[1]
            dp_ = math.hypot(a['real_xy'][0] - b['real_xy'][0],
                             a['real_xy'][1] - b['real_xy'][1])
            dm_ = math.hypot(a['x_m'] - b['x_m'], a['y_m'] - b['y_m'])
            scale_pm = dp_ / dm_ if dm_ > 0 else 1.0
        r_px = self.cov_r * scale_pm

        overlay = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        for pt in self.spts:
            px, py = pt['real_xy']
            risk = pt.get('risk', 'pending')
            fc, oc = {
                'high':    ((231, 76, 60, 20),  (231, 76, 60, 75)),
                'medium':  ((241, 196, 15, 20), (241, 196, 15, 75)),
                'low':     ((39, 174, 96, 20),  (39, 174, 96, 75))
            }.get(risk, ((90, 90, 90, 12), (90, 90, 90, 45)))
            draw.ellipse([px - r_px, py - r_px, px + r_px, py + r_px],
                         fill=fc, outline=oc, width=1)
        self._crp = ImageTk.PhotoImage(overlay)
        self.canv.create_image(0, 0, anchor="nw", image=self._crp)

    def _draw_sens_legend(self, cw, ch):
        lw, lh = 155, 30; lx, ly = cw - lw - 20, ch - lh - 20
        self.canv.create_rectangle(lx, ly, lx + lw, ly + lh,
                                   fill=self.cbg, outline=self.cdm, width=1)
        bx, by, bw, bh = lx + 8, ly + 6, 90, lh - 12
        for i in range(bw):
            c = _turb_rgba(i / bw * 600)
            self.canv.create_line(bx + i, by, bx + i, by + bh,
                                  fill=f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}")
        for v, lb in [(0, "0"), (bw, "600")]:
            self.canv.create_text(bx + v, by + bh + 2, text=lb,
                                  fill=self.cdm, font=("Consolas", 6), anchor="n")
        self.canv.create_text(bx + bw + 24, by + bh / 2, text="NTU",
                              fill=self.cdm, font=("微软雅黑", 7))

    # =========================================================
    # 规划流程
    # =========================================================

    def _load_img(self):
        if not HAS_PILLOW:
            messagebox.showerror("Error", "需要安装 Pillow 库以支持图像加载。"); return
        fp = filedialog.askopenfilename(
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.gif")])
        if not fp:
            return
        try:
            self.pimg = Image.open(fp)
            cw = self.canv.winfo_width(); ch = self.canv.winfo_height()
            if cw < 10: cw, ch = 1000, 800
            self.pimg.thumbnail((cw, ch))
            self.pimg_tk = ImageTk.PhotoImage(self.pimg)
            # 重置所有依赖图片坐标的状态
            self.poly = []; self._ustk = []
            self.spts = []
            self._rnds = []; self._tours = []
            self._cdims(); self._draw_plan()
            self.stvar.set("MAP LOADED: 卫星影像加载完成。")
        except Exception as e:
            messagebox.showerror("Error", f"图像解析异常: {e}")

    def _start_draw(self):
        self.drawing = True
        self.poly = []; self._ustk = []
        self.spts = []
        self._rnds = []; self._tours = []
        self._draw_plan()
        self.stvar.set("DIGITIZING: 左键标定顶点，右键/Ctrl+Z撤销。首边方向=垄向。")

    def _close_poly(self):
        if len(self.poly) < 3:
            messagebox.showwarning("Warning", "多边形边界至少需要3个顶点。"); return
        # 闭合边
        self.canv.create_line(self.poly[-1][0], self.poly[-1][1],
                              self.poly[0][0], self.poly[0][1],
                              fill="#ffffff", width=1.5)
        self.drawing = False
        area_px = _area(self.poly)
        area_m2 = area_px / (self.scale ** 2) if self.scale > 0 else 0
        self.stvar.set(
            f"TOPOLOGY CLOSED: 面积≈{area_m2:.0f}m²，{len(self.poly)}个顶点。")

    def _parse_nums(self):
        try:
            return (float(self._erl.get()), float(self._erd.get()),
                    int(self._esn.get()), float(self._esr.get()),
                    int(self._ek.get()), float(self._esp.get()))
        except ValueError:
            messagebox.showerror("参数错误", "请输入合法数值参数。"); return None

    def _solve(self):
        if len(self.poly) < 3:
            messagebox.showerror("Error", "请先闭合农田边界多边形。"); return
        p = self._parse_nums()
        if not p:
            return
        ref_len_m, ridge_m, n_samp, radius_m, n_rounds, speed_ms = p
        cw, ch = self._cw, self._ch

        self.stvar.set("CALCULATING: 正在求解..."); self.root.update()

        # 标定
        ref_x1, ref_y1 = self.poly[0]
        ref_x2, ref_y2 = self.poly[1]
        px_ref = math.hypot(ref_x2 - ref_x1, ref_y2 - ref_y1)
        if px_ref < 1.0:
            messagebox.showerror("Error", "基准边像素长度过短，请重新标定。"); return
        scale = px_ref / ref_len_m
        self.scale = scale
        self.rx1, self.ry1 = ref_x1, ref_y1
        self.rad_m = radius_m
        self.spd = speed_ms
        ridge_px = ridge_m * scale
        radius_px = radius_m * scale
        theta = math.atan2(ref_y2 - ref_y1, ref_x2 - ref_x1)
        cx, cy = ref_x1, ref_y1

        # 旋转至垄向对齐
        rot_poly = [_rot(x, y, cx, cy, -theta) for x, y in self.poly]
        mnx = min(p[0] for p in rot_poly); mxx = max(p[0] for p in rot_poly)
        mny = min(p[1] for p in rot_poly); mxy = max(p[1] for p in rot_poly)
        box_w, box_h = mxx - mnx, mxy - mny

        # 自适应步长——保证格网单元数在合理范围
        self._gstep = max(4.0 * scale, math.sqrt((box_w * box_h) / 1200.0))
        approx_ridges = max(1, box_h / ridge_px)
        step_px = max(1.5 * scale, (box_w * approx_ridges) / 800.0)

        # ---- 候选点 + 垄DB ----
        pool = []; self.rdb = {}
        scan_y = mny + ridge_px / 2.0; ridge_idx = 0
        while scan_y <= mxy:
            pts = _scan_x(scan_y, rot_poly)
            for i in range(0, len(pts) - 1, 2):
                sx, ex = pts[i], pts[i + 1]
                self.rdb[ridge_idx] = {'y_rot': scan_y, 'left_rot': sx, 'right_rot': ex}
                cur_x = sx + step_px
                while cur_x <= ex - step_px:
                    pool.append({'real_xy': _rot(cur_x, scan_y, cx, cy, theta),
                                 'rot_xy': (cur_x, scan_y), 'ridge_idx': ridge_idx})
                    cur_x += step_px
            if pts:
                ridge_idx += 1
            scan_y += ridge_px

        # ---- 评估格网 ----
        self._egrid = []
        gx = mnx
        while gx <= mxx:
            gy = mny
            while gy <= mxy:
                rx_, ry_ = _rot(gx, gy, cx, cy, theta)
                if _in_poly(rx_, ry_, self.poly):
                    self._egrid.append((rx_, ry_))
                gy += self._gstep
            gx += self._gstep

        if not self._egrid or not pool:
            messagebox.showerror("Error", "算子空间结构异常，请检查标定范围或放宽参数。"); return

        total_candidates = len(pool)
        self.stvar.set(
            f"CALCULATING: {total_candidates}候选点，{len(self._egrid)}格网单元...")
        self.root.update()

        # ---- 覆盖选址(带进度) ----
        ev = CoverEval(self._egrid, pool, radius_px)
        cum_conf = [0.0] * len(self._egrid)
        all_selected = []

        def _progress(step, total):
            self.stvar.set(f"CALCULATING: 第{len(all_selected) + 1}轮 "
                           f"选点 {step}/{total} (候选池{total_candidates})")
            self.root.update()

        for rnd in range(n_rounds):
            sel, cum_conf = ev.select(cum_conf, n_samp, _progress)
            all_selected.append(sel)
        self._cconf = cum_conf

        # ---- 路径规划 ----
        tours = []; segs = []
        for nds in all_selected:
            n = len(nds)
            if n < 2:
                tours.append(list(range(n))); segs.append([]); continue
            tour = _2opt(_nnt(nds, self.rdb, cx, cy, theta),
                         nds, self.rdb, cx, cy, theta)
            tours.append(tour)
            round_segs = []
            for idx in range(n):
                na = nds[tour[idx]]; nb = nds[tour[(idx + 1) % n]]
                dp, _ = _hpath(na, nb, self.rdb, cx, cy, theta)
                dm = dp / scale
                round_segs.append({
                    'from': tour[idx], 'to': tour[(idx + 1) % n],
                    'dist_m': round(dm, 2),
                    'time_s': round(dm / speed_ms, 1)
                })
            segs.append(round_segs)

        self._rnds = all_selected
        self._tours = tours
        self._segs = segs

        # ---- 构建传感用采样点列表 ----
        self.spts = []
        for rnd, nodes in enumerate(all_selected):
            for li, node in enumerate(nodes):
                px, py = node['real_xy']
                self.spts.append({
                    'point_id': f"R{rnd + 1}-P{li + 1}",
                    'real_xy': (px, py),
                    'x_m': round((px - ref_x1) / scale, 2),
                    'y_m': round((py - ref_y1) / scale, 2),
                    'ridge_idx': node['ridge_idx'],
                    'round': rnd + 1,
                    'turbidity': None, 'risk': 'pending', 'read_time': '',
                })

        # 多边形米制坐标
        self.poly_m = [
            (round((x - ref_x1) / scale, 2), round((y - ref_y1) / scale, 2))
            for x, y in self.poly
        ]

        # ---- 统计输出 ----
        covered = sum(1 for c in cum_conf if c > 0.5)
        total = len(cum_conf)
        cov_pct = (covered / total * 100) if total > 0 else 0
        avg_conf = sum(cum_conf) / total if total > 0 else 0
        total_time = sum(sum(s['time_s'] for s in rs) for rs in segs)
        total_dist = sum(sum(s['dist_m'] for s in rs) for rs in segs)

        self.stvar.set(
            f"PLANNING DONE: {n_rounds}轮x~{n_samp}点 | "
            f"覆盖率{cov_pct:.1f}% | 均置信度{avg_conf:.3f} | "
            f"总路程{total_dist:.0f}m | 总时间{total_time:.0f}s")
        self._draw_plan()

    # =========================================================
    # 导出
    # =========================================================

    def export_json(self):
        if not self.spts:
            messagebox.showwarning("Warning", "请先完成路径规划再导出。"); return
        fp = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON 文件", "*.json")],
            title="导出路径规划 JSON")
        if not fp:
            return

        total_t = sum(sum(s['time_s'] for s in rs) for rs in self._segs)
        total_d = sum(sum(s['dist_m'] for s in rs) for rs in self._segs)
        covered = sum(1 for c in self._cconf if c > 0.5)
        total = len(self._cconf)

        data = {
            "meta": {
                "version": "2.0",
                "scale_px_per_m": round(self.scale, 2),
                "reference_point": [round(self.rx1, 1), round(self.ry1, 1)],
                "field_area_m2": round(
                    _area(self.poly) / (self.scale ** 2) if self.scale > 0 else 0, 2),
                "field_params": {
                    "reference_edge_m": float(self._erl.get()),
                    "ridge_distance_m": float(self._erd.get()),
                    "spore_radius_m": self.rad_m,
                    "vehicle_speed_ms": self.spd
                },
                "coverage_summary": {
                    "covered_cells": covered, "total_cells": total,
                    "coverage_pct": round((covered / total * 100) if total > 0 else 0, 1),
                    "mean_confidence": round(
                        sum(self._cconf) / total if total > 0 else 0, 4)
                },
                "path_summary": {
                    "total_distance_m": round(total_d, 2),
                    "total_time_s": round(total_t, 1),
                    "num_rounds": len(self._rnds)
                }
            },
            "field_polygon": {
                "vertices_m": [[v[0], v[1]] for v in self.poly_m],
                "vertices_px": [[round(x, 1), round(y, 1)] for x, y in self.poly]
            },
            "sampling_points": [
                {
                    "id": pt['point_id'],
                    "pixel": [round(pt['real_xy'][0], 1), round(pt['real_xy'][1], 1)],
                    "relative_m": [pt['x_m'], pt['y_m']],
                    "ridge_index": pt['ridge_idx'],
                    "round": pt['round']
                }
                for pt in self.spts
            ],
            "segments": self._segs
        }
        try:
            with open(fp, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.stvar.set(f"EXPORTED: {os.path.basename(fp)}")
            messagebox.showinfo("导出成功", f"已导出至:\n{fp}")
        except Exception as e:
            messagebox.showerror("导出失败", f"{e}")

    def _export_report(self):
        if not self.spts:
            messagebox.showwarning("Warning", "请先完成路径规划。"); return
        fp = filedialog.asksaveasfilename(
            defaultextension=".txt", filetypes=[("文本文件", "*.txt")],
            title="导出规划报告")
        if not fp:
            return

        covered = sum(1 for c in self._cconf if c > 0.5)
        total = len(self._cconf)
        cov_pct = (covered / total * 100) if total > 0 else 0
        total_t = sum(sum(s['time_s'] for s in rs) for rs in self._segs)
        total_d = sum(sum(s['dist_m'] for s in rs) for rs in self._segs)
        area_m2 = _area(self.poly) / (self.scale ** 2) if self.scale > 0 else 0

        lines = [
            "=" * 50,
            "  多模态智能巡检系统 — 路径规划报告",
            f"  生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 50,
            "",
            "[农田参数]",
            f"  地块面积: {area_m2:.1f} m²",
            f"  基准边实际长度: {float(self._erl.get()):.1f} m",
            f"  垄距: {float(self._erd.get()):.1f} m  边界顶点数: {len(self.poly)}",
            "",
            "[覆盖策略]",
            f"  孢子有效半径: {self.rad_m:.1f} m  采集轮次: {len(self._rnds)}",
            f"  每轮采样: ~{len(self.spts) // max(1, len(self._rnds))}点",
            f"  覆盖率(半高阈): {cov_pct:.1f}%",
            (f"  全域均置信度: {sum(self._cconf) / total:.4f}" if total > 0 else "  全域均置信度: N/A"),
            "",
            "[路径规划]",
            f"  小车速度: {self.spd:.1f} m/s  总路程: {total_d:.1f} m  总时间: {total_t:.0f} s",
            "",
            "[采样点清单]",
            f"  {'ID':<10} {'X(m)':>8} {'Y(m)':>8} {'垄':>4}",
            f"  {'-' * 34}",
        ]
        for pt in self.spts:
            lines.append(
                f"  {pt['point_id']:<10} {pt['x_m']:>8.2f} {pt['y_m']:>8.2f} {pt['ridge_idx']:>4}")

        try:
            with open(fp, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            self.stvar.set(f"EXPORTED: {os.path.basename(fp)}")
            messagebox.showinfo("导出成功", f"报告已写入:\n{fp}")
        except Exception as e:
            messagebox.showerror("导出失败", f"{e}")

    def _estimate_density(self):
        """根据地块面积和孢子半径估算推荐采样密度"""
        if not self.poly or self.scale <= 0:
            return None
        area_m2 = _area(self.poly) / (self.scale ** 2)
        # 粗略估计: 每个采样点覆盖面积 ≈ π*r², 取30%冗余
        coverage_per_point = math.pi * (self.rad_m ** 2)
        recommended = max(3, int(area_m2 / coverage_per_point * 1.3))
        return {"area_m2": round(area_m2, 1), "recommended_points": recommended,
                "coverage_per_point_m2": round(coverage_per_point, 1)}

    def _show_density(self):
        est = self._estimate_density()
        if not est:
            messagebox.showwarning("提示", "请先加载底图并闭合多边形。"); return
        # 根据地块形状做进一步修正: 狭长地块需要更多采样点
        if self.poly:
            xs = [p[0] for p in self.poly]; ys = [p[1] for p in self.poly]
            aspect = (max(xs) - min(xs)) / (max(ys) - min(ys) + 1)
            if aspect > 3 or aspect < 0.33:
                est['recommended_points'] = int(est['recommended_points'] * 1.2)
                shape_note = " (狭长地块已上浮20%)"
            else:
                shape_note = ""
        else:
            shape_note = ""
        msg = (f"地块面积: {est['area_m2']:.0f} m²\n"
               f"单点覆盖面积(πR²): {est['coverage_per_point_m2']:.0f} m²\n"
               f"推荐每轮采样点数: ~{est['recommended_points']} 点{shape_note}\n\n"
               f"提示: 实际采样还需考虑垄距、田间通行条件等因素。")
        messagebox.showinfo("推荐采样密度", msg)

    def _check_image_fit(self):
        """检查底图尺寸是否与多边形区域匹配，给出调整建议"""
        if not self.pimg or not self.poly:
            messagebox.showwarning("提示", "请先加载底图并标定多边形。"); return
        iw, ih = self.pimg.size
        xs = [p[0] for p in self.poly]; ys = [p[1] for p in self.poly]
        pw = max(xs) - min(xs); ph = max(ys) - min(ys)
        # 多边形相对图片的比例
        ratio_w = pw / iw * 100 if iw > 0 else 0
        ratio_h = ph / ih * 100 if ih > 0 else 0
        cw = self.canv.winfo_width(); ch = self.canv.winfo_height()
        if cw < 10: cw, ch = 1000, 800
        canvas_ratio = pw / cw * 100
        msg = (f"底图尺寸: {iw}x{ih} px\n"
               f"多边形范围: {pw:.0f}x{ph:.0f} px\n"
               f"多边形占底图: {ratio_w:.0f}% x {ratio_h:.0f}%\n"
               f"多边形占画布: {canvas_ratio:.0f}%\n\n")
        if canvas_ratio < 10:
            msg += "建议: 多边形相对画布偏小，可以放大图片或缩小窗口以获得更好的操作精度。"
        elif canvas_ratio > 90:
            msg += "建议: 多边形几乎占满画布，当前比例合适。"
        else:
            msg += "建议: 当前比例适合操作，可直接标定。"
        messagebox.showinfo("底图适配检查", msg)

    def _clear(self):
        self.poly = []; self.poly_m = []; self._ustk = []
        self.spts = []
        self._rnds = []; self._tours = []; self._segs = []
        self._cconf = []; self._egrid = []
        self.rdb = {}
        self.sel = -1
        self._stop_scan()
        self._draw_plan()
        self.stvar.set("SYS READY: 画布已清空，等待重新标定。")

    # =========================================================
    # 传感操作
    # =========================================================

    def _apply_th(self):
        try:
            tm = float(self._sm.get()); th = float(self._sh.get())
            cr = float(self._sr.get())
        except ValueError:
            messagebox.showerror("输入错误", "阈值必须为数值。"); return
        if tm <= 0 or th <= tm or cr <= 0:
            messagebox.showerror("输入错误", "需满足 0 < 中风险 < 高风险，且半径 > 0。"); return
        self.th_mid = tm; self.th_hi = th; self.cov_r = cr
        for pt in self.spts:
            if pt.get('turbidity') is not None:
                pt['risk'] = self._clfy(pt['turbidity'])
        self._rf_s()
        self.stvar.set(f"阈值已更新: 中>{tm}NTU, 高>{th}NTU, 覆盖半径{cr}m。")

    def _clfy(self, t):
        if t < self.th_mid: return 'low'
        if t < self.th_hi: return 'medium'
        return 'high'

    def _rtxt(self, r):
        return {'low': '低风险', 'medium': '中风险', 'high': '高风险'}.get(r, '待测')

    def _recommend_action(self):
        """根据当前传感数据给出农技建议"""
        if not self.spts:
            return "暂无数据，请先执行田间检测。"
        done = sum(1 for p in self.spts if p.get('turbidity') is not None)
        high = sum(1 for p in self.spts if p.get('risk') == 'high')
        med = sum(1 for p in self.spts if p.get('risk') == 'medium')
        total = len(self.spts)

        if done == 0:
            return "尚未开始检测，请点击「一键全检」或逐点「读取传感器」。"
        if high == 0 and med == 0:
            return f"已完成{done}/{total}点检测，暂未发现风险。建议继续完成剩余{total - done}点。"
        if high > 0:
            high_pts = [p['point_id'] for p in self.spts if p.get('risk') == 'high']
            return (f"⚠ 发现{high}个高风险点: {', '.join(high_pts[:5])}。"
                    f"建议立即对高风险区域进行精测采样(PCR)并考虑定点喷洒作业。")
        if med > 0 and med / max(1, done) > 0.3:
            return (f"⚠ {med}个中风险点(占已测{med / done * 100:.0f}%)。"
                    f"建议加强通风降低田间湿度，密切关注变化趋势。")
        return f"当前风险可控({done}/{total}已测)。继续保持正常巡检频率。"

    def _sim_turb(self, pt):
        """模拟光敏传感器读数。
        实际部署时替换为串口/I2C读取代码。
        目前提供四种分布模式用于算法验证。
        """
        mode = self._sim.get()
        if mode == "uniform":
            # 全域均匀随机[30, 600] NTU
            return round(random.uniform(30, 600), 1)

        elif mode == "hotspot":
            # 地块质心附近孢子在温湿条件下更活跃，浊度偏高
            centro = _centroid(self.poly)
            cx_m = (centro[0] - self.rx1) / self.scale if self.scale > 0 else 0
            cy_m = (centro[1] - self.ry1) / self.scale if self.scale > 0 else 0
            dist = math.hypot(pt['x_m'] - cx_m, pt['y_m'] - cy_m)
            base = max(50, 600 - dist * 8)
            return round(random.gauss(base, 40), 1)

        elif mode == "gradient":
            # 沿X方向线性递增(模拟上风向→下风向扩散)
            xs = [p['x_m'] for p in self.spts]
            rng = max(xs) - min(xs)
            if rng == 0:
                return round(random.uniform(30, 600), 1)
            t = (pt['x_m'] - min(xs)) / rng
            return round(random.gauss(50 + t * 500, 30), 1)

        elif mode == "twozone":
            # 左右双区：左侧高风险、右侧低风险
            xs = [p['x_m'] for p in self.spts]
            mid_x = (min(xs) + max(xs)) / 2
            if pt['x_m'] < mid_x:
                return round(random.gauss(420, 50), 1)
            else:
                return round(random.gauss(80, 25), 1)

        return round(random.uniform(30, 600), 1)

    def _sd_single(self):
        if self.sel < 0:
            messagebox.showwarning("提示", "请先在画布或表格中选中一个采样点。"); return
        self._do_rd(self.sel)

    def _do_rd(self, idx):
        pt = self.spts[idx]
        pt['turbidity'] = self._sim_turb(pt)
        pt['risk'] = self._clfy(pt['turbidity'])
        pt['read_time'] = datetime.now().strftime('%H:%M:%S')
        self.sel = idx
        self._upd_disp(pt)
        if pt['risk'] == 'high':
            self.stvar.set(
                f"ALERT! {pt['point_id']} 浊度{pt['turbidity']:.0f}NTU 超高风险阈值！建议立即干预。")
            self.root.bell()
        self._rf_s()

    def _upd_disp(self, pt):
        self._lpt.config(text=f"当前: {pt['point_id']}")
        if pt.get('turbidity') is not None:
            self._lrd.config(text=f"{pt['turbidity']:.1f} NTU", fg=self.cac)
            self._lrs.config(text=f"风险: {self._rtxt(pt['risk'])}",
                             fg=self.rsk_c.get(pt['risk'], self.cdm))
        else:
            self._lrd.config(text="-- NTU", fg=self.cdm)
            self._lrs.config(text="风险: 待检测", fg=self.cdm)

    def _sd_scan(self):
        unchecked = [i for i, p in enumerate(self.spts) if p.get('turbidity') is None]
        if not unchecked:
            messagebox.showinfo("提示", "所有采样点均已完成检测。"); return
        try:
            delay = float(self._sd.get())
        except ValueError:
            delay = 0.8
        self.scanning = True
        self.stvar.set(f"SCANNING: 开始顺序巡检，共{len(unchecked)}个待测点...")
        self._sd_step(unchecked, 0, delay)

    def _sd_step(self, indices, pos, delay):
        if not self.scanning or pos >= len(indices):
            if pos >= len(indices):
                self.scanning = False
                self._lpg.config(text="全检完成")
                done = sum(1 for p in self.spts if p.get('turbidity') is not None)
                high = sum(1 for p in self.spts if p.get('risk') == 'high')
                self.stvar.set(f"SCAN COMPLETE: {done}点已测, {high}点高风险。")
            return
        idx = indices[pos]
        pt = self.spts[idx]
        pt['turbidity'] = self._sim_turb(pt)
        pt['risk'] = self._clfy(pt['turbidity'])
        pt['read_time'] = datetime.now().strftime('%H:%M:%S')
        self.sel = idx
        self._upd_disp(pt)
        self._lpg.config(text=f"进度: {pos + 1}/{len(indices)}")
        if pt['risk'] == 'high':
            self.stvar.set(
                f"ALERT! [{pos + 1}/{len(indices)}] {pt['point_id']} 高风险！")
            self.root.bell()
        self._rf_s()
        ms = int(delay * 1000)
        self.sjob = self.root.after(ms, lambda: self._sd_step(indices, pos + 1, delay))

    def _stop_scan(self):
        self.scanning = False
        if self.sjob:
            self.root.after_cancel(self.sjob); self.sjob = None
        self._lpg.config(text="已手动停止")

    def _sd_reset(self):
        if messagebox.askyesno("确认重置", "确认清除全部传感器读数？此操作不可撤销。"):
            self._stop_scan()
            for pt in self.spts:
                pt['turbidity'] = None; pt['risk'] = 'pending'; pt['read_time'] = ''
            self.sel = -1
            self._lpt.config(text="当前采样点: 未选中")
            self._lrd.config(text="-- NTU", fg=self.cdm)
            self._lrs.config(text="风险: 等待检测", fg=self.cdm)
            self._lpg.config(text="")
            self._rf_s()
            self.stvar.set("RESET: 全部传感器读数已清除。")

    def _s_clk(self, e):
        """传感画布点击——选中最近的采样点"""
        if not self.spts:
            return
        best_i, best_d = -1, float('inf')
        for i, pt in enumerate(self.spts):
            d2 = (e.x - pt['real_xy'][0]) ** 2 + (e.y - pt['real_xy'][1]) ** 2
            if d2 < best_d:
                best_d, best_i = d2, i
        if best_i >= 0 and best_d < 900:  # 30px内有效
            self.sel = best_i; self._upd_disp(self.spts[best_i]); self._rf_s()

    def _on_tv_sel(self, e):
        sel = self._stv.selection()
        if not sel:
            self.sel = -1; self._rf_s(); return
        self.sel = int(sel[0]); self._upd_disp(self.spts[self.sel]); self._rf_s()

    def _rf_s(self):
        """刷新传感表格 + 统计 + 画布(若在传感页)"""
        for row in self._stv.get_children():
            self._stv.delete(row)
        for i, pt in enumerate(self.spts):
            t = f"{pt['turbidity']:.1f}" if pt.get('turbidity') is not None else '--'
            r = self._rtxt(pt.get('risk', 'pending'))
            tm = pt.get('read_time', '--')
            self._stv.insert('', 'end', iid=str(i),
                             values=(i + 1, pt['point_id'], t, r, tm))
        self._stv.tag_configure('hi', foreground=self.cdg)
        for i, pt in enumerate(self.spts):
            if pt.get('risk') == 'high':
                self._stv.item(str(i), tags=('hi',))

        total = len(self.spts)
        done = sum(1 for p in self.spts if p.get('turbidity') is not None)
        high = sum(1 for p in self.spts if p.get('risk') == 'high')
        self._sst.config(text=f"总计:{total}")
        self._ssd.config(text=f"已测:{done}")
        self._ssh.config(text=f"高风险:{high}")
        if done > 0:
            avg = sum(p['turbidity'] for p in self.spts if p.get('turbidity')) / done
            self._ssa.config(text=f"均值:{avg:.0f}")
        else:
            self._ssa.config(text="均值:--")

        if self.nb.index(self.nb.select()) == 1:
            self._draw_sens()

    def _show_recommend(self):
        msg = self._recommend_action()
        messagebox.showinfo("农技建议", msg)
        self.stvar.set(f"RECOMMEND: {msg[:80]}...")

    def _sd_export(self):
        if not self.spts:
            messagebox.showwarning("Warning", "无采集数据可导出。"); return
        fp = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV 文件", "*.csv")],
            title="导出粗定检测数据")
        if not fp:
            return
        try:
            with open(fp, 'w', newline='', encoding='utf-8-sig') as f:
                w = csv.writer(f)
                w.writerow(['采样点编号', 'X(m)', 'Y(m)', '垄索引',
                            '浊度(NTU)', '风险等级', '检测时间'])
                for pt in self.spts:
                    w.writerow([
                        pt['point_id'], pt['x_m'], pt['y_m'], pt['ridge_idx'],
                        f"{pt['turbidity']:.1f}" if pt.get('turbidity') else '',
                        self._rtxt(pt.get('risk', 'pending')),
                        pt.get('read_time', '')
                    ])
            self.stvar.set(f"EXPORTED: {os.path.basename(fp)}")
            messagebox.showinfo("导出成功",
                                f"已导出{len(self.spts)}条记录至:\n{fp}")
        except Exception as e:
            messagebox.showerror("导出失败", f"{e}")

    # =========================================================
    # 会话持久化
    # =========================================================

    def _save_ses(self):
        if not self.poly:
            messagebox.showwarning("Warning", "尚无数据可保存。"); return
        fp = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON 文件", "*.json")],
            title="保存工作会话")
        if not fp:
            return
        session = {
            "version": "2.0",
            "timestamp": datetime.now().isoformat(),
            "image_loaded": self.pimg is not None,
            "scale": round(self.scale, 4),
            "ref_point": [round(self.rx1, 1), round(self.ry1, 1)],
            "radius_m": self.rad_m, "speed_ms": self.spd,
            "field_polygon": [[round(x, 1), round(y, 1)] for x, y in self.poly],
            "field_polygon_m": [[v[0], v[1]] for v in self.poly_m],
            "params": {
                "ref_len": self._erl.get(), "ridge_dist": self._erd.get(),
                "sample_n": self._esn.get(), "spore_r": self._esr.get(),
                "rounds": self._ek.get(), "speed": self._esp.get()
            },
            "sensing_params": {
                "threshold_mid": self.th_mid, "threshold_high": self.th_hi,
                "coverage_radius": self.cov_r, "sim_mode": self._sim.get()
            },
            "sampling_points": [
                {
                    "point_id": pt['point_id'], "x_m": pt['x_m'], "y_m": pt['y_m'],
                    "real_xy": list(pt['real_xy']), "ridge_idx": pt['ridge_idx'],
                    "round": pt['round'], "turbidity": pt.get('turbidity'),
                    "risk": pt.get('risk'), "read_time": pt.get('read_time', '')
                }
                for pt in self.spts
            ],
            "round_tours": self._tours,
            "round_segments": self._segs
        }
        try:
            with open(fp, 'w', encoding='utf-8') as f:
                json.dump(session, f, ensure_ascii=False, indent=2)
            self.stvar.set(f"SAVED: {os.path.basename(fp)}")
            messagebox.showinfo("保存成功", f"会话已保存至:\n{fp}")
        except Exception as e:
            messagebox.showerror("保存失败", f"{e}")

    def _load_ses(self):
        fp = filedialog.askopenfilename(
            filetypes=[("JSON 文件", "*.json")], title="恢复工作会话")
        if not fp:
            return
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                s = json.load(f)
        except Exception as e:
            messagebox.showerror("加载失败", f"JSON解析异常: {e}"); return

        self.scale = s.get('scale', 1.0)
        rp = s.get('ref_point', [0, 0]); self.rx1, self.ry1 = rp[0], rp[1]
        self.rad_m = s.get('radius_m', 20.0); self.spd = s.get('speed_ms', 0.5)
        self.poly = [(x, y) for x, y in s.get('field_polygon', [])]
        self.poly_m = [(x, y) for x, y in s.get('field_polygon_m', [])]

        prm = s.get('params', {})
        for ent, key in [(self._erl, 'ref_len'), (self._erd, 'ridge_dist'),
                          (self._esn, 'sample_n'), (self._esr, 'spore_r'),
                          (self._ek, 'rounds'), (self._esp, 'speed')]:
            if key in prm: ent.delete(0, "end"); ent.insert(0, str(prm[key]))

        sp = s.get('sensing_params', {})
        self.th_mid = sp.get('threshold_mid', 150); self.th_hi = sp.get('threshold_high', 400)
        self.cov_r = sp.get('coverage_radius', 20)
        self._sim.set(sp.get('sim_mode', 'uniform'))
        for ent, val in [(self._sm, self.th_mid), (self._sh, self.th_hi),
                          (self._sr, self.cov_r)]:
            ent.delete(0, "end"); ent.insert(0, str(val))

        self.spts = []
        for pt in s.get('sampling_points', []):
            rxy = pt.get('real_xy', [0, 0])
            self.spts.append({
                'point_id': pt['point_id'], 'real_xy': tuple(rxy),
                'x_m': pt['x_m'], 'y_m': pt['y_m'],
                'ridge_idx': pt.get('ridge_idx', 0), 'round': pt.get('round', 1),
                'turbidity': pt.get('turbidity'), 'risk': pt.get('risk', 'pending'),
                'read_time': pt.get('read_time', '')
            })

        self._tours = s.get('round_tours', []); self._segs = s.get('round_segments', [])
        self.drawing = False
        self._cdims(); self._redraw()
        self.stvar.set(f"LOADED: {os.path.basename(fp)} — {len(self.spts)}个采样点已恢复。")

    # =========================================================
    # 综合统计弹窗
    # =========================================================

    def _show_stats(self):
        if not self.spts:
            messagebox.showwarning("Warning", "尚无数据可供统计。"); return

        win = tk.Toplevel(self.root)
        win.title("综合统计摘要"); win.geometry("480x520")
        win.configure(bg=self.cpn); win.transient(self.root); win.grab_set()

        tk.Label(win, text="综合统计摘要", fg=self.cif, bg=self.cpn,
                 font=("微软雅黑", 14, "bold")).pack(pady=15)

        nb = ttk.Notebook(win); nb.pack(fill="both", expand=True, padx=16, pady=8)

        # 规划统计页
        p1 = tk.Frame(nb, bg=self.cpn); nb.add(p1, text=" 规划统计 ")
        tp = tk.Text(p1, bg=self.cbg, fg=self.ctx, bd=0,
                     font=("Consolas", 10), padx=14, pady=14)
        tp.pack(fill="both", expand=True)

        n_pts = len(self.spts)
        n_rnds = len(set(p['round'] for p in self.spts))
        area_m2 = (_area(self.poly) / (self.scale ** 2)
                   if self.scale > 0 and self.poly else 0)
        c_ = _centroid(self.poly) if self.poly else (0, 0)
        cmx = (c_[0] - self.rx1) / self.scale if self.scale > 0 else 0
        cmy = (c_[1] - self.ry1) / self.scale if self.scale > 0 else 0

        pinf = [
            "══ 农田建模 ══",
            f"  边界顶点数:    {len(self.poly)}",
            f"  地块面积:      {area_m2:,.1f} m²",
            f"  质心坐标(m):   ({cmx:.1f}, {cmy:.1f})",
            f"  比例尺:        {self.scale:.2f} px/m",
            f"  垄沟总数:      {len(self.rdb)}",
            "",
            "══ 采样策略 ══",
            f"  采集轮次:      {n_rnds}",
            f"  采样点总数:    {n_pts}",
            f"  每轮平均点数:  {n_pts / max(1, n_rnds):.1f}",
            f"  孢子有效半径:  {self.rad_m:.1f} m",
        ]

        if self._cconf:
            covered = sum(1 for c in self._cconf if c > 0.5)
            total = len(self._cconf)
            pinf += [
                "",
                "══ 覆盖分析 ══",
                f"  评估格网单元:  {total}",
                f"  半高覆盖达标:  {covered} ({covered / total * 100:.1f}%)",
                f"  均置信度:      {sum(self._cconf) / total:.4f}",
            ]

        if self._segs:
            td = sum(sum(s['dist_m'] for s in rs) for rs in self._segs)
            tt = sum(sum(s['time_s'] for s in rs) for rs in self._segs)
            pinf += [
                "",
                "══ 路径规划 ══",
                f"  总行驶距离:    {td:,.1f} m",
                f"  预估总时间:    {tt:,.0f} s ({tt / 60:.1f} min)",
                f"  行驶速度:      {self.spd:.1f} m/s",
            ]

        tp.insert("1.0", "\n".join(pinf)); tp.config(state="disabled")

        # 传感统计页
        done = sum(1 for p in self.spts if p.get('turbidity') is not None)
        if done > 0:
            p2 = tk.Frame(nb, bg=self.cpn); nb.add(p2, text=" 传感统计 ")
            ts = tk.Text(p2, bg=self.cbg, fg=self.ctx, bd=0,
                         font=("Consolas", 10), padx=14, pady=14)
            ts.pack(fill="both", expand=True)

            hi = sum(1 for p in self.spts if p.get('risk') == 'high')
            med = sum(1 for p in self.spts if p.get('risk') == 'medium')
            low = sum(1 for p in self.spts if p.get('risk') == 'low')
            readings = [p['turbidity'] for p in self.spts if p.get('turbidity')]
            avg_t = sum(readings) / len(readings) if readings else 0
            var_t = sum((v - avg_t) ** 2 for v in readings) / len(readings) if readings else 0

            sinf = [
                "══ 检测进度 ══",
                f"  已检测:        {done} / {n_pts} ({done / n_pts * 100:.0f}%)",
                f"  待检测:        {n_pts - done}",
                "",
                "══ 风险分布 ══",
                f"  高风险(> {self.th_hi} NTU):    {hi} 点",
                f"  中风险({self.th_mid}-{self.th_hi} NTU): {med} 点",
                f"  低风险(< {self.th_mid} NTU):    {low} 点",
                "",
                "══ 浊度统计 ══",
                f"  均值:          {avg_t:.1f} NTU",
                f"  标准差:        {math.sqrt(var_t):.1f} NTU",
            ]
            if readings:
                sinf += [f"  最大值:        {max(readings):.1f} NTU",
                         f"  最小值:        {min(readings):.1f} NTU"]
            sinf += [f"  模拟模式:      {self._sim.get()}"]
            ts.insert("1.0", "\n".join(sinf)); ts.config(state="disabled")

        tk.Button(win, text="关闭", bg=self.ccd, fg=self.ctx, bd=0,
                  padx=20, pady=4, font=("微软雅黑", 10),
                  command=win.destroy).pack(pady=14)

    def _batch_export(self):
        if not self.spts:
            messagebox.showwarning("Warning", "请先完成路径规划。"); return
        dpath = filedialog.askdirectory(title="选择批量导出目录")
        if not dpath:
            return
        base = os.path.join(dpath, f"inspection_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        errors, files = [], []
        td = sum(sum(s['dist_m'] for s in rs) for rs in self._segs)
        tt = sum(sum(s['time_s'] for s in rs) for rs in self._segs)

        # JSON
        try:
            jp = base + ".json"
            data = {
                "meta": {"version": "2.0"},
                "field_polygon": {"vertices_m": [[v[0], v[1]] for v in self.poly_m]},
                "sampling_points": [
                    {"id": pt['point_id'], "relative_m": [pt['x_m'], pt['y_m']],
                     "turbidity": pt.get('turbidity'), "risk": pt.get('risk')}
                    for pt in self.spts
                ],
                "path_summary": {"total_distance_m": round(td, 2),
                                 "total_time_s": round(tt, 1)}
            }
            with open(jp, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            files.append(jp)
        except Exception as e:
            errors.append(f"JSON: {e}")

        # CSV
        try:
            cp = base + "_sensing.csv"
            with open(cp, 'w', newline='', encoding='utf-8-sig') as f:
                w = csv.writer(f)
                w.writerow(['采样点', 'X(m)', 'Y(m)', '浊度(NTU)', '风险', '时间'])
                for pt in self.spts:
                    w.writerow([pt['point_id'], pt['x_m'], pt['y_m'],
                                f"{pt['turbidity']:.1f}" if pt.get('turbidity') else '',
                                self._rtxt(pt.get('risk', 'pending')),
                                pt.get('read_time', '')])
            files.append(cp)
        except Exception as e:
            errors.append(f"CSV: {e}")

        # TXT
        try:
            tp = base + "_report.txt"
            done = sum(1 for p in self.spts if p.get('turbidity') is not None)
            hi = sum(1 for p in self.spts if p.get('risk') == 'high')
            lines = [
                "多模态智能巡检系统 — 综合导出报告",
                f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                f"采样点总数: {len(self.spts)}  已检测: {done}  高风险: {hi}",
                f"预估总路程: {td:.0f}m  总时间: {tt:.0f}s",
                "", "采样点清单:",
            ]
            for pt in self.spts:
                t = f"{pt['turbidity']:.1f}" if pt.get('turbidity') else '--'
                lines.append(
                    f"  {pt['point_id']:<10} X={pt['x_m']:>7.2f} Y={pt['y_m']:>7.2f}  {t} NTU")
            with open(tp, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            files.append(tp)
        except Exception as e:
            errors.append(f"TXT: {e}")

        msg = f"已导出 {len(files)} 个文件至:\n{dpath}"
        if errors:
            msg += f"\n\n错误: {len(errors)}个"
        self.stvar.set(f"BATCH EXPORT: {len(files)} files.")
        messagebox.showinfo("批量导出", msg)

    # =========================================================
    # 坐标验证工具 —— 检查多边形顶点的米制坐标是否合理
    # =========================================================

    def _validate_coords(self):
        """快速验证坐标转换是否合理，返回(ok, msg)"""
        if not self.poly_m:
            return False, "多边形米制坐标为空，请先完成规划。"
        xs = [v[0] for v in self.poly_m]; ys = [v[1] for v in self.poly_m]
        rng_x = max(xs) - min(xs); rng_y = max(ys) - min(ys)
        if rng_x < 0.5 or rng_y < 0.5:
            return False, f"多边形范围过小: X={rng_x:.1f}m, Y={rng_y:.1f}m，请检查基准边标定。"
        if rng_x > 5000 or rng_y > 5000:
            return False, f"多边形范围异常大: X={rng_x:.0f}m, Y={rng_y:.0f}m，请检查比例尺。"
        # 检查是否有采样点落在多边形外
        if self.spts:
            outside = 0
            for pt in self.spts:
                px = (pt['x_m'] - min(xs)) / (rng_x + 1e-9)
                py = (pt['y_m'] - min(ys)) / (rng_y + 1e-9)
                if not _in_poly(pt['x_m'], pt['y_m'], self.poly_m):
                    outside += 1
            if outside > 0:
                return True, f"坐标正常(警告: {outside}个采样点疑似在多边形外，属正常舍入误差)"
        return True, f"坐标验证通过: 范围X=[{min(xs):.1f},{max(xs):.1f}]m Y=[{min(ys):.1f},{max(ys):.1f}]m"

    # =========================================================
    # 快速巡检摘要 —— 仅统计，不弹窗，直接更新状态栏
    # =========================================================

    def _validate_coords_btn(self):
        ok, msg = self._validate_coords()
        if ok:
            messagebox.showinfo("坐标验证", msg)
        else:
            messagebox.showwarning("坐标验证", msg)
        self.stvar.set(f"VALIDATION: {msg}")

    def _quick_summary(self):
        """状态栏显示当前数据的简要统计"""
        if not self.spts:
            self.stvar.set("SUMMARY: 无数据。"); return
        total = len(self.spts)
        done = sum(1 for p in self.spts if p.get('turbidity') is not None)
        high = sum(1 for p in self.spts if p.get('risk') == 'high')
        if self._segs:
            td = sum(sum(s['dist_m'] for s in rs) for rs in self._segs)
            tt = sum(sum(s['time_s'] for s in rs) for rs in self._segs)
            self.stvar.set(
                f"SUMMARY: {total}采样点 | 已测{done} | 高风险{high} | "
                f"路程{td:.0f}m | 时间{tt:.0f}s")
        else:
            self.stvar.set(f"SUMMARY: {total}采样点 | 已测{done} | 高风险{high}")

    # =========================================================
    # 窗口关闭
    # =========================================================

    def _on_close(self):
        self._stop_scan()
        self.root.destroy()


# =========================================================
# 入口
# =========================================================
if __name__ == "__main__":
    root = tk.Tk()
    app = InspectionSystem(root)
    root.mainloop()
