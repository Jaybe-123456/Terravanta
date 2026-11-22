import pytest

from app.config import Settings
from app.main import app


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
        "/api/v1/auth/onboard",
        headers={
            "Origin": "https://terravanta-five.vercel.app",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://terravanta-five.vercel.app"


def test_email_code_auth_routes_are_removed_from_public_api():
    paths = app.openapi()["paths"]
    assert "/api/v1/auth/request-access-code" not in paths
    assert "/api/v1/auth/access-code-login" not in paths
    assert "/api/v1/auth/onboard" in paths


def test_enabled_whatsapp_sender_requires_complete_configuration_on_api_and_worker():
    common = {
        "_env_file": None,
        "app_env": "test",
        "meta_wa_send_enabled": True,
        "meta_wa_access_token": "test-token",
        "meta_wa_phone_number_id": "test-phone-id",
        "meta_wa_graph_api_version": "v22.0",
        "meta_wa_notification_template": "vet_contact_update",
    }

    api_settings = Settings(**common, service_mode="api")
    assert api_settings.whatsapp_delivery_configured is True

    with pytest.raises(ValueError, match="WHATSAPP_WORKER_DATABASE_URL"):
        Settings(**common, service_mode="worker")

    with pytest.raises(ValueError, match="META_WA_ACCESS_TOKEN"):
        Settings(
            **{**common, "meta_wa_access_token": ""},
            service_mode="api",
        )

    with pytest.raises(ValueError, match="META_WA_GRAPH_API_VERSION"):
        Settings(
            **{**common, "meta_wa_graph_api_version": "latest"},
            service_mode="api",
        )
