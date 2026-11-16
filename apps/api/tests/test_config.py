from app.config import Settings


def test_public_app_origin_is_allowed_without_opening_vercel_previews():
    settings = Settings(
        _env_file=None,
        app_env="test",
        cors_origins="https://trusted.example",
    )

    assert "https://terravanta-five.vercel.app" in settings.allowed_origins
    assert "https://trusted.example" in settings.allowed_origins
    assert "https://preview-123.vercel.app" not in settings.allowed_origins
    assert "*" not in settings.allowed_origins


def test_public_app_origin_can_be_changed_explicitly():
    settings = Settings(
        _env_file=None,
        app_env="test",
        cors_origins="http://localhost:3000",
        public_app_origin="https://terravanta.example",
    )

    assert settings.allowed_origins == [
        "http://localhost:3000",
        "https://terravanta.example",
    ]


def test_development_does_not_allow_production_origin_by_default():
    settings = Settings(
        _env_file=None,
        app_env="development",
        cors_origins="http://localhost:3000",
    )

    assert settings.allowed_origins == ["http://localhost:3000"]


def test_vercel_production_origin_passes_api_preflight(client):
    response = client.options(
        "/api/v1/auth/request-access-code",
        headers={
            "Origin": "https://terravanta-five.vercel.app",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://terravanta-five.vercel.app"
