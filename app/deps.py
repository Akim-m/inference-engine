from config import make_redis

_client = None


def get_redis():
    global _client
    if _client is None:
        _client = make_redis()
    return _client
