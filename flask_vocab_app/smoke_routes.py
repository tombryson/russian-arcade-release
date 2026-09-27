"""Smoke-check the Flask app without starting a browser or external services."""

from app import create_app


ROUTES = [
    ("/", {}),
    ("/metrics", {}),
    ("/vocab", {}),
    ("/comprehension", {}),
    ("/writing", {}),
    ("/lessons", {}),
    ("/word_jumble", {}),
    ("/sentences", {}),
    ("/sentences/saved", {}),
    ("/user/stats", {"HX-Request": "true"}),
    ("/vocab", {"HX-Request": "true", "HX-Target": "mainContent"}),
]


def main():
    client = create_app().test_client()
    failures = []

    for path, headers in ROUTES:
        response = client.get(path, headers=headers)
        print(
            f"{path:18} {response.status_code:3} "
            f"{response.content_type:32} {len(response.get_data()):7}"
        )
        if response.status_code >= 400:
            failures.append((path, response.status_code))

    if failures:
        failed = ", ".join(f"{path}={status}" for path, status in failures)
        raise SystemExit(f"Smoke check failed: {failed}")


if __name__ == "__main__":
    main()
