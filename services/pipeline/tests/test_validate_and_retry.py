import pytest

from pipeline.orchestrator import run_with_retry
from pipeline.ray_runner import DAG, ray_available
from pipeline.scenes import drop_similar, keyframe_times
from pipeline.validate import UploadRejected, assert_upload_allowed


def test_rejects_non_video_and_a_ten_gigabyte_upload():
    with pytest.raises(UploadRejected) as bad:
        assert_upload_allowed(filename="notes.txt", size=10, max_bytes=100)
    assert bad.value.code == "bad_type"
    ten_gb = 10 * 1024**3
    with pytest.raises(UploadRejected) as huge:
        assert_upload_allowed(filename="lecture.mp4", size=ten_gb, max_bytes=2 * 1024**3)
    assert huge.value.code == "too_large"
    assert huge.value.status == 413
    with pytest.raises(UploadRejected) as long:
        assert_upload_allowed(
            filename="lecture.mp4",
            size=100,
            max_bytes=1000,
            duration=50_000,
            max_seconds=4 * 3600,
        )
    assert long.value.code == "too_long"


def test_retry_succeeds_after_two_failures():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("not yet")
        return "ok"

    assert run_with_retry(flaky, attempts=3, base_delay=0.0) == "ok"
    assert calls["n"] == 3


def test_retry_gives_up():
    def always():
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError, match="nope"):
        run_with_retry(always, attempts=2, base_delay=0.0)


def test_keyframe_schedule_fills_empty_buckets_and_drops_duplicates():
    times = keyframe_times([(0.0, 4.0)], duration=4.0, every=1.0)
    assert times
    assert all(0 <= t <= 4 for t in times)
    assert any(t < 1 for t in times)

    class Hash:
        def __init__(self, n):
            self.n = n

        def __sub__(self, other):
            return abs(self.n - other.n)

    kept = drop_similar([(0.0, Hash(1)), (1.0, Hash(1)), (2.0, Hash(9))], threshold=2)
    assert [item[0] for item in kept] == [0.0, 2.0]


def test_ray_dag_is_declared_and_import_does_not_require_ray():
    assert DAG[0] == "extract_audio"
    assert DAG[-1] == "upsert"
    assert ray_available() in (True, False)
