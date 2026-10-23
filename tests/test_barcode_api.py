import base64
import shutil
import subprocess
import pytest
from flask import Flask
from app.routes.barcode import BARCODE_TYPES, create_blueprint


@pytest.fixture
def client():
    app = Flask(__name__)
    barcode_bp, url_prefix = create_blueprint()
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


def test_generate_code128_with_overrides(client):
    """Should apply URL parameter overrides."""
    response = client.get(
        "/barcode",
        query_string={
            "data": "TEST123",
            "type": "code128",
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


def _raw_png(client, **params):
    response = client.get("/barcode", query_string={"data": "123456", "raw": "true", **params})
    assert response.status_code == 200
    return response.data


def test_text_param_replaces_caption(client):
    """A custom caption changes the image; without text shown it is ignored."""
    default = _raw_png(client)
    assert _raw_png(client, text="HELLO") != default
    assert _raw_png(client, text="HELLO", write_text="false") == _raw_png(client, write_text="false")


@pytest.mark.parametrize("barcode_type", list(BARCODE_TYPES))
def test_every_type_renders_its_example(client, barcode_type):
    """The example shown in the UI and docs must be valid for its type."""
    response = client.get("/barcode", query_string={
        "type": barcode_type, "data": BARCODE_TYPES[barcode_type]["example"],
    })
    assert response.status_code == 200, response.get_json()
    json_data = response.get_json()
    assert json_data["barcode_type"] == barcode_type
    assert json_data["encoded"]


@pytest.mark.parametrize("barcode_type, data", [
    ("ean13", "12345"),         # NumberOfDigitsError
    ("ean13", "abcdefghijkl"),  # IllegalCharacterError
    ("jan", "abc"),             # bare ValueError from int()
    ("code39", "bad!"),         # KeyError for the unknown character
    ("codabar", "12345"),       # missing start/stop letters
    ("code128", "héllo"),       # outside ASCII
])
def test_invalid_data_is_a_400(client, barcode_type, data):
    response = client.get("/barcode", query_string={"type": barcode_type, "data": data})
    assert response.status_code == 400
    assert response.get_json()["error"].startswith(
        f"Invalid data for {BARCODE_TYPES[barcode_type]['label']}:"
    )


def test_type_aliases(client):
    response = client.get("/barcode", query_string={"type": "UPC", "data": "03600029145"})
    assert response.status_code == 200
    assert response.get_json()["barcode_type"] == "upca"


@pytest.mark.parametrize("barcode_type, data, module_width, shrinks", [
    ("ean13-guard", "590123412345", 0.2, True),   # 6-digit blocks wider than the guard gap
    ("ean8-guard", "9638507", 0.2, True),
    ("ean13", "590123412345", 0.2, True),         # caption wider than the image
    ("ean13-guard", "590123412345", 0.4, False),  # wide modules leave room
    ("code128", "CODE128", 0.2, False),
])
def test_caption_is_shrunk_only_when_it_does_not_fit(barcode_type, data, module_width, shrinks):
    import barcode as python_barcode
    from barcode.writer import ImageWriter
    from app.routes.barcode import BarcodeAPI

    instance = python_barcode.get_barcode_class(barcode_type)(data, writer=ImageWriter())
    options = {**BarcodeAPI.DEFAULT_OPTIONS, "module_width": module_width,
               "font_path": BarcodeAPI._resolve_font_path("fonts/typo-round-bold.ttf")}
    size = BarcodeAPI._fit_font_size(instance, barcode_type, options, instance.get_fullcode())
    assert (size < options["font_size"]) == shrinks


@pytest.mark.parametrize("barcode_type, data", [("ean13-guard", "590123412345"), ("ean8-guard", "9638507")])
def test_guard_caption_sits_below_the_bars(client, barcode_type, data):
    """python-barcode puts guard captions flush against the bars; ours leave a gap."""
    import io
    from PIL import Image

    png = _raw_png(client, type=barcode_type, data=data, dpi="600")
    im = Image.open(io.BytesIO(png)).convert("L")
    w, h = im.size
    dark = lambda x, y: im.getpixel((x, y)) < 128

    row = int(h * 0.3)  # inside the bars
    bar_bottoms = {}
    for x in range(w):
        if dark(x, row):
            y = row
            while y < h and dark(x, y):
                y += 1
            bar_bottoms[x] = y
    text_top = min(y for y in range(row, h) for x in range(w) if x not in bar_bottoms and dark(x, y))
    assert text_top - min(bar_bottoms.values()) > 20  # px at 600 dpi, about 1 mm


# What a scanner should read back from each type's example (zbar reports
# UPC-A, JAN and the ISBN/ISSN forms as the EAN-13 they are encoded as).
EXPECTED_SCANS = {
    "code128": "CODE-128:CODE128",
    "gs1_128": "CODE-128:0101234567890128",
    "code39": "CODE-39:TEST-39J",
    "codabar": "Codabar:A40156B",
    "itf": "I2/5:1234567890",
    "ean13": "EAN-13:5901234123457",
    "ean13-guard": "EAN-13:5901234123457",
    "ean8": "EAN-8:96385074",
    "ean8-guard": "EAN-8:96385074",
    "ean14": "I2/5:12345678901231",
    "upca": "EAN-13:0036000291452",
    "jan": "EAN-13:4901234567894",
    "isbn13": "EAN-13:9783161484100",
    "isbn10": "EAN-13:9783161484100",
    "issn": "EAN-13:9770317847001",
    "pzn": "CODE-39:PZN-1234562",
}


@pytest.mark.skipif(not shutil.which("zbarimg"), reason="zbarimg (zbar) not installed")
@pytest.mark.parametrize("barcode_type", list(BARCODE_TYPES))
def test_every_type_scans(client, tmp_path, barcode_type):
    """Decode the rendered image with a real barcode reader at default settings."""
    path = tmp_path / "barcode.png"
    path.write_bytes(_raw_png(client, type=barcode_type, data=BARCODE_TYPES[barcode_type]["example"]))
    result = subprocess.run(["zbarimg", "--quiet", str(path)], capture_output=True, text=True)
    assert result.stdout.strip() == EXPECTED_SCANS[barcode_type]


@pytest.mark.parametrize("barcode_type, data, ok", [
    ("ean13", "5053319639404", True),
    ("ean13", "5053319639401", False),   # wrong check digit is rejected, not replaced
    ("isbn10", "3-16-148410-X", True),
    ("isbn10", "3-16-148410-5", False),
    ("issn", "0317-8471", True),
    ("issn", "0317-8472", False),
    ("ean14", "12345678901231", True),
    ("ean14", "12345678901230", False),
])
def test_check_digits(client, barcode_type, data, ok):
    response = client.get("/barcode", query_string={"type": barcode_type, "data": data})
    assert (response.status_code == 200) == ok, response.get_json()
    if not ok:
        assert "check digit should be" in response.get_json()["error"]
