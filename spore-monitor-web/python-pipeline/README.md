# spore-monitor-web — Python offline pipeline

Produces camelCase JSON artifacts (matching `lib/dispersion/`) plus figures.

## Run

```bash
uv sync
uv run python scripts/run_all.py
```

## Artifacts (`artifacts/`)

- `fate_params.json` — default vs calibrated spore-fate parameters + fit report.
- `infection_windows.json` — 8 disease infection windows with citations.
- `ab_results.json` — fine-grid truth vs Eulerian vs Gaussian A/B metrics.
- `ab_heatmaps.png` — horizon-120 log10 concentration heatmaps (3 panels).
- `calibration_scatter.png` — predicted-vs-observed log10 scatter + residuals.
- `infection_bars.png` — per-disease heuristic favorability index.
