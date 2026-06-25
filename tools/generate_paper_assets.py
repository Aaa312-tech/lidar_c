#!/usr/bin/env python3
"""Generate paper-ready tables and figure data from the research evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
from html import escape
import json
from pathlib import Path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def markdown_table(rows: list[dict[str, object]], fieldnames: list[str]) -> str:
    if not rows:
        return ""
    header = "| " + " | ".join(fieldnames) + " |"
    sep = "| " + " | ".join("---" for _ in fieldnames) + " |"
    body = []
    for row in rows:
        values = [str(row.get(name, "")) for name in fieldnames]
        values = [value.replace("|", "\\|") for value in values]
        body.append("| " + " | ".join(values) + " |")
    return "\n".join([header, sep, *body]) + "\n"


def write_markdown_table(path: Path, title: str, rows: list[dict[str, object]], fieldnames: list[str], note: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = f"# {title}\n\n"
    if note:
        text += note.strip() + "\n\n"
    text += markdown_table(rows, fieldnames)
    path.write_text(text, encoding="utf-8")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def short_sha(value: str) -> str:
    return value[:12] if value else ""


def family_for_case(case: str) -> str:
    if case.startswith("mrr_"):
        return "MRR"
    if case.startswith("clements"):
        return "Clements"
    if case.startswith("multiportmmi"):
        return "MultiportMMI"
    return "smoke"


def fmt(value: object, digits: int = 6) -> str:
    if value in ("", None):
        return ""
    return f"{float(value):.{digits}f}"


def svg_text(x: float, y: float, text: object, size: int = 12, anchor: str = "start", weight: str = "400") -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="Arial, sans-serif" '
        f'font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" fill="#1f2937">'
        f"{escape(str(text))}</text>"
    )


def svg_bar(x: float, y: float, width: float, height: float, fill: str) -> str:
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{height:.1f}" fill="{fill}" rx="2" />'


def svg_frame(width: int, height: int, title: str, subtitle: str, body: list[str]) -> str:
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff" />',
        svg_text(24, 34, title, 20, weight="700"),
    ]
    if subtitle:
        parts.append(svg_text(24, 56, subtitle, 12))
    parts.extend(body)
    parts.append("</svg>\n")
    return "\n".join(parts)


def write_text_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def render_mrr_marker_svg(path: Path, rows: list[dict[str, object]]) -> None:
    width, height = 780, 420
    left, top, chart_w, chart_h = 110, 86, 610, 250
    max_marker = max(int(row["markers"]) for row in rows)
    colors = {"H010": "#9ca3af", "H013": "#60a5fa", "H015": "#16a34a"}
    cases = []
    for row in rows:
        if row["case"] not in cases:
            cases.append(row["case"])
    body = [
        '<line x1="110" y1="336" x2="720" y2="336" stroke="#9ca3af" stroke-width="1" />',
        '<line x1="110" y1="86" x2="110" y2="336" stroke="#9ca3af" stroke-width="1" />',
    ]
    for tick in [0, 30, 60, 90, 120]:
        y = top + chart_h - (tick / 120.0) * chart_h
        body.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + chart_w}" y2="{y:.1f}" stroke="#e5e7eb" stroke-width="1" />')
        body.append(svg_text(left - 10, y + 4, tick, 11, anchor="end"))
    group_w = chart_w / len(cases)
    bar_w = 42
    for i, case in enumerate(cases):
        case_rows = [row for row in rows if row["case"] == case]
        base_x = left + i * group_w + 36
        for j, row in enumerate(case_rows):
            iteration = str(row["iteration"])
            markers = int(row["markers"])
            bar_h = (markers / max_marker) * chart_h
            x = base_x + j * (bar_w + 12)
            y = top + chart_h - bar_h
            body.append(svg_bar(x, y, bar_w, bar_h, colors[iteration]))
            body.append(svg_text(x + bar_w / 2, y - 6, markers, 11, anchor="middle", weight="700"))
        label = case.replace("mrr_weight_bank_", "MRR ")
        body.append(svg_text(base_x + 70, 365, label, 12, anchor="middle"))
    legend_x = 505
    for idx, key in enumerate(["H010", "H013", "H015"]):
        x = legend_x + idx * 70
        body.append(svg_bar(x, 28, 14, 14, colors[key]))
        body.append(svg_text(x + 20, 40, key, 12))
    write_text_file(
        path,
        svg_frame(
            width,
            height,
            "MRR marker reduction",
            "Route-geometry markers decrease under H011/H013/H015 general geometry fixes.",
            body,
        ),
    )


def render_runtime_svg(path: Path, rows: list[dict[str, object]]) -> None:
    width, height = 900, 560
    left, top, chart_w = 230, 80, 590
    row_h = 42
    max_full = max(float(row["full_flow_s"]) for row in rows)
    body = [
        svg_text(left, 58, "route core", 12, weight="700"),
        svg_text(left + 110, 58, "non-core full-flow", 12, weight="700"),
        svg_bar(left + 80, 47, 18, 12, "#2563eb"),
        svg_bar(left + 230, 47, 18, 12, "#f59e0b"),
    ]
    for idx, row in enumerate(rows):
        y = top + idx * row_h
        case = str(row["case"])
        route_core = float(row["route_core_s"])
        full_flow = float(row["full_flow_s"])
        non_core = max(0.0, full_flow - route_core)
        core_w = (route_core / max_full) * chart_w
        non_core_w = (non_core / max_full) * chart_w
        body.append(svg_text(24, y + 18, case, 11))
        body.append(svg_bar(left, y, core_w, 20, "#2563eb"))
        body.append(svg_bar(left + core_w, y, non_core_w, 20, "#f59e0b"))
        body.append(svg_text(left + core_w + non_core_w + 8, y + 15, f"{full_flow:.1f}s", 11))
    axis_y = top + len(rows) * row_h + 6
    body.append(f'<line x1="{left}" y1="{axis_y}" x2="{left + chart_w}" y2="{axis_y}" stroke="#9ca3af" stroke-width="1" />')
    for tick in [0, 250, 500, 750, 1000]:
        x = left + (tick / max_full) * chart_w
        body.append(f'<line x1="{x:.1f}" y1="{axis_y}" x2="{x:.1f}" y2="{axis_y + 6}" stroke="#9ca3af" />')
        body.append(svg_text(x, axis_y + 22, f"{tick}s", 10, anchor="middle"))
    write_text_file(
        path,
        svg_frame(
            width,
            height,
            "H015 route-core vs full-flow runtime",
            "Full-flow includes conversion, DB DRC, GDS rendering, KLayout write, and filesystem IO.",
            body,
        ),
    )


def render_standard_xor_svg(path: Path, rows: list[dict[str, object]]) -> None:
    width, height = 760, 380
    left, top, chart_w, chart_h = 90, 86, 580, 210
    max_xor = max(float(row["standard_xor_um2"]) for row in rows) or 1.0
    body = [
        '<line x1="90" y1="296" x2="670" y2="296" stroke="#9ca3af" />',
        '<line x1="90" y1="86" x2="90" y2="296" stroke="#9ca3af" />',
    ]
    bar_w = 90
    gap = (chart_w - len(rows) * bar_w) / len(rows)
    for idx, row in enumerate(rows):
        xor = float(row["standard_xor_um2"])
        bar_h = 2 if xor == 0 else (xor / max_xor) * chart_h
        x = left + gap / 2 + idx * (bar_w + gap)
        y = top + chart_h - bar_h
        color = "#16a34a" if xor == 0 else "#0ea5e9"
        body.append(svg_bar(x, y, bar_w, bar_h, color))
        body.append(svg_text(x + bar_w / 2, y - 8, f"{xor:.6f}", 11, anchor="middle", weight="700"))
        label = str(row["case"]).replace("multiportmmi_", "MMI ").replace("clements_", "Clements ")
        body.append(svg_text(x + bar_w / 2, 322, label, 11, anchor="middle"))
    body.append(svg_text(20, 84, "XOR um2", 11))
    write_text_file(
        path,
        svg_frame(
            width,
            height,
            "Standard-GDS XOR comparison",
            "Clements is exact; MultiportMMI residuals are tiny crossing-area differences.",
            body,
        ),
    )


def render_agent_protocol_svg(path: Path) -> None:
    width, height = 920, 360
    steps = [
        "Hypothesis",
        "Scoped edit",
        "Tiered run",
        "DRC + GDS XOR",
        "A/B timing",
        "Accept / reject",
        "Evidence ledger",
    ]
    body = []
    box_w, box_h = 110, 58
    start_x, y = 34, 142
    for idx, step in enumerate(steps):
        x = start_x + idx * 126
        body.append(f'<rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" rx="6" fill="#f8fafc" stroke="#475569" />')
        words = step.split(" ")
        if len(words) == 1:
            body.append(svg_text(x + box_w / 2, y + 35, step, 12, anchor="middle", weight="700"))
        else:
            body.append(svg_text(x + box_w / 2, y + 26, " ".join(words[:2]), 12, anchor="middle", weight="700"))
            body.append(svg_text(x + box_w / 2, y + 43, " ".join(words[2:]), 12, anchor="middle", weight="700"))
        if idx < len(steps) - 1:
            x1 = x + box_w
            x2 = x + 126
            body.append(f'<line x1="{x1}" y1="{y + box_h / 2}" x2="{x2 - 8}" y2="{y + box_h / 2}" stroke="#64748b" stroke-width="2" />')
            body.append(f'<polygon points="{x2 - 8},{y + box_h / 2 - 5} {x2},{y + box_h / 2} {x2 - 8},{y + box_h / 2 + 5}" fill="#64748b" />')
    body.append(svg_text(34, 250, "Hard gates: build, DRC, protected GDS, standard-GDS comparison, timing evidence", 13, weight="700"))
    body.append(svg_text(34, 276, "Disallowed: standard-GDS replay, case-name route patches, net-id answer leakage", 13))
    write_text_file(
        path,
        svg_frame(
            width,
            height,
            "LAE-LiDAR agentic optimization loop",
            "Each change is a falsifiable routing hypothesis tied to concrete GDS and runtime evidence.",
            body,
        ),
    )


def load_standard_rows(root: Path) -> dict[str, dict[str, str]]:
    rows = read_csv(root / "results" / "research_evidence" / "h015_standard_gds_pair_summary.csv")
    return {
        row["case"]: row
        for row in rows
        if row.get("baseline") == "standard" and row.get("candidate") == "cpp" and row.get("mode") == "raw"
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Path to the lidar_c package root.")
    parser.add_argument(
        "--out-dir",
        default="results/research_evidence/paper_assets",
        help="Output directory relative to --root unless absolute.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    ev = root / "results" / "research_evidence"
    matrix = read_csv(ev / "h015_effect_evidence_matrix.csv")
    standard = load_standard_rows(root)
    h010 = json.loads((ev / "h010_public_validation_summary.json").read_text(encoding="utf-8"))
    h013 = json.loads((ev / "h013_public_validation_summary.json").read_text(encoding="utf-8"))
    h015 = json.loads((ev / "h015_public_validation_summary.json").read_text(encoding="utf-8"))
    h015_ab = json.loads((ev / "h015_ab_timing_n3_summary.json").read_text(encoding="utf-8"))

    generated: list[Path] = []

    table1_fields = [
        "family",
        "case",
        "clean",
        "markers",
        "route_geometry_markers",
        "crossings",
        "route_core_s",
        "full_flow_s",
        "generated_gds",
        "sha256_12",
    ]
    table1 = []
    for row in matrix:
        table1.append(
            {
                "family": family_for_case(row["case"]),
                "case": row["case"],
                "clean": row["clean"],
                "markers": row["markers"],
                "route_geometry_markers": row["route_geometry_markers"],
                "crossings": row["crossings"],
                "route_core_s": fmt(row["route_core_s"]),
                "full_flow_s": fmt(row["full_flow_s"]),
                "generated_gds": row["generated_gds"],
                "sha256_12": short_sha(row["generated_sha256"]),
            }
        )
    path = out_dir / "table1_h015_quality_runtime.csv"
    write_csv(path, table1, table1_fields)
    generated.append(path)
    path = out_dir / "table1_h015_quality_runtime.md"
    write_markdown_table(
        path,
        "Table 1: H015 Quality And Runtime",
        table1,
        table1_fields,
        "Per-case DRC quality, route-core runtime, full-flow runtime, and generated GDS identity.",
    )
    generated.append(path)

    table2_fields = ["case", "generated_gds", "standard_gds", "standard_xor_um2", "overlap_ratio", "interpretation"]
    table2 = []
    for case in ["clements_8x8", "multiportmmi_8x8", "multiportmmi_16x16"]:
        row = next(item for item in matrix if item["case"] == case)
        std = standard[case]
        xor = float(std["xor_total_area_um2"])
        interpretation = "exact geometry" if xor == 0.0 else "DRC-clean, near-exact crossing-area residual"
        table2.append(
            {
                "case": case,
                "generated_gds": row["generated_gds"],
                "standard_gds": std["baseline_file"],
                "standard_xor_um2": fmt(std["xor_total_area_um2"]),
                "overlap_ratio": fmt(std["total_overlap_ratio"], 9),
                "interpretation": interpretation,
            }
        )
    path = out_dir / "table2_standard_gds_agreement.csv"
    write_csv(path, table2, table2_fields)
    generated.append(path)
    path = out_dir / "table2_standard_gds_agreement.md"
    write_markdown_table(
        path,
        "Table 2: Standard-GDS Agreement",
        table2,
        table2_fields,
        "External standard GDS files are validation inputs only and are not shipped.",
    )
    generated.append(path)

    table3_fields = [
        "case",
        "h010_markers",
        "h013_markers",
        "h015_markers",
        "h015_delta_vs_h010",
        "h015_delta_vs_h013",
        "h015_gds",
        "h015_vs_h013_xor_um2",
    ]
    marker_progression = {
        "mrr_weight_bank_8x8": (8, 6, 2),
        "mrr_weight_bank_16x16": (110, 92, 86),
    }
    table3 = []
    for case, (m010, m013, m015) in marker_progression.items():
        row = next(item for item in matrix if item["case"] == case)
        table3.append(
            {
                "case": case,
                "h010_markers": m010,
                "h013_markers": m013,
                "h015_markers": m015,
                "h015_delta_vs_h010": m015 - m010,
                "h015_delta_vs_h013": m015 - m013,
                "h015_gds": row["generated_gds"],
                "h015_vs_h013_xor_um2": fmt(row["h013_xor_um2"]),
            }
        )
    path = out_dir / "table3_mrr_marker_progression.csv"
    write_csv(path, table3, table3_fields)
    generated.append(path)
    path = out_dir / "table3_mrr_marker_progression.md"
    write_markdown_table(
        path,
        "Table 3: MRR Marker Progression",
        table3,
        table3_fields,
        "MRR marker reduction from H010 to H015 through accepted general geometry fixes.",
    )
    generated.append(path)

    table4_fields = [
        "scope",
        "cases",
        "repetitions",
        "route_core_metric",
        "full_flow_metric",
        "quality_gate",
        "gds_gate",
        "primary_evidence",
    ]
    table4 = [
        {
            "scope": "H015 full-suite validation",
            "cases": "9",
            "repetitions": "1 archived full run",
            "route_core_metric": f"total {fmt(h015['total_route_core_s'])} s",
            "full_flow_metric": f"total {fmt(h015['total_full_flow_s'])} s",
            "quality_gate": "6/9 clean, 89 markers",
            "gds_gate": "9 generated GDS with SHA256 in matrix",
            "primary_evidence": "results/reference_run/reference_run.csv",
        },
        {
            "scope": "H015 vs H013 selected A/B",
            "cases": ", ".join(h015_ab["cases"]),
            "repetitions": str(h015_ab["case_count"]) + " cases x 3 reps",
            "route_core_metric": f"{fmt(h015_ab['avg_route_core_delta_percent'])}% delta",
            "full_flow_metric": f"{fmt(h015_ab['avg_full_flow_delta_percent'])}% delta",
            "quality_gate": "quality change intentionally affects MRR cases",
            "gds_gate": "MMI16 exact in 3/3 sampled reps",
            "primary_evidence": "results/research_evidence/h015_ab_timing_n3_summary_by_case.csv",
        },
        {
            "scope": "H005+H007+H008 vs initial C++ seed",
            "cases": "clements_16x16, mrr_weight_bank_16x16, multiportmmi_16x16",
            "repetitions": "3 per case",
            "route_core_metric": "-9.057515% delta",
            "full_flow_metric": "-1.612740% delta",
            "quality_gate": "all_quality_same=true",
            "gds_gate": "all_gds_exact=true",
            "primary_evidence": "docs/PERFORMANCE_AND_QUALITY_EVIDENCE.md",
        },
        {
            "scope": "H010 vs H008",
            "cases": "clements_16x16, multiportmmi_8x8",
            "repetitions": "3 per case",
            "route_core_metric": "-9.949529% delta",
            "full_flow_metric": "-9.582883% delta",
            "quality_gate": "all_quality_same=true",
            "gds_gate": "all_gds_exact=true",
            "primary_evidence": "docs/PERFORMANCE_AND_QUALITY_EVIDENCE.md",
        },
    ]
    path = out_dir / "table4_runtime_evidence.csv"
    write_csv(path, table4, table4_fields)
    generated.append(path)
    path = out_dir / "table4_runtime_evidence.md"
    write_markdown_table(
        path,
        "Table 4: Runtime Evidence",
        table4,
        table4_fields,
        "Route-core timing is interpreted separately from full-flow timing.",
    )
    generated.append(path)

    fig_mrr_fields = ["case", "iteration", "markers"]
    fig_mrr = []
    for case, values in marker_progression.items():
        for iteration, markers in zip(["H010", "H013", "H015"], values):
            fig_mrr.append({"case": case, "iteration": iteration, "markers": markers})
    path = out_dir / "figure_data_mrr_marker_progression.csv"
    write_csv(path, fig_mrr, fig_mrr_fields)
    generated.append(path)
    path = out_dir / "figure1_mrr_marker_progression.svg"
    render_mrr_marker_svg(path, fig_mrr)
    generated.append(path)

    fig_runtime_fields = ["case", "route_core_s", "full_flow_s", "non_core_flow_s", "generated_gds"]
    fig_runtime = []
    for row in matrix:
        route_core = float(row["route_core_s"])
        full_flow = float(row["full_flow_s"])
        fig_runtime.append(
            {
                "case": row["case"],
                "route_core_s": fmt(route_core),
                "full_flow_s": fmt(full_flow),
                "non_core_flow_s": fmt(full_flow - route_core),
                "generated_gds": row["generated_gds"],
            }
        )
    path = out_dir / "figure_data_runtime_breakdown.csv"
    write_csv(path, fig_runtime, fig_runtime_fields)
    generated.append(path)
    path = out_dir / "figure2_runtime_breakdown.svg"
    render_runtime_svg(path, fig_runtime)
    generated.append(path)

    fig_standard_fields = ["case", "standard_xor_um2", "overlap_ratio", "generated_gds"]
    fig_standard = [
        {
            "case": row["case"],
            "standard_xor_um2": row["standard_xor_um2"],
            "overlap_ratio": row["standard_overlap_ratio"],
            "generated_gds": row["generated_gds"],
        }
        for row in matrix
        if row["standard_xor_um2"]
    ]
    path = out_dir / "figure_data_standard_xor.csv"
    write_csv(path, fig_standard, fig_standard_fields)
    generated.append(path)
    path = out_dir / "figure3_standard_xor.svg"
    render_standard_xor_svg(path, fig_standard)
    generated.append(path)

    path = out_dir / "figure4_agent_protocol.svg"
    render_agent_protocol_svg(path)
    generated.append(path)

    readme = out_dir / "README.md"
    readme.write_text(
        "\n".join(
            [
                "# Paper Assets",
                "",
                "These deterministic tables and figure-data CSV files are generated from",
                "the repository evidence by:",
                "",
                "```powershell",
                "python tools\\generate_paper_assets.py --root .",
                "```",
                "",
                "Main sources:",
                "",
                "```text",
                "results/research_evidence/h015_effect_evidence_matrix.csv",
                "results/research_evidence/research_claims_ledger.csv",
                "results/reference_run/reference_run.csv",
                "```",
                "",
                "Generated assets:",
                "",
                "```text",
                "table1_h015_quality_runtime.csv/.md",
                "table2_standard_gds_agreement.csv/.md",
                "table3_mrr_marker_progression.csv/.md",
                "table4_runtime_evidence.csv/.md",
                "figure_data_mrr_marker_progression.csv",
                "figure_data_runtime_breakdown.csv",
                "figure_data_standard_xor.csv",
                "figure1_mrr_marker_progression.svg",
                "figure2_runtime_breakdown.svg",
                "figure3_standard_xor.svg",
                "figure4_agent_protocol.svg",
                "asset_manifest.json",
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )
    generated.append(readme)

    manifest_entries = []
    for path in sorted(generated):
        manifest_entries.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
        )
    manifest = {
        "generator": "tools/generate_paper_assets.py",
        "source_files": [
            "results/research_evidence/h015_effect_evidence_matrix.csv",
            "results/research_evidence/research_claims_ledger.csv",
            "results/reference_run/reference_run.csv",
            "results/research_evidence/h010_public_validation_summary.json",
            "results/research_evidence/h013_public_validation_summary.json",
            "results/research_evidence/h015_public_validation_summary.json",
            "results/research_evidence/h015_ab_timing_n3_summary.json",
        ],
        "assets": manifest_entries,
        "summary": {
            "table1_rows": len(table1),
            "table2_rows": len(table2),
            "table3_rows": len(table3),
            "table4_rows": len(table4),
            "mrr_figure_rows": len(fig_mrr),
            "runtime_figure_rows": len(fig_runtime),
            "standard_xor_rows": len(fig_standard),
            "svg_figures": 4,
        },
    }
    manifest_path = out_dir / "asset_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"paper_assets_generated={len(generated) + 1}")
    print(f"out_dir={out_dir.relative_to(root).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
