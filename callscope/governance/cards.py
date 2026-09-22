"""Model card renderer (T-M5-04)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(enabled_extensions=()),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_model_card(
    model: dict[str, Any],
    *,
    out_dir: Path | None = None,
    metrics: list[dict[str, Any]] | None = None,
    limitations: list[str] | None = None,
    training_data_md: str = "_none recorded_",
    evaluation_data_md: str = "_see linked eval run_",
    changelog_md: str = "_initial registration_",
) -> Path:
    """Render Markdown model card; return output path."""
    out = out_dir or Path("docs/model_cards")
    out.mkdir(parents=True, exist_ok=True)
    mid = str(model.get("model_version_id") or "unknown")
    safe_name = f"{model.get('component', 'model')}-{model.get('name', 'x')}".replace("/", "_")
    path = out / f"{safe_name}-{mid[:8]}.md"

    metrics_rows = metrics or []
    if metrics_rows:
        lines = ["| Metric | Slice | Value | n |", "|--------|-------|------:|--:|"]
        for m in metrics_rows:
            lines.append(
                f"| {m.get('metric')} | {m.get('slice', 'all')} | "
                f"{m.get('value')} | {m.get('n', '')} |"
            )
        metrics_md = "\n".join(lines)
    else:
        metrics_md = "_no metrics attached_"

    text = (
        _env()
        .get_template("model_card.md.j2")
        .render(
            name=model.get("name"),
            revision=model.get("revision"),
            component=model.get("component"),
            base_model=model.get("base_model"),
            license=model.get("license"),
            owner=model.get("owner"),
            status=model.get("status"),
            artifact_uri=model.get("artifact_uri"),
            config_sha256=model.get("config_sha256"),
            mlflow_run_id=model.get("mlflow_run_id"),
            model_version_id=mid,
            intended_use=model.get("intended_use"),
            out_of_scope_use=model.get("out_of_scope_use"),
            training_data_md=training_data_md,
            evaluation_data_md=evaluation_data_md,
            metrics_md=metrics_md,
            limitations=limitations or [],
            changelog_md=changelog_md,
            generated_at=datetime.now(UTC).isoformat(),
        )
    )
    path.write_text(text, encoding="utf-8")
    return path


def card_is_complete(path: Path) -> bool:
    """Minimal completeness: required sections present and non-placeholder intended use."""
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    required = (
        "## Purpose and intended use",
        "## Component",
        "## Metrics",
        "## Safety and privacy",
        "## Monitoring plan",
    )
    if any(s not in text for s in required):
        return False
    purpose = text.split("## Purpose and intended use", 1)[1].split("##", 1)[0]
    return "_not specified_" not in purpose


def card_path_for(model_version_id: UUID, *, out_dir: Path | None = None) -> Path | None:
    root = out_dir or Path("docs/model_cards")
    if not root.is_dir():
        return None
    suffix = str(model_version_id)[:8]
    for path in root.glob(f"*-{suffix}.md"):
        return path
    return None


__all__ = ["card_is_complete", "card_path_for", "render_model_card"]
