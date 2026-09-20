import pytest
from prometheus_client import REGISTRY

from callscope.observability import metrics

pytestmark = pytest.mark.unit


def test_stage_latency_records_sample() -> None:
    before = (
        REGISTRY.get_sample_value("callscope_stage_latency_seconds_count", {"stage": "asr_final"})
        or 0.0
    )
    metrics.observe_stage("asr_final", 0.12)
    after = REGISTRY.get_sample_value(
        "callscope_stage_latency_seconds_count", {"stage": "asr_final"}
    )
    assert after == before + 1


def test_latency_buckets_cover_nfr_targets() -> None:
    assert 1.5 in metrics.LATENCY_BUCKETS
    assert 2.5 in metrics.LATENCY_BUCKETS
