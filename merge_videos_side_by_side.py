"""
merge_videos_side_by_side.py

두 폴더에서 같은 이름의 영상을 찾아 좌우로 붙여 새 영상을 만드는 도구.
- FPS 정규화 (두 영상의 FPS를 통일)
- 해상도 정규화 (같은 높이로 스케일 유지)
- 길이 동기화 (짧은 쪽 기준 trim 또는 긴 쪽 기준 pad)
- ffmpeg 기반 처리

Requirements:
  pip install tqdm
  ffmpeg must be installed and available in PATH
"""

import os
import sys
import json
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Video metadata
# ---------------------------------------------------------------------------

@dataclass
class VideoInfo:
    path: str
    width: int = 0
    height: int = 0
    fps: float = 0.0
    duration: float = 0.0  # seconds
    has_audio: bool = False

    @property
    def name(self) -> str:
        return Path(self.path).name


def probe_video(path: str) -> VideoInfo:
    """ffprobe로 영상 메타데이터 추출."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams", "-show_format",
        path,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
        data = json.loads(result.stdout)
    except Exception as e:
        raise RuntimeError(f"ffprobe 실패: {path}\n{e}")

    info = VideoInfo(path=path)
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            info.width = int(stream.get("width", 0))
            info.height = int(stream.get("height", 0))
            # fps: "30/1" 또는 "30000/1001" 형태
            r_fps = stream.get("r_frame_rate", "0/1")
            try:
                num, den = r_fps.split("/")
                info.fps = round(int(num) / int(den), 4)
            except Exception:
                info.fps = 0.0
        if stream.get("codec_type") == "audio":
            info.has_audio = True

    fmt = data.get("format", {})
    info.duration = float(fmt.get("duration", 0))
    return info


# ---------------------------------------------------------------------------
# Core merge logic
# ---------------------------------------------------------------------------

@dataclass
class MergeOptions:
    fps_mode: str = "higher"      # "higher" | "lower" | "left" | "right" | "custom"
    fps_custom: float = 30.0
    height_mode: str = "higher"   # "higher" | "lower" | "left" | "right" | "custom"
    height_custom: int = 720
    sync_mode: str = "trim"       # "trim"|"pad"|"speed_to_longer"|"speed_to_shorter"
    layout: str = "left_right"    # "left_right" | "right_left"
    vcodec: str = "libx264"
    crf: int = 18
    audio: str = "left"           # "left" | "right" | "mix" | "none"
    output_suffix: str = "_merged"


def resolve_fps(left: VideoInfo, right: VideoInfo, opts: MergeOptions) -> float:
    if opts.fps_mode == "higher":
        return max(left.fps, right.fps)
    elif opts.fps_mode == "lower":
        return min(left.fps, right.fps)
    elif opts.fps_mode == "left":
        return left.fps
    elif opts.fps_mode == "right":
        return right.fps
    else:
        return opts.fps_custom


def resolve_height(left: VideoInfo, right: VideoInfo, opts: MergeOptions) -> int:
    if opts.height_mode == "higher":
        return max(left.height, right.height)
    elif opts.height_mode == "lower":
        return min(left.height, right.height)
    elif opts.height_mode == "left":
        return left.height
    elif opts.height_mode == "right":
        return right.height
    else:
        return opts.height_custom


def _build_atempo_chain(speed: float) -> str:
    """atempo 범위(0.5~2.0)를 벗어나는 속도 비율을 위해 여러 atempo 필터를 체인."""
    filters = []
    remaining = speed
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5
    filters.append(f"atempo={remaining:.6f}")
    return ",".join(filters)


def build_ffmpeg_cmd(
    left: VideoInfo,
    right: VideoInfo,
    output_path: str,
    opts: MergeOptions,
) -> list:
    target_fps = resolve_fps(left, right, opts)
    target_h = resolve_height(left, right, opts)
    is_speed_mode = opts.sync_mode in ("speed_to_longer", "speed_to_shorter")

    # 목표 재생 시간 결정
    if opts.sync_mode in ("trim", "speed_to_shorter"):
        duration = min(left.duration, right.duration)
    else:  # pad, speed_to_longer
        duration = max(left.duration, right.duration)

    # 좌우 순서 결정
    if opts.layout == "right_left":
        a_path, b_path = right.path, left.path
        a_info, b_info = right, left
    else:
        a_path, b_path = left.path, right.path
        a_info, b_info = left, right

    fps_str = f"{target_fps:.4f}".rstrip("0").rstrip(".")

    def build_video_chain(idx, info, h, chain_out):
        steps = []
        if is_speed_mode:
            # pts_ratio = target / original → >1 슬로우, <1 가속
            pts_ratio = duration / info.duration
            steps.append(f"[{idx}:v]setpts={pts_ratio:.6f}*PTS")
            steps.append(f"fps={fps_str}")
            steps.append(f"scale=-2:{h}")
            steps.append(f"trim=duration={duration:.6f}")
            steps.append(f"setpts=PTS-STARTPTS[{chain_out}]")
        else:
            steps.append(f"[{idx}:v]fps={fps_str}")
            steps.append(f"scale=-2:{h}")
            if opts.sync_mode == "pad":
                extra = duration - info.duration
                if extra > 0:
                    pad_frames = int(extra * target_fps) + 2
                    steps.append(f"tpad=stop={pad_frames}:stop_mode=clone")
            steps.append(f"trim=duration={duration:.6f}")
            steps.append(f"setpts=PTS-STARTPTS[{chain_out}]")
        return ",".join(steps[:-1]) + "," + steps[-1]

    def build_audio_for(src_idx, src_info, out_tag):
        """오디오 필터 문자열 반환 (세미콜론 포함)."""
        if is_speed_mode:
            pts_ratio = duration / src_info.duration
            audio_speed = 1.0 / pts_ratio          # atempo는 속도 배율
            atempo = _build_atempo_chain(audio_speed)
            return (
                f";[{src_idx}:a]{atempo},"
                f"atrim=duration={duration:.6f},"
                f"asetpts=PTS-STARTPTS[{out_tag}]"
            )
        else:
            return (
                f";[{src_idx}:a]atrim=duration={duration:.6f},"
                f"asetpts=PTS-STARTPTS[{out_tag}]"
            )

    v0 = build_video_chain(0, a_info, target_h, "v0")
    v1 = build_video_chain(1, b_info, target_h, "v1")
    hstack = "[v0][v1]hstack=inputs=2[vout]"

    filter_complex = f"{v0};{v1};{hstack}"

    # 오디오 처리
    audio_maps = []
    amix_filter = ""
    if opts.audio == "left":
        src_idx = 0 if opts.layout == "left_right" else 1
        src_info = a_info if opts.layout == "left_right" else b_info
        if src_info.has_audio:
            amix_filter = build_audio_for(src_idx, src_info, "aout")
            audio_maps = ["-map", "[aout]"]
    elif opts.audio == "right":
        src_idx = 1 if opts.layout == "left_right" else 0
        src_info = b_info if opts.layout == "left_right" else a_info
        if src_info.has_audio:
            amix_filter = build_audio_for(src_idx, src_info, "aout")
            audio_maps = ["-map", "[aout]"]
    elif opts.audio == "mix":
        has_a = a_info.has_audio
        has_b = b_info.has_audio
        if has_a and has_b:
            amix_filter = (
                build_audio_for(0, a_info, "a0").replace("[aout]", "[a0]") +
                build_audio_for(1, b_info, "a1").replace("[aout]", "[a1]") +
                ";[a0][a1]amix=inputs=2:normalize=0[aout]"
            )
            audio_maps = ["-map", "[aout]"]
        elif has_a:
            amix_filter = build_audio_for(0, a_info, "aout")
            audio_maps = ["-map", "[aout]"]
        elif has_b:
            amix_filter = build_audio_for(1, b_info, "aout")
            audio_maps = ["-map", "[aout]"]

    filter_complex += amix_filter

    cmd = [
        "ffmpeg", "-y",
        "-i", a_path,
        "-i", b_path,
        "-filter_complex", filter_complex,
        "-map", "[vout]",
    ] + audio_maps + [
        "-c:v", opts.vcodec,
        "-crf", str(opts.crf),
        "-preset", "fast",
    ]
    if audio_maps:
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    cmd.append(output_path)
    return cmd


def run_merge(
    left_path: str,
    right_path: str,
    output_path: str,
    opts: MergeOptions,
    log_fn=print,
) -> bool:
    """단일 영상 쌍 병합. 성공 시 True."""
    try:
        log_fn(f"  분석 중: {Path(left_path).name}")
        left = probe_video(left_path)
        right = probe_video(right_path)

        log_fn(
            f"  LEFT  {left.width}x{left.height} @ {left.fps:.2f}fps  {left.duration:.2f}s"
        )
        log_fn(
            f"  RIGHT {right.width}x{right.height} @ {right.fps:.2f}fps  {right.duration:.2f}s"
        )

        # 싱크 정보 출력
        if opts.sync_mode in ("speed_to_longer", "speed_to_shorter"):
            target_dur = (
                max(left.duration, right.duration)
                if opts.sync_mode == "speed_to_longer"
                else min(left.duration, right.duration)
            )
            l_ratio = target_dur / left.duration
            r_ratio = target_dur / right.duration
            log_fn(
                f"  SYNC  목표={target_dur:.2f}s  "
                f"LEFT×{l_ratio:.3f}  RIGHT×{r_ratio:.3f}"
            )

        cmd = build_ffmpeg_cmd(left, right, output_path, opts)
        log_fn(f"  ffmpeg 실행 중...")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3600,
        )
        if result.returncode != 0:
            log_fn(f"  [ERROR] ffmpeg 실패:\n{result.stderr[-2000:]}")
            return False

        log_fn(f"  완료 → {output_path}")
        return True

    except Exception as e:
        log_fn(f"  [ERROR] {e}")
        return False


# ---------------------------------------------------------------------------
# File matching
# ---------------------------------------------------------------------------

VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".webm", ".m4v", ".ts", ".mts"}


def find_matching_pairs(folder_a: str, folder_b: str):
    """두 폴더에서 파일명이 같은 영상 쌍 반환."""
    def video_files(folder):
        return {
            p.name: str(p)
            for p in Path(folder).iterdir()
            if p.is_file() and p.suffix.lower() in VIDEO_EXTS
        }

    files_a = video_files(folder_a)
    files_b = video_files(folder_b)
    common = sorted(set(files_a) & set(files_b))
    only_a = sorted(set(files_a) - set(files_b))
    only_b = sorted(set(files_b) - set(files_a))
    pairs = [(files_a[n], files_b[n]) for n in common]
    return pairs, only_a, only_b


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Video Side-by-Side Merger")
        self.resizable(True, True)
        self.minsize(700, 600)

        self._opts = MergeOptions()
        self._pairs = []
        self._running = False

        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self):
        pad = dict(padx=8, pady=4)

        # ── 폴더 선택 ──────────────────────────────────────────────────
        folder_frame = ttk.LabelFrame(self, text="폴더 설정")
        folder_frame.pack(fill="x", **pad)

        for row, (label, attr) in enumerate([
            ("왼쪽 폴더 (A)", "folder_a"),
            ("오른쪽 폴더 (B)", "folder_b"),
            ("출력 폴더", "folder_out"),
        ]):
            ttk.Label(folder_frame, text=label, width=16, anchor="w").grid(
                row=row, column=0, **pad, sticky="w"
            )
            var = tk.StringVar()
            setattr(self, f"_{attr}_var", var)
            ttk.Entry(folder_frame, textvariable=var, width=50).grid(
                row=row, column=1, **pad, sticky="ew"
            )
            ttk.Button(
                folder_frame, text="찾아보기",
                command=lambda v=var: self._browse(v),
            ).grid(row=row, column=2, **pad)
        folder_frame.columnconfigure(1, weight=1)

        # ── 옵션 ───────────────────────────────────────────────────────
        opt_frame = ttk.LabelFrame(self, text="변환 옵션")
        opt_frame.pack(fill="x", **pad)

        # FPS
        ttk.Label(opt_frame, text="FPS 기준:").grid(row=0, column=0, **pad, sticky="w")
        self._fps_mode = tk.StringVar(value="higher")
        fps_combo = ttk.Combobox(
            opt_frame, textvariable=self._fps_mode, width=12,
            values=["higher", "lower", "left", "right", "custom"], state="readonly",
        )
        fps_combo.grid(row=0, column=1, **pad, sticky="w")
        fps_combo.bind("<<ComboboxSelected>>", self._on_fps_mode)
        ttk.Label(opt_frame, text="커스텀 FPS:").grid(row=0, column=2, **pad, sticky="w")
        self._fps_custom = tk.DoubleVar(value=30.0)
        self._fps_entry = ttk.Entry(opt_frame, textvariable=self._fps_custom, width=8, state="disabled")
        self._fps_entry.grid(row=0, column=3, **pad, sticky="w")

        # 높이
        ttk.Label(opt_frame, text="높이 기준:").grid(row=1, column=0, **pad, sticky="w")
        self._height_mode = tk.StringVar(value="higher")
        h_combo = ttk.Combobox(
            opt_frame, textvariable=self._height_mode, width=12,
            values=["higher", "lower", "left", "right", "custom"], state="readonly",
        )
        h_combo.grid(row=1, column=1, **pad, sticky="w")
        h_combo.bind("<<ComboboxSelected>>", self._on_height_mode)
        ttk.Label(opt_frame, text="커스텀 높이:").grid(row=1, column=2, **pad, sticky="w")
        self._height_custom = tk.IntVar(value=720)
        self._height_entry = ttk.Entry(opt_frame, textvariable=self._height_custom, width=8, state="disabled")
        self._height_entry.grid(row=1, column=3, **pad, sticky="w")

        # 동기화
        ttk.Label(opt_frame, text="길이 동기화:").grid(row=2, column=0, **pad, sticky="w")
        self._sync_mode = tk.StringVar(value="speed_to_longer")
        ttk.Combobox(
            opt_frame, textvariable=self._sync_mode, width=22,
            values=[
                "trim (짧은 쪽 기준 자르기)",
                "pad (긴 쪽 기준 검정채움)",
                "speed_to_longer (짧은 쪽 슬로우→긴 쪽 맞춤)",
                "speed_to_shorter (긴 쪽 가속→짧은 쪽 맞춤)",
            ],
            state="readonly",
        ).grid(row=2, column=1, columnspan=3, **pad, sticky="w")

        # 레이아웃
        ttk.Label(opt_frame, text="배치 순서:").grid(row=2, column=2, **pad, sticky="w")
        self._layout = tk.StringVar(value="left_right")
        ttk.Combobox(
            opt_frame, textvariable=self._layout, width=14,
            values=["left_right (A|B)", "right_left (B|A)"], state="readonly",
        ).grid(row=2, column=3, **pad, sticky="w")

        # 오디오
        ttk.Label(opt_frame, text="오디오:").grid(row=3, column=0, **pad, sticky="w")
        self._audio = tk.StringVar(value="left")
        ttk.Combobox(
            opt_frame, textvariable=self._audio, width=12,
            values=["left", "right", "mix", "none"], state="readonly",
        ).grid(row=3, column=1, **pad, sticky="w")

        # 코덱 / CRF
        ttk.Label(opt_frame, text="코덱:").grid(row=3, column=2, **pad, sticky="w")
        self._vcodec = tk.StringVar(value="libx264")
        ttk.Combobox(
            opt_frame, textvariable=self._vcodec, width=14,
            values=["libx264", "libx265", "libvpx-vp9"], state="readonly",
        ).grid(row=3, column=3, **pad, sticky="w")

        ttk.Label(opt_frame, text="CRF (품질):").grid(row=4, column=0, **pad, sticky="w")
        self._crf = tk.IntVar(value=18)
        ttk.Scale(opt_frame, from_=0, to=51, variable=self._crf, orient="horizontal", length=160).grid(
            row=4, column=1, **pad, sticky="w"
        )
        ttk.Label(opt_frame, textvariable=self._crf).grid(row=4, column=2, **pad, sticky="w")

        ttk.Label(opt_frame, text="출력 접미사:").grid(row=5, column=0, **pad, sticky="w")
        self._suffix = tk.StringVar(value="_merged")
        ttk.Entry(opt_frame, textvariable=self._suffix, width=16).grid(row=5, column=1, **pad, sticky="w")

        # ── 파일 목록 ──────────────────────────────────────────────────
        list_frame = ttk.LabelFrame(self, text="매칭된 파일 쌍")
        list_frame.pack(fill="both", expand=True, **pad)

        cols = ("name", "left_res", "right_res", "status")
        self._tree = ttk.Treeview(list_frame, columns=cols, show="headings", height=8)
        for col, hdr, w in [
            ("name", "파일명", 220),
            ("left_res", "왼쪽 정보", 180),
            ("right_res", "오른쪽 정보", 180),
            ("status", "상태", 100),
        ]:
            self._tree.heading(col, text=hdr)
            self._tree.column(col, width=w)
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=scroll.set)
        self._tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        # ── 진행 ───────────────────────────────────────────────────────
        prog_frame = ttk.Frame(self)
        prog_frame.pack(fill="x", **pad)
        self._progress = ttk.Progressbar(prog_frame, orient="horizontal", mode="determinate")
        self._progress.pack(fill="x")
        self._status_var = tk.StringVar(value="대기 중")
        ttk.Label(prog_frame, textvariable=self._status_var).pack(anchor="w")

        # ── 로그 ───────────────────────────────────────────────────────
        log_frame = ttk.LabelFrame(self, text="로그")
        log_frame.pack(fill="both", expand=False, **pad)
        self._log = tk.Text(log_frame, height=8, state="disabled", wrap="word", font=("Consolas", 9))
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self._log.yview)
        self._log.configure(yscrollcommand=log_scroll.set)
        self._log.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

        # ── 버튼 ───────────────────────────────────────────────────────
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", **pad)
        ttk.Button(btn_frame, text="파일 목록 갱신", command=self._refresh_list).pack(side="left", padx=4)
        self._btn_start = ttk.Button(btn_frame, text="병합 시작", command=self._start)
        self._btn_start.pack(side="left", padx=4)
        ttk.Button(btn_frame, text="종료", command=self.destroy).pack(side="right", padx=4)

    # ------------------------------------------------------------------
    def _browse(self, var: tk.StringVar):
        path = filedialog.askdirectory()
        if path:
            var.set(path)

    def _on_fps_mode(self, _=None):
        state = "normal" if self._fps_mode.get() == "custom" else "disabled"
        self._fps_entry.config(state=state)

    def _on_height_mode(self, _=None):
        state = "normal" if self._height_mode.get() == "custom" else "disabled"
        self._height_entry.config(state=state)

    def _log_msg(self, msg: str):
        self._log.config(state="normal")
        self._log.insert("end", msg + "\n")
        self._log.see("end")
        self._log.config(state="disabled")

    def _refresh_list(self):
        a = self._folder_a_var.get().strip()
        b = self._folder_b_var.get().strip()
        if not a or not b:
            messagebox.showwarning("경고", "왼쪽/오른쪽 폴더를 먼저 선택하세요.")
            return
        if not os.path.isdir(a) or not os.path.isdir(b):
            messagebox.showerror("오류", "유효한 폴더를 선택하세요.")
            return

        pairs, only_a, only_b = find_matching_pairs(a, b)
        self._pairs = pairs

        self._tree.delete(*self._tree.get_children())
        for lp, rp in pairs:
            self._tree.insert("", "end", values=(Path(lp).name, lp, rp, "대기"))

        self._log_msg(f"매칭된 파일: {len(pairs)}개")
        if only_a:
            self._log_msg(f"왼쪽 폴더에만 있음: {', '.join(only_a)}")
        if only_b:
            self._log_msg(f"오른쪽 폴더에만 있음: {', '.join(only_b)}")

    def _collect_opts(self) -> MergeOptions:
        opts = MergeOptions()
        opts.fps_mode = self._fps_mode.get()
        opts.fps_custom = self._fps_custom.get()
        opts.height_mode = self._height_mode.get().split()[0]
        opts.height_custom = self._height_custom.get()
        opts.sync_mode = self._sync_mode.get().split()[0]
        opts.layout = self._layout.get().split()[0]
        opts.audio = self._audio.get()
        opts.vcodec = self._vcodec.get()
        opts.crf = self._crf.get()
        opts.output_suffix = self._suffix.get()
        return opts

    def _start(self):
        if self._running:
            return
        if not self._pairs:
            messagebox.showwarning("경고", "먼저 파일 목록을 갱신하세요.")
            return
        out_dir = self._folder_out_var.get().strip()
        if not out_dir:
            messagebox.showwarning("경고", "출력 폴더를 선택하세요.")
            return
        os.makedirs(out_dir, exist_ok=True)

        opts = self._collect_opts()
        self._running = True
        self._btn_start.config(state="disabled")
        self._progress["maximum"] = len(self._pairs)
        self._progress["value"] = 0

        thread = threading.Thread(target=self._run_all, args=(opts, out_dir), daemon=True)
        thread.start()

    def _run_all(self, opts: MergeOptions, out_dir: str):
        success = 0
        fail = 0
        items = self._tree.get_children()

        for idx, (lp, rp) in enumerate(self._pairs):
            stem = Path(lp).stem
            suffix = Path(lp).suffix
            out_name = f"{stem}{opts.output_suffix}{suffix}"
            out_path = os.path.join(out_dir, out_name)

            self._tree.set(items[idx], "status", "처리 중")
            self._status_var.set(f"[{idx+1}/{len(self._pairs)}] {Path(lp).name}")
            self._log_msg(f"\n[{idx+1}/{len(self._pairs)}] {Path(lp).name}")

            ok = run_merge(lp, rp, out_path, opts, log_fn=self._log_msg)
            if ok:
                self._tree.set(items[idx], "status", "완료")
                success += 1
            else:
                self._tree.set(items[idx], "status", "실패")
                fail += 1

            self._progress["value"] = idx + 1

        self._status_var.set(f"완료: 성공 {success}개 / 실패 {fail}개")
        self._log_msg(f"\n=== 완료: 성공 {success}개 / 실패 {fail}개 ===")
        self._running = False
        self._btn_start.config(state="normal")


# ---------------------------------------------------------------------------
# CLI mode
# ---------------------------------------------------------------------------

def cli_main():
    import argparse

    parser = argparse.ArgumentParser(
        description="두 폴더의 같은 이름 영상을 좌우 병합합니다."
    )
    parser.add_argument("folder_a", help="왼쪽 폴더")
    parser.add_argument("folder_b", help="오른쪽 폴더")
    parser.add_argument("output", help="출력 폴더")
    parser.add_argument("--fps", default="higher",
                        choices=["higher", "lower", "left", "right"],
                        help="FPS 기준 (default: higher)")
    parser.add_argument("--fps-value", type=float, default=30.0,
                        help="커스텀 FPS 값 (--fps custom 일 때)")
    parser.add_argument("--height", default="higher",
                        choices=["higher", "lower", "left", "right"],
                        help="높이 기준 (default: higher)")
    parser.add_argument("--height-value", type=int, default=720,
                        help="커스텀 높이 값")
    parser.add_argument("--sync", default="speed_to_longer",
                        choices=["trim", "pad", "speed_to_longer", "speed_to_shorter"],
                        help=(
                            "길이 동기화: "
                            "trim=짧은 쪽 자르기, "
                            "pad=긴 쪽 검정채움, "
                            "speed_to_longer=짧은 쪽 슬로우→긴 쪽 맞춤(기본), "
                            "speed_to_shorter=긴 쪽 가속→짧은 쪽 맞춤"
                        ))
    parser.add_argument("--layout", default="left_right",
                        choices=["left_right", "right_left"])
    parser.add_argument("--audio", default="left",
                        choices=["left", "right", "mix", "none"])
    parser.add_argument("--crf", type=int, default=18)
    parser.add_argument("--codec", default="libx264",
                        choices=["libx264", "libx265", "libvpx-vp9"])
    parser.add_argument("--suffix", default="_merged")
    args = parser.parse_args()

    pairs, only_a, only_b = find_matching_pairs(args.folder_a, args.folder_b)
    print(f"매칭된 파일: {len(pairs)}개")
    if only_a:
        print(f"왼쪽 폴더에만 있음: {only_a}")
    if only_b:
        print(f"오른쪽 폴더에만 있음: {only_b}")

    if not pairs:
        print("처리할 파일이 없습니다.")
        return

    os.makedirs(args.output, exist_ok=True)
    opts = MergeOptions(
        fps_mode=args.fps,
        fps_custom=args.fps_value,
        height_mode=args.height,
        height_custom=args.height_value,
        sync_mode=args.sync,
        layout=args.layout,
        audio=args.audio,
        vcodec=args.codec,
        crf=args.crf,
        output_suffix=args.suffix,
    )

    success = 0
    for idx, (lp, rp) in enumerate(pairs):
        stem = Path(lp).stem
        suffix = Path(lp).suffix
        out_path = os.path.join(args.output, f"{stem}{opts.output_suffix}{suffix}")
        print(f"\n[{idx+1}/{len(pairs)}] {Path(lp).name}")
        ok = run_merge(lp, rp, out_path, opts)
        if ok:
            success += 1

    print(f"\n완료: {success}/{len(pairs)}개 성공")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) > 1:
        cli_main()
    else:
        app = App()
        app.mainloop()
