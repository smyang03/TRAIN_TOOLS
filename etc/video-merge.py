#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
video_merger.py

두 영상을 좌우로 병합하는 도구.
- 각 영상을 미리보기하며 시작(in)/종료(out) 지점을 초 단위로 마킹
- 트림 후 좌우 hstack 결합
- 두 클립 길이가 다르면 짧은 쪽은 마지막 프레임 정지(freeze)로 채워 총 길이를 긴 쪽에 맞춤
- fps 정규화 없음 (hstack framesync 기본 동작에 위임)
- 오디오 없음

의존성:
  - Python 3.9+
  - PySide6      :  pip install PySide6
  - ffmpeg / ffprobe  : PATH 등록 또는 앱에서 경로 지정

렌더링(내부적으로 생성되는 ffmpeg 필터 형태):
  [0:v]trim=start=Sl:end=El,setpts=PTS-STARTPTS,scale=-2:H,tpad=stop_duration=Pl:stop_mode=clone[l];
  [1:v]trim=start=Sr:end=Er,setpts=PTS-STARTPTS,scale=-2:H,tpad=stop_duration=Pr:stop_mode=clone[r];
  [l][r]hstack=inputs=2[v]
  - H  = 두 영상 중 큰 높이(또는 수동 override)
  - Pl / Pr = maxDur - 해당 클립 길이 (긴 쪽은 0 -> tpad no-op)
