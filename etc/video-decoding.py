# video_roi_extractor.py
# 동영상 타임라인 탐색 + 구간(In/Out) × ROI 크롭 추출 도구
# 의존성: pip install PyQt5 opencv-python numpy

import sys
import os
import cv2
import numpy as np
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QSlider,
    QHBoxLayout, QVBoxLayout, QFileDialog, QMessageBox, QProgressBar
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QRect, QPoint
from PyQt5.QtGui import QImage, QPainter, QColor, QPen


# ----------------------------------------------------------------------
# 프레임 표시 + 마우스 ROI 지정 위젯
#   - 프레임은 종횡비 유지 레터박스로 스케일 표시
#   - ROI는 "원본 해상도 좌표" (x, y, w, h)로 보관 → 해상도 독립적
# ----------------------------------------------------------------------
class VideoWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(640, 360)
        self.setMouseTracking(True)

        self._frame = None          # RGB, contiguous numpy array
        self._fw = 0                # frame width  (원본)
        self._fh = 0                # frame height (원본)

        # 표시 스케일/오프셋 (widget <-> frame 좌표 변환용)
        self._scale = 1.0
        self._ox = 0.0
        self._oy = 0.0

        # ROI (원본 프레임 좌표계)
        self.roi = None             # (x, y, w, h) or None

        # 드래그 상태
        self._dragging = False
        self._drag_start_f = None   # 프레임 좌표 시작점

    # 프레임 세팅 (BGR 입력) --------------------------------------------
    def set_frame(self, frame_bgr):
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        self._frame = np.ascontiguousarray(rgb)
        self._fh, self._fw = self._frame.shape[:2]
        self._recalc_transform()
        self.update()

    def clear(self):
        self._frame = None
        self.roi = None
        self.update()

    # 표시 변환 계산 (레터박스) ------------------------------------------
    def _recalc_transform(self):
        if self._frame is None or self._fw == 0 or self._fh == 0:
            return
        ww, wh = self.width(), self.height()
        self._scale = min(ww / self._fw, wh / self._fh)
        disp_w = self._fw * self._scale
        disp_h = self._fh * self._scale
        self._ox = (ww - disp_w) / 2.0
        self._oy = (wh - disp_h) / 2.0

    def resizeEvent(self, e):
        self._recalc_transform()
        super().resizeEvent(e)

    # 좌표 변환 ----------------------------------------------------------
    def _widget_to_frame(self, px, py):
        if self._scale == 0:
            return 0, 0
        fx = (px - self._ox) / self._scale
        fy = (py - self._oy) / self._scale
        fx = max(0, min(self._fw, fx))
        fy = max(0, min(self._fh, fy))
        return fx, fy

    def _frame_to_widget(self, fx, fy):
        return fx * self._scale + self._ox, fy * self._scale + self._oy

    # 마우스 드래그로 ROI 지정 -------------------------------------------
    def mousePressEvent(self, e):
        if self._frame is None or e.button() != Qt.LeftButton:
            return
        self._dragging = True
        self._drag_start_f = self._widget_to_frame(e.x(), e.y())
        self.roi = None
        self.update()

    def mouseMoveEvent(self, e):
        if not self._dragging:
            return
        cur = self._widget_to_frame(e.x(), e.y())
        x0, y0 = self._drag_start_f
        x1, y1 = cur
        x, y = min(x0, x1), min(y0, y1)
        w, h = abs(x1 - x0), abs(y1 - y0)
        self.roi = (int(x), int(y), int(w), int(h))
        self.update()

    def mouseReleaseEvent(self, e):
        if not self._dragging:
            return
        self._dragging = False
        # 너무 작은 드래그는 무효 처리
        if self.roi and (self.roi[2] < 4 or self.roi[3] < 4):
            self.roi = None
        self.update()

    # 렌더링 -------------------------------------------------------------
    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(30, 30, 30))
        if self._frame is None:
            p.setPen(QColor(180, 180, 180))
            p.drawText(self.rect(), Qt.AlignCenter, "파일 열기 (Open) 후 표시됩니다")
            return

        img = QImage(self._frame.data, self._fw, self._fh,
                     self._frame.strides[0], QImage.Format_RGB888)
        target = QRect(int(self._ox), int(self._oy),
                       int(self._fw * self._scale), int(self._fh * self._scale))
        p.drawImage(target, img)

        # ROI 오버레이
        if self.roi:
            x, y, w, h = self.roi
            wx, wy = self._frame_to_widget(x, y)
            ww, wh = w * self._scale, h * self._scale
            pen = QPen(QColor(0, 220, 120), 2)
            p.setPen(pen)
            p.drawRect(int(wx), int(wy), int(ww), int(wh))
            p.setPen(QColor(0, 220, 120))
            p.drawText(int(wx), int(wy) - 4, f"{w}x{h} @({x},{y})")


