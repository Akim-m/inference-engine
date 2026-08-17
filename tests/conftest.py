import os
from pathlib import Path
import fakeredis
import pytest

# Suppresses duplicate OpenMP runtime abort on Windows (numpy + torch conflict)
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")


@pytest.fixture
def fake_redis():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def valid_key():
    return "test-api-key-32-bytes-long-abcdef"


@pytest.fixture
def valid_key_hash(valid_key):
    from app.auth import hash_key
    return hash_key(valid_key)


@pytest.fixture
def seeded_redis(fake_redis, valid_key_hash):
    fake_redis.sadd("api_keys", valid_key_hash)
    return fake_redis


@pytest.fixture
def sample_jpeg():
    # Minimal valid JPEG (1x1 pixel)
    return (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c"
        b"\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c"
        b"\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\x1e!\x19!\x17\x00"
        b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00"
        b"\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00"
        b"\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b"
        b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xf5\x00\xff\xd9"
    )


@pytest.fixture
def sample_dicom():
    # A real (uncompressed) DICOM CT slice bundled with pydicom — decodes with numpy
    # alone, no extra codec. Skips cleanly if pydicom isn't installed in this env.
    pydicom = pytest.importorskip("pydicom")
    from pydicom.data import get_testdata_file
    return Path(get_testdata_file("CT_small.dcm")).read_bytes()
