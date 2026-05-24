# Agent instructions for Post Reach Backend

Purpose
- Quick reference for any automated agent contributing to this repository.
- Ensure tests, docs, and code conventions are followed when adding or modifying features.

Project layout (important paths)
- Django project directory (contains settings, WSGI/ASGI, and global Swagger/schema setup).
- App folders at the repository root — add new apps here as features are developed; do not hardcode app names in this doc.
- `*/services/` directories — Business logic lives in service classes (service-first pattern).
- `conftest.py` — pytest fixtures (common fixtures like `api_client`, `user`, `authenticated_client`, etc.).
- Tests: each app keeps tests nearby (for example `tests.py` or a `tests/` package inside the app).

Conventions
- Business logic: place in service modules under `*/services/`. Views/controllers should be thin and delegate to services.
- Service classes: use `*Service` named classes with staticmethods or instance methods for logic.
- External integrations: wrap third-party API calls in integration/service modules (e.g., `GoogleAuthService`) so they can be mocked in tests.
- Responses: use the project's response wrappers (`utils.responses.SuccessResponse` / `ErrorResponse` or legacy wrappers in `post_reach_bacend.responses`).

Testing rules
- Test framework: `pytest` + `pytest-django`. Use the fixtures in `conftest.py`.
- Test style: prefer plain `def test_...` functions with pytest fixtures for clarity and speed.
- Use pytest `class TestSomething:` only to group related tests; do not define `__init__` on test classes.
- Unit vs Integration:
  - Unit tests: add fast, focused tests for service logic under `users/services`, `social_accounts/services`, `integrations/services`. Put these in the app's `tests.py` or in a `tests/` module if you split files.
  - Integration tests: keep end-to-end API flow tests (like those in `users/tests.py`) to validate views + serializers + services together.
  - Testing pyramid: many unit tests, fewer integration tests, minimal end-to-end tests.
- DB access: mark tests that require DB using fixtures (`db`) or `pytest.mark.django_db` (already used in `users/tests.py`).
- Mocking: mock external services (HTTP calls, OAuth flows, third-party SDKs) using `mocker` or `monkeypatch`. Example: patch `users.views.GoogleAuthService` and set `verify_and_get_user_info.return_value`.
- Test checklist for any new feature:
  - Add unit tests for core logic in the service file.
  - Add integration test(s) for the public API surface (view/endpoint) demonstrating the feature works end-to-end.
  - Use fixtures where appropriate; avoid creating DB records in setup beyond necessary fixtures.

Swagger / API docs
- Project uses `drf_yasg` — see `post_reach_bacend/swagger.py` and `@swagger_auto_schema` usage in views.
- Requirement: every new or changed API endpoint must have a `swagger_auto_schema` annotation describing request/response serializers and operation summary/description.
- Update the global schema if you add new top-level API routes (register in `post_reach_bacend/swagger.py` or urls if required).

Pull request checklist for agents
- Code: follow the service-first pattern. Keep views thin.
- Tests: include unit tests (service) + at least one integration test (endpoint). Ensure tests run.
- Docs: add or update `swagger_auto_schema` on the modified/new view methods.
- Mock external calls in tests; do not call real external services in CI.
- Run `pytest -q` locally (or CI) and ensure no failures.

Examples
- Unit test (service):

    def test_register_with_password_creates_user():
        user = UserService.register_with_password(...)
        assert user.email == "SERVICE@example.com"

- Integration test (endpoint):

    def test_register_returns_user_and_tokens(api_client):
        response = api_client.post(reverse("register"), {...}, format="json")
        assert response.status_code == 201

- Mock external integration:

    def test_google_sign_in_mocks_google_service(api_client, mocker):
        google_service = mocker.patch("users.views.GoogleAuthService")
        google_service.return_value.verify_and_get_user_info.return_value = {...}
        response = api_client.post(reverse("google-sign-in"), {...}, format="json")
        assert response.status_code == 200

Notes for future agents
- If you add a new service file, also add focused unit tests for it immediately.
- Prefer `pytest` fixtures over class-level `setUp` unless compatibility requires `unittest.TestCase`.
- Keep responses consistent with the project's wrappers.

Contact
- If unsure about where to add tests or docs, open a short PR and request review.
