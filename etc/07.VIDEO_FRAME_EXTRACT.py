# -*- coding: utf-8 -*-
"""
동영상 프레임 추출기 (mp4 / avi -> jpg)

- 동영상 파일 여러 개 추가 또는 폴더 지정(하위 폴더 포함 옵션)
- 저장 경로 지정
- 추출 FPS 1~30 설정 (초당 N장)
- 파일명: <동영상이름>_<HH>h<MM>m<SS>s<mmm>ms.jpg  (예: cam01_00h01m23s500ms.jpg)
"""
import os
import sys
import threading
import queue
import ctypes
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import cv2

VIDEO_EXTS = ('.mp4', '.avi')


def _short_path(path):
    """Windows에서 한글 등 비ASCII 경로를 OpenCV가 못 여는 경우를 위한 8.3 짧은 경로."""
    if os.name != 'nt':
        return path
    try:
        buf = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.kernel32.GetShortPathNameW(path, buf, 1024):
            return buf.value
    except Exception:
        pass
    return path


def open_video(path):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        cap.release()
        short = _short_path(path)
        if short != path:
            cap = cv2.VideoCapture(short)
    return cap


def imwrite_unicode(path, img, quality):
    ok, buf = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        return False
    buf.tofile(path)
    return True


def format_time(sec):
    total_ms = int(round(sec * 1000))
    h, rem = divmod(total_ms, 3600 * 1000)
    m, rem = divmod(rem, 60 * 1000)
    s, ms = divmod(rem, 1000)
    return '%02dh%02dm%02ds%03dms' % (h, m, s, ms)


def unique_stems(paths):
    """동영상 이름이 같은 파일이 여러 개면 _2, _3 ... 을 붙여 파일명 충돌 방지."""
    counts = {}
    result = {}
    for p in paths:
        stem = os.path.splitext(os.path.basename(p))[0]
        key = stem.lower()
        counts[key] = counts.get(key, 0) + 1
        result[p] = stem if counts[key] == 1 else '%s_%d' % (stem, counts[key])
    return result