# ----------------------------------------------------------------------
# 추출 워커 (별도 스레드) : In~Out 구간을 순차 디코딩, ROI 크롭 후 mp4 write
# ----------------------------------------------------------------------
class ExtractWorker(QThread):
    progress = pyqtSignal(int)
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, path, in_frame, out_frame, roi, fps, out_path):
        super().__init__()
        self.path = path
        self.in_frame = in_frame
        self.out_frame = out_frame
        self.roi = roi
        self.fps = fps
        self.out_path = out_path

    def run(self):
        cap = cv2.VideoCapture(self.path)
        if not cap.isOpened():
            self.failed.emit("추출용 VideoCapture 열기 실패")
            return

        x, y, w, h = self.roi
        # 일부 코덱이 짝수 해상도 요구 → 짝수 보정
        w -= w % 2
        h -= h % 2
        if w < 2 or h < 2:
            self.failed.emit("ROI 크기가 너무 작습니다")
            cap.release()
            return

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(self.out_path, fourcc, self.fps, (w, h))
        if not writer.isOpened():
            self.failed.emit("VideoWriter 열기 실패 (코덱/경로 확인)")
            cap.release()
            return

        # In점으로 점프 후, 구간을 프레임 단위로 연속 디코딩 (프레임 누락 없이)
        cap.set(cv2.CAP_PROP_POS_FRAMES, self.in_frame)
        total = self.out_frame - self.in_frame + 1
        done = 0

        for idx in range(self.in_frame, self.out_frame + 1):
            ret, frame = cap.read()
            if not ret:
                break
            fh, fw = frame.shape[:2]
            # ROI가 프레임 경계를 벗어나지 않도록 클램프
            cx = max(0, min(fw - w, x))
            cy = max(0, min(fh - h, y))
            crop = frame[cy:cy + h, cx:cx + w]
            writer.write(crop)

            done += 1
            self.progress.emit(int(done * 100 / total))

        writer.release()
        cap.release()
        self.finished_ok.emit(self.out_path)


