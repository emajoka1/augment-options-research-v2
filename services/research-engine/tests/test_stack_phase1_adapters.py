from ak_system.adapters.akshare_adapter import fetch_akshare_features
from ak_system.adapters.qlib_adapter import fetch_qlib_features
from ak_system.adapters.common import REQUIRED_KEYS


def _assert_schema(payload):
    for k in REQUIRED_KEYS:
        assert k in payload
    assert payload["asof_utc"]
    assert isinstance(payload["feature_set"], dict)
    assert isinstance(payload["quality_flags"], list)


def test_akshare_adapter_schema_keys_and_timestamp_non_null():
    payload = fetch_akshare_features("SPY")
    _assert_schema(payload)


def test_qlib_adapter_schema_keys_and_timestamp_non_null():
    payload = fetch_qlib_features("SPY")
    _assert_schema(payload)