class FrameExtractorApp:
    def __init__(self, root):
        self.root = root
        root.title('동영상 프레임 추출기 (mp4/avi → jpg)')
        root.geometry('760x620')
        root.minsize(640, 520)

        self.videos = []
        self.stop_event = threading.Event()
        self.worker = None
        self.msg_queue = queue.Queue()

        self.out_dir = tk.StringVar()
        self.fps = tk.IntVar(value=1)
        self.quality = tk.IntVar(value=95)
        self.recursive = tk.BooleanVar(value=True)
        self.subfolder = tk.BooleanVar(value=False)

        self._build_ui()
        self.root.after(100, self._poll_queue)

    # ---------------- UI ----------------
    def _build_ui(self):
        pad = {'padx': 8, 'pady': 4}

        # 동영상 목록
        lf = ttk.LabelFrame(self.root, text='동영상 목록 (mp4, avi)')
        lf.pack(fill='both', expand=True, **pad)

        btns = ttk.Frame(lf)
        btns.pack(fill='x', padx=4, pady=4)
        ttk.Button(btns, text='파일 추가', command=self.add_files).pack(side='left')
        ttk.Button(btns, text='폴더 추가', command=self.add_folder).pack(side='left', padx=4)
        ttk.Checkbutton(btns, text='하위 폴더 포함', variable=self.recursive).pack(side='left', padx=4)
        ttk.Button(btns, text='전체 삭제', command=self.clear_list).pack(side='right')
        ttk.Button(btns, text='선택 삭제', command=self.remove_selected).pack(side='right', padx=4)

        list_frame = ttk.Frame(lf)
        list_frame.pack(fill='both', expand=True, padx=4, pady=(0, 4))
        self.listbox = tk.Listbox(list_frame, selectmode='extended')
        sb = ttk.Scrollbar(list_frame, orient='vertical', command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=sb.set)
        self.listbox.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')
        self.count_label = ttk.Label(lf, text='0개')
        self.count_label.pack(anchor='e', padx=4)

        # 설정
        sf = ttk.LabelFrame(self.root, text='설정')
        sf.pack(fill='x', **pad)

        row = ttk.Frame(sf)
        row.pack(fill='x', padx=4, pady=4)
        ttk.Label(row, text='저장 경로:').pack(side='left')
        ttk.Entry(row, textvariable=self.out_dir).pack(side='left', fill='x', expand=True, padx=4)
        ttk.Button(row, text='찾아보기', command=self.choose_out_dir).pack(side='left')

        row2 = ttk.Frame(sf)
        row2.pack(fill='x', padx=4, pady=4)
        ttk.Label(row2, text='추출 FPS (초당 장수):').pack(side='left')
        ttk.Spinbox(row2, from_=1, to=30, textvariable=self.fps, width=5, state='readonly').pack(side='left', padx=4)
        ttk.Label(row2, text='JPG 품질:').pack(side='left', padx=(16, 0))
        ttk.Spinbox(row2, from_=50, to=100, textvariable=self.quality, width=5, state='readonly').pack(side='left', padx=4)
        ttk.Checkbutton(row2, text='동영상별 하위 폴더에 저장', variable=self.subfolder).pack(side='left', padx=16)

        # 진행
        pf = ttk.LabelFrame(self.root, text='진행')
        pf.pack(fill='x', **pad)
        self.cur_label = ttk.Label(pf, text='대기 중')
        self.cur_label.pack(anchor='w', padx=4)
        self.file_progress = ttk.Progressbar(pf, mode='determinate', maximum=100)
        self.file_progress.pack(fill='x', padx=4, pady=2)
        self.total_label = ttk.Label(pf, text='전체: 0 / 0')
        self.total_label.pack(anchor='w', padx=4)
        self.total_progress = ttk.Progressbar(pf, mode='determinate', maximum=100)
        self.total_progress.pack(fill='x', padx=4, pady=(2, 6))

        ctrl = ttk.Frame(self.root)
        ctrl.pack(fill='x', **pad)
        self.start_btn = ttk.Button(ctrl, text='추출 시작', command=self.start)
        self.start_btn.pack(side='right')
        self.stop_btn = ttk.Button(ctrl, text='중지', command=self.stop, state='disabled')
        self.stop_btn.pack(side='right', padx=4)
        self.open_btn = ttk.Button(ctrl, text='저장 폴더 열기', command=self.open_out_dir)
        self.open_btn.pack(side='left')

        # 로그
        logf = ttk.LabelFrame(self.root, text='로그')
        logf.pack(fill='both', expand=False, **pad)
        self.log = tk.Text(logf, height=7, state='disabled')
        self.log.pack(fill='both', expand=True, padx=4, pady=4)

    # ---------------- 목록 관리 ----------------
    def _add_paths(self, paths):
        existing = set(os.path.normcase(os.path.abspath(v)) for v in self.videos)
        added = 0
        for p in paths:
            ap = os.path.abspath(p)
            key = os.path.normcase(ap)
            if key in existing or not ap.lower().endswith(VIDEO_EXTS):
                continue
            existing.add(key)
            self.videos.append(ap)
            self.listbox.insert('end', ap)
            added += 1
        self.count_label.config(text='%d개' % len(self.videos))
        return added

    def add_files(self):
        files = filedialog.askopenfilenames(
            title='동영상 선택',
            filetypes=[('동영상', '*.mp4 *.avi *.MP4 *.AVI'), ('모든 파일', '*.*')])
        if files:
            self._add_paths(files)

    def add_folder(self):
        folder = filedialog.askdirectory(title='동영상 폴더 선택')
        if not folder:
            return
        found = []
        if self.recursive.get():
            for dirpath, _, filenames in os.walk(folder):
                for f in sorted(filenames):
                    if f.lower().endswith(VIDEO_EXTS):
                        found.append(os.path.join(dirpath, f))
        else:
            for f in sorted(os.listdir(folder)):
                fp = os.path.join(folder, f)
                if os.path.isfile(fp) and f.lower().endswith(VIDEO_EXTS):
                    found.append(fp)
        added = self._add_paths(found)
        self._log('폴더에서 동영상 %d개 추가: %s' % (added, folder))
        if not self.out_dir.get():
            self.out_dir.set(os.path.join(folder, 'extracted_frames'))

    def remove_selected(self):
        for idx in reversed(self.listbox.curselection()):
            self.listbox.delete(idx)
            del self.videos[idx]
        self.count_label.config(text='%d개' % len(self.videos))

    def clear_list(self):
        self.listbox.delete(0, 'end')
        self.videos = []
        self.count_label.config(text='0개')

    def choose_out_dir(self):
        d = filedialog.askdirectory(title='저장 경로 선택')
        if d:
            self.out_dir.set(d)

    def open_out_dir(self):
        d = self.out_dir.get()
        if d and os.path.isdir(d):
            os.startfile(d)

    # ---------------- 실행 ----------------
    def _log(self, text):
        self.log.configure(state='normal')
        self.log.insert('end', text + '\n')
        self.log.see('end')
        self.log.configure(state='disabled')

    def start(self):
        if not self.videos:
            messagebox.showwarning('알림', '동영상을 추가하세요.')
            return
        out_dir = self.out_dir.get().strip()
        if not out_dir:
            messagebox.showwarning('알림', '저장 경로를 지정하세요.')
            return
        try:
            os.makedirs(out_dir, exist_ok=True)
        except OSError as e:
            messagebox.showerror('오류', '저장 경로를 만들 수 없습니다.\n%s' % e)
            return

        self.stop_event.clear()
        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.total_progress['value'] = 0
        args = (list(self.videos), out_dir, int(self.fps.get()), int(self.quality.get()), self.subfolder.get())
        self.worker = threading.Thread(target=self._run, args=args, daemon=True)
        self.worker.start()

    def stop(self):
        self.stop_event.set()
        self._log('중지 요청...')

    def _run(self, videos, out_dir, target_fps, quality, use_subfolder):
        q = self.msg_queue
        stems = unique_stems(videos)
        total_saved = 0
        q.put(('log', '시작: 동영상 %d개, %d fps 추출' % (len(videos), target_fps)))

        for vi, path in enumerate(videos):
            if self.stop_event.is_set():
                break
            q.put(('total', vi, len(videos)))
            stem = stems[path]
            save_dir = os.path.join(out_dir, stem) if use_subfolder else out_dir
            os.makedirs(save_dir, exist_ok=True)

            cap = open_video(path)
            if not cap.isOpened():
                q.put(('log', '[실패] 열 수 없음: %s' % path))
                continue

            video_fps = cap.get(cv2.CAP_PROP_FPS)
            if not video_fps or video_fps <= 0 or video_fps > 1000:
                video_fps = 30.0
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            interval = 1.0 / target_fps
            next_t = 0.0
            idx = 0
            saved = 0
            q.put(('file', os.path.basename(path), 0, frame_count))

            while not self.stop_event.is_set():
                if not cap.grab():
                    break
                t = idx / video_fps
                # 부동소수 오차 허용 (반 프레임)
                if t + 0.5 / video_fps >= next_t:
                    ok, frame = cap.retrieve()
                    if ok and frame is not None:
                        name = '%s_%s.jpg' % (stem, format_time(t))
                        if imwrite_unicode(os.path.join(save_dir, name), frame, quality):
                            saved += 1
                    # 다음 추출 시점 (영상 fps보다 높게 설정된 경우 모든 프레임 저장)
                    while next_t <= t + 0.5 / video_fps:
                        next_t += interval
                idx += 1
                if idx % 30 == 0:
                    q.put(('file', os.path.basename(path), idx, frame_count))

            cap.release()
            total_saved += saved
            q.put(('file', os.path.basename(path), frame_count or idx, frame_count or idx))
            q.put(('log', '[완료] %s → %d장 (영상 %.2ffps, %d프레임)'
                   % (os.path.basename(path), saved, video_fps, idx)))

        stopped = self.stop_event.is_set()
        q.put(('done', total_saved, stopped, len(videos)))

    def _poll_queue(self):
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                kind = msg[0]
                if kind == 'log':
                    self._log(msg[1])
                elif kind == 'file':
                    _, name, cur, total = msg
                    pct = (cur / total * 100) if total else 0
                    self.file_progress['value'] = min(pct, 100)
                    self.cur_label.config(text='%s  (%d / %d 프레임)' % (name, cur, total))
                elif kind == 'total':
                    _, cur, total = msg
                    self.total_progress['value'] = cur / total * 100 if total else 0
                    self.total_label.config(text='전체: %d / %d' % (cur + 1, total))
                elif kind == 'done':
                    _, saved, stopped, n = msg
                    self.start_btn.config(state='normal')
                    self.stop_btn.config(state='disabled')
                    if stopped:
                        self.cur_label.config(text='중지됨')
                        self._log('중지됨. 저장된 이미지: %d장' % saved)
                    else:
                        self.total_progress['value'] = 100
                        self.total_label.config(text='전체: %d / %d' % (n, n))
                        self.cur_label.config(text='완료')
                        self._log('전체 완료. 저장된 이미지: %d장' % saved)
                        messagebox.showinfo('완료', '추출 완료\n저장된 이미지: %d장' % saved)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)


def hide_console():
    """exe가 콘솔 모드로 빌드된 경우 콘솔 창 숨김 (백신이 windowed 부트로더를 차단하는 환경 대응)."""
    if os.name == 'nt' and getattr(sys, 'frozen', False):
        try:
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 0)
        except Exception:
            pass


def main():
    hide_console()
    root = tk.Tk()
    try:
        ico = os.path.join(getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__))), 'icon.ico')
        if os.path.exists(ico):
            root.iconbitmap(ico)
    except Exception:
        pass
    FrameExtractorApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
