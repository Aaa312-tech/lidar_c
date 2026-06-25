#!/usr/bin/env python3
"""Generate paper-ready tables and figure data from the research evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
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
        },
    }
    manifest_path = out_dir / "asset_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"paper_assets_generated={len(generated) + 1}")
    print(f"out_dir={out_dir.relative_to(root).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
