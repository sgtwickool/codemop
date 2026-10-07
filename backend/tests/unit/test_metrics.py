"""
Tests that requests are recorded in the Prometheus metrics, labelled by route template.
"""
from prometheus_client import REGISTRY


def requests_recorded(endpoint: str, status_code: str, method: str = "GET") -> float:
    value = REGISTRY.get_sample_value(
        "codemop_requests_total",
        {"method": method, "endpoint": endpoint, "status_code": status_code},
    )
    return value or 0.0


def test_requests_are_counted(client):
    before = requests_recorded("/api/v1/health", "200")

    client.get("/api/v1/health")
    client.get("/api/v1/health")

    assert requests_recorded("/api/v1/health", "200") == before + 2


def test_requests_are_labelled_by_route_template_not_path(client):
    """Every PR mustn't become its own metric series."""
    template = "/api/v1/pr/{pr_id}/suggestions"
    before = requests_recorded(template, "401")

    client.get("/api/v1/pr/1/suggestions")
    client.get("/api/v1/pr/2/suggestions")

    assert requests_recorded(template, "401") == before + 2
    assert requests_recorded("/api/v1/pr/1/suggestions", "401") == 0


def test_unmatched_paths_share_one_label(client):
    before = requests_recorded("unmatched", "404")

    client.get("/does-not-exist")
    client.get("/wp-login.php")

    assert requests_recorded("unmatched", "404") == before + 2


def test_route_with_several_path_parameters(client):
    template = "/api/v1/repos/{owner}/{repo}/pulls/{number}/suggestions"
    before = requests_recorded(template, "401")

    client.get("/api/v1/repos/someone/something/pulls/3/suggestions")

    assert requests_recorded(template, "401") == before + 1
