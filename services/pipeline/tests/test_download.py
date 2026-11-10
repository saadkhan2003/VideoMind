import httpx
import pytest

from pipeline.download import USER_AGENT, download_file


def test_wikimedia_user_agent_and_retry_after_403(tmp_path):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["user-agent"])
        if len(seen) == 1:
            return httpx.Response(403, text="denied")
        return httpx.Response(200, content=b"ogv-bytes")

    sleeps = []
    dest = tmp_path / "clip.ogv"
    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        download_file(
            "https://upload.wikimedia.org/wikipedia/commons/example.ogv",
            dest,
            attempts=3,
            backoff_s=0.5,
            sleep=sleeps.append,
            client=client,
        )

    assert seen == [USER_AGENT, USER_AGENT]
    assert "VideoMind/0.1" in USER_AGENT
    assert "https://github.com/saadkhan2003" in USER_AGENT
    assert sleeps == [0.5]
    assert dest.read_bytes() == b"ogv-bytes"
    assert not (tmp_path / "clip.ogv.part").exists()


def test_download_stops_after_the_last_403(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="denied")

    sleeps = []
    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        with pytest.raises(httpx.HTTPStatusError):
            download_file(
                "https://upload.wikimedia.org/example.ogv",
                tmp_path / "clip.ogv",
                attempts=2,
                backoff_s=0.25,
                sleep=sleeps.append,
                client=client,
            )
    assert sleeps == [0.25]
    assert not (tmp_path / "clip.ogv").exists()
