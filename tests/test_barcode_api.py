import base64
import pytest
from flask import Flask
from routes.barcode import barcode_bp, url_prefix


@pytest.fixture
def client():
    app = Flask(__name__)
    app.register_blueprint(barcode_bp, url_prefix=url_prefix)
    with app.test_client() as client:
        yield client


def test_generate_code128_json(client):
    """Should return a valid JSON response with base64 barcode."""
    response = client.get(
        "/barcode",
        query_string={"data": "123456789012", "type": "code128"}
    )
    assert response.status_code == 200
    json_data = response.get_json()
    assert "barcode" in json_data
    assert json_data["barcode"].startswith("data:image/png;base64,")
    base64_str = json_data["barcode"].split(",")[1]
    img_bytes = base64.b64decode(base64_str)
    assert img_bytes.startswith(b"\x89PNG")  # PNG header


def test_generate_code128_raw(client):
    """Should return raw PNG image when raw=true."""
    response = client.get(
        "/barcode",
        query_string={"data": "123456789012", "type": "code128", "raw": "true"}
    )
    assert response.status_code == 200
    assert response.content_type == "image/png"
    assert response.data.startswith(b"\x89PNG")  # PNG header


def test_generate_ean13_with_overrides(client):
    """Should apply URL parameter overrides."""
    response = client.get(
        "/barcode",
        query_string={
            "data": "123456789012",
            "type": "ean13",
            "module_width": "0.6",
            "foreground": "red",
            "uppercase": "true"
        }
    )
    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["options"]["module_width"] == 0.6
    assert json_data["options"]["foreground"] == "red"


def test_override_font_path(client):
    """Should override default font path via URL parameter."""
    response = client.get(
        "/barcode",
        query_string={
            "data": "123456789012",
            "type": "code128",
            "font_path": "fonts/typo-round-bold.ttf"
        }
    )
    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["options"]["font_path"] == "fonts/typo-round-bold.ttf"


def test_missing_data_param(client):
    """Should return 400 if data parameter is missing."""
    response = client.get("/barcode", query_string={"type": "code128"})
    assert response.status_code == 400
    json_data = response.get_json()
    assert json_data["status"] == "error"


def test_invalid_barcode_format(client):
    """Should return 400 for unsupported format."""
    response = client.get("/barcode", query_string={"data": "123", "type": "fakeformat"})
    assert response.status_code == 400
    json_data = response.get_json()
    assert "Unsupported barcode format" in json_data["error"]