"""

import os
import re
import sys
import json
import shutil
import subprocess

from PySide6.QtCore import Qt, QUrl, QThread, Signal, QStandardPaths
from PySide6.QtGui import QAction
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QSlider,
    QHBoxLayout, QVBoxLayout, QGridLayout, QFileDialog, QMessageBox,
    QProgressBar, QGroupBox, QLineEdit, QSizePolicy, QSpinBox, QCheckBox,
)


# --------------------------------------------------------------------------- #
#  ffmpeg / ffprobe 유틸
# --------------------------------------------------------------------------- #
def find_binary(name: str) -> str:
    """PATH에서 실행파일 탐색. 못 찾으면 빈 문자열."""
    path = shutil.which(name)
    return path or ""


def ffprobe_meta(ffprobe: str, filepath: str) -> dict:
    """
    영상의 duration(초), width, height 를 읽어 dict 반환.
    실패 시 예외를 그대로 올림 (호출부에서 처리).
    """
    cmd = [
        ffprobe, "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height:format=duration",
        "-of", "json",
        filepath,
    ]
    out = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8",
        creationflags=_no_window_flag(),
    )
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or "ffprobe 실패")

    data = json.loads(out.stdout)
    stream = (data.get("streams") or [{}])[0]
    fmt = data.get("format") or {}

    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    duration = float(fmt.get("duration") or 0.0)

    if width <= 0 or height <= 0 or duration <= 0:
        raise RuntimeError("영상 메타데이터를 읽지 못했습니다 (해상도/길이 0).")

    return {"width": width, "height": height, "duration": duration}


def _no_window_flag() -> int:
    """Windows에서 subprocess 콘솔창 안 뜨게."""
    if os.name == "nt":
        return subprocess.CREATE_NO_WINDOW
    return 0


def fmt_time(seconds: float) -> str:
    """초 -> HH:MM:SS.mmm 표시용."""
    if seconds < 0:
        seconds = 0
    ms = int(round((seconds - int(seconds)) * 1000))
    s = int(seconds)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


# --------------------------------------------------------------------------- #
#  렌더링 스레드 (ffmpeg -progress 파싱)
# --------------------------------------------------------------------------- #
class RenderWorker(QThread):
    progress = Signal(int)          # 0-100
    finished_ok = Signal(str)       # 출력 경로
    failed = Signal(str)            # 에러 메시지

    def __init__(self, ffmpeg, left, right, in_l, out_l, in_r, out_r,
                 height, out_path, parent=None):
        super().__init__(parent)
        self.ffmpeg = ffmpeg
        self.left = left
        self.right = right
        self.in_l, self.out_l = in_l, out_l
        self.in_r, self.out_r = in_r, out_r
        self.height = height
        self.out_path = out_path
        self._proc = None
        self._cancelled = False

    def cancel(self):
        self._cancelled = True
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass

    def build_cmd(self):
        dur_l = self.out_l - self.in_l
        dur_r = self.out_r - self.in_r
        max_dur = max(dur_l, dur_r)
        # 짧은 쪽만 채움. 긴 쪽은 0 -> tpad no-op
        pad_l = max(0.0, max_dur - dur_l)
        pad_r = max(0.0, max_dur - dur_r)
        H = self.height

        # 마지막 프레임 정지(freeze): stop_mode=clone
        filter_complex = (
            f"[0:v]trim=start={self.in_l:.6f}:end={self.out_l:.6f},"
            f"setpts=PTS-STARTPTS,scale=-2:{H},"
            f"tpad=stop_duration={pad_l:.6f}:stop_mode=clone[l];"
            f"[1:v]trim=start={self.in_r:.6f}:end={self.out_r:.6f},"
            f"setpts=PTS-STARTPTS,scale=-2:{H},"
            f"tpad=stop_duration={pad_r:.6f}:stop_mode=clone[r];"
            f"[l][r]hstack=inputs=2[v]"
        )

        cmd = [
            self.ffmpeg, "-y",
            "-i", self.left,
            "-i", self.right,
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-an",                       # 오디오 없음
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-crf", "18",
            "-preset", "medium",
            "-progress", "pipe:1",       # 진행률 stdout
            "-nostats",
            self.out_path,
        ]
        return cmd, max_dur

    def run(self):
        try:
            cmd, max_dur = self.build_cmd()
            total_us = max_dur * 1_000_000  # out_time_us 기준

            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,
                creationflags=_no_window_flag(),
            )

            # -progress 출력은 key=value 라인. out_time_us / progress=end 파싱
            for line in self._proc.stdout:
                if self._cancelled:
                    break
                line = line.strip()
                if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
                    try:
                        val = int(line.split("=", 1)[1])
                        # out_time_ms 는 실제로 마이크로초 단위로 나오는 버전이 있어
                        # out_time_us 를 우선 사용. 둘 다 us 스케일로 처리.
                        if total_us > 0:
                            pct = int(min(99, max(0, val / total_us * 100)))
                            self.progress.emit(pct)
                    except (ValueError, ZeroDivisionError):
                        pass
                elif line == "progress=end":
                    self.progress.emit(100)

            stderr = self._proc.stderr.read()
            ret = self._proc.wait()

            if self._cancelled:
                # 중간 산출물 정리
                if os.path.exists(self.out_path):
                    try:
                        os.remove(self.out_path)
                    except OSError:
                        pass
                self.failed.emit("렌더링이 취소되었습니다.")
                return

            if ret != 0:
                self.failed.emit(f"ffmpeg 오류 (code {ret}):\n{stderr.strip()[-1500:]}")
                return

            self.progress.emit(100)
            self.finished_ok.emit(self.out_path)

        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"렌더링 예외: {e}")


# --------------------------------------------------------------------------- #
#  단일 영상 프리뷰 + in/out 마킹 패널
# --------------------------------------------------------------------------- #
class VideoPanel(QGroupBox):
    """파일 열기 · 재생 · 시크 · 시작/종료 지점 마킹."""

    def __init__(self, title: str, ffprobe: str, parent=None):
        super().__init__(title, parent)
        self.ffprobe = ffprobe
        self.filepath = ""
        self.meta = None                # {"width","height","duration"}
        self.in_sec = 0.0
        self.out_sec = 0.0
        self._duration_ms = 0

        # --- 위젯 ---
        self.video = QVideoWidget()
        self.video.setMinimumSize(320, 200)
        self.video.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.player = QMediaPlayer(self)
        # 프리뷰용 오디오 (출력엔 안 들어가지만 마킹 시 참고). 볼륨 0 기본.
        self.audio_out = QAudioOutput(self)
        self.audio_out.setVolume(0.0)
        self.player.setAudioOutput(self.audio_out)
        self.player.setVideoOutput(self.video)
        self.player.positionChanged.connect(self._on_position)
        self.player.durationChanged.connect(self._on_duration)
        self.player.playbackStateChanged.connect(self._on_state)

        self.btn_open = QPushButton("파일 열기…")
        self.btn_open.clicked.connect(self.open_file)

        self.lbl_file = QLabel("(선택된 파일 없음)")
        self.lbl_file.setStyleSheet("color:#666;")
        self.lbl_file.setWordWrap(True)

        self.seek = QSlider(Qt.Horizontal)
        self.seek.setEnabled(False)
        self.seek.sliderMoved.connect(self._on_seek_moved)
        self.seek.sliderPressed.connect(lambda: setattr(self, "_seeking", True))
        self.seek.sliderReleased.connect(self._on_seek_released)
        self._seeking = False

        self.btn_play = QPushButton("▶")
        self.btn_play.setFixedWidth(44)
        self.btn_play.setEnabled(False)
        self.btn_play.clicked.connect(self.toggle_play)

        self.lbl_pos = QLabel("00:00:00.000 / 00:00:00.000")
        self.lbl_pos.setStyleSheet("font-family:monospace;")

        self.btn_set_in = QPushButton("⟬ 시작 지점")
        self.btn_set_out = QPushButton("종료 지점 ⟭")
        self.btn_set_in.setEnabled(False)
        self.btn_set_out.setEnabled(False)
        self.btn_set_in.clicked.connect(self.mark_in)
        self.btn_set_out.clicked.connect(self.mark_out)

        self.lbl_in = QLabel("in : —")
        self.lbl_out = QLabel("out: —")
        self.lbl_in.setStyleSheet("font-family:monospace; color:#1a7f37;")
        self.lbl_out.setStyleSheet("font-family:monospace; color:#b35900;")

        self.chk_mute = QCheckBox("프리뷰 음소거")
        self.chk_mute.setChecked(True)
        self.chk_mute.toggled.connect(
            lambda on: self.audio_out.setVolume(0.0 if on else 0.7)
        )

        # --- 레이아웃 ---
        top = QHBoxLayout()
        top.addWidget(self.btn_open)
        top.addWidget(self.lbl_file, 1)

        transport = QHBoxLayout()
        transport.addWidget(self.btn_play)
        transport.addWidget(self.seek, 1)
        transport.addWidget(self.chk_mute)

        marks = QHBoxLayout()
        marks.addWidget(self.btn_set_in)
        marks.addWidget(self.lbl_in, 1)
        marks.addWidget(self.lbl_out, 1)
        marks.addWidget(self.btn_set_out)

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.video, 1)
        lay.addLayout(transport)
        lay.addWidget(self.lbl_pos, alignment=Qt.AlignCenter)
        lay.addLayout(marks)

    # ---- 파일 로드 ----
    def open_file(self):
        start_dir = QStandardPaths.writableLocation(QStandardPaths.MoviesLocation) or ""
        path, _ = QFileDialog.getOpenFileName(
            self, "영상 선택", start_dir,
            "동영상 (*.mp4 *.mov *.avi *.mkv *.m4v *.webm *.flv);;모든 파일 (*.*)",
        )
        if not path:
            return

        # ffprobe로 메타 읽기
        if not self.ffprobe:
            QMessageBox.warning(self, "ffprobe 없음",
                                "ffprobe를 찾을 수 없습니다. 상단에서 ffmpeg 경로를 지정하세요.")
            return
        try:
            meta = ffprobe_meta(self.ffprobe, path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "메타 읽기 실패", str(e))
            return

        self.filepath = path
        self.meta = meta
        self.in_sec = 0.0
        self.out_sec = meta["duration"]

        self.player.setSource(QUrl.fromLocalFile(path))
        self.lbl_file.setText(
            f"{os.path.basename(path)}  "
            f"({meta['width']}×{meta['height']}, {fmt_time(meta['duration'])})"
        )
        self.lbl_file.setStyleSheet("color:#111;")
        self.seek.setEnabled(True)
        self.btn_play.setEnabled(True)
        self.btn_set_in.setEnabled(True)
        self.btn_set_out.setEnabled(True)
        self._refresh_mark_labels()

    # ---- 재생 제어 ----
    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _on_state(self, state):
        self.btn_play.setText("⏸" if state == QMediaPlayer.PlayingState else "▶")

    def _on_duration(self, dur_ms):
        self._duration_ms = dur_ms
        self.seek.setRange(0, dur_ms)

    def _on_position(self, pos_ms):
        if not self._seeking:
            self.seek.setValue(pos_ms)
        total = self._duration_ms / 1000.0 if self._duration_ms else (
            self.meta["duration"] if self.meta else 0.0)
        self.lbl_pos.setText(f"{fmt_time(pos_ms / 1000.0)} / {fmt_time(total)}")

    def _on_seek_moved(self, pos_ms):
        total = self._duration_ms / 1000.0 if self._duration_ms else 0.0
        self.lbl_pos.setText(f"{fmt_time(pos_ms / 1000.0)} / {fmt_time(total)}")

    def _on_seek_released(self):
        self._seeking = False
        self.player.setPosition(self.seek.value())

    # ---- in/out 마킹 ----
    def _current_sec(self) -> float:
        return self.player.position() / 1000.0

    def mark_in(self):
        cur = self._current_sec()
        if cur >= self.out_sec:
            QMessageBox.warning(self, "마킹 오류", "시작 지점이 종료 지점 이후입니다.")
            return
        self.in_sec = cur
        self._refresh_mark_labels()

    def mark_out(self):
        cur = self._current_sec()
        if cur <= self.in_sec:
            QMessageBox.warning(self, "마킹 오류", "종료 지점이 시작 지점 이전입니다.")
            return
        self.out_sec = cur
        self._refresh_mark_labels()

    def _refresh_mark_labels(self):
        self.lbl_in.setText(f"in : {fmt_time(self.in_sec)}")
        self.lbl_out.setText(
            f"out: {fmt_time(self.out_sec)}  (길이 {fmt_time(self.out_sec - self.in_sec)})"
        )

    # ---- 검증 ----
    def is_ready(self) -> bool:
        return bool(self.filepath and self.meta and self.out_sec > self.in_sec)


# --------------------------------------------------------------------------- #
#  메인 윈도우
# --------------------------------------------------------------------------- #
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("좌우 병합 도구 — Side-by-Side Video Merger")
        self.resize(1100, 720)

        self.ffmpeg = find_binary("ffmpeg")
        self.ffprobe = find_binary("ffprobe")
        self.worker = None

        # --- ffmpeg 경로 바 ---
        self.ed_ffmpeg = QLineEdit(self.ffmpeg)
        self.ed_ffmpeg.setPlaceholderText("ffmpeg 실행파일 경로")
        self.ed_ffprobe = QLineEdit(self.ffprobe)
        self.ed_ffprobe.setPlaceholderText("ffprobe 실행파일 경로")
        btn_ff = QPushButton("ffmpeg…")
        btn_fp = QPushButton("ffprobe…")
        btn_ff.clicked.connect(lambda: self._pick_binary(self.ed_ffmpeg))
        btn_fp.clicked.connect(lambda: self._pick_binary(self.ed_ffprobe))

        ff_bar = QHBoxLayout()
        ff_bar.addWidget(QLabel("ffmpeg:"))
        ff_bar.addWidget(self.ed_ffmpeg, 1)
        ff_bar.addWidget(btn_ff)
        ff_bar.addWidget(QLabel("ffprobe:"))
        ff_bar.addWidget(self.ed_ffprobe, 1)
        ff_bar.addWidget(btn_fp)

        # --- 좌/우 패널 ---
        self.panel_l = VideoPanel("좌측 영상 (LEFT)", self.ffprobe)
        self.panel_r = VideoPanel("우측 영상 (RIGHT)", self.ffprobe)
        panels = QHBoxLayout()
        panels.addWidget(self.panel_l, 1)
        panels.addWidget(self.panel_r, 1)

        # --- 출력 옵션 바 ---
        self.spin_h = QSpinBox()
        self.spin_h.setRange(0, 8192)
        self.spin_h.setSingleStep(2)
        self.spin_h.setValue(0)
        self.spin_h.setSpecialValueText("자동(큰 쪽)")
        self.spin_h.setSuffix(" px")

        self.ed_out = QLineEdit()
        self.ed_out.setPlaceholderText("출력 파일 경로 (.mp4)")
        btn_out = QPushButton("출력 파일…")
        btn_out.clicked.connect(self._pick_output)

        self.btn_merge = QPushButton("병합 실행")
        self.btn_merge.setStyleSheet("font-weight:bold; padding:6px 18px;")
        self.btn_merge.clicked.connect(self.run_merge)

        self.btn_cancel = QPushButton("취소")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.cancel_merge)

        out_bar = QHBoxLayout()
        out_bar.addWidget(QLabel("출력 높이:"))
        out_bar.addWidget(self.spin_h)
        out_bar.addSpacing(12)
        out_bar.addWidget(self.ed_out, 1)
        out_bar.addWidget(btn_out)
        out_bar.addWidget(self.btn_merge)
        out_bar.addWidget(self.btn_cancel)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setTextVisible(True)

        self.status = QLabel("준비됨. 좌/우 영상을 열고 in·out을 마킹하세요.")
        self.status.setStyleSheet("color:#444;")

        # --- 전체 레이아웃 ---
        central = QWidget()
        root = QVBoxLayout(central)
        root.addLayout(ff_bar)
        root.addLayout(panels, 1)
        root.addLayout(out_bar)
        root.addWidget(self.progress)
        root.addWidget(self.status)
        self.setCentralWidget(central)

        if not self.ffmpeg or not self.ffprobe:
            self.status.setText(
                "⚠ ffmpeg / ffprobe를 PATH에서 찾지 못했습니다. 상단에서 경로를 지정하세요."
            )

    # ---- 경로 선택 ----
    def _pick_binary(self, line_edit: QLineEdit):
        flt = "실행파일 (*.exe);;모든 파일 (*.*)" if os.name == "nt" else "모든 파일 (*.*)"
        path, _ = QFileDialog.getOpenFileName(self, "실행파일 선택", "", flt)
        if path:
            line_edit.setText(path)
            # 패널 ffprobe 갱신
            self.ffmpeg = self.ed_ffmpeg.text().strip()
            self.ffprobe = self.ed_ffprobe.text().strip()
            self.panel_l.ffprobe = self.ffprobe
            self.panel_r.ffprobe = self.ffprobe

    def _pick_output(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "출력 파일 저장", "merged.mp4", "MP4 (*.mp4)"
        )
        if path:
            if not path.lower().endswith(".mp4"):
                path += ".mp4"
            self.ed_out.setText(path)

    # ---- 병합 실행 ----
    def run_merge(self):
        self.ffmpeg = self.ed_ffmpeg.text().strip()
        self.ffprobe = self.ed_ffprobe.text().strip()

        if not self.ffmpeg or not os.path.exists(self.ffmpeg):
            QMessageBox.warning(self, "ffmpeg 없음", "유효한 ffmpeg 경로를 지정하세요.")
            return
        if not self.panel_l.is_ready() or not self.panel_r.is_ready():
            QMessageBox.warning(self, "입력 부족",
                                "좌/우 영상이 모두 열려 있고 in < out 인지 확인하세요.")
            return
        out_path = self.ed_out.text().strip()
        if not out_path:
            QMessageBox.warning(self, "출력 경로 없음", "출력 파일 경로를 지정하세요.")
            return

        # 출력 높이 결정
        h = self.spin_h.value()
        if h == 0:  # 자동
            h = max(self.panel_l.meta["height"], self.panel_r.meta["height"])
        if h % 2 != 0:  # yuv420p 호환 위해 짝수
            h += 1

        # 프리뷰 정지 (파일 핸들/디코더 충돌 방지)
        self.panel_l.player.pause()
        self.panel_r.player.pause()

        self.worker = RenderWorker(
            self.ffmpeg,
            self.panel_l.filepath, self.panel_r.filepath,
            self.panel_l.in_sec, self.panel_l.out_sec,
            self.panel_r.in_sec, self.panel_r.out_sec,
            h, out_path,
        )
        self.worker.progress.connect(self.progress.setValue)
        self.worker.finished_ok.connect(self._on_done)
        self.worker.failed.connect(self._on_fail)

        self._set_running(True)
        self.status.setText(f"렌더링 중… (출력 높이 {h}px)")
        self.progress.setValue(0)
        self.worker.start()

    def cancel_merge(self):
        if self.worker and self.worker.isRunning():
            self.status.setText("취소 요청 중…")
            self.worker.cancel()

    def _on_done(self, path):
        self._set_running(False)
        self.progress.setValue(100)
        self.status.setText(f"완료: {path}")
        QMessageBox.information(self, "완료", f"병합 완료:\n{path}")

    def _on_fail(self, msg):
        self._set_running(False)
        self.status.setText("실패/취소됨.")
        QMessageBox.critical(self, "렌더링 실패", msg)

    def _set_running(self, running: bool):
        self.btn_merge.setEnabled(not running)
        self.btn_cancel.setEnabled(running)
        self.panel_l.btn_open.setEnabled(not running)
        self.panel_r.btn_open.setEnabled(not running)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(3000)
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()