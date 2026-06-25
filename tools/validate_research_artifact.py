#!/usr/bin/env python3
"""Validate the packaged LAE-LiDAR research artifact.

This script checks repository-internal evidence only. External standard GDS
files are intentionally not required because they are validators, not shipped
generation inputs.
"""

from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Iterable


LOCAL_PATH_PATTERNS = [
    re.compile(r"D:/xprogram", re.IGNORECASE),
    re.compile(r"D:\\xprogram", re.IGNORECASE),
    re.compile(r"C:/Users", re.IGNORECASE),
    re.compile(r"C:\\Users", re.IGNORECASE),
    re.compile(r"wxid_", re.IGNORECASE),
    re.compile(r"lidar_c_agent", re.IGNORECASE),
    re.compile(r"PIC-DB-main", re.IGNORECASE),
    re.compile(r"<LIDAR_C_AGENT_ROOT>", re.IGNORECASE),
]

EXPECTED_CASES = {
    "toy_example_gp",
    "mrr_weight_bank_4x4",
    "mrr_weight_bank_8x8",
    "mrr_weight_bank_16x16",
    "clements_8x8",
    "clements_16x16",
    "multiportmmi_8x8",
    "multiportmmi_16x16",
    "multiportmmi_32x32",
}


class ValidationError(Exception):
    pass


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def parse_float(value: str, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    return float(value)


def parse_int(value: str, default: int = 0) -> int:
    if value is None or value == "":
        return default
    return int(float(value))


def evidence_paths(value: str) -> Iterable[str]:
    for item in (value or "").split(";"):
        item = item.strip()
        if item:
            yield item


def resolve_artifact_path(root: Path, value: str) -> list[Path]:
    normalized = value.replace("\\", "/")
    if normalized.startswith("<"):
        return []
    if "*" in normalized:
        return [Path(p) for p in glob.glob(str(root / normalized))]
    return [root / normalized]


def validate_json(root: Path, errors: list[str], report: dict[str, object]) -> None:
    json_files = sorted((root / "results").glob("**/*.json"))
    for path in json_files:
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - message is the value here.
            errors.append(f"invalid_json: {path.relative_to(root)}: {exc}")
    report["json_files_checked"] = len(json_files)


def validate_no_local_paths(root: Path, errors: list[str], report: dict[str, object]) -> None:
    checked = 0
    for base in [root / "README.md", root / "docs", root / "results"]:
        paths = [base] if base.is_file() else sorted(base.glob("**/*"))
        for path in paths:
            if not path.is_file() or path.suffix.lower() not in {".md", ".csv", ".json"}:
                continue
            checked += 1
            text = path.read_text(encoding="utf-8", errors="replace")
            for pattern in LOCAL_PATH_PATTERNS:
                if pattern.search(text):
                    errors.append(f"local_path_leak: {path.relative_to(root)} matches {pattern.pattern}")
    report["portable_text_files_checked"] = checked


def validate_matrix(root: Path, errors: list[str], report: dict[str, object]) -> list[dict[str, str]]:
    matrix_path = root / "results" / "research_evidence" / "h015_effect_evidence_matrix.csv"
    require(matrix_path.exists(), f"missing_matrix: {matrix_path}", errors)
    if not matrix_path.exists():
        return []
    rows = read_csv(matrix_path)
    cases = {row.get("case", "") for row in rows}
    require(cases == EXPECTED_CASES, f"matrix_cases_mismatch: {sorted(cases)}", errors)
    require(len(rows) == len(EXPECTED_CASES), f"matrix_row_count_mismatch: {len(rows)}", errors)

    for row in rows:
        case = row["case"]
        benchmark = root / row["benchmark_yml"]
        gds = root / row["generated_gds"]
        require(benchmark.exists(), f"missing_benchmark_yml: {case}: {benchmark}", errors)
        require(gds.exists(), f"missing_generated_gds: {case}: {gds}", errors)
        if gds.exists():
            digest = sha256_file(gds)
            require(digest == row["generated_sha256"], f"gds_sha256_mismatch: {case}", errors)
            require(gds.stat().st_size == parse_int(row["generated_bytes"]), f"gds_size_mismatch: {case}", errors)
        for evidence_file in evidence_paths(row.get("primary_evidence_files", "")):
            for resolved in resolve_artifact_path(root, evidence_file):
                require(resolved.exists(), f"missing_matrix_evidence_file: {case}: {evidence_file}", errors)

    report["matrix_rows"] = len(rows)
    report["matrix_gds_sha256_checked"] = sum(1 for row in rows if (root / row["generated_gds"]).exists())
    return rows


def validate_h015_summary(root: Path, matrix_rows: list[dict[str, str]], errors: list[str], report: dict[str, object]) -> None:
    summary_path = root / "results" / "research_evidence" / "h015_public_validation_summary.json"
    reference_csv = root / "results" / "reference_run" / "reference_run.csv"
    require(summary_path.exists(), f"missing_summary: {summary_path}", errors)
    require(reference_csv.exists(), f"missing_reference_run_csv: {reference_csv}", errors)
    if not summary_path.exists() or not reference_csv.exists():
        return

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    reference_rows = read_csv(reference_csv)
    ok_cases = sum(1 for row in reference_rows if row.get("status") == "ok")
    clean_cases = sum(parse_int(row.get("clean", "")) for row in reference_rows)
    total_markers = sum(parse_int(row.get("markers", "")) for row in reference_rows)
    route_markers = sum(parse_int(row.get("route_geometry_markers", "")) for row in reference_rows)
    route_core = sum(parse_float(row.get("timing_cpp_route_core_s", "")) for row in reference_rows)
    full_flow = sum(parse_float(row.get("timing_lidar_full_flow_s", "")) for row in reference_rows)

    require(summary.get("cases") == len(EXPECTED_CASES), "summary_cases_mismatch", errors)
    require(summary.get("ok_cases") == ok_cases, "summary_ok_cases_mismatch", errors)
    require(summary.get("clean_cases") == clean_cases, "summary_clean_cases_mismatch", errors)
    require(int(summary.get("total_markers", -1)) == total_markers, "summary_total_markers_mismatch", errors)
    require(int(summary.get("route_geometry_markers", -1)) == route_markers, "summary_route_markers_mismatch", errors)
    require(abs(float(summary.get("total_route_core_s", -1.0)) - route_core) < 1e-6, "summary_route_core_mismatch", errors)
    require(abs(float(summary.get("total_full_flow_s", -1.0)) - full_flow) < 1e-6, "summary_full_flow_mismatch", errors)
    require(int(summary.get("total_marker_delta_vs_h013", 999)) == -10, "summary_h013_delta_mismatch", errors)
    require(int(summary.get("total_marker_delta_vs_h010", 999)) == -30, "summary_h010_delta_mismatch", errors)

    matrix_cases = {row["case"] for row in matrix_rows}
    reference_cases = {row["case"] for row in reference_rows}
    require(matrix_cases == reference_cases, "matrix_reference_case_mismatch", errors)

    report["h015_total_markers"] = total_markers
    report["h015_route_geometry_markers"] = route_markers
    report["h015_clean_cases"] = clean_cases
    report["h015_total_route_core_s"] = round(route_core, 6)
    report["h015_total_full_flow_s"] = round(full_flow, 6)


def validate_standard_gds_rows(root: Path, errors: list[str], report: dict[str, object]) -> None:
    path = root / "results" / "research_evidence" / "h015_standard_gds_pair_summary.csv"
    require(path.exists(), f"missing_standard_compare: {path}", errors)
    if not path.exists():
        return
    rows = read_csv(path)
    raw_cpp = {
        row["case"]: row
        for row in rows
        if row.get("baseline") == "standard" and row.get("candidate") == "cpp" and row.get("mode") == "raw"
    }
    expected = {
        "clements_8x8": (0.0, 1.0),
        "multiportmmi_8x8": (5.091752, 0.999978471),
        "multiportmmi_16x16": (18.680864, 0.999969043),
    }
    for case, (xor_expected, overlap_expected) in expected.items():
        row = raw_cpp.get(case)
        require(row is not None, f"missing_standard_raw_cpp_row: {case}", errors)
        if row is None:
            continue
        require(abs(parse_float(row["xor_total_area_um2"]) - xor_expected) < 1e-6, f"standard_xor_mismatch: {case}", errors)
        require(abs(parse_float(row["total_overlap_ratio"]) - overlap_expected) < 1e-9, f"standard_overlap_mismatch: {case}", errors)
    report["standard_gds_raw_cpp_rows"] = len(raw_cpp)


def validate_claims(root: Path, errors: list[str], report: dict[str, object]) -> None:
    path = root / "results" / "research_evidence" / "research_claims_ledger.csv"
    require(path.exists(), f"missing_claims_ledger: {path}", errors)
    if not path.exists():
        return
    rows = read_csv(path)
    require(len(rows) >= 7, f"claims_ledger_too_short: {len(rows)}", errors)
    for row in rows:
        claim_id = row.get("claim_id", "<missing>")
        for column in ["primary_files", "comparison_files", "gds_files"]:
            for value in evidence_paths(row.get(column, "")):
                resolved_paths = resolve_artifact_path(root, value)
                if value.startswith("<"):
                    continue
                require(resolved_paths, f"claim_glob_empty: {claim_id}: {column}: {value}", errors)
                for resolved in resolved_paths:
                    require(resolved.exists(), f"claim_file_missing: {claim_id}: {column}: {value}", errors)
    report["claims_checked"] = len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Path to the lidar_c package root.")
    parser.add_argument("--json-out", default="", help="Optional path for a JSON validation report.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    errors: list[str] = []
    report: dict[str, object] = {"artifact_root": "<LIDAR_C_ROOT>"}

    validate_json(root, errors, report)
    validate_no_local_paths(root, errors, report)
    matrix_rows = validate_matrix(root, errors, report)
    validate_h015_summary(root, matrix_rows, errors, report)
    validate_standard_gds_rows(root, errors, report)
    validate_claims(root, errors, report)

    report["status"] = "fail" if errors else "pass"
    report["errors"] = errors

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if errors:
        print("research_artifact_validation=fail")
        for error in errors:
            print(error)
        return 1

    print("research_artifact_validation=pass")
    for key in [
        "json_files_checked",
        "portable_text_files_checked",
        "matrix_rows",
        "matrix_gds_sha256_checked",
        "h015_clean_cases",
        "h015_total_markers",
        "h015_route_geometry_markers",
        "h015_total_route_core_s",
        "h015_total_full_flow_s",
        "standard_gds_raw_cpp_rows",
        "claims_checked",
    ]:
        print(f"{key}={report.get(key)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
