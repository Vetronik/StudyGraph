from collections import defaultdict
from threading import Lock


class HttpMetrics:
    """Small dependency-free metrics collector for the current process."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._requests: dict[tuple[str, str, int], int] = defaultdict(int)
        self._duration_seconds: dict[tuple[str, str], float] = defaultdict(float)

    def observe(
        self,
        *,
        method: str,
        route: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        with self._lock:
            self._requests[(method, route, status_code)] += 1
            self._duration_seconds[(method, route)] += duration_seconds

    def render_prometheus(self) -> str:
        lines = [
            "# HELP studygraph_http_requests_total HTTP requests handled.",
            "# TYPE studygraph_http_requests_total counter",
        ]
        with self._lock:
            requests = sorted(self._requests.items())
            durations = sorted(self._duration_seconds.items())

        for (method, route, status_code), count in requests:
            lines.append(
                "studygraph_http_requests_total{"
                f'method="{_escape_label(method)}",'
                f'route="{_escape_label(route)}",'
                f'status_code="{status_code}"}} {count}'
            )

        lines.extend(
            [
                "# HELP studygraph_http_request_duration_seconds "
                "Total request duration in seconds.",
                "# TYPE studygraph_http_request_duration_seconds counter",
            ]
        )
        for (method, route), duration in durations:
            lines.append(
                "studygraph_http_request_duration_seconds{"
                f'method="{_escape_label(method)}",'
                f'route="{_escape_label(route)}"}} {duration:.6f}'
            )
        return "\n".join(lines) + "\n"


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
