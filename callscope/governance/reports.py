"""Validation report renderer (T-M5-04)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(enabled_extensions=()),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def thresholds_snapshot(path: Path | None = None) -> tuple[dict[str, Any], str]:
    p = path or Path("eval/thresholds.yaml")
    raw = p.read_bytes() if p.is_file() else b"{}\n"
    data = yaml.safe_load(raw.decode()) or {}
    if not isinstance(data, dict):
        data = {}
    return data, hashlib.sha256(raw).hexdigest()


def render_validation_report(
    *,
    model: dict[str, Any],
    eval_run_id: str,
    git_sha: str,
    dataset_id: str,
    stack_version_id: str,
    results: dict[str, Any],
    passed: bool,
    thresholds_path: Path | None = None,
    comparison_md: str = "_no incumbent compare_",
    risks_md: str = "_none open_",
    slices_md: str = "_see results_",
    signed_off_by: str | None = None,
    out_dir: Path | None = None,
    write_docx: bool = True,
) -> dict[str, Any]:
    """Write Markdown (+ optional DOCX) validation report; return metadata."""
    thr, thr_sha = thresholds_snapshot(thresholds_path)
    report_id = str(uuid4())
    out = out_dir or Path("docs/validation_reports")
    out.mkdir(parents=True, exist_ok=True)
    mid = str(model.get("model_version_id") or "unknown")
    md_path = out / f"validation-{mid[:8]}-{report_id[:8]}.md"
    repro = (
        f"python -m callscope.devtools.eval_cli run --stack {stack_version_id} "
        f"--dataset {dataset_id} --git-sha {git_sha}"
    )
    results_md = "```json\n" + json.dumps(results, indent=2) + "\n```"
    text = (
        _env()
        .get_template("validation_report.md.j2")
        .render(
            name=model.get("name"),
            revision=model.get("revision"),
            report_id=report_id,
            model_version_id=mid,
            eval_run_id=eval_run_id,
            passed=passed,
            git_sha=git_sha,
            dataset_id=dataset_id,
            stack_version_id=stack_version_id,
            thresholds_sha256=thr_sha,
            thresholds_yaml=yaml.safe_dump(thr, sort_keys=True),
            results_md=results_md,
            slices_md=slices_md,
            comparison_md=comparison_md,
            risks_md=risks_md,
            reproduction_cmd=repro,
            signed_off_by=signed_off_by,
            generated_at=datetime.now(UTC).isoformat(),
        )
    )
    md_path.write_text(text, encoding="utf-8")
    docx_uri: str | None = None
    if write_docx:
        docx_path = md_path.with_suffix(".docx")
        try:
            _write_docx(docx_path, text)
            docx_uri = str(docx_path)
        except Exception:
            docx_uri = None
    return {
        "report_id": report_id,
        "model_version_id": mid,
        "eval_run_id": eval_run_id,
        "thresholds": thr,
        "thresholds_sha256": thr_sha,
        "results": results,
        "passed": passed,
        "report_uri": str(md_path),
        "docx_uri": docx_uri,
        "signed_off_by": signed_off_by,
        "reproduction_cmd": repro,
    }


def _write_docx(path: Path, markdown_text: str) -> None:
    from docx import Document

    doc = Document()
    for line in markdown_text.splitlines():
        doc.add_paragraph(line)
    doc.save(str(path))


def report_repro_fingerprint(payload: dict[str, Any]) -> str:
    """Stable hash of reproduction-critical fields (same inputs → same fingerprint)."""
    keys = (
        "model_version_id",
        "eval_run_id",
        "thresholds_sha256",
        "passed",
        "reproduction_cmd",
    )
    blob = json.dumps({k: payload.get(k) for k in keys}, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()


def parse_report_id(report_id: str) -> UUID:
    return UUID(report_id)


__all__ = [
    "parse_report_id",
    "render_validation_report",
    "report_repro_fingerprint",
    "thresholds_snapshot",
]
