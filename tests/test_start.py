import pytest
from unittest.mock import MagicMock, patch
from worker.start import wait_for_vllm


def test_wait_for_vllm_returns_when_healthy():
    ok = MagicMock()
    ok.status_code = 200
    with patch("worker.start.httpx.get", return_value=ok) as mock_get:
        wait_for_vllm("http://vllm:8001/v1", retries=3, delay=0.0)
    called_url = mock_get.call_args.args[0]
    assert called_url == "http://vllm:8001/health"


def test_wait_for_vllm_raises_after_retries():
    with patch("worker.start.httpx.get", side_effect=Exception("boom")), \
         patch("worker.start.time.sleep"):
        with pytest.raises(RuntimeError):
            wait_for_vllm("http://vllm:8001/v1", retries=2, delay=0.0)


def test_main_single_replica_runs_one_worker_no_pool():
    from worker import start
    with patch("worker.start.wait_for_vllm"), \
         patch("worker.start._run_single_worker") as single, \
         patch("worker.start.Process") as proc:
        start.main(replicas=1)
    single.assert_called_once()
    proc.assert_not_called()


def test_main_spawns_n_replica_processes():
    from worker import start
    inst = MagicMock()
    with patch("worker.start.wait_for_vllm"), \
         patch("worker.start.Process", return_value=inst) as proc:
        start.main(replicas=3)
    assert proc.call_count == 3
    assert inst.start.call_count == 3
    assert inst.join.call_count == 3
