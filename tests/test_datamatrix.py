import zxingcpp

from app.services.datamatrix_service import (
    _parse_yymmdd,
    parse_gs1_datamatrix,
)


def test_parse_yymmdd():
    assert _parse_yymmdd("260831") == "2026-08-31"
    assert _parse_yymmdd("250228") == "2025-02-28"
    # day 00 -> last day of month
    assert _parse_yymmdd("260300") == "2026-03-31"
    assert _parse_yymmdd("invalid") is None

def test_parse_gs1_brackets():
    raw = "(01)04601234567890(21)ABC1234567890(17)261031(10)LOT9988(91)ABCD(92)CRYPTO=="
    res = parse_gs1_datamatrix(raw)
    assert res.is_valid_gs1 is True
    assert res.gtin == "04601234567890"
    assert res.ean13 == "4601234567890"
    assert res.serial == "ABC1234567890"
    assert res.expiry_date == "2026-10-31"
    assert res.lot_number == "LOT9988"
    assert res.crypto_key == "ABCD"
    assert res.crypto_signature == "CRYPTO=="

def test_parse_rf_pharma_stream_with_gs():
    # 01<14>21<13>\x1d91<4>\x1d92<44>
    raw = "010460555566667721SER1234567890\x1d91FF01\x1d92aBcDeFgHiJkLmNoPqRsTuVwXyZ1234567890abcdef=="
    res = parse_gs1_datamatrix(raw)
    assert res.is_valid_gs1 is True
    assert res.gtin == "04605555666677"
    assert res.ean13 == "4605555666677"
    assert res.serial == "SER1234567890"
    assert res.crypto_key == "FF01"

def test_parse_plain_ean13():
    res = parse_gs1_datamatrix("4601234567893")
    assert res.is_valid_gs1 is True
    assert res.ean13 == "4601234567893"
    assert res.gtin == "04601234567893"

def test_decode_datamatrix_from_generated_image():
    payload = "010460123456789021ABC1234567890\x1d17261231\x1d10LOT42"
    bc = zxingcpp.create_barcode(payload, zxingcpp.BarcodeFormat.DataMatrix)
    img = zxingcpp.write_barcode_to_image(bc)

    read_res = zxingcpp.read_barcode(img)
    assert read_res.text is not None
    assert "04601234567890" in read_res.text