# ----------------------------------------------------------------------
# 메인 윈도우
# ----------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Video ROI Extractor")
        self.resize(960, 720)

        # 상태
        self.cap = None
        self.path = None
        self.total_frames = 0
        self.fps = 30.0
        self.cur_frame = 0
        self.in_frame = None
        self.out_frame = None
        self.worker = None
        self._slider_updating = False   # 슬라이더 피드백 루프 방지

        # 재생 타이머
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_tick)

        self._build_ui()

    # UI 구성 ------------------------------------------------------------
    def _build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)

        self.video = VideoWidget()
        root.addWidget(self.video, stretch=1)

        # 슬라이더
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setEnabled(False)
        self.slider.valueChanged.connect(self._on_slider)
        root.addWidget(self.slider)

        # 시간/프레임 정보
        self.info = QLabel("00:00:00.000  |  frame 0 / 0  |  In: -  Out: -")
        root.addWidget(self.info)

        # 컨트롤 버튼들
        ctrl = QHBoxLayout()
        self.btn_open = QPushButton("Open")
        self.btn_prev = QPushButton("◀ Prev")
        self.btn_play = QPushButton("Play")
        self.btn_next = QPushButton("Next ▶")
        self.btn_in = QPushButton("Set In")
        self.btn_out = QPushButton("Set Out")
        self.btn_extract = QPushButton("Extract")

        self.btn_open.clicked.connect(self.open_file)
        self.btn_prev.clicked.connect(lambda: self.step_frame(-1))
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_next.clicked.connect(lambda: self.step_frame(1))
        self.btn_in.clicked.connect(self.set_in)
        self.btn_out.clicked.connect(self.set_out)
        self.btn_extract.clicked.connect(self.extract)

        for b in (self.btn_open, self.btn_prev, self.btn_play, self.btn_next,
                  self.btn_in, self.btn_out, self.btn_extract):
            ctrl.addWidget(b)
        root.addLayout(ctrl)

        # 진행률
        self.progress = QProgressBar()
        self.progress.setValue(0)
        root.addWidget(self.progress)

        self.setCentralWidget(central)
        self._set_controls_enabled(False)

    def _set_controls_enabled(self, on):
        for b in (self.btn_prev, self.btn_play, self.btn_next,
                  self.btn_in, self.btn_out, self.btn_extract):
            b.setEnabled(on)
        self.slider.setEnabled(on)

    # 파일 열기 ----------------------------------------------------------
    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "동영상 열기", "",
            "Video (*.mp4 *.avi *.mkv *.mov *.wmv);;All Files (*.*)")
        if not path:
            return

        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            QMessageBox.critical(self, "오류", "동영상 열기 실패")
            return

        if self.cap is not None:
            self.cap.release()

        self.cap = cap
        self.path = path
        self.total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        self.fps = fps if fps and fps > 0 else 30.0   # fps 미보고 파일 대비
        self.cur_frame = 0
        self.in_frame = None
        self.out_frame = None

        self.slider.setRange(0, max(0, self.total_frames - 1))
        self.slider.setValue(0)
        self._set_controls_enabled(True)
        self.show_frame(0)

    # 특정 프레임 표시 (미리보기용 시크) ---------------------------------
    def show_frame(self, idx):
        if self.cap is None:
            return
        idx = max(0, min(self.total_frames - 1, idx))
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = self.cap.read()
        if not ret:
            return
        self.cur_frame = idx
        self.video.set_frame(frame)

        self._slider_updating = True
        self.slider.setValue(idx)
        self._slider_updating = False
        self._update_info()

    def _update_info(self):
        t = self.cur_frame / self.fps if self.fps else 0
        hh = int(t // 3600)
        mm = int((t % 3600) // 60)
        ss = int(t % 60)
        ms = int((t - int(t)) * 1000)
        in_s = "-" if self.in_frame is None else str(self.in_frame)
        out_s = "-" if self.out_frame is None else str(self.out_frame)
        self.info.setText(
            f"{hh:02d}:{mm:02d}:{ss:02d}.{ms:03d}  |  "
            f"frame {self.cur_frame} / {self.total_frames - 1}  |  "
            f"In: {in_s}  Out: {out_s}")

    # 슬라이더 스크러빙 --------------------------------------------------
    def _on_slider(self, val):
        if self._slider_updating:
            return
        self.show_frame(val)

    # 프레임 스텝 --------------------------------------------------------
    def step_frame(self, delta):
        self.pause()
        self.show_frame(self.cur_frame + delta)

    # 재생 제어 ----------------------------------------------------------
    def toggle_play(self):
        if self.timer.isActive():
            self.pause()
        else:
            interval = int(1000 / self.fps) if self.fps else 33
            self.timer.start(max(1, interval))
            self.btn_play.setText("Pause")

    def pause(self):
        if self.timer.isActive():
            self.timer.stop()
        self.btn_play.setText("Play")

    def _on_tick(self):
        # 재생 중에는 연속 read (시크 없이) → 부드럽고 정확
        ret, frame = self.cap.read()
        if not ret:
            self.pause()
            return
        self.cur_frame += 1
        self.video.set_frame(frame)
        self._slider_updating = True
        self.slider.setValue(self.cur_frame)
        self._slider_updating = False
        self._update_info()

    # In / Out 지정 ------------------------------------------------------
    def set_in(self):
        self.in_frame = self.cur_frame
        self._update_info()

    def set_out(self):
        self.out_frame = self.cur_frame
        self._update_info()

    # 키보드 ← → 로 프레임 이동 ------------------------------------------
    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Left:
            self.step_frame(-1)
        elif e.key() == Qt.Key_Right:
            self.step_frame(1)
        elif e.key() == Qt.Key_Space:
            self.toggle_play()
        else:
            super().keyPressEvent(e)

    # 추출 ---------------------------------------------------------------
    def extract(self):
        if self.cap is None:
            return
        if self.video.roi is None:
            QMessageBox.warning(self, "ROI 없음", "먼저 영상 위에서 드래그로 영역을 지정하세요.")
            return
        if self.in_frame is None or self.out_frame is None:
            QMessageBox.warning(self, "구간 없음", "In / Out 지점을 모두 지정하세요.")
            return

        in_f, out_f = self.in_frame, self.out_frame
        if in_f > out_f:
            in_f, out_f = out_f, in_f   # 순서 뒤바뀌면 자동 스왑

        base = os.path.splitext(os.path.basename(self.path))[0]
        default_out = os.path.join(os.path.dirname(self.path),
                                   f"{base}_roi_{in_f}-{out_f}.mp4")
        out_path, _ = QFileDialog.getSaveFileName(
            self, "저장 위치", default_out, "MP4 (*.mp4)")
        if not out_path:
            return

        self.pause()
        self._set_controls_enabled(False)
        self.progress.setValue(0)

        self.worker = ExtractWorker(
            self.path, in_f, out_f, self.video.roi, self.fps, out_path)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.finished_ok.connect(self._on_extract_done)
        self.worker.failed.connect(self._on_extract_fail)
        self.worker.start()

    def _on_extract_done(self, out_path):
        self._set_controls_enabled(True)
        QMessageBox.information(self, "완료", f"저장 완료:\n{out_path}")

    def _on_extract_fail(self, msg):
        self._set_controls_enabled(True)
        QMessageBox.critical(self, "추출 실패", msg)

    def closeEvent(self, e):
        self.pause()
        if self.worker and self.worker.isRunning():
            self.worker.wait()
        if self.cap is not None:
            self.cap.release()
        super().closeEvent(e)


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()