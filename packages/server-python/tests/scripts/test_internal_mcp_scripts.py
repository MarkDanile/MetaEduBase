"""Contract checks for REQ-046 operational scripts."""
from __future__ import annotations

from tests.scripts._script_loader import load_server_script

register_script = load_server_script("register_internal_mcp")
upload_script = load_server_script("upload_park_datasets")
_request = register_script._request
WORKBOOKS = upload_script.WORKBOOKS


def test_upload_manifest_maps_all_park_workbooks():
    assert WORKBOOKS["05_客户.xlsx"] == "customer"
    assert WORKBOOKS["06_合同_基本信息.xlsx"] == "contract"
    assert WORKBOOKS["13_客户_合作跟进记录_待审核.xlsx"] == "cooperation_note"
    assert len(WORKBOOKS) == 13


def test_registration_request_helper_is_importable():
    assert callable(_request)
