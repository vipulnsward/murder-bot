"""Low-latency HLS stream manager for the BlueStacks emulator."""

from __future__ import annotations

from collections import deque
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
from typing import Any


class HLSStreamManager:
    """Keep ffmpeg alive while cycling screenrecord before its 180s limit."""

    def __init__(self, device: str = "127.0.0.1:5555") -> None:
        self.device = device
        self.output_dir = Path(tempfile.mkdtemp(prefix="keep-hls-"))
        # Shared frame: the SAME ffmpeg also writes a fresh JPEG here so the mapper
        # can read frames without a second adb capture (one screenrecord, two consumers).
        self.frame_path = Path(__file__).resolve().parents[1] / "game_brain" / "live" / "latest.jpg"
        self.frame_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None
        self._screenrecord: subprocess.Popen[bytes] | None = None
        self._ffmpeg: subprocess.Popen[bytes] | None = None
        self._logs: deque[str] = deque(maxlen=200)
        self._fps_line: str | None = None
        self._error: str | None = None
        self._restarts = 0
        self._last_screenrecord_pid: int | None = None
        self._last_ffmpeg_pid: int | None = None
        self._last_screenrecord_returncode: int | None = None
        self._last_ffmpeg_returncode: int | None = None

    def start_hls(self) -> dict[str, Any]:
        with self._lock:
            if self._worker and self._worker.is_alive():
                return self.status()
            self._signal_remote_screenrecord("-9")
            for path in self.output_dir.iterdir():
                if path.is_file():
                    path.unlink()
            self._stop.clear()
            self._logs.clear()
            self._fps_line = None
            self._error = None
            self._restarts = 0
            self._worker = threading.Thread(target=self._run, name="keep-hls", daemon=True)
            self._worker.start()
            return self.status()

    def stop_hls(self) -> dict[str, Any]:
        with self._lock:
            self._stop.set()
            worker = self._worker
            screenrecord = self._screenrecord
            ffmpeg = self._ffmpeg
        self._stop_screenrecord(screenrecord)
        self._terminate(ffmpeg)
        if worker:
            worker.join(timeout=10)
        with self._lock:
            if worker and worker.is_alive():
                self._error = "stream worker did not exit"
            return self.status()

    def status(self) -> dict[str, Any]:
        with self._lock:
            worker_alive = bool(self._worker and self._worker.is_alive())
            screenrecord_alive = bool(self._screenrecord and self._screenrecord.poll() is None)
            ffmpeg_alive = bool(self._ffmpeg and self._ffmpeg.poll() is None)
            return {
                "running": worker_alive and ffmpeg_alive and not self._stop.is_set(),
                "ready": (self.output_dir / "stream.m3u8").is_file(),
                "owns_adb": worker_alive and not self._stop.is_set(),
                "device": self.device,
                "output_dir": str(self.output_dir),
                "screenrecord_pid": self._screenrecord.pid if screenrecord_alive else None,
                "ffmpeg_pid": self._ffmpeg.pid if ffmpeg_alive else None,
                "worker_alive": worker_alive,
                "screenrecord_alive": screenrecord_alive,
                "ffmpeg_alive": ffmpeg_alive,
                "last_screenrecord_pid": self._last_screenrecord_pid,
                "last_ffmpeg_pid": self._last_ffmpeg_pid,
                "last_screenrecord_returncode": self._last_screenrecord_returncode,
                "last_ffmpeg_returncode": self._last_ffmpeg_returncode,
                "screenrecord_restarts": self._restarts,
                "fps_line": self._fps_line,
                "segment_duration_s": 1,
                "error": self._error,
            }

    def close(self) -> None:
        self.stop_hls()
        shutil.rmtree(self.output_dir, ignore_errors=True)

    def _run(self) -> None:
        ffmpeg: subprocess.Popen[bytes] | None = None
        try:
            ffmpeg = subprocess.Popen(
                self._ffmpeg_command(),
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                bufsize=0,
            )
            with self._lock:
                self._ffmpeg = ffmpeg
                self._last_ffmpeg_pid = ffmpeg.pid
            threading.Thread(target=self._read_ffmpeg_log, args=(ffmpeg,), daemon=True).start()

            while not self._stop.is_set() and ffmpeg.poll() is None:
                screenrecord = subprocess.Popen(
                    self._screenrecord_command(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    bufsize=0,
                )
                with self._lock:
                    self._screenrecord = screenrecord
                    self._last_screenrecord_pid = screenrecord.pid
                assert screenrecord.stdout is not None and ffmpeg.stdin is not None
                try:
                    while not self._stop.is_set():
                        chunk = screenrecord.stdout.read(1024 * 1024)
                        if not chunk:
                            break
                        ffmpeg.stdin.write(chunk)
                except BrokenPipeError:
                    self._error = "ffmpeg stopped accepting video"
                    break
                finally:
                    self._terminate(screenrecord)
                    with self._lock:
                        self._last_screenrecord_returncode = screenrecord.returncode
                        self._screenrecord = None
                if not self._stop.is_set() and ffmpeg.poll() is None:
                    self._restarts += 1
                    self._stop.wait(0.1)
        except (OSError, subprocess.SubprocessError) as error:
            self._error = str(error)
        finally:
            if ffmpeg and ffmpeg.stdin:
                try:
                    ffmpeg.stdin.close()
                except BrokenPipeError:
                    pass
            self._terminate(ffmpeg)
            with self._lock:
                if ffmpeg:
                    self._last_ffmpeg_returncode = ffmpeg.returncode
                self._ffmpeg = None
                self._screenrecord = None

    def _read_ffmpeg_log(self, ffmpeg: subprocess.Popen[bytes]) -> None:
        assert ffmpeg.stderr is not None
        for raw in iter(ffmpeg.stderr.readline, b""):
            line = raw.decode(errors="replace").strip()
            if line:
                with self._lock:
                    self._logs.append(line)
                    if "Stream #0:0: Video:" in line and "fps" in line and self._fps_line is None:
                        self._fps_line = line

    def _screenrecord_command(self) -> list[str]:
        return [
            "adb", "-s", self.device, "exec-out", "screenrecord",
            "--output-format=h264", "--size", "1080x1920",
            "--bit-rate", "8000000", "--time-limit", "175", "-",
        ]

    def _stop_screenrecord(self, process: subprocess.Popen[bytes] | None) -> None:
        self._signal_remote_screenrecord("-2")
        if process and process.poll() is None:
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self._terminate(process)
        self._signal_remote_screenrecord("-9")

    def _signal_remote_screenrecord(self, signal: str) -> None:
        try:
            subprocess.run(
                [
                    "adb", "-s", self.device, "shell", "pkill", signal, "-f",
                    "screenrecord.*--bit-rate 8000000",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            pass

    def _ffmpeg_command(self) -> list[str]:
        playlist = self.output_dir / "stream.m3u8"
        segments = self.output_dir / "segment_%06d.ts"
        return [
            "ffmpeg", "-hide_banner", "-loglevel", "info",
            "-fflags", "+genpts", "-r", "60", "-f", "h264", "-i", "pipe:0",
            # HLS output: downscale 1080p capture -> 720p for browser bandwidth
            "-map", "0:v:0", "-vf", "scale=720:1280",
            "-an", "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
            "-profile:v", "baseline", "-b:v", "8000000", "-maxrate", "8000000",
            "-bufsize", "4000000", "-g", "60", "-keyint_min", "60",
            "-sc_threshold", "0", "-bf", "0", "-pix_fmt", "yuv420p",
            "-f", "hls", "-hls_time", "1", "-hls_list_size", "4",
            "-hls_flags", "delete_segments+omit_endlist+independent_segments",
            "-hls_segment_type", "mpegts", "-hls_segment_filename", str(segments),
            str(playlist),
            # 2nd output from the same decoded input: a fresh native-1080p JPEG for the
            # mapper's OCR (real detail; coords already == device space).
            "-map", "0:v:0", "-vf", "fps=8", "-q:v", "3", "-update", "1",
            "-atomic_writing", "1", "-y", str(self.frame_path),
        ]

    def latest_frame_bytes(self) -> bytes | None:
        """The most recent shared JPEG frame (written by the HLS ffmpeg), or None."""
        try:
            if self.frame_path.is_file():
                return self.frame_path.read_bytes()
        except OSError:
            return None
        return None

    @staticmethod
    def _terminate(process: subprocess.Popen[bytes] | None) -> None:
        if not process or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
