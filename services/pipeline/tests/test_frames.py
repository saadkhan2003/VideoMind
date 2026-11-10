from pipeline.media import clamp_timestamp, grab_frame, probe_duration, seek_candidates
from pipeline.scenes import keyframe_times
from pipeline.tests.ffmpeg_util import tiny_mp4


def test_hufsky_eof_timestamp_is_clamped():
    # The cloud run asked ffmpeg for 30.050s of a 30.10s file and the mjpeg
    # encoder died. The seek has to land at least EOF_MARGIN_S before the end.
    assert clamp_timestamp(30.05, 30.10) == 29.85
    assert seek_candidates(30.05, 30.10) == [29.85, 29.35, 28.85, 0.0]
    times = keyframe_times([(29.9, 30.10)], 30.10, every=0)
    assert times == [29.85]
    assert all(30.10 - ts >= 0.25 - 1e-9 for ts in times)


def test_bucket_near_eof_is_clamped():
    times = keyframe_times([(0.0, 30.10)], 30.10, every=30.0)
    assert 30.05 not in times
    assert 29.85 in times
    assert 15.05 in times


def test_grab_near_eof_falls_back_to_an_earlier_frame(tmp_path, monkeypatch):
    calls = []

    def fake_run(cmd):
        timestamp = cmd[cmd.index("-ss") + 1]
        calls.append(timestamp)
        dest = cmd[-1]
        if timestamp == "29.850":
            from pipeline.media import MediaError

            raise MediaError("me_thread_encoder_init failed")
        from pathlib import Path

        Path(dest).write_bytes(b"\xff\xd8\xff\xd9")

    monkeypatch.setattr("pipeline.media._run", fake_run)
    dest = tmp_path / "frame.jpg"
    grab_frame(tmp_path / "clip.ogv", 30.05, dest, duration=30.10)
    assert calls == ["29.850", "29.350"]
    assert dest.read_bytes().startswith(b"\xff\xd8")


def test_grab_frame_near_eof_writes_a_jpeg(tmp_path):
    video = tiny_mp4(tmp_path / "clip.mp4", seconds=1.2)
    duration = probe_duration(video)
    dest = tmp_path / "frame.jpg"
    grab_frame(video, duration - 0.05, dest, duration=duration)
    assert dest.read_bytes()[:2] == b"\xff\xd8"
