from studygraph.metrics import HttpMetrics


def test_http_metrics_render_prometheus_format() -> None:
    metrics = HttpMetrics()
    metrics.observe(
        method="GET",
        route="/documents/{document_id}",
        status_code=200,
        duration_seconds=0.25,
    )

    output = metrics.render_prometheus()

    assert "studygraph_http_requests_total" in output
    assert 'method="GET"' in output
    assert 'route="/documents/{document_id}"' in output
    assert "status_code=\"200\"} 1" in output
    assert "0.250000" in output
