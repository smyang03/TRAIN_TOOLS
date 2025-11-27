import sys
# PyInstaller RecursionError 방지 - 빌드 프로세스에서 recursion limit 증가
sys.setrecursionlimit(100000)

import tkinter as tk
from tkinter import TclError, filedialog, ttk
from PIL import Image, ImageTk
import os
from tqdm import tqdm
from PIL import ImageDraw
from datetime import datetime
import time
from collections import Counter, defaultdict,OrderedDict
import random
import gc
import shutil
import numpy as np
import copy
import threading
import queue
import logging

try:
    import psutil
except ImportError:
    pass  # psutil은 선택적 의존성

class ImageViewer:
    def __init__(self, root):
        self.root = root
        self.rootpath = ""
        self.filename = ""
        self.current_datetime = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.root.title("Image Viewer")
        
        # Pagination related variables
        self.page_size = 350  # Number of images per page
        self.current_page = 0
        self.total_pages = 0
        self.current_images = []  # Store current page's images

        self.selid = -1

        # OrderedDict로 LRU 캐시 구현 (O(1) move_to_end 성능)
        self.label_cache = OrderedDict()  # 라벨 데이터 캐시
        self.image_cache = OrderedDict()  # 썸네일 이미지 캐시
        self.cache_limit = 2000  # 최대 캐시 항목 수

        # 마스킹 관련 변수 추가
        self.original_width = 0
        self.original_height = 0
        self.masking = None
        self.has_saved_masking = False
        self.maskingframewidth = 0
        self.maskingframeheight = 0
        self.ctrl_pressed = False
        
        # Data storage
        self.image_paths = []
        self.labels = []
        self.labelsdata = [[] for _ in range(100)]
        self.selected_image_labels = []
        self.checklist = []

        # Initialize box image checkbox as checked
        self.box_image_var = tk.IntVar(value=1)

        # 겹침 필터 변수 초기화 - 이 부분이 누락되었습니다
        self.overlap_class_selector = tk.StringVar()
        self.overlap_class_selector.set("선택 안함")
        self.overlap_filter_var = tk.StringVar(value="모두 보기")

        self.overlap_cache = {}
        
        # 필터링 결과 통계
        self.filter_stats = {"total": 0, "overlapping": 0, "non_overlapping": 0}

        self.iou_threshold_var = tk.DoubleVar(value=0.1)

        self.shift_pressed = False
        self.caps_locked = False
        self.drag_start = None
        self.drag_rectangle = None
        self.multi_select_start = None  # 다중 선택 시작 인덱스
        self.last_drag_update = 0  # 드래그 업데이트 throttling용
        
        self.selected_label_info = []  # 선택한 라벨의 상세 정보 저장
        self.preview_window = None

        self.tooltip_window = None
        self.tooltip_timer = None

        self.file_encoding_cache = {}
        self.default_encoding = 'utf-8'
        self.changing_class = False  # 클래스 변경 작업 여부
        self.strict_class_filtering = True  # 클래스 필터링 강제 여부

        # 새 개선 사항을 위한 변수들 (추가)
        self.ui_update_pending = False
        self.last_ui_update_time = time.time()
        self.memory_check_counter = 0
        self.ui_busy = False
        self.data_loading = False
        
        # 성능 설정 적용 (메모리 기반 설정 등)
        self.setup_performance_settings()
        
        # 캐시 시스템 설정
        self.setup_caching()
        
        # 작업 큐 설정 (멀티스레딩)
        self.setup_task_queue()

        self.setup_ui()
        self.status_bar = tk.Label(self.root, text="준비됨", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.setup_memory_monitoring()


    def setup_ui(self):
        # Top control panel - 전체 UI 컨테이너를 나누어 관리
        self.main_frame = tk.Frame(self.root)
        self.main_frame.pack(fill="both", expand=True)
        
        # 컨트롤 패널을 두 줄로 나누기
        self.control_panel_top = tk.Frame(self.main_frame)
        self.control_panel_top.pack(fill="x", padx=5, pady=5)
        
        self.control_panel_bottom = tk.Frame(self.main_frame)
        self.control_panel_bottom.pack(fill="x", padx=5, pady=2)
        
        # 첫 번째 줄: 기본 버튼들 (왼쪽 그룹)
        basic_frame = tk.Frame(self.control_panel_top)
        basic_frame.pack(side=tk.LEFT, padx=0)
        
        self.load_button = tk.Button(basic_frame, text="Load Data", width=10, command=self.load_data)
        self.load_button.pack(side=tk.LEFT, padx=1)
        
        self.file_slice_button = tk.Button(basic_frame, text="File Slice", width=10, command=self.file_slice)
        self.file_slice_button.pack(side=tk.LEFT, padx=1)
        
        # 클래스 선택기
        class_frame = tk.Frame(basic_frame)
        class_frame.pack(side=tk.LEFT, padx=1)
        
        class_label = tk.Label(class_frame, text="Select Class:")
        class_label.pack(side=tk.LEFT)
        
        self.class_selector = tk.StringVar()
        self.class_selector.set("Select Class")
        self.class_dropdown = tk.OptionMenu(class_frame, self.class_selector, "Select Class")
        self.class_dropdown.config(width=10)
        self.class_dropdown.pack(side=tk.LEFT)
        
        # IoU 필터
        iou_frame = tk.Frame(self.control_panel_top)
        iou_frame.pack(side=tk.LEFT, padx=1)
        
        iou_label = tk.Label(iou_frame, text="IoU 임계값:")
        iou_label.pack(side=tk.LEFT)
        
        self.iou_threshold_var = tk.DoubleVar(value=0.0)
        iou_slider = tk.Scale(iou_frame, from_=0.0, to=1.0, resolution=0.05,
                            orient=tk.HORIZONTAL, length=120,
                            variable=self.iou_threshold_var,
                            command=lambda v: self.update_iou_value())
        iou_slider.pack(side=tk.LEFT)
        
        self.iou_value_label = tk.Label(iou_frame, text="0.10", width=4)
        self.iou_value_label.pack(side=tk.LEFT, padx=1)
        
        # 저장 및 디스플레이 컨트롤 (오른쪽 그룹)
        control_frame = tk.Frame(self.control_panel_top)
        control_frame.pack(side=tk.LEFT, padx=1)
        
        self.save_button = tk.Button(control_frame, text="Save Label Data", command=self.save_labeldata)
        self.save_button.pack(side=tk.LEFT, padx=1)
        
        self.box_image_var = tk.IntVar(value=1)
        self.box_image_checkbox = tk.Checkbutton(control_frame, text="Box Images", 
                                            variable=self.box_image_var, onvalue=1, offvalue=0,
                                            command=self.update_display)
        self.box_image_checkbox.select()
        self.box_image_checkbox.pack(side=tk.LEFT, padx=1)
        
        self.reset_button = tk.Button(control_frame, text="Reset View", command=self.reset_view)
        self.reset_button.pack(side=tk.LEFT, padx=1)
        
        # 선택 관련 버튼들 (원래 control_panel_bottom에 있던 것을 여기로 이동)
        selection_frame = tk.Frame(control_frame)  # 그룹화를 위한 프레임
        selection_frame.pack(side=tk.LEFT, padx=1)

        # 전체 선택/해제 버튼을 하나의 토글 버튼으로 변경
        self.selection_state = tk.BooleanVar(value=False)  # 선택 상태 추적
        self.selection_toggle_button = tk.Button(
            selection_frame, 
            text="전체 선택", 
            command=self.toggle_all_selection,
            width=10
        )
        self.selection_toggle_button.pack(side=tk.LEFT)

        # 키보드 단축키 추가 (Ctrl+A: 전체 선택/해제 토글)
        self.root.bind("<Control-a>", lambda e: self.toggle_all_selection())
        self.delete_labels_button = tk.Button(control_frame, text="선택 삭제", 
                                        command=self.delete_selected_labels,
                                        bg="#ffcccc")  # 위험 동작임을 표시하기 위한 빨간 배경
        self.delete_labels_button.pack(side=tk.LEFT, padx=1)    

        # 클래스 변경 버튼 추가
        self.change_class_button = tk.Button(control_frame, text="클래스 변경", 
                                        command=self.change_class_labels)
        self.change_class_button.pack(side=tk.LEFT, padx=1)

        self.label_to_mask_button = tk.Button(control_frame, text="Label→Mask", 
                                        command=self.convert_label_to_mask)
        self.label_to_mask_button.pack(side=tk.LEFT, padx=1)

        # 데이터 리프레시 버튼 추가
        self.refresh_button = tk.Button(control_frame, text="데이터 리프레시", 
                                    command=self.refresh_data)
        self.refresh_button.pack(side=tk.LEFT, padx=1)

        self.setup_pagination_ui()

        similar_box_button = tk.Button(
        self.control_panel_top,  # 또는 적절한 부모 컨테이너
        text="유사 박스 처리",
        command=self.select_similar_boxes)
        similar_box_button.pack(side=tk.LEFT, padx=1)  # 또는 적절한 배치

        # 두 번째 줄 - 겹침 필터 관련 UI
        filter_frame = tk.Frame(self.control_panel_bottom)
        filter_frame.pack(side=tk.LEFT, fill="x", padx=0)
        
        # 겹침 필터 타이틀 및 설명
        filter_header_frame = tk.Frame(filter_frame)
        filter_header_frame.pack(side=tk.TOP, fill="x")
        
        overlap_label = tk.Label(filter_header_frame, text="겹침 필터:", font=("Arial", 9, "bold"))
        overlap_label.pack(side=tk.LEFT, padx=1)
        
        # 색상 범례 추가
        color_legend_frame = tk.Frame(filter_header_frame)
        color_legend_frame.pack(side=tk.LEFT, padx=10)
        
        tk.Label(color_legend_frame, text="색상 구분:", font=("Arial", 8)).pack(side=tk.LEFT)
        
        # 색상 샘플 표시
        for color, desc, iou_range in [
            ("yellow", "낮음", "<0.3"), 
            ("orange", "중간", "0.3-0.5"), 
            ("red", "높음", "0.5-0.7"), 
            ("purple", "매우 높음", ">0.7")
        ]:
            color_frame = tk.Frame(color_legend_frame, bg=color, width=15, height=15)
            color_frame.pack(side=tk.LEFT, padx=1)
            tk.Label(color_legend_frame, text=f"{desc}({iou_range})", 
                    font=("Arial", 7)).pack(side=tk.LEFT, padx=1)
            
        self.ctrl_status_label = tk.Label(
            self.control_panel_bottom, 
            text="Ctrl: ⬛", 
            font=("Arial", 9, "bold"),
            fg="gray"
        )
        
        # 겹침 컨트롤 프레임
        filter_controls_frame = tk.Frame(filter_frame)
        filter_controls_frame.pack(side=tk.TOP, fill="x")
        
        # 겹침 대상 클래스 선택 드롭다운
        overlap_class_label = tk.Label(filter_controls_frame, text="대상 클래스:")
        overlap_class_label.pack(side=tk.LEFT, padx=1)
        
        self.overlap_class_selector = tk.StringVar()
        self.overlap_class_selector.set("선택 안함")
        self.overlap_class_dropdown = tk.OptionMenu(filter_controls_frame, self.overlap_class_selector, "선택 안함")
        self.overlap_class_dropdown.config(width=10)
        self.overlap_class_dropdown.pack(side=tk.LEFT, padx=1)
        
        # 겹침 필터 옵션 라디오 버튼
        filter_options_frame = tk.Frame(filter_controls_frame)
        filter_options_frame.pack(side=tk.LEFT, padx=5)
        
        tk.Radiobutton(filter_options_frame, text="모두 보기", variable=self.overlap_filter_var, 
                    value="모두 보기", command=self.update_display).pack(side=tk.LEFT)
        tk.Radiobutton(filter_options_frame, text="겹치는 것만", variable=self.overlap_filter_var, 
                    value="겹치는 것만", command=self.update_display).pack(side=tk.LEFT)
        tk.Radiobutton(filter_options_frame, text="겹치지 않는 것만", variable=self.overlap_filter_var, 
                    value="겹치지 않는 것만", command=self.update_display).pack(side=tk.LEFT)
        
        # 필터링 결과 정보 레이블
        self.filter_info_label = tk.Label(filter_controls_frame, text="", font=("Arial", 9))
        self.filter_info_label.pack(side=tk.LEFT, padx=5)
        
        # 선택 정보 (오른쪽 정렬)
        selection_frame = tk.Frame(self.control_panel_bottom)
        selection_frame.pack(side=tk.RIGHT, padx=2)
        
        # 전체 데이터셋 통계 정보
        self.dataset_info_label = tk.Label(selection_frame, text="", font=("Arial", 8))
        self.dataset_info_label.pack(side=tk.RIGHT, padx=2)
        
        self.selection_info_label = tk.Label(selection_frame, text="Selected Images: 0", width=15)
        self.selection_info_label.pack(side=tk.RIGHT, padx=2)

        # Main display area
        self.canvas_frame = tk.Frame(self.main_frame)
        self.canvas_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.canvas = tk.Canvas(self.canvas_frame, borderwidth=0, background="white")
        self.scrollbar = tk.Scrollbar(self.canvas_frame, orient="vertical", command=self.canvas.yview)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.frame = tk.Frame(self.canvas)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.frame, anchor="nw")
        
        # Event bindings
        self.canvas.bind("<Configure>", self.on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self.on_mousewheel)
        self.class_selector.trace_add("write", lambda *args: self.update_display())
        self.class_selector.trace_add("write", self.on_class_changed)
        self.overlap_class_selector.trace_add("write", lambda *args: self.reset_overlap_cache())
        self.overlap_class_selector.trace_add("write", lambda *args: self.update_display())

        self.root.bind("<Button-1>", self.handle_left_click)

        self.setup_keyboard_events()
        self.add_similar_label_controls()
    def toggle_all_selection(self):
        """전체 선택/해제를 토글합니다."""
        # 현재 상태 확인 (선택된 이미지가 있으면 해제, 없으면 선택)
        if self.selected_image_labels:
            # 현재 선택된 것이 있으면 전체 해제
            self.deselect_all_images()
            self.selection_toggle_button.config(text="전체 선택")
            self.selection_state.set(False)
        else:
            # 현재 선택된 것이 없으면 전체 선택
            self.select_all_images()
            self.selection_toggle_button.config(text="전체 해제")
            self.selection_state.set(True)
    def log_system_info(self):
        """시스템 정보 로깅"""
        try:
            import platform
            import psutil
            
            self.logger.info("===== 시스템 정보 =====")
            self.logger.info(f"OS: {platform.platform()}")
            self.logger.info(f"Python: {platform.python_version()}")
            
            # 메모리 정보
            mem = psutil.virtual_memory()
            self.logger.info(f"Memory: Total={mem.total/(1024**3):.2f}GB, Available={mem.available/(1024**3):.2f}GB")
            
            # CPU 정보
            self.logger.info(f"CPU: {psutil.cpu_count(logical=False)} cores, {psutil.cpu_count()} threads")
            
            # 디스크 정보
            disk = psutil.disk_usage('/')
            self.logger.info(f"Disk: Total={disk.total/(1024**3):.2f}GB, Free={disk.free/(1024**3):.2f}GB")
            
            # 화면 정보
            if hasattr(self.root, 'winfo_screenwidth') and hasattr(self.root, 'winfo_screenheight'):
                screen_width = self.root.winfo_screenwidth()
                screen_height = self.root.winfo_screenheight()
                self.logger.info(f"Screen: {screen_width}x{screen_height}")
            
            self.logger.info("===== 시스템 정보 끝 =====")
            
        except ImportError as e:
            self.logger.warning(f"시스템 정보 수집 중 ImportError: {e}")
            self.logger.warning("psutil 라이브러리가 설치되지 않았습니다. 시스템 정보를 완전히 로깅할 수 없습니다.")
            
            # platform 모듈을 통해 제한된 정보라도 로깅
            try:
                import platform
                self.logger.info(f"OS: {platform.platform()}")
                self.logger.info(f"Python: {platform.python_version()}")
            except ImportError:
                self.logger.warning("platform 모듈도 임포트할 수 없습니다.")
        
        except Exception as e:
            self.logger.error(f"시스템 정보 로깅 중 오류: {e}")
    def setup_logging(self):
        """로깅 시스템 설정"""
        import logging
        
        # 로그 디렉토리 생성
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
        os.makedirs(log_dir, exist_ok=True)
        
        # 로거 설정
        logger = logging.getLogger("ImageViewer")
        logger.setLevel(logging.INFO)
        
        # 파일 핸들러
        log_file = os.path.join(log_dir, f"image_viewer_{self.current_datetime}.log")
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        
        # 콘솔 핸들러
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # 포맷 설정
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        # 핸들러 추가
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        # 시작 메시지 로깅
        logger.info("===== 이미지 뷰어 애플리케이션 시작 =====")
        logger.info(f"시작 시간: {self.current_datetime}")
        
        return logger
    def setup_performance_settings(self):
        """성능 최적화 설정"""
        # 시스템 메모리에 따른 캐시 크기 조정
        try:
            import psutil
            total_mem_gb = psutil.virtual_memory().total / (1024**3)
            
            # 메모리 크기에 따른 페이지 크기 조정
            if total_mem_gb < 4:  # 4GB 미만
                self.page_size = 100
                self.cache_limit = 500
            elif total_mem_gb < 8:  # 8GB 미만
                self.page_size = 200
                self.cache_limit = 1000
            elif total_mem_gb < 16:  # 16GB 미만
                self.page_size = 350
                self.cache_limit = 2000
            else:  # 16GB 이상
                self.page_size = 500
                self.cache_limit = 5000
            
            # 로그 메시지 (logger가 설정된 경우)
            if hasattr(self, 'logger'):
                self.logger.info(f"메모리 기반 설정: 페이지 크기={self.page_size}, 캐시 제한={self.cache_limit}")
            else:
                print(f"메모리 기반 설정: 페이지 크기={self.page_size}, 캐시 제한={self.cache_limit}")
        except ImportError:
            # 기본값 사용
            self.page_size = 200
            self.cache_limit = 1000
            print("기본 설정 사용: 페이지 크기=200, 캐시 제한=1000")
        
        # 파이썬 GC 설정 조정
        gc.set_threshold(100, 5, 5)  # GC 임계값 조정하여 더 자주 수집하도록 설정
        
        # 멀티스레딩을 위한 스레드 수 계산
        try:
            import multiprocessing
            self.worker_threads = max(1, multiprocessing.cpu_count() - 1)  # UI 스레드용으로 하나 남김
        except:
            self.worker_threads = 2  # 기본값
        
        # 로그 메시지
        if hasattr(self, 'logger'):
            self.logger.info(f"작업자 스레드 수: {self.worker_threads}")
        else:
            print(f"작업자 스레드 수: {self.worker_threads}")

    def setup_caching(self):
        """캐시 시스템 설정"""
        # 캐시 딕셔너리 생성 - OrderedDict로 LRU 캐시 구현
        self.label_cache = OrderedDict()
        self.image_cache = OrderedDict()
        
        # 캐시 통계
        self.cache_hits = {'label': 0, 'image': 0}
        self.cache_misses = {'label': 0, 'image': 0}
        
        # 캐시 적중률 로깅 타이머 설정
        self.last_cache_stat_time = time.time()
        self.root.after(300000, self.log_cache_stats)  # 5분마다 로깅

    def log_cache_stats(self):
        """캐시 통계 로깅"""
        total_hits = sum(self.cache_hits.values())
        total_misses = sum(self.cache_misses.values())
        total_accesses = total_hits + total_misses
        
        if total_accesses > 0:
            hit_rate = total_hits / total_accesses * 100
            self.logger.info(f"캐시 통계: 적중={total_hits}, 미스={total_misses}, 적중률={hit_rate:.2f}%")
            self.logger.info(f"캐시 크기: 라벨={len(self.label_cache)}, 이미지={len(self.image_cache)}")
        
        # 다음 로깅 일정 설정
        self.root.after(300000, self.log_cache_stats)  # 5분마다 반복

    def perform_memory_cleanup(self):
        """메모리 정리 작업 수행"""
        print("메모리 정리 작업 시작...")
        
        # 1. 캐시 크기 줄이기 (OrderedDict 사용)
        target_size = int(self.cache_limit * 0.7)  # 30% 줄이기
        removed_label_count = 0
        removed_image_count = 0

        # 라벨 캐시 정리 (OrderedDict의 popitem(last=False) 사용)
        while len(self.label_cache) > target_size:
            self.label_cache.popitem(last=False)
            removed_label_count += 1

        # 이미지 캐시 정리 (OrderedDict의 popitem(last=False) 사용)
        while len(self.image_cache) > target_size:
            self.image_cache.popitem(last=False)
            removed_image_count += 1
        
        # 2. 미사용 데이터 정리
        # 현재 표시되지 않은 이미지 관련 데이터 정리
        current_display_paths = set()
        
        # 현재 화면에 표시된 라벨 경로 수집
        for widget in self.frame.winfo_children():
            if hasattr(widget, 'label_path'):
                current_display_paths.add(widget.label_path)
        
        # 표시되지 않는 이미지 캐시 정리 (현재 페이지에 없는 이미지)
        cleaned_paths = 0
        for key in list(self.image_cache.keys()):
            if isinstance(key, str) and not any(path in key for path in current_display_paths):
                del self.image_cache[key]
                cleaned_paths += 1
        
        # 3. 명시적 가비지 컬렉션 수행
        gc.collect()
        
        print(f"메모리 정리 완료: 라벨 캐시 {removed_label_count}개, 이미지 캐시 {removed_image_count}개, 미사용 경로 {cleaned_paths}개 제거")
        
        # 로그 남기기
        if hasattr(self, 'logger'):
            self.logger.info(f"메모리 정리: 라벨 캐시 {removed_label_count}개, 이미지 캐시 {removed_image_count}개 제거")
    def setup_ui_addition(self):
        # 이 코드를 setup_ui 메서드 마지막 부분에 추가
        self.setup_keyboard_events()
        self.add_similar_label_controls()

    def reset_overlap_cache(self):
        """겹침 캐시 초기화"""
        self.overlap_cache = {}
        # 값이 변경되면 디스플레이 업데이트
        if self.overlap_filter_var.get() != "모두 보기" and self.overlap_class_selector.get() != "선택 안함":
            self.update_display()
    def update_cache_access(self, cache_type, key):
        """캐시 접근 순서를 업데이트합니다 (OrderedDict의 move_to_end 사용)."""
        try:
            if cache_type == 'label' and key in self.label_cache:
                self.label_cache.move_to_end(key)
            elif cache_type == 'image' and key in self.image_cache:
                self.image_cache.move_to_end(key)
        except KeyError:
            # 키가 없는 경우 무시
            pass

    def manage_cache_size(self, cache_type):
        """LRU 전략으로 캐시 크기를 관리합니다 (OrderedDict의 popitem 사용)."""
        if cache_type == 'label':
            while len(self.label_cache) > self.cache_limit:
                # popitem(last=False)로 가장 오래된 항목 제거 (O(1))
                self.label_cache.popitem(last=False)
        elif cache_type == 'image':
            while len(self.image_cache) > self.cache_limit:
                # popitem(last=False)로 가장 오래된 항목 제거 (O(1))
                self.image_cache.popitem(last=False)
    def initial_setup(self, file_path):
        """Initialize/reset all instance variables when loading new data"""
        # Reset paths and file info
        self.rootpath = os.path.dirname(file_path)
        self.filename = os.path.basename(file_path)
        self.current_datetime = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Reset data structures
        self.image_paths = []
        self.labels = []
        self.labelsdata = [[] for _ in range(100)]
        
        # Reset selection state
        self.selected_image_labels = []
        for widget in self.checklist:
            if widget.winfo_exists():
                widget.destroy()
        self.checklist = []
        
        # Reset pagination
        self.current_page = 0
        self.total_pages = 0

        self.overlap_cache = {}
        
        # Reset filter stats
        self.filter_stats = {"total": 0, "overlapping": 0, "non_overlapping": 0}
        self.filter_info_label.config(text="")
        
        # Clear display
        for widget in self.frame.winfo_children():
            widget.destroy()
        
        # Force garbage collection
        gc.collect()
    def flash_widget(self, widget, color, times=3, delay=50):
        """위젯에 깜빡임 효과를 적용합니다."""
        if times <= 0:
            return
            
        orig_bg = widget.cget("bg")
        widget.config(bg=color)
        
        def revert():
            widget.config(bg=orig_bg)
            self.root.after(delay, lambda: self.flash_widget(widget, color, times-1, delay))
            
        self.root.after(delay, revert)
    def show_status_message(self, message, duration=3000):
        """상태 표시줄에 메시지를 표시합니다."""
        if hasattr(self, 'status_bar'):
            self.status_bar.config(text=message)
            # 일정 시간 후 메시지 초기화
            self.root.after(duration, lambda: self.status_bar.config(text="준비됨"))
    def update_iou_value(self):
        """IoU 임계값 레이블 업데이트"""
        self.iou_value_label.config(text=f"{self.iou_threshold_var.get():.2f}")
        # 캐시 초기화 - IoU 임계값이 변경되면 겹침 결과가 달라질 수 있음
        self.reset_overlap_cache()
        # 값이 변경되면 디스플레이 업데이트
        self.update_display()
    def load_data(self):
        """멀티스레딩을 활용한 이미지 및 라벨 데이터 로드"""
        # 이미 로딩 중이면 무시 (중복 로딩 방지)
        if self.data_loading:
            print("[WARNING] 이미 데이터를 로딩 중입니다. 중복 로딩 무시.")
            return

        file_path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
        if not file_path:
            return

        self.initial_setup(file_path)
        self.data_loading = True  # 로딩 상태 설정
        
        try:
            # 진행 창 생성
            progress_window = tk.Toplevel(self.root)
            progress_window.title("데이터 로드 중")
            
            # 창 위치 중앙 정렬
            window_width = 400
            window_height = 150
            position_right = int(self.root.winfo_x() + (self.root.winfo_width() - window_width) / 2)
            position_down = int(self.root.winfo_y() + (self.root.winfo_height() - window_height) / 2)
            progress_window.geometry(f"{window_width}x{window_height}+{position_right}+{position_down}")
            
            # 창을 항상 위에 표시하고 모달로 설정
            progress_window.transient(self.root)
            progress_window.grab_set()
            
            # 진행 상황 표시 요소 생성
            file_label = tk.Label(progress_window, text="파일 읽는 중...", anchor='w')
            file_label.pack(padx=20, pady=(10,0), fill='x')
            
            progress_bar = ttk.Progressbar(progress_window, length=360, mode='determinate')
            progress_bar.pack(padx=20, pady=(5,0))
            
            status_label = tk.Label(progress_window, text="")
            status_label.pack(padx=20, pady=(5,0), fill='x')
            
            detail_label = tk.Label(progress_window, text="", anchor='w')
            detail_label.pack(padx=20, pady=(5,10), fill='x')
            
            progress_window.update()
            
            # 파일 읽기 (UI 스레드에서 빠르게 수행)
            file_encoding = self.detect_file_encoding(file_path)
            with open(file_path, encoding=file_encoding) as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]
                
            total_lines = len(lines)
            progress_bar['maximum'] = total_lines
            
            # 작업 대기열 및 결과 대기열 생성
            task_queue = queue.Queue()
            result_queue = queue.Queue()
            
            # 작업 추가
            for i, line in enumerate(lines):
                task_queue.put((i, line))

            print(f"작업 큐에 {task_queue.qsize()}개 작업 추가됨")

            # 작업자 스레드 함수 정의
            def worker():
                processed_count = 0
                while True:
                    try:
                        idx, line = task_queue.get(timeout=1)  # 1초 타임아웃
                        img_path = line
                        label_path = self.convert_jpegimages_to_labels(line)

                        # 추가 검증 작업 (파일 존재 확인 등)
                        img_exists = os.path.isfile(img_path)
                        label_exists = os.path.isfile(label_path)

                        result_queue.put((idx, img_path, label_path, img_exists, label_exists))
                        task_queue.task_done()
                        processed_count += 1
                    except queue.Empty:
                        # 큐가 비어있으면 종료
                        break
                    except Exception as e:
                        print(f"작업자 스레드 오류: {e}")
                        import traceback
                        traceback.print_exc()
                        try:
                            task_queue.task_done()
                        except:
                            pass
                print(f"작업자 스레드 종료: {processed_count}개 처리")
            
            # 작업자 스레드 시작 (CPU 코어 수에 맞게 조정)
            import multiprocessing
            num_workers = max(1, multiprocessing.cpu_count() - 1)  # 하나는 UI 스레드용으로 남김
            print(f"작업자 스레드 수: {num_workers}")
            threads = []

            for i in range(num_workers):
                t = threading.Thread(target=worker, name=f"Worker-{i}")
                t.daemon = True  # 메인 스레드 종료 시 함께 종료
                t.start()
                threads.append(t)
                print(f"스레드 {i} 시작됨")

            # 처리된 항목 카운터 초기화
            processed = 0
            print("update_progress 함수 스케줄링...")
            
            # 진행 상황 업데이트 및 결과 처리 함수 정의
            def update_progress():
                nonlocal processed

                print(f"[DEBUG] update_progress 호출됨 - processed={processed}/{total_lines}, result_queue size={result_queue.qsize()}")

                # 결과 대기열에서 데이터 가져오기 (최대 1000개씩 배치 처리)
                results_to_process = []
                max_batch_size = 1000
                try:
                    batch_count = 0
                    while batch_count < max_batch_size:  # 배치 크기 제한
                        results_to_process.append(result_queue.get(block=False))
                        result_queue.task_done()
                        batch_count += 1
                except queue.Empty:
                    pass

                print(f"[DEBUG] 이번 배치에서 {len(results_to_process)}개 결과 처리")

                # 결과 처리
                for idx, img_path, label_path, img_exists, label_exists in results_to_process:
                    self.image_paths.append(img_path)
                    self.labels.append(label_path)
                    processed += 1

                    # 진행 상태 표시 업데이트 (매 10개 파일마다)
                    if processed % 10 == 0 or processed == total_lines:
                        detail_label.config(text=f"현재 파일: {os.path.basename(img_path)}")

                # UI 업데이트
                progress = (processed / total_lines) * 100 if total_lines > 0 else 0
                progress_bar['value'] = processed
                status_label.config(text=f"진행 상황: {progress:.1f}% ({processed}/{total_lines} 파일)")
                progress_window.update()  # 강제 UI 업데이트

                # 모든 작업이 완료되었는지 확인
                is_complete = processed >= total_lines
                all_threads_done = all(not t.is_alive() for t in threads)
                queues_empty = task_queue.empty() and result_queue.empty()

                print(f"[DEBUG] 완료 상태: processed={is_complete}, threads={all_threads_done}, queues={queues_empty}")

                if is_complete or (queues_empty and all_threads_done):
                    # 작업 완료 - 마무리 단계
                    print("[DEBUG] 작업 완료, 마무리 단계 시작")
                    self.finalize_data_loading(progress_window)
                else:
                    # 아직 진행 중 - 100ms 후 다시 확인
                    self.root.after(100, update_progress)

            # 첫 번째 업데이트 시작
            print("[DEBUG] 첫 번째 update_progress 스케줄링 (100ms 후)")
            self.root.after(100, update_progress)
            
        except Exception as e:
            print(f"데이터 로드 오류: {e}")
            import traceback
            traceback.print_exc()
            self.data_loading = False  # 로딩 상태 해제
            if 'progress_window' in locals():
                progress_window.destroy()
    def detect_file_encoding(self, file_path):
        """파일 인코딩을 감지합니다."""
        encodings_to_try = ['utf-8', 'cp949', 'euc-kr', 'latin-1']
        
        for encoding in encodings_to_try:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    f.read(100)  # 작은 샘플만 읽기
                    return encoding
            except UnicodeDecodeError:
                continue
        
        return 'utf-8'  # 기본값
    def finalize_data_loading(self, progress_window):
        """데이터 로딩 완료 후 마무리 작업"""
        try:
            print("[DEBUG] finalize_data_loading 시작")
            print("[DEBUG] update_class_dropdown 호출 (동기 방식)")
            # 클래스 정보 업데이트 (progress_window와 완료 콜백 전달)
            self.update_class_dropdown(
                existing_progress_window=progress_window,
                completion_callback=lambda: self.finalize_ui_update(progress_window)
            )

        except Exception as e:
            print(f"데이터 로딩 마무리 오류: {e}")
            import traceback
            traceback.print_exc()
            self.data_loading = False  # 로딩 상태 해제
            if progress_window and progress_window.winfo_exists():
                progress_window.destroy()

    def finalize_ui_update(self, progress_window):
        """UI 업데이트 마무리 (메인 스레드에서 실행)"""
        try:
            print("[DEBUG] finalize_ui_update 시작")
            print(f"[DEBUG] image_paths 수: {len(self.image_paths)}")
            print(f"[DEBUG] labels 수: {len(self.labels)}")
            print(f"[DEBUG] labelsdata 수: {sum(len(x) for x in self.labelsdata)}")

            # 페이지네이션 업데이트
            self.total_pages = (len(self.image_paths) + self.page_size - 1) // self.page_size
            print(f"[DEBUG] total_pages: {self.total_pages}")
            self.update_pagination_controls()
            print("[DEBUG] update_pagination_controls 완료")

            # 첫 페이지 표시
            self.current_page = 0
            print("[DEBUG] update_display 호출 시작")
            self.update_display()
            print("[DEBUG] update_display 완료")

            # 로딩 상태 해제
            self.data_loading = False
            print("[DEBUG] data_loading = False 설정")

            # 진행 창 업데이트 및 닫기
            if progress_window and progress_window.winfo_exists():
                print("[DEBUG] progress_window 업데이트 시작")
                progress_window.title("로딩 완료")

                # 위젯 인덱스 오류 방지
                widgets = progress_window.winfo_children()
                if len(widgets) >= 3:
                    file_label = widgets[0]  # 첫 번째 라벨
                    status_label = widgets[2]  # 세 번째 라벨

                    file_label.config(text="데이터 로딩 완료!")
                    status_label.config(text=f"{len(self.image_paths)}개 이미지 성공적으로 로드됨")

                    # 닫기 버튼 추가
                    status_label.config(text=f"데이터 로드 완료. 창이 자동으로 닫힙니다...")

                # 자동 닫기 시간 단축 (1.5초 후)
                self.root.after(1500, progress_window.destroy)
                print("[DEBUG] progress_window 자동 닫기 예약")

            print("[DEBUG] finalize_ui_update 완료")

        except Exception as e:
            print(f"UI 업데이트 마무리 오류: {e}")
            import traceback
            traceback.print_exc()
            self.data_loading = False  # 로딩 상태 해제
            if progress_window and progress_window.winfo_exists():
                progress_window.destroy()
    def setup_task_queue(self):
        """작업 대기열 설정"""
        import queue
        
        # 작업 대기열 생성
        self.task_queue = queue.Queue()
        self.result_queue = queue.Queue()
        
        # 작업자 스레드 시작
        for i in range(self.worker_threads):
            threading.Thread(target=self.worker_thread_func, daemon=True).start()
        
        # 결과 처리 타이머 시작
        self.root.after(100, self.process_results)

    def worker_thread_func(self):
        """작업자 스레드 함수"""
        while True:
            try:
                # 대기열에서 작업 가져오기
                task_type, task_data = self.task_queue.get()
                
                if task_type == "load_label":
                    # 라벨 파일 로드 작업
                    label_path = task_data
                    result = self.load_label_file_worker(label_path)
                    self.result_queue.put(("label", label_path, result))
                
                elif task_type == "load_image":
                    # 이미지 파일 로드 작업
                    img_path, size = task_data
                    result = self.load_image_worker(img_path, size)
                    self.result_queue.put(("image", img_path, result))
                
                elif task_type == "save_data":
                    # 데이터 저장 작업
                    save_path, data = task_data
                    result = self.save_data_worker(save_path, data)
                    self.result_queue.put(("save", save_path, result))
                
                elif task_type == "process_batch":
                    # 배치 처리 작업
                    batch_type, batch_data = task_data
                    result = self.process_batch_worker(batch_type, batch_data)
                    self.result_queue.put((f"batch_{batch_type}", batch_data, result))
                
                # 작업 완료 표시
                self.task_queue.task_done()
                
            except Exception as e:
                self.logger.error(f"작업자 스레드 오류: {e}")
                if 'task_type' in locals() and 'task_data' in locals():
                    self.result_queue.put((f"error_{task_type}", task_data, str(e)))
                    self.task_queue.task_done()

    def process_results(self):
        """결과 대기열 처리"""
        try:
            # 처리할 결과가 있는지 확인
            results_to_process = []
            try:
                while True:  # 대기열에 있는 모든 결과 가져오기
                    results_to_process.append(self.result_queue.get(block=False))
                    self.result_queue.task_done()
            except queue.Empty:
                pass
            
            # 결과 처리
            for result_type, data, result in results_to_process:
                try:
                    if result_type == "label":
                        # 라벨 파일 로드 결과 처리
                        label_path = data
                        self.label_cache[label_path] = {
                            'data': result,
                            'timestamp': os.path.getmtime(label_path),
                            'last_access': time.time()
                        }
                        
                        # LRU 캐시 업데이트
                        self.label_cache_ordered[label_path] = None
                        if len(self.label_cache) > self.cache_limit:
                            oldest = next(iter(self.label_cache_ordered))
                            del self.label_cache_ordered[oldest]
                            del self.label_cache[oldest]
                    
                    elif result_type == "image":
                        # 이미지 로드 결과 처리
                        img_path, size = data if isinstance(data, tuple) else (data, None)
                        cache_key = f"{img_path}_{size}" if size else img_path
                        
                        if result is not None:
                            self.image_cache[cache_key] = result
                            
                            # LRU 캐시 업데이트
                            self.image_cache_ordered[cache_key] = None
                            if len(self.image_cache) > self.cache_limit:
                                oldest = next(iter(self.image_cache_ordered))
                                del self.image_cache_ordered[oldest]
                                del self.image_cache[oldest]
                    
                    elif result_type.startswith("batch_"):
                        # 배치 처리 결과 처리
                        batch_type = result_type[6:]  # "batch_" 제거
                        if batch_type == "delete":
                            self.handle_batch_delete_result(data, result)
                        elif batch_type == "change_class":
                            self.handle_batch_class_change_result(data, result)
                    
                    elif result_type.startswith("error_"):
                        # 오류 처리
                        error_type = result_type[6:]  # "error_" 제거
                        self.logger.error(f"{error_type} 작업 중 오류: {result}")
                        
                        # UI에 오류 메시지 표시
                        if hasattr(self, 'show_status_message'):
                            self.show_status_message(f"작업 오류: {error_type} - {result}", duration=5000)
                
                except Exception as e:
                    self.logger.error(f"결과 처리 중 오류: {e}")
        
        except Exception as e:
            self.logger.error(f"결과 처리 루프 오류: {e}")
        
        finally:
            # 다음 결과 처리 일정 설정
            self.root.after(100, self.process_results)
    def setup_pagination_ui(self):
        """페이지네이션 UI 설정 - 직접 페이지 입력 기능 추가"""
        # 페이지네이션 컨트롤 프레임
        self.pagination_frame = tk.Frame(self.control_panel_bottom)
        self.pagination_frame.pack(side=tk.RIGHT, padx=5)

        # 페이지 크기 조절 UI (왼쪽)
        page_size_frame = tk.Frame(self.pagination_frame)
        page_size_frame.pack(side=tk.LEFT, padx=(0, 15))

        tk.Label(page_size_frame, text="전체:", font=("Arial", 9)).pack(side=tk.LEFT, padx=2)
        self.total_files_label = tk.Label(page_size_frame, text="0개", font=("Arial", 9, "bold"))
        self.total_files_label.pack(side=tk.LEFT, padx=2)

        tk.Label(page_size_frame, text=" | 페이지 크기:", font=("Arial", 9)).pack(side=tk.LEFT, padx=(10, 2))
        self.page_size_entry = tk.Entry(page_size_frame, width=5, justify=tk.CENTER)
        self.page_size_entry.insert(0, str(self.page_size))
        self.page_size_entry.pack(side=tk.LEFT, padx=2)

        apply_page_size_btn = tk.Button(page_size_frame, text="적용", width=4, command=self.apply_page_size)
        apply_page_size_btn.pack(side=tk.LEFT, padx=2)

        # 구분선
        tk.Frame(self.pagination_frame, width=2, bg="gray").pack(side=tk.LEFT, fill="y", padx=10)

        # 이전 버튼
        self.prev_button = tk.Button(self.pagination_frame, text="◀", width=3, command=self.prev_page)
        self.prev_button.pack(side=tk.LEFT)

        # 페이지 입력 프레임
        page_input_frame = tk.Frame(self.pagination_frame)
        page_input_frame.pack(side=tk.LEFT, padx=3)

        # 페이지 입력 필드 (엔트리)
        self.page_entry = tk.Entry(page_input_frame, width=5, justify=tk.CENTER)
        self.page_entry.pack(side=tk.LEFT)

        # 페이지 구분자와 전체 페이지 레이블
        self.total_pages_label = tk.Label(page_input_frame, text="/0")
        self.total_pages_label.pack(side=tk.LEFT, padx=2)

        # 페이지 범위 표시 레이블
        self.page_range_label = tk.Label(page_input_frame, text="(0-0)")
        self.page_range_label.pack(side=tk.LEFT, padx=5)

        # 페이지 이동 버튼
        go_page_button = tk.Button(self.pagination_frame, text="이동", width=4, command=self.go_to_entered_page)
        go_page_button.pack(side=tk.LEFT, padx=3)

        # 다음 버튼
        self.next_button = tk.Button(self.pagination_frame, text="▶", width=3, command=self.next_page)
        self.next_button.pack(side=tk.LEFT)

        # 페이지 입력 필드에 엔터 키 이벤트 바인딩
        self.page_entry.bind("<Return>", lambda event: self.go_to_entered_page())

        # 페이지네이션 상태 업데이트
        self.update_pagination_controls()

    # def update_pagination_controls(self):
    #     """페이지네이션 컨트롤 상태 업데이트"""
    #     # 페이지 입력 필드와 전체 페이지 레이블 업데이트
    #     self.page_entry.delete(0, tk.END)  # 기존 내용 삭제
    #     self.page_entry.insert(0, str(self.current_page + 1))  # 1부터 시작하는 페이지 번호 삽입
    #     self.total_pages_label.config(text=f"/{self.total_pages}")
        
    #     # 버튼 활성화/비활성화 상태 업데이트
    #     self.prev_button.config(state="normal" if self.current_page > 0 else "disabled")
    #     self.next_button.config(state="normal" if self.current_page < self.total_pages - 1 else "disabled")

    def go_to_entered_page(self):
        """입력된 페이지 번호로 이동"""
        try:
            # 입력 필드에서 페이지 번호 가져오기
            entered_page = int(self.page_entry.get())
            
            # 유효한 페이지 범위 확인 (1부터 total_pages까지)
            if 1 <= entered_page <= self.total_pages:
                # 내부 페이지 번호는 0부터 시작하므로 1 감소
                self.current_page = entered_page - 1
                self.update_display()
            else:
                # 유효하지 않은 페이지 번호인 경우 메시지 표시
                tk.messagebox.showwarning("페이지 오류", f"페이지 번호는 1부터 {self.total_pages}까지 입력 가능합니다.")
                # 현재 페이지로 다시 설정
                self.update_pagination_controls()
                
        except ValueError:
            # 숫자가 아닌 입력인 경우
            tk.messagebox.showwarning("입력 오류", "유효한 페이지 번호를 입력하세요.")
            # 현재 페이지로 다시 설정
            self.update_pagination_controls()
    def file_slice(self):
        """Split input file into smaller chunks with random sampling"""
        file_path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
        if not file_path:
            return

        dirpath = os.path.dirname(file_path)
        filename = os.path.basename(file_path)
        savepath = os.path.join(dirpath, "datalist")

        try:
            # 먼저 파일을 읽어서 전체 라인 개수 확인
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                total_lines = len(lines)

            # 전체 파일 개수를 표시하고 슬라이스 크기 입력받기
            slice_dialog = tk.Toplevel(self.root)
            slice_dialog.title("파일 슬라이스 설정")
            slice_dialog.geometry("400x200")
            slice_dialog.transient(self.root)
            slice_dialog.grab_set()

            # 중앙 정렬
            slice_dialog.update_idletasks()
            x = (slice_dialog.winfo_screenwidth() // 2) - (400 // 2)
            y = (slice_dialog.winfo_screenheight() // 2) - (200 // 2)
            slice_dialog.geometry(f"400x200+{x}+{y}")

            # 파일 정보 표시
            info_frame = tk.Frame(slice_dialog)
            info_frame.pack(pady=20, padx=20, fill=tk.X)

            tk.Label(info_frame, text=f"선택한 파일: {filename}",
                    font=("Arial", 10, "bold")).pack(anchor=tk.W)
            tk.Label(info_frame, text=f"전체 라인 개수: {total_lines}개",
                    font=("Arial", 10), fg="blue").pack(anchor=tk.W, pady=(5, 0))

            # 슬라이스 크기 입력
            input_frame = tk.Frame(slice_dialog)
            input_frame.pack(pady=10, padx=20, fill=tk.X)

            tk.Label(input_frame, text="슬라이스 크기 (파일당 라인 개수):",
                    font=("Arial", 9)).pack(side=tk.LEFT)

            slice_size_var = tk.StringVar(value="100")
            slice_entry = tk.Entry(input_frame, textvariable=slice_size_var, width=10)
            slice_entry.pack(side=tk.LEFT, padx=(10, 0))

            # 예상 파일 개수 표시
            estimated_label = tk.Label(input_frame, text="", font=("Arial", 9), fg="green")
            estimated_label.pack(side=tk.LEFT, padx=(10, 0))

            def update_estimated_files(*args):
                try:
                    size = int(slice_size_var.get())
                    if size > 0:
                        num_files = (total_lines + size - 1) // size
                        estimated_label.config(text=f"→ {num_files}개 파일 생성")
                    else:
                        estimated_label.config(text="")
                except ValueError:
                    estimated_label.config(text="")

            slice_size_var.trace('w', update_estimated_files)
            update_estimated_files()

            # 결과 저장 변수
            result = {'confirmed': False, 'size': 100}

            # 버튼 프레임
            button_frame = tk.Frame(slice_dialog)
            button_frame.pack(pady=20)

            def on_confirm():
                try:
                    size = int(slice_size_var.get())
                    if size <= 0:
                        tk.messagebox.showerror("오류", "슬라이스 크기는 1 이상이어야 합니다.")
                        return
                    if size > total_lines:
                        tk.messagebox.showwarning("경고",
                            f"슬라이스 크기({size})가 전체 라인 개수({total_lines})보다 큽니다.\n"
                            f"전체 파일이 하나의 파일로 복사됩니다.")
                    result['confirmed'] = True
                    result['size'] = size
                    slice_dialog.destroy()
                except ValueError:
                    tk.messagebox.showerror("오류", "유효한 숫자를 입력하세요.")

            def on_cancel():
                slice_dialog.destroy()

            tk.Button(button_frame, text="확인", width=10, command=on_confirm).pack(side=tk.LEFT, padx=5)
            tk.Button(button_frame, text="취소", width=10, command=on_cancel).pack(side=tk.LEFT, padx=5)

            # 엔터 키로 확인
            slice_entry.bind("<Return>", lambda e: on_confirm())
            slice_entry.focus_set()

            # 다이얼로그가 닫힐 때까지 대기
            slice_dialog.wait_window()

            # 취소한 경우
            if not result['confirmed']:
                return

            lines_per_file = result['size']
            num_files = (total_lines + lines_per_file - 1) // lines_per_file

            # 저장 폴더 생성
            if not os.path.isdir(savepath):
                os.mkdir(savepath)

            # 파일 슬라이싱 시작
            for i in range(num_files):
                current_lines = min(lines_per_file, len(lines))
                if current_lines == 0:
                    break

                random_lines = random.sample(lines, current_lines)
                output_file = os.path.join(savepath, f'{filename}_{i}.txt')

                with open(output_file, 'w', encoding='utf-8') as out_f:
                    out_f.writelines(random_lines)

                # Remove used lines from the pool
                for line in random_lines:
                    lines.remove(line)

                print(f"Saved file: {output_file}")

            if hasattr(self, 'show_status_message'):
                self.show_status_message(f"데이터 슬라이스 완료: {savepath}에 {num_files}개 파일 저장됨", duration=5000)

            # 자동으로 저장 폴더 열기 기능 추가
            if os.path.exists(savepath):
                try:
                    # 운영체제에 따라 적절한 명령 실행
                    import platform
                    if platform.system() == "Windows":
                        os.startfile(savepath)
                    elif platform.system() == "Darwin":  # macOS
                        import subprocess
                        subprocess.call(["open", savepath])
                    else:  # Linux
                        import subprocess
                        subprocess.call(["xdg-open", savepath])
                except Exception as e:
                    print(f"폴더 열기 오류: {e}")
        except Exception as e:
            print(f"Error during file slicing: {e}")
    def convert_label_to_mask(self):
        """선택한 이미지의 특정 바운딩 박스만 마스킹으로 변환"""
        if not self.selected_image_labels:
            print("마스킹할 이미지를 먼저 선택하세요.")
            return
        
        if not self.selected_label_info:
            print("마스킹할 라벨이 선택되지 않았습니다.")
            return
        
        # 선택된 바운딩 박스 수 계산
        total_boxes = sum(len(info['boxes']) for info in self.selected_label_info)

        current_class = self.class_selector.get()
        current_page = self.current_page

        # 경고 메시지 표시
        confirmation = tk.messagebox.askyesno(
            "라벨→마스크 변환 확인", 
            f"선택한 {len(self.selected_label_info)}개 이미지에서 {total_boxes}개의 바운딩 박스를 마스킹으로 변환하시겠습니까?\n"
            "이 작업은 되돌릴 수 없습니다."
        )
        
        if not confirmation:
            return
        
        # 진행 상황을 보여주는 창 생성
        progress_window = tk.Toplevel(self.root)
        progress_window.title("라벨→마스크 변환 중")
        progress_window.geometry("400x200")
        progress_window.transient(self.root)
        progress_window.grab_set()  # 모달 창으로 설정
        
        # 진행 상황 표시 요소
        progress_label = tk.Label(progress_window, text="선택한 바운딩 박스 마스킹 중...", font=("Arial", 10, "bold"))
        progress_label.pack(pady=(15, 5))
        
        info_label = tk.Label(progress_window, text=f"총 {total_boxes}개의 바운딩 박스를 마스킹합니다")
        info_label.pack(pady=5)
        
        progress_bar = ttk.Progressbar(progress_window, length=350)
        progress_bar.pack(pady=10)
        progress_bar["maximum"] = len(self.selected_label_info)
        
        status_label = tk.Label(progress_window, text="0/0 처리 완료")
        status_label.pack(pady=5)
        
        result_label = tk.Label(progress_window, text="")
        result_label.pack(pady=5)
        
        progress_window.update()
        
        # 변환 작업 수행
        converted_count = 0
        error_count = 0
        
        # 선택된 라벨 정보 별로 처리
        for i, label_info in enumerate(self.selected_label_info):
            try:
                label_path = label_info['path']
                
                # 진행 상황 업데이트
                progress_bar["value"] = i + 1
                status_label.config(text=f"{i+1}/{len(self.selected_label_info)} 처리 완료")
                result_label.config(text=f"변환: {converted_count}, 오류: {error_count}")
                progress_window.update()
                
                # 파일 존재 확인
                if not os.path.isfile(label_path):
                    error_count += 1
                    continue
                
                # 이미지 경로 가져오기
                img_path = self.convert_labels_to_jpegimages(label_path)
                if not os.path.exists(img_path):
                    img_path = img_path.replace(".jpg", ".png")
                    if not os.path.exists(img_path):
                        error_count += 1
                        continue
                
                # 백업 디렉토리 확인/생성
                d_path = 'original_backup/JPEGImages/'
                if not os.path.isdir(d_path):
                    os.makedirs(d_path)
                if not os.path.isdir('original_backup/labels/'):
                    os.makedirs(os.path.join('original_backup/labels/'))
                
                # 백업 생성
                backup_dir = 'original_backup'
                img_backup_dir = os.path.join(backup_dir, 'JPEGImages')
                label_backup_dir = os.path.join(backup_dir, 'labels')

                # 백업 디렉토리 구조 확인 및 생성
                os.makedirs(img_backup_dir, exist_ok=True)
                os.makedirs(label_backup_dir, exist_ok=True)

                # 백업 경로 생성
                img_rel_path = self.make_path(img_path)
                label_rel_path = self.make_path(label_path)

                img_backup = os.path.join(img_backup_dir, img_rel_path)
                label_backup = os.path.join(label_backup_dir, label_rel_path)

                # 백업 디렉토리 구조 생성
                os.makedirs(os.path.dirname(img_backup), exist_ok=True)
                os.makedirs(os.path.dirname(label_backup), exist_ok=True)

                # 파일 존재 확인 및 백업
                if not os.path.exists(img_backup) and os.path.exists(img_path):
                    try:
                        shutil.copyfile(img_path, img_backup)
                        print(f"이미지 백업 생성: {img_backup}")
                    except Exception as backup_error:
                        print(f"이미지 백업 실패: {str(backup_error)}")

                if not os.path.exists(label_backup) and os.path.exists(label_path):
                    try:
                        shutil.copyfile(label_path, label_backup)
                        print(f"라벨 백업 생성: {label_backup}")
                    except Exception as backup_error:
                        print(f"라벨 백업 실패: {str(backup_error)}")
                
                # 라벨 파일 읽기
                with open(label_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                # 마스킹할 박스 정보 추출
                mask_boxes = []
                filtered_lines = []
                
                # 삭제할 박스의 라인 인덱스 목록 생성 (중복 제거)
                box_line_indices = list(set([box['line_idx'] for box in label_info['boxes'] if 'line_idx' in box]))
                
                # 각 라인 처리
                for line_idx, line in enumerate(lines):
                    parts = line.strip().split()
                    if not parts:
                        filtered_lines.append(line)
                        continue
                    
                    try:
                        # 현재 라인이 마스킹할 박스인지 확인
                        if line_idx in box_line_indices:
                            # 마스킹할 박스 정보 추출
                            class_id = int(float(parts[0]))
                            x_center = float(parts[1])
                            y_center = float(parts[2])
                            width = float(parts[3])
                            height = float(parts[4])
                            
                            mask_boxes.append({
                                'class_id': class_id,
                                'x_center': x_center,
                                'y_center': y_center,
                                'width': width,
                                'height': height
                            })
                        else:
                            # 그 외 라인은 유지
                            filtered_lines.append(line)
                    except (ValueError, IndexError):
                        # 잘못된 형식의 라인은 유지
                        filtered_lines.append(line)
                
                # 마스킹할 박스가 있는 경우만 처리
                if mask_boxes:
                    # 이미지 로드
                    img = Image.open(img_path)
                    img_array = np.array(img)
                    
                    # 이미지 크기
                    img_height, img_width = img_array.shape[:2]
                    
                    # 각 마스킹 박스 처리
                    for box in mask_boxes:
                        # YOLO 형식 좌표 (중심 x, 중심 y, 너비, 높이)
                        cx, cy, w, h = box['x_center'], box['y_center'], box['width'], box['height']
                        
                        # 픽셀 좌표로 변환
                        x1 = int((cx - w/2) * img_width)
                        y1 = int((cy - h/2) * img_height)
                        x2 = int((cx + w/2) * img_width)
                        y2 = int((cy + h/2) * img_height)
                        
                        # 좌표를 이미지 범위 내로 제한
                        x1 = max(0, x1)
                        y1 = max(0, y1)
                        x2 = min(img_width - 1, x2)
                        y2 = min(img_height - 1, y2)
                        
                        # 해당 영역 마스킹 (마젠타 색)
                        img_array[y1:y2, x1:x2] = [255, 0, 255]
                    
                    # 마스킹된 이미지 저장
                    masked_img = Image.fromarray(img_array)
                    masked_img.save(img_path)
                    
                    # 변경된 라벨 파일 저장
                    with open(label_path, 'w', encoding='utf-8') as f:
                        f.writelines(filtered_lines)
                    
                    converted_count += 1
                
            except Exception as e:
                print(f"라벨 마스킹 중 오류 발생 ({label_path}): {e}")
                error_count += 1
            
            # 주기적으로 UI 업데이트
            if i % 10 == 0 or i == len(self.selected_label_info) - 1:
                progress_window.update()
        
        # 작업 완료 후 표시
        progress_label.config(text="라벨→마스크 변환 완료!")
        result_summary = f"총 {len(self.selected_label_info)}개 이미지 중 {converted_count}개 파일에서 바운딩 박스가 마스킹으로 변환되었습니다. 오류: {error_count}개"
        result_label.config(text=result_summary)

        # 선택 상태 초기화
        self.deselect_all_images()

        # 화면의 모든 썸네일 제거 (UI 클리어)
        for widget in self.frame.winfo_children():
            widget.destroy()

        # 클래스 정보 갱신 완료 후 호출될 콜백 정의
        def on_update_complete():
            """클래스 드롭다운 업데이트 완료 후 호출"""
            # 원래 클래스로 복원
            if current_class != "Select Class":
                self.class_selector.set(current_class)

            # 페이지 번호 조정
            self.current_page = min(current_page, self.total_pages - 1) if self.total_pages > 0 else 0
            if self.current_page < 0:
                self.current_page = 0

            # 화면 갱신
            self.update_display()

            # progress_window 닫기
            if progress_window and progress_window.winfo_exists():
                progress_window.destroy()

        # 클래스 정보 갱신 (비동기, 완료 후 on_update_complete 호출)
        self.update_class_dropdown(completion_callback=on_update_complete)

    def convert_view_to_original(self, view_x, view_y):
        """뷰 좌표를 원본 이미지 좌표로 변환"""
        # 줌 비율 고려하여 원본 좌표 계산
        original_x = int(view_x / self.zoom_ratio)
        original_y = int(view_y / self.zoom_ratio)
        return original_x, original_y

    def convert_original_to_view(self, original_x, original_y):
        """원본 이미지 좌표를 뷰 좌표로 변환"""
        view_x = int(original_x * self.zoom_ratio)
        view_y = int(original_y * self.zoom_ratio)
        return view_x, view_y
    
    def make_path(self, path):
        """
        경로에서 파일명을 안전하게 추출합니다.
        
        Args:
            path (str): 처리할 파일 경로
            
        Returns:
            str: 추출된 파일명 또는 빈 문자열
        """
        # 경로가 없는 경우 처리
        if not path:
            return ""
            
        # 입력 검증 - 문자열만 허용
        if not isinstance(path, str):
            return ""
            
        try:
            # 경로 정규화
            path = os.path.normpath(path)
            
            # os.path 모듈 사용하여 안전하게 파일명 추출
            basename = os.path.basename(path)
            
            # 추가 검증 - 상대 경로 공격 방지
            if '..' in basename or '/' in basename or '\\' in basename:
                # 위험한 문자가 포함된 경우 필터링
                basename = basename.replace('..', '').replace('/', '_').replace('\\', '_')
            
            # 파일명 유효성 확인 (운영체제별 금지 문자 필터링)
            invalid_chars = ['<', '>', ':', '"', '|', '?', '*']
            for char in invalid_chars:
                basename = basename.replace(char, '_')
                
            return basename
        
        except Exception as e:
            print(f"파일명 추출 오류: {e}")
            return os.path.basename(path) if path else ""

    def convert_jpegimages_to_labels(self, img_path):
        """
        JPEGImages 경로를 labels 경로로 변환 (.jpg → .txt)
        백슬래시(\)와 슬래시(/) 경로 모두 처리

        Args:
            img_path (str): JPEGImages 경로

        Returns:
            str: labels 경로
        """
        if not img_path:
            return ""

        # 백슬래시 경로 처리 (Windows UNC 경로 등)
        if "\\JPEGImages\\" in img_path:
            label_path = img_path.replace("\\JPEGImages\\", "\\labels\\")
        # 슬래시 경로 처리 (Unix/URL 스타일)
        elif "/JPEGImages/" in img_path:
            label_path = img_path.replace("/JPEGImages/", "/labels/")
        else:
            # 경로 구분자 없이 폴더명만 있는 경우 (fallback)
            label_path = img_path.replace("JPEGImages", "labels")

        # 확장자 변환
        label_path = label_path.replace(".jpg", ".txt")
        return label_path

    def convert_labels_to_jpegimages(self, label_path):
        """
        labels 경로를 JPEGImages 경로로 변환 (.txt → .jpg)
        백슬래시(\)와 슬래시(/) 경로 모두 처리

        Args:
            label_path (str): labels 경로

        Returns:
            str: JPEGImages 경로
        """
        if not label_path:
            return ""

        # 백슬래시 경로 처리 (Windows UNC 경로 등)
        if "\\labels\\" in label_path:
            img_path = label_path.replace("\\labels\\", "\\JPEGImages\\")
        # 슬래시 경로 처리 (Unix/URL 스타일)
        elif "/labels/" in label_path:
            img_path = label_path.replace("/labels/", "/JPEGImages/")
        else:
            # 경로 구분자 없이 폴더명만 있는 경우 (fallback)
            img_path = label_path.replace("labels", "JPEGImages")

        # 확장자 변환
        img_path = img_path.replace(".txt", ".jpg")
        return img_path

    def update_dataset_info(self):
        """전체 데이터셋 통계 정보 업데이트"""
        if not self.labelsdata or not any(len(x) > 0 for x in self.labelsdata):
            self.dataset_info_label.config(text="")
            return
            
        total_images = len(self.image_paths)
        filtered_count = len(self.selected_image_labels)
        filtering_percent = (filtered_count / total_images * 100) if total_images > 0 else 0
        
        # 겹침 관련 통계
        overlap_class = self.overlap_class_selector.get()
        if overlap_class != "선택 안함" and self.filter_stats["total"] > 0:
            overlap_count = self.filter_stats["overlapping"]
            overlap_percent = (overlap_count / self.filter_stats["total"] * 100)
            
            info_text = f"🔍 {total_images}개 이미지 중 검색: {filtered_count}개 ({filtering_percent:.1f}%), 겹치지 않음: {overlap_count}개 ({overlap_percent:.1f}%)"
        else:
            info_text = f"🔍 {total_images}개 이미지 중 검색: {filtered_count}개 ({filtering_percent:.1f}%)"
            
        self.dataset_info_label.config(text=info_text)

    def handle_left_click(self, event):
        """왼쪽 마우스 클릭 전역 이벤트 처리"""
        # 이벤트가 이미지 라벨에서 발생한 경우 무시 (이미 개별 바인딩 있음)
        if event.widget != self.root and isinstance(event.widget, tk.Label) and hasattr(event.widget, 'img_path'):
            return
        
        # 미리보기 창 닫기 (있는 경우)
        if hasattr(self, 'preview_window') and self.preview_window is not None and self.preview_window.winfo_exists():
            self.preview_window.destroy()
            self.preview_window = None

    # 이미지 라벨에서 클릭한 경우
    def show_preview(self, img_path, label_path, x, y):
        """이미지 미리보기 창을 표시합니다"""
        # 기존 창이 있으면 제거
        if hasattr(self, 'preview_window') and self.preview_window is not None:
            if self.preview_window.winfo_exists():
                self.preview_window.destroy()
                
        # 화면 경계 확인
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # 미리보기 크기 설정
        preview_width = 350  # 더 큰 미리보기
        preview_height = 400  # 바운딩 박스 표시 공간 포함
        
        # 화면 경계를 벗어나지 않도록 위치 조정
        preview_x = min(x + 20, screen_width - preview_width - 10)
        preview_y = min(y + 20, screen_height - preview_height - 10)
        
        # 미리보기 창 생성
        self.preview_window = tk.Toplevel(self.root)
        self.preview_window.title("미리보기")
        self.preview_window.overrideredirect(True)  # 제목 표시줄 없애기
        
        # 테두리 추가
        self.preview_window.configure(bg="black")
        main_frame = tk.Frame(self.preview_window, padx=2, pady=2, bg="white")
        main_frame.pack(fill="both", expand=True)
        
        # 창 위치 설정
        self.preview_window.geometry(f"{preview_width}x{preview_height}+{preview_x}+{preview_y}")
        
        # 마우스 이탈 시 창 닫기
        self.preview_window.bind("<Leave>", lambda e: self._close_preview_delayed())
        
        try:
            # 이미지 파일 존재 확인
            if not os.path.isfile(img_path):
                raise FileNotFoundError(f"이미지 파일이 존재하지 않습니다: {img_path}")
            
            with Image.open(img_path) as img:
                # 미리보기 이미지 크기 계산 (원본 비율 유지)
                img_width, img_height = img.size
                ratio = min(300 / img_width, 300 / img_height)
                new_width = int(img_width * ratio)
                new_height = int(img_height * ratio)
                
                # 바운딩 박스 그리기
                preview_img = img.resize((new_width, new_height), Image.LANCZOS)
                draw = ImageDraw.Draw(preview_img)
                
                # 바운딩 박스 정보 가져오기
                boxes_info = []
                if os.path.isfile(label_path):
                    with open(label_path, 'r', encoding='utf-8') as f:
                        for line_idx, line in enumerate(f):
                            parts = line.strip().split()
                            if len(parts) >= 5:
                                try:
                                    class_id = int(float(parts[0]))
                                    x_center = float(parts[1])
                                    y_center = float(parts[2])
                                    width = float(parts[3])
                                    height = float(parts[4])
                                    
                                    # 박스 좌표 계산
                                    x1 = int((x_center - width/2) * new_width)
                                    y1 = int((y_center - height/2) * new_height)
                                    x2 = int((x_center + width/2) * new_width)
                                    y2 = int((y_center + height/2) * new_height)
                                    
                                    # 클래스별 색상
                                    color = ["red", "green", "blue", "cyan", "magenta", "yellow", 
                                            "orange", "purple", "brown", "gray"][class_id % 10]
                                    
                                    boxes_info.append({
                                        'class_id': class_id, 
                                        'coords': (x1, y1, x2, y2),
                                        'color': color,
                                        'line_idx': line_idx
                                    })
                                except (ValueError, IndexError):
                                    continue
                
                # 박스 그리기
                for box in boxes_info:
                    # 박스 그리기
                    draw.rectangle(box['coords'], outline=box['color'], width=2)
                    
                    # 클래스 ID 표시
                    draw.text((box['coords'][0], box['coords'][1] - 10), 
                            f"C{box['class_id']}", fill=box['color'])
                
                # 이미지 표시
                photo = ImageTk.PhotoImage(preview_img)
                image_label = tk.Label(main_frame, image=photo)
                image_label.image = photo  # 참조 유지
                image_label.pack(padx=2, pady=2)
                
                # 파일 정보 표시
                info_frame = tk.Frame(main_frame, bg="white")
                info_frame.pack(fill="x", padx=5, pady=5)
                
                # 파일명 표시
                name_label = tk.Label(
                    info_frame, 
                    text=os.path.basename(img_path),
                    font=("Arial", 9, "bold"),
                    bg="white"
                )
                name_label.pack(anchor="w")
                
                # 이미지 크기 정보
                size_label = tk.Label(
                    info_frame,
                    text=f"크기: {img_width}x{img_height}",
                    font=("Arial", 8),
                    bg="white"
                )
                size_label.pack(anchor="w")
                
                # 박스 개수 정보
                box_label = tk.Label(
                    info_frame,
                    text=f"바운딩 박스: {len(boxes_info)}개",
                    font=("Arial", 8),
                    bg="white"
                )
                box_label.pack(anchor="w")
                
                # 클래스별 통계
                if boxes_info:
                    class_counts = {}
                    for box in boxes_info:
                        class_id = box['class_id']
                        class_counts[class_id] = class_counts.get(class_id, 0) + 1
                    
                    class_stats = ", ".join([f"C{cls}: {cnt}" for cls, cnt in sorted(class_counts.items())])
                    
                    class_label = tk.Label(
                        info_frame,
                        text=f"클래스: {class_stats}",
                        font=("Arial", 8),
                        bg="white"
                    )
                    class_label.pack(anchor="w")
                    
                # ESC 키로 창 닫기 가능하게 설정
                self.preview_window.bind("<Escape>", lambda e: self.preview_window.destroy())
                
        except Exception as e:
            # 오류 발생 시 메시지 표시
            error_frame = tk.Frame(main_frame, bg="white")
            error_frame.pack(fill="both", expand=True, padx=10, pady=10)
            
            error_icon = tk.Label(
                error_frame, 
                text="❌", 
                font=("Arial", 24),
                fg="red",
                bg="white"
            )
            error_icon.pack(pady=(20, 10))
            
            error_msg = tk.Label(
                error_frame,
                text=f"이미지 로드 오류",
                font=("Arial", 10, "bold"),
                fg="red",
                bg="white"
            )
            error_msg.pack()
            
            error_detail = tk.Label(
                error_frame,
                text=str(e),
                font=("Arial", 8),
                fg="red",
                wraplength=300,
                bg="white"
            )
            error_detail.pack(pady=5)
            
            file_info = tk.Label(
                error_frame,
                text=f"파일: {os.path.basename(img_path)}",
                font=("Arial", 8),
                bg="white"
            )
            file_info.pack(pady=5)

    def _close_preview_delayed(self):
        """미리보기 창을 일정 시간 후에 닫습니다"""
        if hasattr(self, '_preview_close_timer'):
            self.root.after_cancel(self._preview_close_timer)
        
        # 500ms 후에 닫기
        self._preview_close_timer = self.root.after(500, self._close_preview_now)

    def _close_preview_now(self):
        """미리보기 창을 즉시 닫습니다"""
        if hasattr(self, 'preview_window') and self.preview_window is not None:
            if self.preview_window.winfo_exists():
                self.preview_window.destroy()
                self.preview_window = None

    def update_class_dropdown(self, existing_progress_window=None, completion_callback=None):
        """Update class dropdown with available classes from label files - 병렬 처리 및 오류 복구 강화"""
        # 상태 메시지 표시
        if hasattr(self, 'show_status_message'):
            self.show_status_message("클래스 정보 업데이트 중...", duration=10000)

        try:
            total_files = len(self.labels)
            start_time = time.time()

            # 프로그레스 창 생성 또는 재사용
            if existing_progress_window is not None:
                progress_window = existing_progress_window
                # 기존 위젯 정리
                for widget in progress_window.winfo_children():
                    widget.destroy()
                progress_window.title("클래스 정보 업데이트")
            else:
                progress_window = tk.Toplevel(self.root)
                progress_window.title("클래스 정보 업데이트")
                progress_window.geometry("400x150")

                # 창 위치 중앙 정렬
                window_width = 400
                window_height = 150
                position_right = int(self.root.winfo_x() + (self.root.winfo_width() - window_width) / 2)
                position_down = int(self.root.winfo_y() + (self.root.winfo_height() - window_height) / 2)
                progress_window.geometry(f"{window_width}x{window_height}+{position_right}+{position_down}")

                # 창을 항상 위에 표시하고 모달로 설정
                progress_window.transient(self.root)
                progress_window.grab_set()

            # 진행 상황 표시 요소 생성
            info_label = tk.Label(progress_window, text=f"전체 {total_files}개 라벨 파일 분석 중...", anchor='w')
            info_label.pack(padx=20, pady=(10,0), fill='x')

            progress_bar = ttk.Progressbar(progress_window, length=360, mode='determinate')
            progress_bar.pack(padx=20, pady=(5,0))
            progress_bar["maximum"] = total_files

            status_label = tk.Label(progress_window, text="클래스 정보 수집 중...")
            status_label.pack(padx=20, pady=(5,10), fill='x')

            progress_window.update()
            
            # 클래스 정보 초기화
            labelsdata_new = [[] for _ in range(100)]
            classes = set()
            valid_files = 0
            invalid_files = 0
            processed_files = 0

            # 오류 종류별 카운터 추가
            error_stats = {
                "파일 없음": 0,
                "빈 파일": 0,
                "유효 라벨 없음": 0,
                "읽기 오류": 0
            }

            # 병렬 처리를 위한 설정
            import queue
            import threading

            task_queue = queue.Queue()
            result_queue = queue.Queue()
            
            # 모든 작업 추가
            for label_path in self.labels:
                task_queue.put(label_path)
            
            # 작업자 스레드 함수
            def worker():
                while True:
                    try:
                        label_path = task_queue.get(timeout=1)  # 1초 타임아웃
                        
                        file_classes = set()
                        file_labels = defaultdict(list)
                        file_valid = False
                        
                        # 파일 존재 여부 확인
                        if not os.path.isfile(label_path):
                            result_queue.put((label_path, file_classes, file_labels, file_valid, "파일 없음"))
                            task_queue.task_done()
                            continue
                        
                        try:
                            # 파일 읽기 (개선된 파일 읽기 함수 사용)
                            lines = self.read_label_file(label_path)
                            
                            if not lines:
                                result_queue.put((label_path, file_classes, file_labels, file_valid, "빈 파일"))
                                task_queue.task_done()
                                continue
                            
                            for line in lines:
                                try:
                                    parts = line.split()
                                    if not parts:
                                        continue
                                    class_index = parts[0]
                                    class_index_int = int(float(class_index))  # 부동 소수점으로 먼저 변환 후 정수로 변환

                                    # 클래스 인덱스 유효성 검사
                                    if class_index_int < 0 or class_index_int >= 100:
                                        continue

                                    file_classes.add(class_index)  # 문자열 버전 저장
                                    file_labels[class_index_int].append(label_path)
                                    file_valid = True
                                except (IndexError, ValueError):
                                    continue

                            # 파일을 읽었지만 유효한 라벨이 없는 경우
                            if file_valid:
                                result_queue.put((label_path, file_classes, file_labels, file_valid, "성공"))
                            else:
                                result_queue.put((label_path, file_classes, file_labels, file_valid, "유효 라벨 없음"))
                            
                        except Exception as e:
                            result_queue.put((label_path, file_classes, file_labels, file_valid, f"오류: {str(e)}"))
                        
                        task_queue.task_done()
                        
                    except queue.Empty:
                        break
            
            # 작업자 스레드 시작
            num_threads = min(20, max(4, os.cpu_count() or 4))
            threads = []

            for i in range(num_threads):
                t = threading.Thread(target=worker, name=f"ClassWorker-{i}")
                t.daemon = True
                t.start()
                threads.append(t)

            # 결과 처리 함수
            def process_results():
                nonlocal processed_files, valid_files, invalid_files

                try:
                    # 최대 100개 결과 처리 (UI 응답성 유지)
                    batch_size = 100
                    batch_count = 0

                    # 배치 처리 - queue.Empty 예외는 여기서만 처리
                    try:
                        for _ in range(batch_size):
                            label_path, file_classes, file_labels, file_valid, status = result_queue.get(block=False)
                            batch_count += 1

                            # 결과 통합
                            classes.update(file_classes)
                            for class_idx, paths in file_labels.items():
                                labelsdata_new[class_idx].extend(paths)

                            # 통계 업데이트
                            processed_files += 1
                            if file_valid:
                                valid_files += 1
                            else:
                                invalid_files += 1
                                # 오류 종류별 카운트
                                if "파일 없음" in status:
                                    error_stats["파일 없음"] += 1
                                elif "빈 파일" in status:
                                    error_stats["빈 파일"] += 1
                                elif "유효 라벨 없음" in status:
                                    error_stats["유효 라벨 없음"] += 1
                                elif "오류:" in status:
                                    error_stats["읽기 오류"] += 1

                            result_queue.task_done()
                    except queue.Empty:
                        # 배치 처리 중 큐가 비었음 - 정상 동작
                        pass

                    # 진행 상황 업데이트
                    if processed_files > 0:
                        progress = (processed_files / total_files) * 100
                        progress_bar["value"] = processed_files
                        status_label.config(text=f"처리 중: {processed_files}/{total_files} 파일 ({progress:.1f}%), 유효: {valid_files}, 오류: {invalid_files}")

                    # 작업이 완료되었는지 확인 (항상 실행됨)
                    task_queue_empty = task_queue.empty()
                    threads_alive = sum(1 for t in threads if t.is_alive())

                    if task_queue_empty and threads_alive == 0:

                        # 모든 결과를 최종 처리
                        try:
                            while True:
                                label_path, file_classes, file_labels, file_valid, status = result_queue.get(block=False)

                                # 결과 통합
                                classes.update(file_classes)
                                for class_idx, paths in file_labels.items():
                                    labelsdata_new[class_idx].extend(paths)

                                # 통계 업데이트
                                processed_files += 1
                                if file_valid:
                                    valid_files += 1
                                else:
                                    invalid_files += 1
                                    # 오류 종류별 카운트
                                    if "파일 없음" in status:
                                        error_stats["파일 없음"] += 1
                                    elif "빈 파일" in status:
                                        error_stats["빈 파일"] += 1
                                    elif "유효 라벨 없음" in status:
                                        error_stats["유효 라벨 없음"] += 1
                                    elif "오류:" in status:
                                        error_stats["읽기 오류"] += 1

                                result_queue.task_done()
                        except queue.Empty:
                            pass

                        # 클래스 처리 완료
                        finalize_update()
                    else:
                        # 다음 배치 처리 예약
                        self.root.after(50, process_results)

                except Exception as e:
                    print(f"결과 처리 중 오류: {e}")
                    import traceback
                    traceback.print_exc()

                    # 오류 상태 표시
                    status_label.config(text=f"처리 오류: {str(e)[:50]}")

                    # 메인 처리 완료
                    self.root.after(2000, finalize_update)
            
            # 업데이트 완료 함수
            def finalize_update():
                nonlocal labelsdata_new

                try:
                    # 최종 진행 상황 업데이트
                    progress_bar["value"] = total_files
                    status_label.config(text=f"처리 완료: {processed_files}/{total_files} 파일, 유효: {valid_files}, 오류: {invalid_files}")

                    # labelsdata 업데이트
                    self.labelsdata = labelsdata_new

                    # 클래스 정렬 및 메뉴 업데이트
                    sorted_classes = sorted(list(classes), key=lambda x: int(float(x)))

                    # 메인 클래스 드롭다운 메뉴 업데이트
                    menu = self.class_dropdown["menu"]
                    menu.delete(0, "end")

                    for class_index in sorted_classes:
                        class_index_int = int(float(class_index))
                        label_count = len(self.labelsdata[class_index_int])
                        label_text = f"Class {class_index} ({label_count})"
                        menu.add_command(
                            label=label_text,
                            command=lambda idx=class_index: self.class_selector.set(idx)
                        )
                    
                    # 겹침 필터 드롭다운 메뉴 업데이트
                    overlap_menu = self.overlap_class_dropdown["menu"]
                    overlap_menu.delete(0, "end")
                    
                    # 먼저 "선택 안함" 옵션 추가
                    overlap_menu.add_command(
                        label="선택 안함",
                        command=lambda: self.overlap_class_selector.set("선택 안함")
                    )
                    
                    # 각 클래스 옵션 추가
                    for class_index in sorted_classes:
                        class_index_int = int(float(class_index))
                        label_count = len(self.labelsdata[class_index_int])
                        label_text = f"Class {class_index} ({label_count})"
                        overlap_menu.add_command(
                            label=label_text,
                            command=lambda idx=class_index: self.overlap_class_selector.set(idx)
                        )
                    
                    # 페이지 초기화 및 첫 번째 클래스 선택 (클래스가 있는 경우)
                    if sorted_classes:
                        self.current_page = 0
                        self.class_selector.set(sorted_classes[0])

                    # 소요 시간 표시
                    elapsed_time = time.time() - start_time

                    # 오류 종류별 상세 정보 생성
                    error_detail = " | ".join([f"{k}: {v}개" for k, v in error_stats.items() if v > 0])
                    if error_detail:
                        status_text = f"완료: 유효 {valid_files}개, 오류 {invalid_files}개 ({error_detail}), {elapsed_time:.2f}초"
                    else:
                        status_text = f"완료: {valid_files}개 유효 파일, {invalid_files}개 오류 파일, {elapsed_time:.2f}초 소요"

                    status_label.config(text=status_text)

                    # 닫기 버튼은 추가하지 않음 (finalize_ui_update에서 처리)
                    # close_button = tk.Button(progress_window, text="닫기", command=progress_window.destroy)
                    # close_button.pack(pady=10)

                    # 콘솔 출력 (상세 오류 정보)
                    print(f"\n{'='*60}")
                    print(f"클래스 정보 업데이트 완료")
                    print(f"{'='*60}")
                    print(f"✓ 유효 파일: {valid_files}개")
                    print(f"✗ 오류 파일: {invalid_files}개")
                    if invalid_files > 0:
                        print(f"\n[오류 상세]")
                        for error_type, count in error_stats.items():
                            if count > 0:
                                print(f"  - {error_type}: {count}개")
                    print(f"\n처리 시간: {elapsed_time:.2f}초")
                    print(f"클래스 개수: {len(sorted_classes)}개")
                    print(f"{'='*60}\n")

                    # 로깅
                    if hasattr(self, 'logger'):
                        self.logger.info(f"클래스 정보 업데이트 완료: {len(sorted_classes)}개 클래스, {valid_files}개 유효 파일, {elapsed_time:.2f}초 소요")
                        if error_detail:
                            self.logger.info(f"오류 상세: {error_detail}")

                    # 상태 메시지 업데이트
                    if hasattr(self, 'show_status_message'):
                        self.show_status_message(f"클래스 정보 업데이트 완료: {len(sorted_classes)}개 클래스")

                    # 완료 콜백 호출 또는 자동 종료 처리
                    if completion_callback:
                        # 콜백이 있으면 콜백에서 창 닫기 처리
                        self.root.after(0, completion_callback)
                    else:
                        # 콜백이 없으면 자동으로 progress_window 닫기
                        if existing_progress_window is None:
                            # 새로 생성된 창인 경우만 자동으로 닫기
                            self.root.after(3000, progress_window.destroy)

                except Exception as e:
                    print(f"마무리 중 오류: {e}")
                    import traceback
                    traceback.print_exc()
                    
                    # 오류 표시
                    status_label.config(text=f"오류 발생: {str(e)[:50]}")
                    
                    # 닫기 버튼 추가
                    close_button = tk.Button(progress_window, text="닫기", command=progress_window.destroy)
                    close_button.pack(pady=10)
            
            # 결과 처리 시작
            self.root.after(100, process_results)
            
        except Exception as e:
            print(f"클래스 드롭다운 업데이트 오류: {e}")
            import traceback
            traceback.print_exc()
            
            # 상태 메시지 업데이트
            if hasattr(self, 'show_status_message'):
                self.show_status_message(f"클래스 정보 업데이트 실패: {str(e)}", duration=5000)
            
            # 프로그레스 창이 있으면 닫기
            if 'progress_window' in locals() and progress_window.winfo_exists():
                progress_window.destroy()
            
            # 기존 클래스 선택자 상태 유지 (첫 번째 클래스 선택)
            if self.labelsdata and any(len(x) > 0 for x in self.labelsdata):
                for i, labels in enumerate(self.labelsdata):
                    if labels:
                        self.class_selector.set(str(i))
                        break
    def get_iou_color(self, iou_value):
        """IoU 값에 따른 색상 반환"""
        if iou_value <= 0:
            return "gray"
            
        # IoU값에 따라 색상 그라데이션 생성
        if iou_value < 0.3:
            return "red"  # 낮은 IoU
        elif iou_value < 0.5:
            return "red"  # 중간 IoU
        elif iou_value < 0.7:
            return "red"     # 높은 IoU
        else:
            return "purple"  # 매우 높은 IoU
    def update_filter_stats(self):
        """필터링 결과 통계 정보 업데이트"""
        stats = self.filter_stats
        if not stats or stats["total"] == 0:
            self.filter_info_label.config(text="")
            return
            
        # 필터링 결과 요약 생성
        summary = (f"총 {stats['total']}개 이미지 중 "
                f"겹침: {stats['overlapping']}개 ({stats['overlapping']/stats['total']*100:.1f}%), "
                f"겹치지 않음: {stats['non_overlapping']}개 ({stats['non_overlapping']/stats['total']*100:.1f}%)")
        
        self.filter_info_label.config(text=summary)
        self.update_dataset_info()

    def calculate_iou(self, box1, box2):
        """
        두 박스 간의 IoU(Intersection over Union)를 계산합니다.
        엄격한 유효성 검사와 예외 처리로 안정성을 강화했습니다.
        
        Args:
            box1: (x1, y1, x2, y2) 형식의 박스 좌표
            box2: (x1, y1, x2, y2) 형식의 박스 좌표
            
        Returns:
            float: IoU 값 (0~1 사이)
        """
        try:
            # 입력 유효성 검사
            if box1 is None or box2 is None:
                return 0.0
            
            if len(box1) != 4 or len(box2) != 4:
                return 0.0
                
            # 모든 값이 숫자인지 확인
            for val in box1 + box2:
                if not isinstance(val, (int, float)):
                    return 0.0
            
            # 박스 좌표 추출 및 정렬 (x1 < x2, y1 < y2가 보장되도록)
            x1_1, y1_1, x2_1, y2_1 = box1
            if x1_1 > x2_1:
                x1_1, x2_1 = x2_1, x1_1
            if y1_1 > y2_1:
                y1_1, y2_1 = y2_1, y1_1
                
            x1_2, y1_2, x2_2, y2_2 = box2
            if x1_2 > x2_2:
                x1_2, x2_2 = x2_2, x1_2
            if y1_2 > y2_2:
                y1_2, y2_2 = y2_2, y1_2
            
            # 박스 유효성 검사 (미세한 차이 허용)
            epsilon = 1e-6  # 부동소수점 오차 허용 범위
            if x2_1 - x1_1 <= epsilon or y2_1 - y1_1 <= epsilon or x2_2 - x1_2 <= epsilon or y2_2 - y1_2 <= epsilon:
                return 0.0
            
            # 교집합 영역 계산
            x_left = max(x1_1, x1_2)
            y_top = max(y1_1, y1_2)
            x_right = min(x2_1, x2_2)
            y_bottom = min(y2_1, y2_2)
            
            # 교집합이 없는 경우
            if x_right <= x_left or y_bottom <= y_top:
                return 0.0
                
            # 교집합 넓이 계산
            intersection_area = max(0, x_right - x_left) * max(0, y_bottom - y_top)
            
            # 각 박스의 넓이 계산
            box1_area = max(0, x2_1 - x1_1) * max(0, y2_1 - y1_1)
            box2_area = max(0, x2_2 - x1_2) * max(0, y2_2 - y1_2)
            
            # 넓이가 0인 경우 처리
            if box1_area <= epsilon or box2_area <= epsilon:
                return 0.0
            
            # 합집합 넓이 계산 (합집합 = A + B - 교집합)
            union_area = box1_area + box2_area - intersection_area
            
            # IoU 계산 (교집합 / 합집합)
            iou = intersection_area / union_area if union_area > epsilon else 0.0
            
            # 결과 유효성 검사 (0~1 사이 값인지 확인)
            if iou < 0:
                return 0.0
            elif iou > 1:
                return 1.0
                
            return iou
            
        except Exception as e:
            if hasattr(self, 'logger'):
                self.logger.error(f"IoU 계산 중 오류: {e}")
            else:
                print(f"IoU 계산 중 오류: {e}")
            return 0.0
    def check_box_overlap(self, label_path, main_class_idx, target_class_idx):
        """
        특정 클래스의 각 박스별로 겹침 정보를 분석합니다.
        """
        # 캐시 키 생성
        cache_key = (label_path, main_class_idx, target_class_idx, self.iou_threshold_var.get())
        if cache_key in self.overlap_cache:
            return self.overlap_cache[cache_key]

        if not os.path.isfile(label_path):
            return False, 0.0, [], []

        try:
            # 라벨 파일에서 박스 정보 읽기
            boxes_by_class = {}
            original_line_indices = {}  # 원본 라인 인덱스 저장

            with open(label_path, 'r', encoding='utf-8') as f:
                for line_idx, line in enumerate(f):
                    parts = line.strip().split()
                    # 안전한 입력 확인
                    if not parts or len(parts) < 5:
                        continue

                    try:
                        # 안전한 형변환 처리
                        box_class = int(float(parts[0]))
                        x_center = float(parts[1])
                        y_center = float(parts[2])
                        width = float(parts[3])
                        height = float(parts[4])
                        
                        # 값 범위 검증 (정규화된 좌표는 0~1 사이)
                        if not (0 <= x_center <= 1 and 0 <= y_center <= 1 and 
                                0 <= width <= 1 and 0 <= height <= 1):
                            print(f"경고: 범위를 벗어난 좌표 값 무시: {line}")
                            continue
                        
                        # 박스 좌표 계산 (normalized coordinates)
                        x1 = x_center - width/2
                        y1 = y_center - height/2
                        x2 = x_center + width/2
                        y2 = y_center + height/2

                        if box_class not in boxes_by_class:
                            boxes_by_class[box_class] = []
                            original_line_indices[box_class] = []

                        boxes_by_class[box_class].append({
                            'coords': (x1, y1, x2, y2),
                            'class': box_class,
                            'center': (x_center, y_center),
                            'size': (width, height)
                        })
                        original_line_indices[box_class].append(line_idx)
                    except (IndexError, ValueError):
                        continue

                # 지정된 클래스들의 박스 정보 확인
                if int(main_class_idx) not in boxes_by_class:
                    result = (False, 0.0, [], [])  # 각 박스별 정보 추가
                    self.overlap_cache[cache_key] = result
                    return result

                # 선택한 클래스의 모든 박스에 대한 겹침 정보를 저장
                # 각 박스별로 정보를 저장하기 위해 배열 구조 변경
                all_boxes_overlap_info = []
                any_overlap = False
                max_overall_iou = 0.0

                # 선택한 클래스의 모든 박스에 대해 정보 분석
                for i, main_box in enumerate(boxes_by_class[int(main_class_idx)]):
                    # 이 박스의 겹침 정보
                    box_overlap_info = {
                        'box_index': i,
                        'original_line_index': original_line_indices[int(main_class_idx)][i],
                        'has_overlap': False,
                        'max_iou': 0.0,
                        'overlapping_boxes': []
                    }
                    
                    # 대상 클래스가 존재하는 경우에만 겹침 검사
                    if int(target_class_idx) in boxes_by_class:
                        for j, target_box in enumerate(boxes_by_class[int(target_class_idx)]):
                            # 같은 클래스인 경우 같은 박스끼리는 비교하지 않음
                            if int(main_class_idx) == int(target_class_idx) and i == j:
                                continue
                                
                            iou = self.calculate_iou(main_box['coords'], target_box['coords'])
                            
                            # IoU 임계값 이상인 경우 겹침으로 간주
                            if iou >= self.iou_threshold_var.get():
                                box_overlap_info['has_overlap'] = True
                                any_overlap = True
                                
                                # 최대 IoU 값 업데이트
                                if iou > box_overlap_info['max_iou']:
                                    box_overlap_info['max_iou'] = iou
                                    
                                # 겹치는 박스 정보 저장
                                box_overlap_info['overlapping_boxes'].append({
                                    'target_box_index': j,
                                    'original_line_index': original_line_indices[int(target_class_idx)][j],
                                    'iou': iou
                                })
                    
                    # 전체 최대 IoU 업데이트
                    if box_overlap_info['max_iou'] > max_overall_iou:
                        max_overall_iou = box_overlap_info['max_iou']
                        
                    # 이 박스 정보 추가
                    all_boxes_overlap_info.append(box_overlap_info)

                # 각 박스별 상세 겹침 정보를 분석하여 기존 형식의 정보도 생성
                detailed_overlap_info = []
                for box_info in all_boxes_overlap_info:
                    if box_info['has_overlap']:
                        detail_info = {
                            'main_box_index': box_info['box_index'],  # 주 클래스의 박스 인덱스
                            'max_iou': box_info['max_iou'],          # 최대 IoU 값
                            'overlapping_boxes': box_info['overlapping_boxes']  # 겹치는 대상 박스 정보
                        }
                        detailed_overlap_info.append(detail_info)

                # 결과 반환 및 캐싱 (기존 호환성 유지 + 박스별 정보 추가)
                result = (any_overlap, max_overall_iou, detailed_overlap_info, all_boxes_overlap_info)
                self.overlap_cache[cache_key] = result
                return result

        except Exception as e:
            print(f"Error checking box overlap in {label_path}: {e}")
            import traceback
            traceback.print_exc()
            return False, 0.0, [], []
    def check_boxes_overlap(self, box1, box2):
        """
        두 박스가 겹치는지 확인합니다.
        
        Args:
            box1: (x1, y1, x2, y2) 형식의 박스 좌표
            box2: (x1, y1, x2, y2) 형식의 박스 좌표
            
        Returns:
            True: 박스가 겹침
            False: 박스가 겹치지 않음
        """
        # 박스가 겹치지 않는 조건 확인
        if box1[2] <= box2[0] or box1[0] >= box2[2] or box1[3] <= box2[1] or box1[1] >= box2[3]:
            return False
        return True
    
    def save_labeldata(self):
        """Save selected image paths to a file with progress indication"""
        if not self.selected_image_labels:
            print("No images selected to save")
            return
            
        try:
            # Create progress window
            progress_window = tk.Toplevel(self.root)
            progress_window.title("Saving Data")
            
            # Center the progress window
            window_width = 400
            window_height = 150
            position_right = int(self.root.winfo_x() + (self.root.winfo_width() - window_width) / 2)
            position_down = int(self.root.winfo_y() + (self.root.winfo_height() - window_height) / 2)
            progress_window.geometry(f"{window_width}x{window_height}+{position_right}+{position_down}")
            
            # Make the window stay on top and modal
            progress_window.transient(self.root)
            progress_window.grab_set()
            
            # Create progress indicators
            status_label = tk.Label(progress_window, text="Saving selected images...", anchor='w')
            status_label.pack(padx=20, pady=(10,0), fill='x')
            
            progress_bar = ttk.Progressbar(progress_window, length=360, mode='determinate')
            progress_bar.pack(padx=20, pady=(5,0))
            
            detail_label = tk.Label(progress_window, text="", anchor='w')
            detail_label.pack(padx=20, pady=(5,10), fill='x')
            
            progress_window.update()
            
            # Prepare save path
            savepath = os.path.join(self.rootpath, 
                                  f"{self.filename}_labelcheckdata{self.current_datetime}.txt")
            
            # Get unique paths
            unique_paths = set(self.selected_image_labels)
            total_paths = len(unique_paths)
            progress_bar['maximum'] = total_paths
            
            # Save paths
            mode = 'a' if os.path.isfile(savepath) else 'w'
            with open(savepath, mode, encoding='utf-8') as f:
                for i, label_path in enumerate(unique_paths, 1):
                    # Convert label path to image path
                    img_path = self.get_image_path_from_label(label_path)

                    f.write(f"{img_path}\n")
                    
                    # Update progress
                    progress = (i / total_paths) * 100
                    detail_label.config(text=f"Saving: {os.path.basename(img_path)}")
                    progress_bar['value'] = i
                    
                    if i % 10 == 0 or i == total_paths:
                        progress_window.update()
            
            # Reset selection state
            for label in self.checklist:
                if label.winfo_exists():
                    label.config(highlightbackground="white", highlightthickness=2)
            self.selected_image_labels.clear()
            self.checklist.clear()
            self.update_selection_info()
            
            # Show completion
            status_label.config(text="Save complete!")
            detail_label.config(text=f"Saved {total_paths} files to {os.path.basename(savepath)}")
            progress_bar['value'] = progress_bar['maximum']
            progress_window.update()
            
            # Close progress window after a delay
            self.root.after(1500, progress_window.destroy)
            
            print(f"Data saved successfully to {savepath}")
            
        except Exception as e:
            print(f"Error saving data: {e}")
            if 'progress_window' in locals():
                progress_window.destroy()
            import traceback
            traceback.print_exc()
    def filter_images_by_overlap(self, class_images, class_idx, overlap_class_idx):
        """
        클래스 이미지를 겹침 조건에 따라 필터링합니다.
        - 겹치는 것만: IoU가 적힌 이미지만 표시
        - 겹치지 않는 것만: IoU가 적히지 않은 이미지만 표시
        - 모두 보기: 모든 이미지 표시
        """
        overlap_filter = self.overlap_filter_var.get()
        if overlap_class_idx == "선택 안함":
            return class_images, {"total": len(class_images), "overlapping": 0, "non_overlapping": 0}
        
        # 진행 상황을 보여주는 진행 창 생성
        progress_window = tk.Toplevel(self.root)
        progress_window.title("이미지 필터링 중")
        progress_window.geometry("400x200")
        progress_window.transient(self.root)
        
        # 진행 창 요소 생성
        progress_label = tk.Label(progress_window, text="클래스 간 겹침 관계를 분석 중입니다...", font=("Arial", 10, "bold"))
        progress_label.pack(pady=(15, 5))
        
        # IoU 임계값 및 필터 정보 표시
        filter_info = tk.Label(progress_window, 
                            text=f"주 클래스: {class_idx}, 대상 클래스: {overlap_class_idx}, IoU 임계값: {self.iou_threshold_var.get():.2f}",
                            font=("Arial", 9))
        filter_info.pack(pady=5)
        
        # 진행 바 생성
        progress_bar = ttk.Progressbar(progress_window, length=350)
        progress_bar.pack(pady=10)
        progress_bar["maximum"] = len(class_images)
        
        # 현재 진행 상태 표시 레이블
        status_label = tk.Label(progress_window, text="0/0 분석 완료")
        status_label.pack(pady=5)
        
        # 현재까지 발견된 겹침 정보 표시
        result_label = tk.Label(progress_window, text="발견된 겹침: 0, 겹치지 않음: 0")
        result_label.pack(pady=5)
        
        # 진행 창 업데이트
        progress_window.update()
        
        # 필터링 결과와 통계
        filtered_images = []
        stats = {"total": len(class_images), "overlapping": 0, "non_overlapping": 0}
        
        for i, label_path in enumerate(class_images):
            # 진행 상황 업데이트
            progress_bar["value"] = i + 1
            status_label.config(text=f"{i+1}/{len(class_images)} 분석 완료")
            
            # 박스 겹침 확인 - 수정된 버전 사용
            has_overlap, max_iou, detailed_info, all_boxes_info = self.check_box_overlap(
                label_path, class_idx, overlap_class_idx)
            
            # 필터 조건에 따라 이미지 필터링
            if overlap_filter == "겹치는 것만":
                # 겹치는 것만 필터링
                if has_overlap:
                    stats["overlapping"] += 1
                    filtered_images.append((label_path, max_iou))
                else:
                    stats["non_overlapping"] += 1
            elif overlap_filter == "겹치지 않는 것만":
                # 겹치지 않는 것만 필터링
                if not has_overlap:
                    stats["non_overlapping"] += 1
                    filtered_images.append((label_path, 0.0))
                else:
                    stats["overlapping"] += 1
            else:  # "모두 보기"
                # 모든 이미지 표시
                if has_overlap:
                    stats["overlapping"] += 1
                    filtered_images.append((label_path, max_iou))
                else:
                    stats["non_overlapping"] += 1
                    filtered_images.append((label_path, 0.0))
                        
                result_label.config(text=f"발견된 겹침: {stats['overlapping']}, 겹치지 않음: {stats['non_overlapping']}")
                
                # UI 업데이트 (10개 이미지마다)
                if i % 10 == 0 or i == len(class_images) - 1:
                    progress_window.update()
            
        # 결과 요약 표시
        progress_label.config(text="필터링 완료!")
        filter_summary = (f"총 {stats['total']}개 이미지 중 "
                        f"겹침: {stats['overlapping']}개 ({stats['overlapping']/stats['total']*100:.1f}%), "
                        f"겹치지 않음: {stats['non_overlapping']}개 ({stats['non_overlapping']/stats['total']*100:.1f}%)")
        result_label.config(text=filter_summary)
        progress_window.update()
        
        # 결과 정렬 - 겹치는 것이 있는 경우 IoU 값으로 정렬
        if overlap_filter in ["겹치는 것만", "모두 보기"] and stats["overlapping"] > 0:
            filtered_images.sort(key=lambda x: x[1], reverse=True)
        
        # 2초 후 진행 창 닫기
        self.root.after(2000, progress_window.destroy)
        
        return [img[0] for img in filtered_images], stats
    def on_canvas_configure(self, event):
        """Update the scroll region when the canvas size changes"""
        # Update the scrollable region to include all content
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def on_mousewheel(self, event):
        """Handle mouse wheel scrolling"""
        if self.canvas.winfo_exists():
            self.canvas.yview_scroll(-1*(event.delta//120), "units")

    def cleanup_handlers(self):
        """리소스 정리 메서드"""
        try:
            # 모든 바인딩 해제
            self.canvas.unbind_all("<MouseWheel>")
            self.root.unbind_all("<MouseWheel>")
        except:
            pass
    def get_current_page_data(self):
        """Get data for the current page"""
        start_idx = self.current_page * self.page_size
        end_idx = min(start_idx + self.page_size, len(self.image_paths))
        return self.image_paths[start_idx:end_idx], self.labels[start_idx:end_idx]

    def process_boxed_image(self, image, label_path, class_idx, row, col, img_index):
        """Process image with cropped boxes for specific class. Returns next column position."""
        try:
            with open(label_path, "r", encoding='utf-8') as f:
                boxes = [line.strip().split() for line in f]
            
            has_boxes = False
            current_col = col
            
            for box in boxes:
                if int(box[0]) != class_idx:
                    continue
                    
                # Extract box coordinates
                x, y, w, h = map(float, box[1:])
                left = int((x - w/2) * image.width)
                top = int((y - h/2) * image.height)
                right = int((x + w/2) * image.width)
                bottom = int((y + h/2) * image.height)
                
                # Crop and resize
                cropped = image.crop((left, top, right, bottom)).resize((100, 100))
                self.draw_boxes_on_image_corp(cropped, label_path, row, current_col, class_idx, img_index)
                
                has_boxes = True
                current_col += 1
                if current_col >= 12:
                    current_col = 0
                    row += 2
            
            # Return original column if no boxes were processed
            return current_col if has_boxes else col
                
        except Exception as e:
            print(f"Error in process_boxed_image for {label_path}: {e}")
            return col  # Return original column on error
    def toggle_image_view(self, img_path, label_path):
        """Show full view of the image in the main window"""
        if not hasattr(self, 'current_full_view'):
            self.current_full_view = None
            
        if self.current_full_view == img_path:
            self.current_full_view = None
        else:
            self.current_full_view = img_path
            
        self.update_display()

    def reset_view(self):
        """Reset all views to default state"""
        if hasattr(self, 'current_full_view'):
            self.current_full_view = None
        self.update_display()

    def read_label_file(self, label_path, max_retries=3):
        """효율적인 인코딩 감지로 라벨 파일 읽기 - 오류 처리 강화"""
        if not label_path:
            return []
            
        # 파일 존재 여부 확인
        if not os.path.isfile(label_path):
            if hasattr(self, 'logger'):
                self.logger.warning(f"라벨 파일이 존재하지 않습니다: {label_path}")
            else:
                print(f"라벨 파일이 존재하지 않습니다: {label_path}")
            return []

        # 파일 크기 확인
        try:
            file_size = os.path.getsize(label_path)
            if file_size == 0:
                # 빈 파일은 경고만 하고 빈 리스트 반환 (에러는 아님)
                # print(f"빈 라벨 파일입니다: {label_path}")
                return []

            # 지나치게 큰 파일 확인 (100MB 이상)
            if file_size > 100_000_000:
                print(f"경고: 라벨 파일이 너무 큽니다 ({file_size / 1024 / 1024:.2f}MB): {label_path}")
        except OSError as e:
            print(f"파일 크기 확인 중 오류: {label_path}, error: {e}")
            return []
        
        # 재시도 로직 추가
        retry_count = 0
        last_error = None
        
        while retry_count < max_retries:
            try:
                # 1. 캐시된 인코딩 확인
                if label_path in self.file_encoding_cache:
                    try:
                        with open(label_path, 'r', encoding=self.file_encoding_cache[label_path]) as f:
                            return f.readlines()
                    except UnicodeDecodeError:
                        # 캐시된 인코딩이 더이상 유효하지 않으면 캐시에서 제거
                        del self.file_encoding_cache[label_path]
                
                # 2. 파일 형식 체크 - 바이너리 모드로 헤더 읽기
                with open(label_path, 'rb') as f:
                    header = f.read(4)
                    
                    # BOM 확인
                    if header.startswith(b'\xef\xbb\xbf'):
                        encoding = 'utf-8-sig'
                    elif header.startswith(b'\xff\xfe'):
                        encoding = 'utf-16-le'
                    elif header.startswith(b'\xfe\xff'):
                        encoding = 'utf-16-be'
                    else:
                        # 3. 일반적인 인코딩 시도
                        encodings_to_try = ['utf-8', 'cp949', 'euc-kr', 'latin-1']
                        for enc in encodings_to_try:
                            try:
                                with open(label_path, 'r', encoding=enc) as f:
                                    lines = f.readlines()
                                    # 성공한 인코딩 캐시에 저장
                                    self.file_encoding_cache[label_path] = enc
                                    return lines
                            except UnicodeDecodeError:
                                continue
                        
                        # 모든 인코딩 실패 시 기본 인코딩으로 바이너리 모드 사용
                        with open(label_path, 'rb') as f:
                            binary_data = f.read()
                            try:
                                text = binary_data.decode(self.default_encoding, errors='replace')
                                lines = text.splitlines(keepends=True)
                                return lines
                            except:
                                print(f"모든 인코딩 실패: {label_path}")
                                # 마지막 재시도가 아니면 재시도
                                if retry_count < max_retries - 1:
                                    retry_count += 1
                                    time.sleep(0.1)
                                    continue
                                return []
                
                # BOM이 있는 경우 처리
                try:
                    with open(label_path, 'r', encoding=encoding) as f:
                        lines = f.readlines()
                        self.file_encoding_cache[label_path] = encoding
                        return lines
                except Exception as bom_error:
                    last_error = bom_error
                    retry_count += 1
                    time.sleep(0.1)
                    continue
                    
            except PermissionError as e:
                # 파일 접근 권한 오류
                print(f"파일 접근 권한 오류 ({label_path}): {e}")
                return []
                
            except (IOError, OSError) as e:
                # 파일 I/O 오류는 재시도
                last_error = e
                retry_count += 1
                time.sleep(0.5)  # 0.5초 대기 후 재시도
                
            except Exception as e:
                print(f"파일 읽기 중 예상치 못한 오류 ({label_path}): {e}")
                import traceback
                traceback.print_exc()
                return []
        
        # 최대 재시도 횟수 초과
        if last_error:
            print(f"파일 읽기 최대 재시도 횟수({max_retries}) 초과 ({label_path}): {last_error}")
        
        return []
    
    def update_display(self):
        """Update the image display for the current page with improved overlap visualization"""
        # Clear existing images and free memory\
        if hasattr(self, 'ui_busy') and self.ui_busy:
            print("이미 UI 업데이트가 진행 중입니다.")
            return

        self.ui_busy = True
        update_start_time = time.time()
        try:
            if hasattr(self, 'status_bar'):
                self.status_bar.config(text="화면 업데이트 중...")

            self.root.config(cursor="watch")  # 커서 변경으로 처리 중임을 표시
            self.root.update_idletasks()  # UI 즉시 업데이트    

            for widget in self.frame.winfo_children():
                widget.destroy()
            gc.collect()


            if hasattr(self, 'show_only_similar') and self.show_only_similar and hasattr(self, 'current_filtered_labels'):
                # 유사 라벨 필터링 모드에서는 기존 클래스 필터링을 무시하고 유사 라벨만 표시
                current_images = self.current_filtered_labels.copy()
                
                # 페이지네이션 처리
                # 페이지 크기에 맞게 분할
                self.total_pages = (len(current_images) + self.page_size - 1) // self.page_size
                start_idx = self.current_page * self.page_size
                end_idx = min(start_idx + self.page_size, len(current_images))
                current_page_images = current_images[start_idx:end_idx]
                
                # 상태 표시 업데이트
                self.filter_info_label.config(
                    text=f"기준 라벨과 유사한 라벨만 표시 중: 총 {len(current_images)}개 중 {len(current_page_images)}개"
                )
                
                # 페이지네이션 컨트롤 업데이트
                self.update_pagination_controls()
                
                # 이미지 및 라벨 표시
                current_row = 0
                current_col = 0
                
                for idx, label_path in enumerate(current_page_images):
                    img_path = self.get_image_path_from_label(label_path)

                    if not os.path.isfile(img_path) or not os.path.isfile(label_path):
                        print(f"File not found: {img_path} or {label_path}")
                        continue
                        
                    try:
                            # 이미지 로드 및 처리
                        with Image.open(img_path) as img:
                                selected_class = int(self.class_selector.get())
                                
                                # Box 이미지 모드인 경우
                                if self.box_image_var.get():
                                    boxes_processed = False
                                    
                                    # 라벨 파일에서 클래스 박스 정보 읽기
                                    with open(label_path, "r", encoding='utf-8') as f:
                                        lines = f.readlines()
                                        for line_idx, line in enumerate(lines):
                                            try:
                                                class_index, x_center, y_center, width, height = map(float, line.split())
                                                if int(class_index) != selected_class:
                                                    continue
                                                    
                                                # 특정 박스만 표시 (주요 수정 사항)
                                                if hasattr(self, 'filtered_similar_label_info'):
                                                    # 현재 라벨의 박스 정보 찾기
                                                    label_info = next((info for info in self.filtered_similar_label_info 
                                                                    if info['path'] == label_path), None)
                                                    
                                                    if label_info:
                                                        # 유사한 박스 라인 인덱스 목록
                                                        similar_line_indices = [box['line_idx'] for box in label_info['boxes']]
                                                        
                                                        # 현재 라인이 유사 박스가 아니면 건너뛰기
                                                        if line_idx not in similar_line_indices:
                                                            continue
                                                
                                                left = int((float(x_center) - float(width)/2) * img.width)
                                                top = int((float(y_center) - float(height)/2) * img.height)
                                                right = int((float(x_center) + float(width)/2) * img.width)
                                                bottom = int((float(y_center) + float(height)/2) * img.height)
                                                
                                                # 박스 이미지 자르기
                                                cropped = img.crop((left, top, right, bottom)).resize((100, 100))
                                                # 박스 그리기 - 정확한 라인 인덱스 전달
                                                self.draw_boxes_on_image_corp(
                                                    cropped, label_path, current_row, current_col, 
                                                    selected_class, start_idx + idx, line_idx  # line_idx 전달
                                                )
                                                
                                                boxes_processed = True
                                                current_col += 1
                                                if current_col >= 12:
                                                    current_col = 0
                                                    current_row += 2
                                            except (ValueError, IndexError) as e:
                                                print(f"Error processing line in {label_path}: {e}")
                                                continue
                                    
                                    # 박스가 없는 경우 전체 이미지 표시
                                    if not boxes_processed:
                                        img_resized = img.resize((200, 200))
                                        self.draw_boxes_on_image(img_resized, label_path, current_row, current_col, start_idx + idx)
                                        current_col += 1
                                        if current_col >= 5:
                                            current_col = 0
                                            current_row += 2
                                else:
                                    # 전체 이미지 모드일 때
                                    img_resized = img.resize((200, 200))
                                    self.draw_boxes_on_image(img_resized, label_path, current_row, current_col, start_idx + idx)
                                    current_col += 1
                                    if current_col >= 5:
                                        current_col = 0
                                        current_row += 2
                    except (FileNotFoundError, IOError) as e:
                        print(f"이미지 파일 로드 실패 ({img_path}): {e}")
                        # 오류 이미지 대체 표시
                        placeholder = Image.new('RGB', (200, 200), color=(240, 240, 240))
                        draw = ImageDraw.Draw(placeholder)
                        draw.text((40, 80), f"이미지 로드 오류", fill=(0, 0, 0))
                        draw.text((40, 100), f"{os.path.basename(img_path)}", fill=(255, 0, 0))
                        self.draw_boxes_on_image(placeholder, label_path, current_row, current_col, start_idx + idx)
                        current_col += 1
                        if current_col >= 5:
                            current_col = 0
                            current_row += 2
                        continue
                    except Exception as e:
                        print(f"이미지 처리 중 오류 발생 ({img_path}): {e}")
                        import traceback
                        traceback.print_exc()
                        continue
                
                # 프레임 업데이트
                self.frame.update_idletasks()
                self.canvas.configure(scrollregion=self.canvas.bbox("all"))
                return  # 유사 라벨 모드일 때는 여기서 리턴
            selected_class = self.class_selector.get()
            if selected_class == "Select Class":
                return
            

            class_idx = int(float(selected_class))
            print(f"Selected class: {class_idx}")

            # 겹침 필터 설정 가져오기
            selected_class = self.class_selector.get()
            overlap_class = self.overlap_class_selector.get()
            overlap_filter = self.overlap_filter_var.get()
            
            print(f"Number of images for class {class_idx}: {len(self.labelsdata[class_idx])}")
            # Get all images for selected class
            class_images = [path for path in self.labels if path in self.labelsdata[class_idx]]
            if not class_images:
                print(f"No images found for class {class_idx}")
                return
                
            # 필터링된 이미지와 통계 정보 가져오기
            if overlap_class != "선택 안함":
                overlap_class_idx = int(float(overlap_class))  # 일관된 형식으로 변환
                class_images, self.filter_stats = self.filter_images_by_overlap(
                    class_images, class_idx, overlap_class_idx)
                
                # 필터링 결과 정보 업데이트
                self.update_filter_stats()
            else:
                # 필터링을 사용하지 않는 경우 필터 통계 초기화
                self.filter_stats = {"total": len(class_images), "overlapping": 0, "non_overlapping": 0}
                self.filter_info_label.config(text="")

            total_class_images = len(class_images)
            
            if total_class_images == 0:
                # 필터링된 이미지가 없는 경우 메시지 표시
                message_label = tk.Label(self.frame, text="필터 조건에 맞는 이미지가 없습니다.", font=("Arial", 16))
                message_label.pack(pady=50)
                return
            
            # 여기서부터 이미지를 실제로 표시하는 코드 추가
            
            # Update total pages based on class images
            self.total_pages = (total_class_images + self.page_size - 1) // self.page_size
            
            # Get current page's worth of images
            start_idx = self.current_page * self.page_size
            end_idx = min(start_idx + self.page_size, total_class_images)
            current_images = class_images[start_idx:end_idx]
            
            # Update pagination display
            self.update_pagination_controls()
            
            current_row = 0
            current_col = 0
            
            for idx, label_path in enumerate(current_images):
                img_path = self.get_image_path_from_label(label_path)

                if not os.path.isfile(img_path) or not os.path.isfile(label_path):
                    print(f"File not found: {img_path} or {label_path}")
                    continue
                cache_key = f"{img_path}_{200}"  # 200px 크기 썸네일
                if cache_key in self.image_cache:
                    img_resized = self.image_cache[cache_key]
                    img = Image.open(img_path)  # 원본 이미지도 필요한 경우
                else:
                    try:
                        img = Image.open(img_path)
                        img_resized = img.resize((200, 200))
                        
                        # 캐시 크기 제한 확인
                        if len(self.image_cache) >= self.cache_limit:
                            # 가장 오래된 항목 제거 (간단한 LRU 전략)
                            self.image_cache.pop(next(iter(self.image_cache)))
                            
                        # 캐시에 저장
                        self.image_cache[cache_key] = img_resized
                    except Exception as e:
                        print(f"이미지 로드 오류 ({img_path}): {e}")
                        continue
                show_full = hasattr(self, 'current_full_view') and img_path == self.current_full_view

                try:
                    # Load and process image
                    with Image.open(img_path) as img:
                        show_full = hasattr(self, 'current_full_view') and img_path == self.current_full_view
                        
                        if self.box_image_var.get() and not show_full:
                            # Process boxes
                            boxes_processed = False
                            try:
                                # 라벨 파일에서 클래스 박스 정보 읽기
                                box_idx = 0  # 같은 클래스 내 박스 인덱스
                                with open(label_path, "r", encoding='utf-8') as f:
                                    lines = f.readlines()
                                    for line_idx, line in enumerate(lines):
                                        try:
                                            class_index, x_center, y_center, width, height = map(float, line.split())
                                            if int(class_index) != class_idx:
                                                continue
                                                
                                            left = int((float(x_center) - float(width)/2) * img.width)
                                            top = int((float(y_center) - float(height)/2) * img.height)
                                            right = int((float(x_center) + float(width)/2) * img.width)
                                            bottom = int((float(y_center) + float(height)/2) * img.height)
                                            
                                            # 겹침 정보 확인
                                            show_box = True
                                            if overlap_class != "선택 안함":
                                                # 박스별 겹침 정보 확인
                                                has_overlap, max_iou, detail_info, all_boxes_info = self.check_box_overlap(
                                                    label_path, class_idx, int(overlap_class))
                                                
                                                # 해당 박스의 겹침 정보 찾기
                                                current_box_overlap = False
                                                for box_info in all_boxes_info:
                                                    if box_info['box_index'] == box_idx:
                                                        current_box_overlap = box_info['has_overlap']
                                                        break
                                                        
                                                # 필터 조건에 따라 박스 표시 여부 결정
                                                if overlap_filter == "겹치는 것만" and not current_box_overlap:
                                                    show_box = False
                                                elif overlap_filter == "겹치지 않는 것만" and current_box_overlap:
                                                    show_box = False
                                            
                                            # 표시 조건을 만족하는 경우만 박스 처리
                                            if show_box:
                                                # 박스 이미지 자르기
                                                cropped = img.crop((left, top, right, bottom)).resize((100, 100))
                                                # 박스 그리기
                                                self.draw_boxes_on_image_corp(
                                                    cropped, label_path, current_row, current_col, 
                                                    class_idx, start_idx + idx, box_idx
                                                )
                                                
                                                boxes_processed = True
                                                current_col += 1
                                                if current_col >= 12:
                                                    current_col = 0
                                                    current_row += 2
                                            
                                            # 박스 인덱스 증가
                                            box_idx += 1
                                            
                                        except (ValueError, IndexError) as e:
                                            print(f"Error processing line in {label_path}: {e}")
                                            continue
                            except Exception as e:
                                print(f"Error reading label file {label_path}: {e}")
                            
                            # If no boxes were processed, show full image
                            if not boxes_processed:
                                show_image = True
                                if overlap_class != "선택 안함":
                                    has_overlap, _, _, _ = self.check_box_overlap(
                                        label_path, class_idx, int(overlap_class))
                                    
                                    if overlap_filter == "겹치는 것만" and not has_overlap:
                                        show_image = False
                                    elif overlap_filter == "겹치지 않는 것만" and has_overlap:
                                        show_image = False
                                
                                if show_image:
                                    img_resized = img.resize((200, 200))
                                    self.draw_boxes_on_image(img_resized, label_path, current_row, current_col, start_idx + idx)
                                    current_col += 1
                                    if current_col >= 5:
                                        current_col = 0
                                        current_row += 2
                        else:
                            # Show full image
                            show_image = True
                            if overlap_class != "선택 안함":
                                has_overlap, _, _, _ = self.check_box_overlap(
                                    label_path, class_idx, int(overlap_class))
                                
                                if overlap_filter == "겹치는 것만" and not has_overlap:
                                    show_image = False
                                elif overlap_filter == "겹치지 않는 것만" and has_overlap:
                                    show_image = False
                            
                            if show_image:
                                img_resized = img.resize((200, 200))
                                self.draw_boxes_on_image(img_resized, label_path, current_row, current_col, start_idx + idx)
                                current_col += 1
                                if current_col >= 5:
                                    current_col = 0
                                    current_row += 2
                        
                except Exception as e:
                    print(f"Error processing image {img_path}: {e}")
                    continue

            self.root.config(cursor="")  # 기본 커서로 복원
            self.update_dataset_info()

            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            self.root.after(100, self.refresh_bindings)
            self.frame.update_idletasks()
        except Exception as e:
            print(f"화면 업데이트 중 오류 발생: {e}")
            import traceback
            traceback.print_exc()
            if hasattr(self, 'status_bar'):
                self.status_bar.config(text=f"오류: {str(e)[:30]}...")

        finally:
            self.ui_busy = False     

    def toggle_image_view(self, img_path, label_path):
        """Toggle between box view and full view for a specific image"""
        if not hasattr(self, 'full_view_images'):
            self.full_view_images = set()
            
        if img_path in self.full_view_images:
            self.full_view_images.remove(img_path)
        else:
            self.full_view_images.add(img_path)
            
        self.update_display()

    def select_reference_label(self, label, label_path):
        """
        특정 라벨을 기준 라벨로 선택하고 해당 라벨의 정보를 저장합니다.
        """
        try:
            # 이미 선택된 라벨이 있는지 확인
            if hasattr(self, 'reference_label') and self.reference_label:
                # 기존 참조 라벨의 하이라이트 제거
                if hasattr(self, 'reference_label_widget') and self.reference_label_widget and self.reference_label_widget.winfo_exists():
                    self.reference_label_widget.config(highlightbackground="white", highlightthickness=2)
            
            # 현재 선택된 클래스
            selected_class = self.class_selector.get()
            if selected_class == "Select Class":
                tk.messagebox.showwarning("선택 오류", "클래스를 먼저 선택하세요.")
                return
                
            # class_idx = int(selected_class)
            class_idx = int(float(selected_class))

            # 라벨 파일에서 해당 클래스의 박스 정보 추출
            reference_boxes = []
            specific_line_idx = None

            if hasattr(label, 'line_idx') and label.line_idx is not None:
                specific_line_idx = label.line_idx
                print(f"특정 박스 선택 (라인 인덱스: {specific_line_idx})")
            
            with open(label_path, 'r', encoding='utf-8') as f:
                for line_idx, line in enumerate(f):
                    if specific_line_idx is not None and line_idx != specific_line_idx:
                        continue
                    parts = line.strip().split()
                    if not parts:
                        continue
                        
                    try:
                        box_class = int(float(parts[0]))
                        if box_class != class_idx:
                            continue
                            
                        # 박스 좌표 정보 저장 (정규화된 좌표)
                        x_center = float(parts[1])
                        y_center = float(parts[2])
                        width = float(parts[3])
                        height = float(parts[4])
                        
                        reference_boxes.append({
                            'class': box_class,
                            'x': x_center,
                            'y': y_center,
                            'w': width,
                            'h': height,
                            'line_idx': line_idx
                        })
                        if specific_line_idx is not None:
                            break
                    except (ValueError, IndexError) as e:
                        print(f"Error parsing line in reference label {label_path}: {e}")
                        continue
            
            if not reference_boxes:
                tk.messagebox.showwarning("선택 오류", f"선택한 이미지에서 클래스 {class_idx}의 박스를 찾을 수 없습니다.")
                return
                
            # 기준 라벨 정보 저장
            self.reference_label = {
                'path': label_path,
                'class': class_idx,
                'boxes': reference_boxes
            }
            
            # 기준 라벨 위젯 저장 및 하이라이트
            self.reference_label_widget = label
            self.reference_label_widget.config(highlightbackground="blue", highlightthickness=4)
            
            # 기준 라벨 상태 정보 업데이트
            if hasattr(self, 'ref_label_status'):
                img_path = self.get_image_path_from_label(label_path)

                base_name = os.path.basename(img_path)
                self.ref_label_status.config(
                    text=f"기준 라벨: 클래스 {class_idx}, {base_name}, 박스 {len(reference_boxes)}개",
                    fg="blue"
                )
            
            # 사용자에게 선택 확인 메시지
            box_count = len(reference_boxes)
            tk.messagebox.showinfo("기준 라벨 선택", 
                                f"클래스 {class_idx}의 기준 라벨이 선택되었습니다.\n"
                                f"선택된 라벨에는 {box_count}개의 박스가 있습니다.\n"
                                f"'유사 라벨 찾기' 버튼을 클릭하여 유사한 라벨을 찾으세요.")
                
        except Exception as e:
            print(f"Error selecting reference label: {e}")
            import traceback
            traceback.print_exc()
            tk.messagebox.showerror("오류", f"기준 라벨 선택 중 오류가 발생했습니다: {str(e)}")
    def filter_by_reference_label(self):
        """
        기준 라벨과 유사한 위치에 있는 라벨들을 필터링하여 표시합니다.
        기준 라벨도 필터링 결과에 포함합니다.
        """
        if not hasattr(self, 'reference_label') or not self.reference_label:
            tk.messagebox.showwarning("필터링 오류", "먼저 기준 라벨을 선택하세요.")
            return
            
        # 진행 창 생성
        progress_window = tk.Toplevel(self.root)
        progress_window.title("유사 라벨 찾기")
        progress_window.geometry("450x500")  # 창 크기 조금 증가
        progress_window.transient(self.root)
        progress_window.grab_set()
        
        # 진행 창 요소
        ttk.Label(progress_window, text="유사한 라벨 찾는 중...", font=("Arial", 12, "bold")).pack(pady=(15, 5))
        
        # 기준 라벨 정보 표시
        ref_info = ttk.Label(
            progress_window, 
            text=f"기준 클래스: {self.reference_label['class']}, 박스 수: {len(self.reference_label['boxes'])}"
        )
        ref_info.pack(pady=5)
        
        # 픽셀 오차 범위 설정
        info_frame = ttk.Frame(progress_window)
        info_frame.pack(pady=10, fill="x", padx=20)
        
        ttk.Label(
            info_frame, 
            text="좌표 오차 범위: ±5 픽셀", 
            font=("Arial", 10, "bold")
        ).pack(side="left", padx=5)
        
        ttk.Label(
            info_frame,
            text="(이미지에서 정확히 같은 위치에 있는 객체를 찾습니다)",
            font=("Arial", 9)
        ).pack(side="left", padx=5)
        
        # 검색 범위 선택 옵션 추가
        scope_frame = ttk.LabelFrame(progress_window, text="검색 범위")
        scope_frame.pack(pady=10, fill="x", padx=20)
        
        scope_var = tk.StringVar(value="current_class")
        
        ttk.Radiobutton(
            scope_frame, 
            text=f"현재 선택된 클래스만 (클래스 {self.reference_label['class']})", 
            variable=scope_var, 
            value="current_class"
        ).pack(anchor="w", padx=10, pady=2)
        
        ttk.Radiobutton(
            scope_frame, 
            text="모든 클래스", 
            variable=scope_var, 
            value="all_classes"
        ).pack(anchor="w", padx=10, pady=2)
        
        # 기준 라벨 포함 옵션
        include_ref_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            scope_frame,
            text="기준 라벨도 결과에 포함",
            variable=include_ref_var
        ).pack(anchor="w", padx=10, pady=2)
        
        # 진행 상황 표시
        progress_bar = ttk.Progressbar(progress_window, length=400)
        progress_bar.pack(pady=10)
        
        status_label = ttk.Label(progress_window, text="준비 중...")
        status_label.pack(pady=5)
        
        result_label = ttk.Label(progress_window, text="")
        result_label.pack(pady=5)
        
        # 버튼 프레임
        button_frame = ttk.Frame(progress_window)
        button_frame.pack(pady=15, fill="x", padx=20)
        
        # 필터링 로직
        def execute_filtering():
            try:
                # 필터링 설정
                class_idx = self.reference_label['class']
                reference_boxes = self.reference_label['boxes']
                search_scope = scope_var.get()
                include_reference = include_ref_var.get()
                
                # 라벨 파일 리스트
                label_files = [path for path in self.labels if os.path.isfile(path)]
                total_files = len(label_files)
                
                # 진행 상황 설정
                progress_bar["maximum"] = total_files
                progress_bar["value"] = 0
                
                # 필터링된 라벨 저장 변수
                similar_labels = []
                
                # 기준 라벨의 정확한 라인 인덱스도 함께 저장 (주요 수정 사항)
                similar_label_info = []
                
                # 기준 라벨 미리 추가 (옵션 설정 시)
                if include_reference:
                    similar_labels.append(self.reference_label['path'])
                    # 기준 라벨의 박스 정보도 저장 (주요 수정 사항)
                    similar_label_info.append({
                        'path': self.reference_label['path'],
                        'boxes': self.reference_label['boxes']
                    })
                
                # 각 라벨 파일 처리
                for i, label_path in enumerate(label_files):
                    # 진행 상황 업데이트
                    progress_bar["value"] = i + 1
                    status_label.config(text=f"처리 중: {i+1}/{total_files}")
                    result_label.config(text=f"찾은 유사 라벨: {len(similar_labels)}개")
                    progress_window.update()
                    
                    # 자기 자신은 이미 추가했으므로 건너뛰기
                    if label_path == self.reference_label['path']:
                        continue
                    
                    # 라벨 파일 처리
                    try:
                        with open(label_path, 'r', encoding='utf-8') as f:
                            lines = f.readlines()
                        
                        # 해당 클래스의 박스 추출
                        similar_boxes = []  # 유사한 박스 정보 저장 (주요 수정 사항)
                        is_similar = False
                        
                        for line_idx, line in enumerate(lines):
                            parts = line.strip().split()
                            if not parts:
                                continue
                                
                            try:
                                box_class = int(float(parts[0]))
                                
                                # 검색 범위에 따라 클래스 필터링
                                if search_scope == "current_class" and box_class != class_idx:
                                    continue
                                    
                                x = float(parts[1])
                                y = float(parts[2])
                                w = float(parts[3])
                                h = float(parts[4])
                                
                                # 현재 박스 정보
                                current_box = {
                                    'class': box_class,
                                    'x': x,
                                    'y': y,
                                    'w': w,
                                    'h': h,
                                    'line_idx': line_idx  # 라인 인덱스 저장
                                }
                                
                                # 모든 참조 박스와 비교
                                for ref_box in reference_boxes:
                                    # 이미지 경로 가져오기
                                    img_path = self.get_image_path_from_label(label_path)
                                    
                                    # 이미지 사이즈 확인 (실제 픽셀 좌표 계산을 위해)
                                    try:
                                        # 이미지가 존재하는지 확인
                                        if not os.path.isfile(img_path):
                                            continue
                                            
                                        # 이미지 크기 가져오기
                                        with Image.open(img_path) as img:
                                            img_width, img_height = img.size
                                        
                                        # 정규화된 좌표를 픽셀 좌표로 변환
                                        ref_x_px = ref_box['x'] * img_width
                                        ref_y_px = ref_box['y'] * img_height
                                        cur_x_px = x * img_width
                                        cur_y_px = y * img_height
                                        
                                        # 픽셀 단위로 차이 계산
                                        x_diff_px = abs(ref_x_px - cur_x_px)
                                        y_diff_px = abs(ref_y_px - cur_y_px)
                                        
                                        # 5픽셀 오차 범위 내에 있는지 확인
                                        if x_diff_px <= 5 and y_diff_px <= 5:
                                            # 유사한 박스 발견
                                            is_similar = True
                                            # 유사한 박스 정보 저장 (주요 수정 사항)
                                            if current_box not in similar_boxes:
                                                similar_boxes.append(current_box)
                                    except Exception as e:
                                        print(f"Error comparing image dimensions: {e}")
                                        continue
                            except Exception as e:
                                print(f"Error comparing image dimensions: {e}")
                                continue
                        
                        # 유사한 라벨이 발견되면 목록에 추가
                        if is_similar:
                            similar_labels.append(label_path)
                            # 유사한 박스 정보도 저장 (주요 수정 사항)
                            similar_label_info.append({
                                'path': label_path,
                                'boxes': similar_boxes
                            })
                    
                    except Exception as e:
                        print(f"Error processing label {label_path}: {e}")
                        continue
                    
                    # 주기적으로 UI 업데이트
                    if i % 10 == 0 or i == total_files - 1:
                        progress_window.update()
                
                # 필터링 완료
                progress_bar["value"] = total_files
                
                if similar_labels:
                    status_label.config(text="필터링 완료")
                    result_label.config(text=f"총 {len(similar_labels)}개의 유사 라벨을 찾았습니다")
                    
                    # 결과 저장 및 표시
                    self.filtered_similar_labels = similar_labels
                    # 박스 정보도 저장 (주요 수정 사항)
                    self.filtered_similar_label_info = similar_label_info
                    
                    # 필터링 완료 후 버튼 활성화
                    display_button.config(state="normal")
                    save_button.config(state="normal")
                else:
                    status_label.config(text="유사한 라벨을 찾지 못했습니다")
                    result_label.config(text="검색 조건을 변경하여 다시 시도해보세요")
                
            except Exception as e:
                print(f"Error during filtering: {e}")
                import traceback
                traceback.print_exc()
                status_label.config(text=f"오류 발생: {str(e)}")
        
        # 필터링 결과 표시
        def display_filtered_results():
            if hasattr(self, 'filtered_similar_labels') and self.filtered_similar_labels:
                # 선택 상태 초기화
                self.deselect_all_images()
                
                # 필터링된 이미지만 선택 상태로 변경
                self.selected_image_labels = self.filtered_similar_labels.copy()
                
                # 박스 정보도 선택 상태로 저장 (주요 수정 사항)
                if hasattr(self, 'filtered_similar_label_info'):
                    self.selected_label_info = self.filtered_similar_label_info.copy()
                
                # 결과 표시를 위한 특수 플래그 설정
                self.show_only_similar = True
                
                # 결과 표시용 필터링된 라벨 목록 저장
                self.current_filtered_labels = self.filtered_similar_labels.copy()
                
                # 현재 페이지 초기화
                self.current_page = 0
                
                # 디스플레이 업데이트
                self.update_display()
                
                # 다이얼로그 닫기
                progress_window.destroy()
                
                # 결과 메시지
                tk.messagebox.showinfo(
                    "필터링 완료", 
                    f"기준 라벨과 유사한 {len(self.filtered_similar_labels)}개의 라벨을 표시합니다."
                )
            else:
                tk.messagebox.showinfo("알림", "유사한 라벨을 찾지 못했습니다.")
        
        # 필터링 결과 저장
        def save_filtered_results():
            if hasattr(self, 'filtered_similar_labels') and self.filtered_similar_labels:
                # 저장 경로 설정
                save_path = os.path.join(
                    self.rootpath, 
                    f"similar_labels_{self.current_datetime}.txt"
                )
                
                # 이미지 경로로 변환하여 저장
                with open(save_path, 'w', encoding='utf-8') as f:
                    for label_path in self.filtered_similar_labels:
                        img_path = self.get_image_path_from_label(label_path)
                        f.write(f"{img_path}\n")
                
                tk.messagebox.showinfo(
                    "저장 완료", 
                    f"유사 라벨 목록이 저장되었습니다:\n{save_path}"
                )
        
        # 버튼 추가
        ttk.Button(button_frame, text="필터링 시작", command=execute_filtering).pack(side="left", padx=5)
        
        display_button = ttk.Button(button_frame, text="결과 표시", command=display_filtered_results, state="disabled")
        display_button.pack(side="left", padx=5)
        
        save_button = ttk.Button(button_frame, text="결과 저장", command=save_filtered_results, state="disabled")
        save_button.pack(side="left", padx=5)
        
        ttk.Button(button_frame, text="취소", command=progress_window.destroy).pack(side="right", padx=5)
        
        # 창 업데이트
        progress_window.update()
    def clear_reference_label(self):
        """참조 라벨 선택을 초기화합니다."""
        if hasattr(self, 'reference_label'):
            delattr(self, 'reference_label')
            
        if hasattr(self, 'reference_label_widget') and self.reference_label_widget and self.reference_label_widget.winfo_exists():
            self.reference_label_widget.config(highlightbackground="white", highlightthickness=2)
            
        if hasattr(self, 'filtered_similar_labels'):
            delattr(self, 'filtered_similar_labels')
            
        if hasattr(self, 'show_only_similar'):
            delattr(self, 'show_only_similar')
            
        if hasattr(self, 'current_filtered_labels'):
            delattr(self, 'current_filtered_labels')
        
        # 기준 라벨 상태 표시 업데이트
        if hasattr(self, 'ref_label_status'):
            self.ref_label_status.config(text="기준 라벨: 없음", fg="gray")
        
        # 디스플레이 업데이트 - 원래 클래스 필터 모드로 돌아감
        self.current_page = 0  # 페이지 초기화
        self.update_display()
        
        tk.messagebox.showinfo("알림", "참조 라벨 선택이 초기화되었습니다.")

    # 기존 update_display 메서드 수정 - 유사 라벨 필터링 기능 추가
    def update_display_modified(self):
        """Update the image display for the current page with improved overlap visualization"""
        # 기존 update_display 메서드의 내용...
        
        # 유사 라벨 필터링이 활성화된 경우 추가 처리
        if hasattr(self, 'show_only_similar') and self.show_only_similar and hasattr(self, 'filtered_similar_labels'):
            # 필터링된 라벨만 표시
            class_images = [path for path in class_images if path in self.filtered_similar_labels]
            
            # 상태 표시 업데이트
            self.filter_info_label.config(
                text=f"기준 라벨과 유사한 라벨만 표시 중: {len(class_images)}개"
            )
        
        # 나머지 기존 코드는 그대로 유지
        # ...

    # 이미지 클릭 이벤트 핸들러 수정
    def on_image_click_modified(self, label, label_path):
        """이미지 클릭 이벤트 핸들러 - 기준 라벨 선택 기능 추가"""
        # 오른쪽 컨트롤 키가 눌린 상태에서 클릭한 경우 - 기준 라벨로 선택
        if hasattr(self, 'ctrl_pressed') and self.ctrl_pressed:
            self.select_reference_label(label, label_path)
        else:
            # 기존 기능 유지
            try:
                if label in self.checklist:
                    # 선택 해제 시
                    label.config(bd=2, highlightbackground="white", highlightthickness=2)
                    label.config(bg="white")
                    if label_path in self.selected_image_labels:
                        self.selected_image_labels.remove(label_path)
                    if label in self.checklist:
                        self.checklist.remove(label)
                else:
                    # 선택 시
                    label.config(bd=2, highlightbackground="red", highlightthickness=4)
                    label.config(bg="#ffdddd")  # 연한 빨간색 배경
                    self.selected_image_labels.append(label_path)
                    if label not in self.checklist:
                        self.checklist.append(label)
                
                self.update_selection_info()
                
            except TclError as e:
                print(f"Error handling image click: {e}")
    def create_tooltip(self, widget, text):
        """
        위젯 위에 툴팁을 표시합니다.
        
        Parameters:
            widget (tk.Widget): 툴팁을 표시할 위젯
            text (str): 툴팁에 표시할 텍스트
        """
        # 기존 툴팁 제거
        self.remove_tooltip()
        
        # 툴팁 창 생성
        x, y, _, _ = widget.bbox("insert")
        x += widget.winfo_rootx() + 15
        y += widget.winfo_rooty() + 10
        
        self.tooltip_window = tk.Toplevel(widget)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_geometry(f"+{x}+{y}")
        
        label = tk.Label(self.tooltip_window, text=text, background="#ffffe0", 
                    relief="solid", borderwidth=1, font=("Arial", 8))
        label.pack(padx=2, pady=2)
        
        # 3초 후 자동으로 제거
        self.tooltip_timer = self.root.after(3000, self.remove_tooltip)

    def remove_tooltip(self):
        """툴팁 창을 제거합니다."""
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None
        
        if self.tooltip_timer:
            self.root.after_cancel(self.tooltip_timer)
            self.tooltip_timer = None
    def draw_boxes_on_image_corp(self, image, label_path, row, col, class_index, img_index, line_idx=None):
        """
        크롭된 이미지에 정보를 그리고, 대상 클래스 박스도 함께 표시합니다.
        
        Parameters:
            image (PIL.Image): 처리할 이미지
            label_path (str): 라벨 파일 경로
            row (int): 그리드 행 위치
            col (int): 그리드 열 위치
            class_index (int): 현재 선택된 클래스 인덱스
            img_index (int): 이미지 인덱스 (표시용)
            line_idx (int, optional): 같은 클래스 내에서의 박스 인덱스
        """
        draw = ImageDraw.Draw(image)
        overlap_class = self.overlap_class_selector.get()
        
        text_color = "red"
        border_color = "black"
        iou_value = 0.0
        show_iou = False
        all_boxes = []
        same_class_boxes = []

        # 라벨 데이터 읽기
        try:
            with open(label_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                for i, line in enumerate(lines):
                    parts = line.strip().split()
                    if len(parts) >= 5:
                        box_class = int(float(parts[0]))
                        box_info = {
                            'line_idx': i,  # 실제 파일 라인 인덱스
                            'class': box_class,
                            'x': float(parts[1]),
                            'y': float(parts[2]),
                            'w': float(parts[3]),
                            'h': float(parts[4])
                        }
                        all_boxes.append(box_info)
                        if box_class == class_index:
                            same_class_boxes.append(box_info)
        except Exception as e:
            print(f"라벨 파일 읽기 오류: {e}")
            return None

        # 선택된 현재 박스
        current_box = None
        if line_idx is not None and 0 <= line_idx < len(same_class_boxes):
            current_box = same_class_boxes[line_idx]

        # 겹침 클래스 IoU 처리
        if overlap_class != "선택 안함" and current_box:
            try:
                overlap_class_idx = int(float(overlap_class))
                target_boxes = [box for box in all_boxes if box['class'] == overlap_class_idx]

                current_coords = (
                    current_box['x'] - current_box['w'] / 2,
                    current_box['y'] - current_box['h'] / 2,
                    current_box['x'] + current_box['w'] / 2,
                    current_box['y'] + current_box['h'] / 2
                )

                for target_box in target_boxes:
                    target_coords = (
                        target_box['x'] - target_box['w'] / 2,
                        target_box['y'] - target_box['h'] / 2,
                        target_box['x'] + target_box['w'] / 2,
                        target_box['y'] + target_box['h'] / 2
                    )
                    iou = self.calculate_iou(current_coords, target_coords)
                    if iou >= self.iou_threshold_var.get():
                        show_iou = True
                        iou_value = max(iou_value, iou)
                        text_color = self.get_iou_color(iou)
                        border_color = text_color

                        # 상대좌표 → 픽셀좌표 변환
                        curr_x1 = current_coords[0]
                        curr_y1 = current_coords[1]
                        rel_x1 = (target_coords[0] - curr_x1) / current_box['w']
                        rel_y1 = (target_coords[1] - curr_y1) / current_box['h']
                        rel_x2 = (target_coords[2] - curr_x1) / current_box['w']
                        rel_y2 = (target_coords[3] - curr_y1) / current_box['h']

                        px1 = max(0, min(int(rel_x1 * image.width), image.width - 1))
                        py1 = max(0, min(int(rel_y1 * image.height), image.height - 1))
                        px2 = max(0, min(int(rel_x2 * image.width), image.width - 1))
                        py2 = max(0, min(int(rel_y2 * image.height), image.height - 1))

                        if px2 > px1 and py2 > py1:
                            draw.rectangle((px1, py1, px2, py2), outline="blue", width=2)
                            draw.text((px1 + 2, py1 + 2), f"IoU:{iou:.2f}", fill="blue")
            except Exception as e:
                print(f"겹침 박스 처리 중 오류: {e}")

        # 기본 텍스트 정보 출력
        if show_iou:
            draw.text((5, 5), f"IoU: {iou_value:.2f}", fill=text_color)
            draw.text((5, 20), f"No: {img_index}", fill=text_color)
        else:
            draw.text((5, 5), f"No: {img_index}", fill=text_color)

        # 클래스 및 라인 정보 표시
        if current_box:
            y_pos = 35 if show_iou else 20
            actual_line_idx = current_box['line_idx']  # 실제 파일의 라인 인덱스
            draw.text((5, y_pos), f"Line: {actual_line_idx} (Class: {current_box['class']})", fill=text_color)

        # 라벨 생성 및 이미지 표시
        try:
            photo = ImageTk.PhotoImage(image)
            label = tk.Label(self.frame, image=photo, bg="white")
            label.image = photo
            label.label_path = label_path

            # 라벨 위젯에 라인 인덱스 저장
            if current_box:
                # 실제 파일의 라인 인덱스 저장
                label.line_idx = current_box['line_idx']
            elif line_idx is not None:
                # 전달받은 라인 인덱스 사용 (백업)
                label.line_idx = line_idx

            label.config(relief="solid", bd=1, highlightbackground=border_color, highlightthickness=2)
            label.grid(row=row, column=col, padx=10, pady=10)

            img_path = self.get_image_path_from_label(label_path)

            # 이벤트 바인딩 - 현재 박스의 실제 라인 인덱스 또는 전달받은 인덱스
            bind_line_idx = current_box['line_idx'] if current_box else line_idx

            # 드래그 선택 이벤트 바인딩 (Shift + 클릭/드래그 포함)
            self.setup_drag_select_events(label, label_path)

            label.bind("<Button-3>", lambda event, img_p=img_path, lbl_p=label_path, ln_idx=bind_line_idx:
                    self.show_full_image(img_p, lbl_p, ln_idx))
            label.bind("<Enter>", lambda event, l=label:
                    self.show_box_tooltip(l, label_path, bind_line_idx))
            label.bind("<Leave>", lambda event:
                    self.remove_tooltip())

            return label
        except Exception as e:
            print(f"이미지 라벨 생성 실패 ({label_path}): {e}")
            return None

    def show_box_tooltip(self, label_widget, label_path, line_idx):
        """
        박스에 대한 상세 정보 툴팁을 표시합니다.
        
        Parameters:
            label_widget (tk.Label): 툴팁을 표시할 라벨 위젯
            label_path (str): 라벨 파일 경로
            line_idx (int): 라벨 파일에서의 라인 인덱스
        """
        if line_idx is None:
            return
        
        try:
            # 라벨 파일 데이터 가져오기
            lines = self._get_label_data(label_path)
            
            if 0 <= line_idx < len(lines):
                line = lines[line_idx]
                parts = line.strip().split()
                
                if len(parts) >= 5:
                    class_id = int(float(parts[0]))
                    x_center = float(parts[1])
                    y_center = float(parts[2])
                    width = float(parts[3])
                    height = float(parts[4])
                    
                    # 툴팁 텍스트 구성
                    tooltip_text = (
                        f"클래스: {class_id}\n"
                        f"중심 좌표: ({x_center:.4f}, {y_center:.4f})\n"
                        f"크기: {width:.4f} x {height:.4f}\n"
                        f"파일: {os.path.basename(label_path)}\n"
                        f"라인: {line_idx}"
                    )
                    
                    # 툴팁 표시
                    self.create_tooltip(label_widget, tooltip_text)
        except Exception as e:
            print(f"툴팁 표시 오류: {e}")
    def process_boxed_image(self, image, label_path, class_idx, row, col, img_index):
        """Process image with cropped boxes for specific class. Returns next column position."""

        try:
            with open(label_path, "r", encoding='utf-8') as f:
                # 读取文件中的每一行，并分割成列表
                boxes = [line.strip().split() for line in f]
            
            # 保存原始列位置，以便在出现异常时返回
            orig_col = col
            # 遍历所有的框
            for box in boxes:
                # 如果框的类别索引不匹配，跳过该框
                # if int(box[0]) != class_idx:
                #     continue
                if int(float(box[0])) != class_idx:
                    continue
                    
                # Extract box coordinates
                x, y, w, h = map(float, box[1:])
                left = int((x - w/2) * image.width)
                top = int((y - h/2) * image.height)
                right = int((x + w/2) * image.width)
                bottom = int((y + h/2) * image.height)
                
                # Crop and resize
                cropped = image.crop((left, top, right, bottom)).resize((100, 100))
                self.draw_boxes_on_image_corp(cropped, label_path, row, col, class_idx, img_index)
                
                col += 1
                if col == 12:
                    col = 0
                    
            return col
                
        except Exception as e:
            print(f"Error processing boxes in {label_path}: {e}")
            return orig_col
    def setup_keyboard_events(self):
    
        self.ctrl_pressed = False
        
        # Ctrl 키 상태 표시 레이블 생성

        # 라벨을 페이지네이션 컨트롤 왼쪽에 배치
        self.ctrl_status_label.pack(side=tk.RIGHT, padx=5)
    
        self.root.bind('<KeyPress>', self.on_key_press)
        self.root.bind('<KeyRelease>', self.on_key_release)
        self.root.bind("<KeyPress-Shift_L>", self.on_shift_press)
        self.root.bind("<KeyRelease-Shift_L>", self.on_shift_release)
        self.root.bind("<KeyPress-Shift_R>", self.on_shift_press)
        self.root.bind("<KeyRelease-Shift_R>", self.on_shift_release)
        
        # Caps Lock 키 이벤트
        self.root.bind("<KeyPress-Caps_Lock>", self.on_caps_lock_press)
        self.root.bind("<KeyRelease-Caps_Lock>", self.on_caps_lock_release)
        # 기존 setup_ui 메서드에 컨트롤 추가
    def on_key_press(self, event):
        if event.keysym in ('Control_L', 'Control_R'):
            self.ctrl_pressed = True
            if hasattr(self, 'ctrl_status_label'):
                self.ctrl_status_label.config(text="Ctrl: ✅", fg="green")
            # print("Ctrl key pressed, ctrl_pressed =", self.ctrl_pressed)
        

    def on_key_release(self, event):
        if event.keysym in ('Control_L', 'Control_R'):
            self.ctrl_pressed = False
            if hasattr(self, 'ctrl_status_label'):
                self.ctrl_status_label.config(text="Ctrl: ⬛", fg="gray")
            # print("Ctrl key released, ctrl_pressed =", self.ctrl_pressed)
            
    def on_shift_press(self, event):
        """Shift 키가 눌렸을 때 호출"""
        self.shift_pressed = True
        if hasattr(self, 'shift_status_label'):
            self.shift_status_label.config(text="Shift: ✅", fg="blue")
        # print("Shift key pressed")  # 디버깅용
        
    def on_shift_release(self, event):
        """Shift 키가 떼졌을 때 호출"""
        self.shift_pressed = False
        if hasattr(self, 'shift_status_label'):
            self.shift_status_label.config(text="Shift: ⬛", fg="gray")
        
    def on_caps_lock_press(self, event):
        """Caps Lock 키가 눌렸을 때 호출"""
        self.caps_locked = True
        if hasattr(self, 'caps_status_label'):
            self.caps_status_label.config(text="Caps: ✅", fg="purple")
        
    def on_caps_lock_release(self, event):
        """Caps Lock 키가 떼졌을 때 호출"""
        self.caps_locked = False
        if hasattr(self, 'caps_status_label'):
            self.caps_status_label.config(text="Caps: ⬛", fg="gray")

    def add_similar_label_controls(self):
        """유사 라벨 찾기 관련 컨트롤을 UI에 추가"""
        # 기준 라벨 프레임 추가 (control_panel_bottom에 추가)
        ref_label_frame = tk.Frame(self.control_panel_bottom)
        ref_label_frame.pack(side=tk.LEFT, padx=5)
        
        # 라벨 아이콘
        tk.Label(ref_label_frame, text="🔍", font=("Arial", 12)).pack(side=tk.LEFT, padx=1)
        
        # 버튼 추가
        find_similar_btn = tk.Button(
            ref_label_frame, 
            text="유사 라벨 찾기", 
            command=self.filter_by_reference_label
        )
        find_similar_btn.pack(side=tk.LEFT, padx=1)
        
        clear_ref_btn = tk.Button(
            ref_label_frame, 
            text="기준 초기화", 
            command=self.clear_reference_label
        )
        clear_ref_btn.pack(side=tk.LEFT, padx=1)
        
        # 기준 라벨 상태 표시 레이블
        self.ref_label_status = tk.Label(
            ref_label_frame,
            text="기준 라벨: 없음",
            font=("Arial", 8),
            fg="gray"
        )
        self.ref_label_status.pack(side=tk.LEFT, padx=5)
        
        # 사용자 안내 레이블
        help_label = tk.Label(
            ref_label_frame, 
            text="Ctrl+클릭: 기준 라벨 선택", 
            font=("Arial", 8, "bold"),
            fg="blue"
        )
        help_label.pack(side=tk.LEFT, padx=5)
    def setup_drag_select_events(self, label, label_path):
        """드래그 선택을 위한 이벤트 설정"""
        # 마우스 왼쪽 버튼 누름 이벤트
        label.bind("<ButtonPress-1>", lambda e, l=label, p=label_path: self.on_drag_start(e, l, p))
        
        # 마우스 이동 이벤트
        label.bind("<B1-Motion>", lambda e, l=label: self.on_drag_motion(e, l))
        
        # 마우스 왼쪽 버튼 뗌 이벤트
        label.bind("<ButtonRelease-1>", lambda e: self.on_drag_end(e))
        
    def on_drag_start(self, event, label, label_path):
        """드래그 시작 처리"""
        # Shift 키가 눌려있지 않으면 일반 클릭 처리
        if not self.shift_pressed:
            img_path = self.convert_labels_to_jpegimages(label_path)
            line_idx = getattr(label, 'line_idx', None)
            self.on_image_click(label, label_path, event, img_path, line_idx)
            return

        # 드래그 시작 위치 저장
        self.drag_start = (event.x_root, event.y_root)
        
        # 선택 영역 사각형 생성 (아직 그리지 않음)
        self.drag_rectangle = None
        
        print("Drag selection started")  # 디버깅용
    def find_similar_boxes(self, iou_threshold=0.97):
        """
        현재 페이지에서 IoU가 97% 이상인 서로 다른 클래스의 바운딩 박스들을 찾습니다.
        
        Returns:
            list: 유사한 바운딩 박스 그룹 목록. 각 그룹은 바운딩 박스 정보 사전의 목록입니다.
        """
        # 현재 페이지의 이미지 목록 가져오기
        current_page_images = self.get_current_page_images()
        
        # 유사한 박스 그룹 저장 리스트
        similar_box_groups = []
        
        # 진행 창 생성
        progress_window = tk.Toplevel(self.root)
        progress_window.title(f"유사한 바운딩 박스 탐색 중 (IoU ≥ {iou_threshold:.2f})")
        progress_window.geometry("450x200")
        progress_window.transient(self.root)
        progress_window.grab_set()

        progress_label = tk.Label(
        progress_window, 
        text=f"IoU {iou_threshold:.2f} 이상인 유사한 바운딩 박스 찾는 중...", 
        font=("Arial", 10, "bold")
        )
        progress_label.pack(pady=(15, 5))
        
        # 진행 상황 표시 요소
        progress_label = tk.Label(progress_window, text="유사한 바운딩 박스 찾는 중...", font=("Arial", 10, "bold"))
        progress_label.pack(pady=(15, 5))
        
        progress_bar = ttk.Progressbar(progress_window, length=400)
        progress_bar.pack(pady=10)
        progress_bar["maximum"] = len(current_page_images)
        
        status_label = tk.Label(progress_window, text="0/0 처리 완료")
        status_label.pack(pady=5)
        
        result_label = tk.Label(progress_window, text="")
        result_label.pack(pady=5)
        
        progress_window.update()
        
        # 각 이미지 처리
        for i, img_path in enumerate(current_page_images):
            # 진행 상황 업데이트
            progress_bar["value"] = i + 1
            status_label.config(text=f"{i+1}/{len(current_page_images)} 처리 중")
            progress_window.update()
            
            # 라벨 파일 경로
            label_path = self.convert_jpegimages_to_labels(img_path)
            
            if not os.path.isfile(label_path):
                continue
                
            # 모든 바운딩 박스 정보 읽기
            boxes = []
            try:
                with open(label_path, 'r', encoding='utf-8') as f:
                    for line_idx, line in enumerate(f):
                        parts = line.strip().split()
                        if len(parts) >= 5:
                            class_idx = int(float(parts[0]))
                            x_center = float(parts[1])
                            y_center = float(parts[2])
                            width = float(parts[3])
                            height = float(parts[4])
                            
                            box_info = {
                                'label_path': label_path,
                                'img_path': img_path,
                                'class': class_idx,
                                'line_idx': line_idx,
                                'x_center': x_center,
                                'y_center': y_center,
                                'width': width,
                                'height': height,
                                'coords': (
                                    x_center - width/2,
                                    y_center - height/2,
                                    x_center + width/2,
                                    y_center + height/2
                                )
                            }
                            boxes.append(box_info)
            except Exception as e:
                print(f"라벨 파일 읽기 오류 ({label_path}): {e}")
                continue
                
            # 모든 박스 쌍에 대해 IoU 계산
            for j in range(len(boxes)):
                for k in range(j+1, len(boxes)):
                    box1 = boxes[j]
                    box2 = boxes[k]
                    
                    # 같은 클래스면 건너뛰기
                    if box1['class'] == box2['class']:
                        continue
                        
                    # IoU 계산
                    iou = self.calculate_iou(box1['coords'], box2['coords'])
                    
                    # IoU가 97% 이상이면 유사한 박스로 간주
                    if iou >= iou_threshold:
                        # 이미 유사한 그룹에 포함되어 있는지 확인
                        found_group = False
                        for group in similar_box_groups:
                            if any(box['label_path'] == box1['label_path'] and 
                                box['line_idx'] == box1['line_idx'] for box in group):
                                # 기존 그룹에 추가
                                if not any(box['label_path'] == box2['label_path'] and 
                                        box['line_idx'] == box2['line_idx'] for box in group):
                                    group.append(box2)
                                found_group = True
                                break
                        
                        if not found_group:
                            # 새 그룹 생성
                            similar_box_groups.append([box1, box2])
            
            # 주기적으로 UI 업데이트
            if i % 10 == 0 or i == len(current_page_images) - 1:
                result_label.config(text=f"발견된 유사 박스 그룹: {len(similar_box_groups)}개")
                progress_window.update()
        
        # 완료 메시지
        progress_label.config(text="유사한 바운딩 박스 탐색 완료!")
        result_label.config(text=f"총 {len(similar_box_groups)}개의 유사 박스 그룹 발견")
        
        # 닫기 버튼
        close_button = tk.Button(progress_window, text="닫기", command=progress_window.destroy)
        close_button.pack(pady=10)
        
        return similar_box_groups    
    def select_similar_boxes(self):
        """
        유사한 바운딩 박스들을 찾고, 어떤 클래스를 유지할지 선택하는 UI를 제공합니다.
        각 박스의 시각적 미리보기와 함께 표시합니다.
        """
        threshold_window = tk.Toplevel(self.root)
        threshold_window.title("IoU 임계값 설정")
        threshold_window.geometry("400x200")
        threshold_window.transient(self.root)
        threshold_window.grab_set()

        tk.Label(threshold_window, 
           text="유사한 바운딩 박스를 찾기 위한 IoU 임계값을 설정하세요",
           font=("Arial", 11)).pack(pady=(20, 10))
    
        tk.Label(threshold_window, 
            text="값이 클수록 더 유사한 박스만 찾습니다(0.8 ~ 1.0)",
            font=("Arial", 9)).pack(pady=(0, 15))
        
        # IoU 임계값 설정 슬라이더
        iou_var = tk.DoubleVar(value=0.97)  # 기본값 97%
        
        slider_frame = ttk.Frame(threshold_window)
        slider_frame.pack(fill="x", padx=20, pady=10)
        
        tk.Label(slider_frame, text="0.8").pack(side="left")
        
        slider = ttk.Scale(
            slider_frame,
            from_=0.8,
            to=1.0,
            orient="horizontal",
            length=250,
            variable=iou_var,
            command=lambda v: iou_value_label.config(text=f"{float(v):.2f}")
        )
        slider.pack(side="left", padx=10)
        
        tk.Label(slider_frame, text="1.0").pack(side="left")
        
        # 현재 값 표시 레이블
        iou_value_frame = ttk.Frame(threshold_window)
        iou_value_frame.pack(pady=10)
        
        tk.Label(iou_value_frame, text="현재 값: ").pack(side="left")
        iou_value_label = tk.Label(iou_value_frame, text="0.97", font=("Arial", 10, "bold"))
        iou_value_label.pack(side="left")
        
        # 버튼 프레임
        button_frame = ttk.Frame(threshold_window)
        button_frame.pack(fill="x", pady=20, padx=20)
        
        def start_search():
            iou_threshold = iou_var.get()
            threshold_window.destroy()
            self.find_and_show_similar_boxes(iou_threshold)
        
        ttk.Button(button_frame, text="검색 시작", command=start_search).pack(side="left", padx=5)
        ttk.Button(button_frame, text="취소", command=threshold_window.destroy).pack(side="right", padx=5)

        threshold_window.wait_window()

        # 유사한 박스 그룹 찾기
        similar_box_groups = self.find_similar_boxes()
        
        if not similar_box_groups:
            tk.messagebox.showinfo("알림", "현재 페이지에서 유사한 바운딩 박스를 찾지 못했습니다.")
            return
        
        # 선택 창 생성
        selection_window = tk.Toplevel(self.root)
        selection_window.title("유사 바운딩 박스 처리")
        selection_window.geometry("800x600")  # 더 큰 창으로 조정
        selection_window.transient(self.root)
        
        # 안내 텍스트
        tk.Label(selection_window, text="IoU가 97% 이상인 서로 다른 클래스의 바운딩 박스들이 발견되었습니다.", 
            font=("Arial", 11)).pack(pady=(15, 5))
        tk.Label(selection_window, text="각 그룹에서 유지할 클래스를 선택하세요. 나머지는 자동으로 삭제됩니다.", 
            font=("Arial", 10)).pack(pady=(0, 10))
        
        # 스크롤 가능한 프레임
        canvas = tk.Canvas(selection_window)
        scrollbar = ttk.Scrollbar(selection_window, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        scrollbar.pack(side="right", fill="y")
        
        # 마우스 휠 스크롤 이벤트 바인딩
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", on_mousewheel)
        
        # 선택된 클래스 저장 변수
        selected_classes = {}
        
        # 박스 미리보기 이미지 저장 변수 (참조 유지용)
        preview_images = []
        
        # 각 그룹에 대한 UI 요소 생성
        for i, group in enumerate(similar_box_groups):
            # 그룹 프레임
            group_frame = ttk.LabelFrame(scrollable_frame, text=f"그룹 {i+1}")
            group_frame.pack(fill="x", padx=10, pady=10, ipadx=5, ipady=5)
            
            # 그룹 정보 표시
            img_path = group[0]['img_path']
            info_text = f"파일: {os.path.basename(img_path)}\n"
            info_text += f"박스 수: {len(group)}개\n"
            
            tk.Label(group_frame, text=info_text, anchor="w", justify="left").pack(padx=5, pady=(5,10), fill="x")
            
            # 클래스 선택 라디오 버튼과 미리보기 이미지 프레임
            preview_frame = ttk.Frame(group_frame)
            preview_frame.pack(fill="x", padx=5, pady=5)
            
            # 클래스 선택 변수
            class_var = tk.IntVar()
            class_var.set(group[0]['class'])  # 기본값은 첫 번째 클래스
            selected_classes[i] = class_var
            
            # 원본 이미지 로드 (한 번만)
            try:
                with Image.open(img_path) as full_img:
                    img_width, img_height = full_img.size
                    
                    # 각 박스에 대한 미리보기 생성
                    for box_idx, box in enumerate(group):
                        # 박스 컨테이너 프레임
                        box_frame = ttk.Frame(preview_frame)
                        box_frame.pack(side="left", padx=10, pady=5)
                        
                        # 클래스 타이틀
                        class_label = tk.Label(
                            box_frame, 
                            text=f"클래스 {box['class']}", 
                            font=("Arial", 10, "bold"),
                            fg="blue"
                        )
                        class_label.pack(pady=(0, 5))
                        
                        # 박스 좌표 계산
                        x_center, y_center = box['x_center'], box['y_center']
                        width, height = box['width'], box['height']
                        
                        left = int((x_center - width/2) * img_width)
                        top = int((y_center - height/2) * img_height)
                        right = int((x_center + width/2) * img_width)
                        bottom = int((y_center + height/2) * img_height)
                        
                        # 박스 이미지 자르기 및 리사이즈
                        crop_coords = (
                            max(0, left),
                            max(0, top),
                            min(img_width, right),
                            min(img_height, bottom)
                        )
                        
                        cropped = full_img.crop(crop_coords)
                        preview_size = (120, 120)  # 미리보기 크기
                        cropped.thumbnail(preview_size, Image.LANCZOS)
                        
                        # 박스 테두리와 배경색 설정을 위한 이미지 컨테이너
                        box_container = tk.Frame(
                            box_frame, 
                            bd=3, 
                            relief="solid", 
                            bg="white"
                        )
                        box_container.pack(pady=5)
                        
                        # 이미지를 tkinter 호환 형식으로 변환
                        photo = ImageTk.PhotoImage(cropped)
                        preview_images.append(photo)  # 참조 유지
                        
                        # 이미지 라벨
                        img_label = tk.Label(box_container, image=photo, bg="white")
                        img_label.image = photo
                        img_label.pack(padx=2, pady=2)
                        
                        # 좌표 및 크기 정보
                        coord_info = f"중심: ({x_center:.2f}, {y_center:.2f})\n"
                        coord_info += f"크기: {width:.2f} x {height:.2f}"
                        
                        coord_label = tk.Label(box_frame, text=coord_info, font=("Arial", 8))
                        coord_label.pack(pady=2)
                        
                        # 라디오 버튼 생성 및 연결
                        radio = tk.Radiobutton(
                            box_frame, 
                            text="이 클래스 유지", 
                            variable=class_var, 
                            value=box['class'],
                            command=lambda bf=box_container, cv=class_var, bc=box['class']: 
                                    update_selection_highlight(bf, cv, bc)
                        )
                        radio.pack(pady=5)
                        
                        # 초기 선택 상태 하이라이트
                        if box['class'] == class_var.get():
                            box_container.config(bg="lightgreen")
            
            except Exception as e:
                print(f"이미지 미리보기 생성 중 오류: {e}")
                tk.Label(preview_frame, text=f"미리보기 오류: {str(e)}", fg="red").pack(pady=10)
        
        # 선택 상태 하이라이트 업데이트 함수
        def update_selection_highlight(box_frame, class_var, box_class):
            # 모든 박스 컨테이너 찾기
            parent = box_frame.master
            box_containers = [widget for widget in parent.winfo_children() 
                            if isinstance(widget, tk.Frame)]
            
            # 선택된 클래스에 따라 하이라이트 적용
            for container in box_containers:
                # 선택된 박스는 녹색 배경, 나머지는 흰색 배경
                if class_var.get() == box_class and container == box_frame:
                    container.config(bg="lightgreen")
                else:
                    container.config(bg="white")
        
        # 버튼 프레임
        button_frame = ttk.Frame(selection_window)
        button_frame.pack(fill="x", pady=15, padx=10)
        
        # 처리 함수
        def process_selection():
            """선택한 항목을 처리하는 함수 - 유지할 클래스 이외의 박스만 선택합니다."""
            # 삭제 대상 목록 생성
            selected_for_deletion = []
            
            print("유사 박스 그룹 처리 시작...")
            print(f"총 {len(similar_box_groups)}개의 유사 박스 그룹이 있습니다.")
            
            for i, group in enumerate(similar_box_groups):
                keep_class = selected_classes[i].get()
                print(f"그룹 {i+1}: 유지할 클래스 {keep_class}")
                
                for box in group:
                    if box['class'] != keep_class:
                        # 삭제 대상 목록에 추가
                        selected_for_deletion.append((box['label_path'], box['line_idx']))
                        print(f"  - 삭제 대상: 파일 {os.path.basename(box['label_path'])}, 라인 {box['line_idx']}, 클래스 {box['class']}")
            
            if not selected_for_deletion:
                tk.messagebox.showinfo("알림", "삭제할 박스가 없습니다.")
                selection_window.destroy()
                return
            
            # 특정 파일의 특정 박스만 선택하는 대신 직접 선택 정보 업데이트
            success_count = 0
            
            # 직접 선택 정보 구성
            for box_path, box_line_idx in selected_for_deletion:
                # 라벨 파일 정보 읽기
                try:
                    with open(box_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        
                    if 0 <= box_line_idx < len(lines):
                        line = lines[box_line_idx]
                        parts = line.strip().split()
                        
                        if len(parts) >= 5:
                            # 박스 정보 추출
                            class_id = int(float(parts[0]))
                            
                            # 선택된 이미지 목록에 추가
                            if box_path not in self.selected_image_labels:
                                self.selected_image_labels.append(box_path)
                            
                            # 박스 정보 구성
                            box_info = {
                                'class_id': class_id,
                                'x_center': float(parts[1]),
                                'y_center': float(parts[2]),
                                'width': float(parts[3]),
                                'height': float(parts[4]),
                                'line_idx': box_line_idx
                            }
                            
                            # 이미 해당 라벨이 있는지 확인
                            found = False
                            for info in self.selected_label_info:
                                if info['path'] == box_path:
                                    # 이미 같은 라인의 박스가 있는지 확인
                                    box_found = False
                                    for box in info['boxes']:
                                        if box.get('line_idx') == box_line_idx:
                                            box.update(box_info)
                                            box_found = True
                                            break
                                            
                                    if not box_found:
                                        info['boxes'].append(box_info)
                                        success_count += 1
                                        
                                    found = True
                                    break
                                    
                            if not found:
                                # 새 라벨 정보 생성
                                new_label_info = {
                                    'path': box_path,
                                    'boxes': [box_info]
                                }
                                self.selected_label_info.append(new_label_info)
                                success_count += 1
                except Exception as e:
                    print(f"라벨 정보 처리 오류 ({os.path.basename(box_path)}): {e}")
            
            # 중요: 현재 페이지의 위젯들을 직접 업데이트
            label_widgets = [widget for widget in self.frame.winfo_children() 
                        if isinstance(widget, tk.Label) and hasattr(widget, 'label_path')]
            
            print(f"현재 페이지의 위젯 수: {len(label_widgets)}")
            
            # 위젯을 순회하며 선택 대상인지 확인하고 시각적으로 표시
            for widget in label_widgets:
                if not hasattr(widget, 'label_path') or not hasattr(widget, 'line_idx'):
                    continue
                    
                for box_path, box_line_idx in selected_for_deletion:
                    # 경로와 라인 인덱스 비교 (경로 정규화)
                    if (os.path.normpath(widget.label_path) == os.path.normpath(box_path) and 
                        widget.line_idx == box_line_idx):
                        # 이 위젯은 삭제 대상 - 빨간색으로 표시
                        print(f"위젯 시각적 표시: {os.path.basename(widget.label_path)}, 라인 {widget.line_idx}")
                        widget.config(highlightbackground="red", highlightthickness=4)
                        widget.config(bg="#ffdddd")  # 연한 빨간색 배경
                        
                        # checklist에 추가
                        if widget not in self.checklist:
                            self.checklist.append(widget)
            
            # 위젯 업데이트 강제 실행
            self.root.update_idletasks()
            
            # 선택 정보 업데이트 (선택 카운터 등)
            self.update_selection_info()
            
            print(f"박스 선택 완료: {success_count}개")
            print(f"selected_image_labels 크기: {len(self.selected_image_labels)}")
            print(f"selected_label_info 크기: {len(self.selected_label_info)}")
            print(f"위젯 강조 표시: {len(self.checklist)}개")
            
            if success_count > 0:
                tk.messagebox.showinfo(
                    "박스 선택 완료", 
                    f"{success_count}개의 바운딩 박스가 선택되었습니다.\n"
                    "이제 [선택 삭제] 버튼을 클릭하여 삭제를 완료하세요."
                )
            else:
                tk.messagebox.showwarning(
                    "선택 실패",
                    "박스 선택에 실패했습니다. 현재 표시된 페이지에 해당 박스가 없을 수 있습니다.\n"
                    "대상 이미지가 있는 페이지로 이동한 후 다시 시도하세요."
                )
            
            # 창 닫기 전에 마우스 휠 이벤트 해제
            canvas.unbind_all("<MouseWheel>")
            selection_window.destroy()
        # 선택 처리 버튼
            select_button = ttk.Button(
                button_frame, 
                text="선택한 클래스 유지하고 나머지 삭제", 
                command=process_selection,
                default="active"  # 기본 버튼으로 설정 - Enter 키로 활성화
            )
            select_button.pack(side="left", padx=5)

            cancel_button = ttk.Button(
                button_frame, 
                text="취소", 
                command=lambda: (canvas.unbind_all("<MouseWheel>"), selection_window.destroy())
            )
            cancel_button.pack(side="right", padx=5)

            # Enter 키로 기본 버튼 활성화
            selection_window.bind("<Return>", lambda e: process_selection())
            # Escape 키로 취소 버튼 활성화
            selection_window.bind("<Escape>", lambda e: (canvas.unbind_all("<MouseWheel>"), selection_window.destroy()))
    def find_and_show_similar_boxes(self, iou_threshold):
        """
        설정된 IoU 임계값으로 유사한 박스를 찾고 UI를 표시합니다.
        
        Parameters:
            iou_threshold (float): IoU 임계값 (0.0 ~ 1.0)
        """
        # 유사한 박스 그룹 찾기
        similar_box_groups = self.find_similar_boxes(iou_threshold)
        
        if not similar_box_groups:
            tk.messagebox.showinfo("알림", f"현재 페이지에서 IoU {iou_threshold:.2f} 이상인 유사한 바운딩 박스를 찾지 못했습니다.")
            return
        
        # 선택 창 생성
        selection_window = tk.Toplevel(self.root)
        selection_window.title(f"유사 바운딩 박스 처리 (IoU ≥ {iou_threshold:.2f})")
        selection_window.geometry("800x600")  # 더 큰 창으로 조정
        selection_window.transient(self.root)
        
        # 안내 텍스트
        tk.Label(selection_window, 
            text=f"IoU가 {iou_threshold:.2f} 이상인 서로 다른 클래스의 바운딩 박스들이 발견되었습니다.", 
            font=("Arial", 11)).pack(pady=(15, 5))
        tk.Label(selection_window, 
            text="각 그룹에서 유지할 클래스를 선택하세요. 나머지는 자동으로 삭제됩니다.", 
            font=("Arial", 10)).pack(pady=(0, 10))
        
        # 스크롤 가능한 프레임
        canvas = tk.Canvas(selection_window)
        scrollbar = ttk.Scrollbar(selection_window, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        scrollbar.pack(side="right", fill="y")
        
        # 마우스 휠 스크롤 이벤트 바인딩
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", on_mousewheel)
        
        # 선택된 클래스 저장 변수
        selected_classes = {}
        
        # 박스 미리보기 이미지 저장 변수 (참조 유지용)
        preview_images = []
        
        # 각 그룹에 대한 UI 요소 생성
        for i, group in enumerate(similar_box_groups):
            # 그룹 프레임
            group_frame = ttk.LabelFrame(scrollable_frame, text=f"그룹 {i+1}")
            group_frame.pack(fill="x", padx=10, pady=10, ipadx=5, ipady=5)
            
            # 그룹 정보 표시
            img_path = group[0]['img_path']
            info_text = f"파일: {os.path.basename(img_path)}\n"
            info_text += f"박스 수: {len(group)}개\n"
            
            tk.Label(group_frame, text=info_text, anchor="w", justify="left").pack(padx=5, pady=(5,10), fill="x")
            
            # 클래스 선택 라디오 버튼과 미리보기 이미지 프레임
            preview_frame = ttk.Frame(group_frame)
            preview_frame.pack(fill="x", padx=5, pady=5)
            
            # 클래스 선택 변수
            class_var = tk.IntVar()
            class_var.set(group[0]['class'])  # 기본값은 첫 번째 클래스
            selected_classes[i] = class_var
            
            # 원본 이미지 로드 (한 번만)
            try:
                with Image.open(img_path) as full_img:
                    img_width, img_height = full_img.size
                    
                    # 각 박스에 대한 미리보기 생성
                    for box_idx, box in enumerate(group):
                        # 박스 컨테이너 프레임
                        box_frame = ttk.Frame(preview_frame)
                        box_frame.pack(side="left", padx=10, pady=5)
                        
                        # 클래스 타이틀
                        class_label = tk.Label(
                            box_frame, 
                            text=f"클래스 {box['class']}", 
                            font=("Arial", 10, "bold"),
                            fg="blue"
                        )
                        class_label.pack(pady=(0, 5))
                        
                        # 박스 좌표 계산
                        x_center, y_center = box['x_center'], box['y_center']
                        width, height = box['width'], box['height']
                        
                        left = int((x_center - width/2) * img_width)
                        top = int((y_center - height/2) * img_height)
                        right = int((x_center + width/2) * img_width)
                        bottom = int((y_center + height/2) * img_height)
                        
                        # 박스 이미지 자르기 및 리사이즈
                        crop_coords = (
                            max(0, left),
                            max(0, top),
                            min(img_width, right),
                            min(img_height, bottom)
                        )
                        
                        cropped = full_img.crop(crop_coords)
                        preview_size = (120, 120)  # 미리보기 크기
                        cropped.thumbnail(preview_size, Image.LANCZOS)
                        
                        # 박스 테두리와 배경색 설정을 위한 이미지 컨테이너
                        box_container = tk.Frame(
                            box_frame, 
                            bd=3, 
                            relief="solid", 
                            bg="white"
                        )
                        box_container.pack(pady=5)
                        
                        # 이미지를 tkinter 호환 형식으로 변환
                        photo = ImageTk.PhotoImage(cropped)
                        preview_images.append(photo)  # 참조 유지
                        
                        # 이미지 라벨
                        img_label = tk.Label(box_container, image=photo, bg="white")
                        img_label.image = photo
                        img_label.pack(padx=2, pady=2)
                        
                        # 좌표 및 크기 정보
                        coord_info = f"중심: ({x_center:.2f}, {y_center:.2f})\n"
                        coord_info += f"크기: {width:.2f} x {height:.2f}"
                        
                        coord_label = tk.Label(box_frame, text=coord_info, font=("Arial", 8))
                        coord_label.pack(pady=2)
                        
                        # 라디오 버튼 생성 및 연결
                        radio = tk.Radiobutton(
                            box_frame, 
                            text="이 클래스 유지", 
                            variable=class_var, 
                            value=box['class'],
                            command=lambda bf=box_container, cv=class_var, bc=box['class']: 
                                    update_selection_highlight(bf, cv, bc)
                        )
                        radio.pack(pady=5)
                        
                        # 초기 선택 상태 하이라이트
                        if box['class'] == class_var.get():
                            box_container.config(bg="lightgreen")
            
            except Exception as e:
                print(f"이미지 미리보기 생성 중 오류: {e}")
                tk.Label(preview_frame, text=f"미리보기 오류: {str(e)}", fg="red").pack(pady=10)
        
        # 선택 상태 하이라이트 업데이트 함수
        def update_selection_highlight(box_container, class_var, box_class):
            # 모든 박스 컨테이너 찾기
            parent = box_container.master.master  # box_container -> box_frame -> preview_frame
            box_frames = [widget for widget in parent.winfo_children() 
                        if isinstance(widget, ttk.Frame)]
            
            # 선택된 클래스에 따라 하이라이트 적용
            for frame in box_frames:
                # 각 프레임에서 이미지 컨테이너 찾기
                containers = [widget for widget in frame.winfo_children() 
                            if isinstance(widget, tk.Frame) and widget.cget("relief") == "solid"]
                
                # 클래스 라벨 찾기
                class_labels = [widget for widget in frame.winfo_children() 
                            if isinstance(widget, tk.Label) and widget.cget("font") == ("Arial", 10, "bold")]
                
                if containers and class_labels:
                    container = containers[0]
                    class_label = class_labels[0]
                    # 라벨에서 클래스 번호 추출
                    try:
                        current_class = int(class_label.cget("text").split()[1])
                        # 선택된 박스는 녹색 배경, 나머지는 흰색 배경
                        if class_var.get() == current_class:
                            container.config(bg="lightgreen")
                        else:
                            container.config(bg="white")
                    except:
                        pass
        
        # 버튼 프레임
        button_frame = ttk.Frame(selection_window)
        button_frame.pack(fill="x", pady=15, padx=10)
        
        # 처리 함수
        def process_selection():
            # 선택된 클래스를 제외한 나머지 박스 선택
            self.deselect_all_images()
            
            selected_for_deletion = []
            
            for i, group in enumerate(similar_box_groups):
                keep_class = selected_classes[i].get()
                
                for box in group:
                    if box['class'] != keep_class:
                        # 삭제 대상 목록에 추가
                        selected_for_deletion.append((box['label_path'], box['line_idx']))
            
            if not selected_for_deletion:
                tk.messagebox.showinfo("알림", "삭제할 박스가 없습니다.")
                selection_window.destroy()
                return
            
            # 삭제 대상 박스 선택
            self.auto_select_boxes(selected_for_deletion)
            
            tk.messagebox.showinfo(
                "박스 선택 완료", 
                f"{len(selected_for_deletion)}개의 바운딩 박스가 선택되었습니다.\n"
                "이제 [선택 삭제] 버튼을 클릭하여 삭제를 완료하세요."
            )
            
            # 창 닫기 전에 마우스 휠 이벤트 해제
            canvas.unbind_all("<MouseWheel>")
            selection_window.destroy()
        
        # 선택 처리 버튼
        ttk.Button(button_frame, text="선택 항목 처리", command=process_selection).pack(side="left", padx=5)
        ttk.Button(button_frame, text="취소", command=lambda: 
                (canvas.unbind_all("<MouseWheel>"), selection_window.destroy())
                ).pack(side="right", padx=5)
        
    def auto_select_boxes(self, box_list):
        """
        지정된 라벨 파일의 특정 라인 인덱스에 해당하는 박스를 자동으로 선택합니다.
        
        Parameters:
            box_list (list): (label_path, line_idx) 튜플의 목록
        """
        # 디버깅 정보 출력
        start_time = time.time()

        # 진행 창 생성 (선택할 박스가 많은 경우)
        progress_window = None
        progress_bar = None
        progress_label = None
            
        if len(box_list) > 50:
            progress_window = tk.Toplevel(self.root)
            progress_window.title("박스 선택 중")
            progress_window.geometry("350x150")
            progress_window.transient(self.root)
            
            progress_label = tk.Label(progress_window, text=f"{len(box_list)}개 박스 선택 중...")
            progress_label.pack(pady=(15, 10))
            
            progress_bar = ttk.Progressbar(progress_window, length=300)
            progress_bar.pack(pady=10)
            progress_bar["maximum"] = len(box_list)
            
            status_label = tk.Label(progress_window, text="0% 완료")
            status_label.pack(pady=5)
            
            progress_window.update()

        # 디버깅 정보 출력
            print(f"선택할 박스 목록: {len(box_list)}개")

            # 효율적인 검색을 위해 경로-라인 인덱스 매핑 생성
            path_line_map = {}
            for i, (box_path, box_line_idx) in enumerate(box_list):
                # 진행 창 업데이트
                if progress_bar and i % 10 == 0:
                    progress = (i / len(box_list)) * 100
                    progress_bar["value"] = i
                    status_label.config(text=f"{progress:.1f}% 완료")
                    progress_window.update_idletasks()
                
                norm_path = os.path.normpath(box_path)
                if norm_path not in path_line_map:
                    path_line_map[norm_path] = []
                path_line_map[norm_path].append(box_line_idx)

            # 처리 과정 최적화 - 미리 선택된 경로 확인
            already_selected_paths = set(self.selected_image_labels)
                
        # 현재 페이지의 모든 이미지 라벨 위젯 가져오기
        label_widgets = [widget for widget in self.frame.winfo_children() 
                    if isinstance(widget, tk.Label) and hasattr(widget, 'label_path')]
        
        print(f"현재 페이지의 위젯 수: {len(label_widgets)}")
        
        # 보다 상세한 디버깅 정보
        for i, widget in enumerate(label_widgets[:5]):
            if hasattr(widget, 'label_path'):
                label_path = widget.label_path
                line_idx = widget.line_idx if hasattr(widget, 'line_idx') else "없음"
                print(f"위젯 {i}: 경로={os.path.basename(label_path)}, 라인={line_idx}")
        
        selected_count = 0
        
        # 각 위젯에 대해 확인
        for widget in label_widgets:
            if not hasattr(widget, 'label_path'):
                continue
                
            # 정규화된 경로로 확인
            norm_label_path = os.path.normpath(widget.label_path)
            
            # 이 위젯이 특정 박스를 표시하는지 확인
            if norm_label_path in path_line_map and hasattr(widget, 'line_idx'):
                # 현재 위젯의 라인 인덱스
                current_line_idx = widget.line_idx
                
                # 라인 인덱스가 선택 대상인지 확인
                if current_line_idx in path_line_map[norm_label_path]:
                    # 박스 선택 처리
                    print(f"박스 선택 시도: {os.path.basename(widget.label_path)}, 라인 {current_line_idx}")
                    
                    try:
                        # 시각적 선택 처리
                        widget.config(highlightbackground="red", highlightthickness=4)
                        widget.config(bg="#ffdddd")  # 연한 빨간색 배경
                        
                        # 선택 목록에 추가
                        if widget.label_path not in self.selected_image_labels:
                            self.selected_image_labels.append(widget.label_path)
                            print(f"  - selected_image_labels에 추가됨")
                        
                        if widget not in self.checklist:
                            self.checklist.append(widget)
                            print(f"  - checklist에 추가됨")
                        
                        # 박스 정보 캐시된 방식으로 가져오기
                        lines = self._get_label_data(widget.label_path)
                        
                        if lines and 0 <= current_line_idx < len(lines):
                            line = lines[current_line_idx]
                            parts = line.strip().split()
                            
                            if len(parts) >= 5:
                                # 박스 정보 추출
                                class_id = int(float(parts[0]))
                                x_center = float(parts[1])
                                y_center = float(parts[2])
                                width = float(parts[3])
                                height = float(parts[4])
                                
                                # 박스 정보 생성
                                box_info = {
                                    'class_id': class_id,
                                    'x_center': x_center,
                                    'y_center': y_center,
                                    'width': width,
                                    'height': height,
                                    'line_idx': current_line_idx
                                }
                                
                                # selected_label_info 업데이트 - 기존 항목 확인
                                self.update_label_info(widget.label_path, box_info)
                                
                                print(f"  - 박스 정보 저장됨: 클래스 {class_id}")
                                selected_count += 1
                    
                    except Exception as e:
                        print(f"  - 박스 선택 처리 실패: {e}")
                        import traceback
                        traceback.print_exc()
        
        # 선택 정보 업데이트
        self.update_selection_info()
        self.root.update_idletasks()  # UI 업데이트
        
        print(f"선택 완료: {selected_count}개 박스 선택됨")
        print(f"최종 selected_image_labels 길이: {len(self.selected_image_labels)}")
        print(f"최종 selected_label_info 길이: {len(self.selected_label_info)}")
        
        end_time = time.time()
        elapsed_time = end_time - start_time
        print(f"박스 선택 완료: {elapsed_time:.2f}초 소요")

        # 진행 창 업데이트 및 닫기
        if progress_window:
            progress_bar["value"] = len(box_list)
            progress_label.config(text=f"{len(box_list)}개 박스 선택 완료")
            status_label.config(text=f"100% 완료 ({elapsed_time:.2f}초)")
            
            # 닫기 버튼 추가
            close_button = tk.Button(progress_window, text="닫기", command=progress_window.destroy)
            close_button.pack(pady=10)
            
            # 3초 후 자동 닫기
            self.root.after(3000, progress_window.destroy)

        return selected_count

    def update_label_info(self, label_path, box_info):
        """
        라벨 정보를 효율적으로 업데이트하는 헬퍼 함수
        
        Parameters:
            label_path (str): 라벨 파일 경로
            box_info (dict): 박스 정보 딕셔너리
        """
        line_idx = box_info['line_idx']
        
        # 이미 해당 라벨이 있는지 확인
        existing_label = None
        for info in self.selected_label_info:
            if info['path'] == label_path:
                existing_label = info
                break
        
        if existing_label:
            # 이미 같은 라인의 박스가 있는지 확인
            for box in existing_label['boxes']:
                if box.get('line_idx') == line_idx:
                    # 기존 박스 정보 업데이트
                    box.update(box_info)
                    return
                    
            # 같은 라인의 박스가 없으면 추가
            existing_label['boxes'].append(box_info)
        else:
            # 새 라벨 정보 생성
            new_label_info = {
                'path': label_path,
                'boxes': [box_info]
            }
            self.selected_label_info.append(new_label_info)
    def get_current_page_images(self):
        """
        현재 페이지에 표시된 이미지 경로 목록을 반환합니다.
        """
        # 현재 선택된 클래스 확인
        selected_class = self.class_selector.get()
        if selected_class == "Select Class":
            return []
            
        class_idx = int(float(selected_class))
        
        # 해당 클래스의 모든 이미지 가져오기
        class_images = [path for path in self.labels if path in self.labelsdata[class_idx]]
        
        # 겹침 필터가 적용된 경우 필터링
        overlap_class = self.overlap_class_selector.get()
        if overlap_class != "선택 안함":
            overlap_class_idx = int(float(overlap_class))
            filter_type = self.overlap_filter_var.get()
            
            if filter_type != "모두 보기":
                # 필터링된 이미지만 가져오기 (이 부분은 기존 코드에 따라 조정 필요)
                filtered_images, _ = self.filter_images_by_overlap(
                    class_images, class_idx, overlap_class_idx)
                class_images = filtered_images
        
        # 현재 페이지 범위 계산
        start_idx = self.current_page * self.page_size
        end_idx = min(start_idx + self.page_size, len(class_images))
        
        # 현재 페이지 이미지 목록
        current_images = class_images[start_idx:end_idx]
        
        # 이미지 경로로 변환
        image_paths = [self.convert_labels_to_jpegimages(label_path)
                    for label_path in current_images]
        
        return image_paths
    def on_drag_motion(self, event, label):
        """드래그 중 처리 - 실시간 시각적 피드백 (성능 최적화)"""
        # Shift 키가 눌려있지 않거나 드래그 시작 위치가 없으면 무시
        if not self.shift_pressed or not self.drag_start:
            return

        # Throttling: 16ms(약 60 FPS) 간격으로만 업데이트하여 성능 개선
        current_time = time.time() * 1000  # 밀리초
        if current_time - self.last_drag_update < 16:
            return
        self.last_drag_update = current_time

        try:
            current_pos = (event.x_root, event.y_root)

            # 이전에 그려진 사각형이 있으면 삭제
            if self.drag_rectangle:
                self.canvas.delete(self.drag_rectangle)

            # Canvas 상의 좌표로 변환
            canvas_x1 = self.drag_start[0] - self.canvas.winfo_rootx()
            canvas_y1 = self.drag_start[1] - self.canvas.winfo_rooty()
            canvas_x2 = current_pos[0] - self.canvas.winfo_rootx()
            canvas_y2 = current_pos[1] - self.canvas.winfo_rooty()

            # 드래그 영역 사각형 그리기 (빨간 점선)
            self.drag_rectangle = self.canvas.create_rectangle(
                canvas_x1, canvas_y1, canvas_x2, canvas_y2,
                outline="red", width=2, dash=(4, 4), tags="drag_selection"
            )

            # 실시간으로 선택될 위젯들을 미리 하이라이트
            self._preview_drag_selection(current_pos)
        except Exception as e:
            # exe 빌드 시 발생할 수 있는 예외 무시
            print(f"드래그 모션 에러 (무시): {e}")

    def _preview_drag_selection(self, end_pos):
        """드래그 중 선택될 위젯들을 미리 표시 (시각적 피드백)"""
        try:
            # 드래그 영역 계산
            x1 = min(self.drag_start[0], end_pos[0])
            y1 = min(self.drag_start[1], end_pos[1])
            x2 = max(self.drag_start[0], end_pos[0])
            y2 = max(self.drag_start[1], end_pos[1])

            # 모든 위젯에 대해 미리보기 상태 초기화
            for widget in self.frame.winfo_children():
                if not isinstance(widget, tk.Label) or not hasattr(widget, 'label_path'):
                    continue

                try:
                    widget_x = widget.winfo_rootx()
                    widget_y = widget.winfo_rooty()
                    widget_width = widget.winfo_width()
                    widget_height = widget.winfo_height()

                    # 위젯이 드래그 영역과 겹치는지 확인
                    is_in_drag_area = (widget_x < x2 and widget_x + widget_width > x1 and
                                       widget_y < y2 and widget_y + widget_height > y1)

                    if is_in_drag_area:
                        # 드래그 영역 내: 색상 미리보기
                        if widget in self.checklist:
                            # 현재 선택된 것 -> 해제될 예정: 주황색
                            widget.config(highlightbackground="orange", highlightthickness=3)
                        else:
                            # 현재 미선택 -> 선택될 예정: 파란색
                            widget.config(highlightbackground="blue", highlightthickness=3)
                    else:
                        # 드래그 영역 밖: 원래 상태로 복원
                        if widget in self.checklist:
                            # 선택된 상태 유지
                            widget.config(highlightbackground="red", highlightthickness=4)
                        else:
                            # 미선택 상태 유지
                            widget.config(highlightbackground="white", highlightthickness=2)
                except TclError:
                    # 위젯이 이미 삭제되었을 경우 무시
                    continue
        except Exception as e:
            # 예기치 않은 에러 발생 시 무시 (exe 안정성 향상)
            print(f"드래그 미리보기 에러 (무시): {e}")
        
    def on_drag_end(self, event):
        """드래그 종료 처리 - 토글 선택 기능 (Shift + 클릭 또는 Shift + 드래그)"""
        # Shift 키가 눌려있지 않거나 드래그 시작 위치가 없으면 무시
        if not self.shift_pressed or not self.drag_start:
            return

        # 드래그 종료 위치
        end_pos = (event.x_root, event.y_root)

        # 드래그 거리 계산
        drag_distance = ((end_pos[0] - self.drag_start[0]) ** 2 +
                        (end_pos[1] - self.drag_start[1]) ** 2) ** 0.5

        # 이전에 그려진 사각형이 있으면 삭제
        if self.drag_rectangle:
            self.canvas.delete(self.drag_rectangle)
            self.drag_rectangle = None

        # 드래그 거리가 10픽셀 미만이면 "클릭"으로 간주
        if drag_distance < 10:
            # Shift + 클릭: 클릭한 위젯만 토글
            clicked_widget = event.widget

            # 이벤트가 발생한 위젯이 Label이고 label_path 속성이 있는지 확인
            if isinstance(clicked_widget, tk.Label) and hasattr(clicked_widget, 'label_path'):
                self._toggle_widget_selection(clicked_widget)
            else:
                # 클릭 위치에서 가장 가까운 위젯 찾기
                for widget in self.frame.winfo_children():
                    if isinstance(widget, tk.Label) and hasattr(widget, 'label_path'):
                        widget_x = widget.winfo_rootx()
                        widget_y = widget.winfo_rooty()
                        widget_width = widget.winfo_width()
                        widget_height = widget.winfo_height()

                        # 클릭 위치가 위젯 영역 내에 있는지 확인
                        if (widget_x <= end_pos[0] <= widget_x + widget_width and
                            widget_y <= end_pos[1] <= widget_y + widget_height):
                            self._toggle_widget_selection(widget)
                            break

            print("Shift + Click: Single toggle")
        else:
            # Shift + 드래그: 드래그 영역 내의 모든 위젯 토글
            x1 = min(self.drag_start[0], end_pos[0])
            y1 = min(self.drag_start[1], end_pos[1])
            x2 = max(self.drag_start[0], end_pos[0])
            y2 = max(self.drag_start[1], end_pos[1])

            # 드래그 영역 내의 이미지 라벨 찾아서 토글 선택
            for widget in self.frame.winfo_children():
                if isinstance(widget, tk.Label) and hasattr(widget, 'label_path'):
                    # 위젯의 전역 좌표 계산
                    widget_x = widget.winfo_rootx()
                    widget_y = widget.winfo_rooty()
                    widget_width = widget.winfo_width()
                    widget_height = widget.winfo_height()

                    # 위젯이 드래그 영역과 겹치는지 확인
                    if (widget_x < x2 and widget_x + widget_width > x1 and
                        widget_y < y2 and widget_y + widget_height > y1):
                        self._toggle_widget_selection(widget)

            print(f"Shift + Drag: Area selection (distance: {drag_distance:.1f}px)")

        # 드래그 정보 초기화
        self.drag_start = None

        # 선택 정보 업데이트
        self.update_selection_info()

    def _toggle_widget_selection(self, widget):
        """위젯의 선택 상태를 토글합니다."""
        if widget in self.checklist:
            # 선택 해제
            widget.config(highlightbackground="white", highlightthickness=2)
            widget.config(bg="white")
            if widget.label_path in self.selected_image_labels:
                self.selected_image_labels.remove(widget.label_path)
            if widget in self.checklist:
                self.checklist.remove(widget)
        else:
            # 선택
            widget.config(highlightbackground="red", highlightthickness=4)
            widget.config(bg="#ffdddd")  # 연한 빨간색 배경
            self.selected_image_labels.append(widget.label_path)
            if widget not in self.checklist:
                self.checklist.append(widget)
    def process_full_image(self, image, label_path, row, col, idx, class_idx=None):
        """
        전체 이미지를 처리하고 바운딩 박스를 표시합니다.
        
        Parameters:
            image (PIL.Image): 처리할 이미지
            label_path (str): 라벨 파일 경로
            row (int): 그리드 행 위치
            col (int): 그리드 열 위치
            idx (int): 이미지 인덱스
            class_idx (int, optional): 특정 클래스 인덱스 (바운딩 박스 필터링용)
        
        Returns:
            int: 업데이트된 열 위치
        """
        # 전체 이미지 표시
        image_resized = image.resize((200, 200))
        self.draw_boxes_on_image(image_resized, label_path, row, col, idx)
        
        # class_idx가 제공된 경우에만 박스 처리
        if class_idx is not None:
            try:
                # 캐싱된 라벨 데이터 사용
                lines = self._get_label_data(label_path)
                boxes = [line.strip().split() for line in lines if line.strip()]
                
                boxes_processed = False
                current_col = col
                
                for line_idx, box in enumerate(boxes):
                    if len(box) < 5:  # 유효한 박스 데이터 확인
                        continue
                        
                    try:
                        box_class = int(float(box[0]))  # 일관된 방식으로 변환
                        if box_class != class_idx:
                            continue
                            
                        # Extract box coordinates
                        x, y, w, h = map(float, box[1:])
                        left = int((x - w/2) * image.width)
                        top = int((y - h/2) * image.height)
                        right = int((x + w/2) * image.width)
                        bottom = int((y + h/2) * image.height)
                        
                        # Crop and resize
                        cropped = image.crop((left, top, right, bottom)).resize((100, 100))
                        self.draw_boxes_on_image_corp(cropped, label_path, row, current_col, class_idx, idx, line_idx)
                        
                        boxes_processed = True
                        current_col += 1
                        if current_col >= 12:  # 한 행에 최대 12개 이미지
                            current_col = 0
                            row += 2  # 다음 행으로 이동
                    except (ValueError, IndexError) as e:
                        print(f"박스 데이터 처리 오류 (라인 {line_idx}): {e}")
                        continue
                        
                # 처리된 박스가 있으면 업데이트된 열 위치 반환, 없으면 원래 위치 반환
                return current_col if boxes_processed else col
                    
            except Exception as e:
                print(f"Error processing boxes in {label_path}: {e}")
                self.show_status_message(f"박스 처리 오류: {os.path.basename(label_path)}")
                return col  # 오류 발생 시 원래 열 위치 반환
        
        return col + 1  # 다음 열 위치 반환
    def _get_label_data(self, label_path):
        """
        라벨 파일 데이터를 가져오고, 가능하면 캐시에서 읽습니다.
        
        Parameters:
            label_path (str): 라벨 파일 경로
            
        Returns:
            list: 라벨 파일의 라인 목록 (빈 리스트: 오류 발생 또는 파일 없음)
        """
        if not os.path.isfile(label_path):
            return []
            
        # 캐시 사용 (캐시 시스템이 있는 경우)
        if hasattr(self, 'label_cache') and label_path in self.label_cache:
            # 파일 수정 시간 확인
            mod_time = os.path.getmtime(label_path)
            cached_time = self.label_cache[label_path]['timestamp']
            
            # 캐시가 최신이면 캐시된 데이터 반환
            if mod_time <= cached_time:
                self.update_cache_access('label', label_path)  # 캐시 접근 시간 업데이트 (필요시)
                return self.label_cache[label_path]['data']
        
        # 파일에서 읽기
        lines = []  # 기본값 초기화
        try:
            # 다양한 인코딩 시도
            encodings_to_try = ['utf-8', 'cp949', 'euc-kr', 'latin-1']
            for encoding in encodings_to_try:
                try:
                    with open(label_path, 'r', encoding=encoding) as f:
                        lines = [line.strip() for line in f.readlines()]
                    break  # 성공하면 반복 중단
                except UnicodeDecodeError:
                    continue
            
            # 캐시 시스템이 있는 경우, 캐시에 저장
            if hasattr(self, 'label_cache'):
                # 캐시 크기 제한 확인
                if hasattr(self, 'cache_limit') and len(self.label_cache) >= self.cache_limit:
                    self.manage_cache_size('label')  # 캐시 관리 함수가 있는 경우 호출
                    
                # 캐시에 저장
                self.label_cache[label_path] = {
                    'data': lines,
                    'timestamp': os.path.getmtime(label_path),
                    'last_access': time.time()
                }
                
                # 캐시 접근 순서 업데이트
                if hasattr(self, 'update_cache_access'):
                    self.update_cache_access('label', label_path)
            
            return lines
        except Exception as e:
            print(f"라벨 파일 읽기 오류 ({label_path}): {e}")
            return []        
    def draw_boxes_on_image(self, image, label_path, row, col, image_index):
        """
        Draw bounding boxes on full image with improved visualization for overlapping boxes.
        겹치는 박스 간의 관계를 더 명확하게 시각화합니다.
        """
        draw = ImageDraw.Draw(image)
        img_path = self.get_image_path_from_label(label_path)
        
        # 선택된 클래스와 겹침 클래스 정보 가져오기
        selected_class = int(self.class_selector.get())
        overlap_class = self.overlap_class_selector.get()
        
        # 박스별 겹침 정보 저장 변수
        box_overlap_data = {}
        overlapping_pairs = []  # 겹치는 박스 쌍 저장
        
        # 겹침 정보 가져오기 (박스별 분석)
        if overlap_class != "선택 안함":
            overlap_class_idx = int(overlap_class)
            has_overlap, max_iou, detailed_info, all_boxes_info = self.check_box_overlap(
                label_path, selected_class, overlap_class_idx)
            
            # 박스별 겹침 정보를 인덱스로 접근할 수 있도록 변환
            for box_info in all_boxes_info:
                box_overlap_data[box_info['box_index']] = box_info
                
                # 겹치는 박스 쌍 정보 수집
                if box_info['has_overlap']:
                    for overlap_box in box_info['overlapping_boxes']:
                        overlapping_pairs.append({
                            'main_box': (selected_class, box_info['box_index']),
                            'target_box': (overlap_class_idx, overlap_box['target_box_index']),
                            'iou': overlap_box['iou']
                        })
        
        # Draw class information and boxes
        try:
            # 라벨 파일에서 모든 박스 정보 읽기
            boxes_by_class = defaultdict(list)
            
            with open(label_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                for i, line in enumerate(lines):
                    parts = line.split()
                    if not parts:
                        continue
                        
                    class_index, x_center, y_center, width, height = map(float, parts)
                    
                    # Convert normalized coordinates to pixel coordinates
                    width_px = width * image.width
                    height_px = height * image.height
                    x_center_px = x_center * image.width
                    y_center_px = y_center * image.height
                    
                    # Calculate box coordinates
                    x0 = x_center_px - (width_px / 2)
                    y0 = y_center_px - (height_px / 2)
                    x1 = x_center_px + (width_px / 2)
                    y1 = y_center_px + (height_px / 2)
                    
                    # 박스 정보 저장
                    box_info = {
                        "coords": [x0, y0, x1, y1],
                        "class": int(class_index),
                        "index": i,
                        "center": (x_center_px, y_center_px)
                    }
                    boxes_by_class[int(class_index)].append(box_info)
            
            # 모든 박스 그리기 - 박스별로 겹침 정보 시각화
            for class_id, boxes in boxes_by_class.items():
                for box_idx, box in enumerate(boxes):
                    # 기본 색상 및 두께 설정
                    color = "green"  # 기본 색상
                    width = 2        # 기본 두께
                    show_iou = False # IoU 표시 여부
                    iou_value = 0.0  # IoU 값
                    overlap_id = None # 겹침 관계 ID
                    
                    # 선택된 클래스의 박스인 경우 겹침 정보 확인 
                    if class_id == selected_class:
                        if overlap_class != "선택 안함" and box_idx in box_overlap_data:
                            overlap_info = box_overlap_data[box_idx]
                            
                            # 이 박스가 겹치는 경우
                            if overlap_info['has_overlap']:
                                # IoU 값에 따라 색상 결정
                                iou_value = overlap_info['max_iou']
                                color = self.get_iou_color(iou_value)
                                width = 4  # 두꺼운 테두리로 강조
                                show_iou = True
                                
                                # 겹침 ID 설정 (박스 쌍 식별용)
                                for i, pair in enumerate(overlapping_pairs):
                                    if pair['main_box'][1] == box_idx:
                                        overlap_id = i + 1  # 1부터 시작하는 ID
                            else:
                                # 겹치지 않는 선택 클래스 박스
                                color = "red"
                                width = 3
                        else:
                            # 겹침 정보가 없는 경우
                            color = "red"
                            width = 3
                    
                    # 대상 클래스의 박스인 경우
                    elif overlap_class != "선택 안함" and class_id == int(overlap_class):
                        # 기본 대상 클래스 색상
                        color = "blue"
                        width = 3
                        
                        # 이 대상 박스가 선택 클래스와 겹치는지 확인
                        for i, pair in enumerate(overlapping_pairs):
                            if pair['target_box'][1] == box_idx:
                                # 겹치는 대상 박스는 특별한 색상으로 표시
                                iou_value = pair['iou']
                                color = "purple"  # 특별한 색상으로 구분
                                width = 4
                                show_iou = True
                                overlap_id = i + 1  # 선택 클래스의 박스와 동일한 ID
                                break
                            
                    # 박스 그리기
                    draw.rectangle(box["coords"], outline=color, width=width)
                    
                    # 텍스트 정보 표시
                    text_y_offset = box["coords"][1]
                    
                    # 클래스 정보 표시
                    draw.text((box["coords"][0], text_y_offset), 
                            f"Class: {class_id}", fill=color)
                    text_y_offset += 15
                    
                    # 겹침 관계 ID 표시 (겹치는 박스 쌍 식별)
                    if overlap_id is not None:
                        draw.text((box["coords"][0], text_y_offset),
                                f"Pair: #{overlap_id}", fill=color)
                        text_y_offset += 15
                    
                    # IoU 값 표시 (겹치는 경우에만)
                    if show_iou:
                        draw.text((box["coords"][0], text_y_offset),
                                f"IoU: {iou_value:.2f}", fill=color)
            
            # 겹치는 박스 간 연결선 그리기
            for i, pair in enumerate(overlapping_pairs):
                if (pair['main_box'][0] in boxes_by_class and 
                    pair['target_box'][0] in boxes_by_class and
                    len(boxes_by_class[pair['main_box'][0]]) > pair['main_box'][1] and
                    len(boxes_by_class[pair['target_box'][0]]) > pair['target_box'][1]):
                    
                    main_box = boxes_by_class[pair['main_box'][0]][pair['main_box'][1]]
                    target_box = boxes_by_class[pair['target_box'][0]][pair['target_box'][1]]
                    
                    # 박스 중심점 좌표
                    main_center = main_box["center"]
                    target_center = target_box["center"]
                    
                    # 연결선 그리기 (점선 효과)
                    color = self.get_iou_color(pair['iou'])
                    
                    # 연결선은 점선으로 표현 (5픽셀 간격)
                    x1, y1 = main_center
                    x2, y2 = target_center
                    
                    # 연결선 길이
                    line_length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
                    dx = (x2 - x1) / line_length
                    dy = (y2 - y1) / line_length
                    
                    # 점선 그리기 (5픽셀 간격)
                    for d in range(0, int(line_length), 10):
                        x = int(x1 + dx * d)
                        y = int(y1 + dy * d)
                        draw.ellipse((x-2, y-2, x+2, y+2), fill=color)
            
            # 이미지 번호 표시
            if image_index is not None:
                draw.text((10, 10), f"No: {image_index}", fill="white",
                        stroke_width=2, stroke_fill="black")
            
        except Exception as e:
            print(f"Error drawing boxes for {label_path}: {e}")
            import traceback
            traceback.print_exc()
        
        # Create photo image and label
        photo = ImageTk.PhotoImage(image)
        label = tk.Label(self.frame, image=photo, bg="white")
        label.image = photo
        label.label_path = label_path  # 라벨에 label_path 속성 추가
        label.config(relief="solid", bd=1)  # relief 타입을 명확히 지정
        label.grid(row=row, column=col, padx=10, pady=10)

        # 드래그 선택 이벤트 바인딩 (Shift + 클릭/드래그 포함)
        self.setup_drag_select_events(label, label_path)

        # 오른쪽 클릭 - 전체 이미지 보기
        label.bind("<Button-3>", lambda event,
                img_path=img_path,
                label_path=label_path: self.show_full_image(img_path, label_path, None))

        return label
    def get_image_path_from_label(self, label_path):
        """라벨 경로로부터 이미지 경로를 안전하게 생성합니다."""
        if not label_path:
            return None

        # 헬퍼 함수를 사용하여 경로 변환
        img_path = self.convert_labels_to_jpegimages(label_path)

        # 확장자 확인 및 변경
        if img_path.endswith(".txt"):
            # 먼저 jpg 확인 후 없으면 png 시도
            jpg_path = img_path.replace(".txt", ".jpg")
            if os.path.exists(jpg_path):
                return jpg_path
                
            png_path = img_path.replace(".txt", ".png")
            if os.path.exists(png_path):
                return png_path
                
            # 기본값으로 jpg 반환
            return jpg_path
        
        return img_path
    def show_full_image(self, img_path, label_path, selected_line_idx=None):
        """Show full image with bounding boxes in a new window"""
        try:
            # Create new window
            detail_window = tk.Toplevel(self.root)
            detail_window.title("Full Image View")

            # Center window on screen
            window_width = 900  # 더 넓게 조정
            window_height = 700  # 더 높게 조정
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            x = (screen_width - window_width) // 2
            y = (screen_height - window_height) // 2
            detail_window.geometry(f"{window_width}x{window_height}+{x}+{y}")

            # 상단 정보 프레임
            info_frame = tk.Frame(detail_window)
            info_frame.pack(fill="x", padx=10, pady=5)

            # 파일 경로 표시
            file_label = tk.Label(info_frame, text=f"이미지: {os.path.basename(img_path)}", anchor="w")
            file_label.pack(side="left", padx=5)

            # 선택된 클래스 정보
            selected_class = self.class_selector.get()
            class_label = tk.Label(info_frame, text=f"선택 클래스: {selected_class}", anchor="w")
            class_label.pack(side="left", padx=20)

            # 라벨 표시 토글 변수
            show_labels_var = tk.BooleanVar(value=True)

            # 토글 버튼 추가
            toggle_button = tk.Button(info_frame, text="라벨 숨기기",
                                     command=lambda: None, width=10)  # command는 나중에 설정
            toggle_button.pack(side="right", padx=10)

            # Create canvas for scrollable image
            canvas_frame = tk.Frame(detail_window)
            canvas_frame.pack(fill="both", expand=True, padx=5, pady=5)

            canvas = tk.Canvas(canvas_frame)
            scrollbar_y = tk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
            scrollbar_x = tk.Scrollbar(detail_window, orient="horizontal", command=canvas.xview)

            # Configure canvas
            canvas.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)

            # Layout
            canvas.pack(side="left", fill="both", expand=True)
            scrollbar_y.pack(side="right", fill="y")
            scrollbar_x.pack(fill="x")

            # Create frame inside canvas
            frame = tk.Frame(canvas, bg="white")
            canvas_window = canvas.create_window((0, 0), window=frame, anchor="nw")

            # 원본 이미지 로드 및 정보 저장
            with Image.open(img_path) as img:
                # 이미지 크기 정보 표시
                size_label = tk.Label(info_frame, text=f"크기: {img.width}x{img.height}px", anchor="w")
                size_label.pack(side="left", padx=20)

                # 이미지 표시 크기 계산 (화면에 맞게 조정)
                display_width = min(img.width, window_width - 100)
                ratio = display_width / img.width
                display_height = int(img.height * ratio)

                # 원본 이미지 복사 및 리사이즈 (토글용)
                original_img = img.copy()
                resized_original = original_img.resize((display_width, display_height), Image.LANCZOS)

            # 이미지 레이블 위젯 저장용
            img_label_widget = [None]  # 리스트로 감싸서 내부 함수에서 참조 가능하게

            def redraw_image():
                """이미지를 라벨 표시 여부에 따라 다시 그리기"""
                try:
                    # 선택된 클래스와 겹침 클래스 정보 가져오기
                    class_idx = int(float(selected_class))
                    overlap_class = self.overlap_class_selector.get()

                    # 기존 이미지 위젯 제거
                    if img_label_widget[0]:
                        img_label_widget[0].destroy()

                    # 이미지 복사본 생성
                    display_img = resized_original.copy()

                    # 라벨 표시가 켜져있으면 박스 그리기
                    if show_labels_var.get():
                        img_label_widget[0] = self.draw_boxes_on_full_image(
                            display_img, label_path, frame, class_idx,
                            overlap_class, selected_line_idx)
                    else:
                        # 라벨 없이 이미지만 표시
                        photo = ImageTk.PhotoImage(display_img)
                        img_label_widget[0] = tk.Label(frame, image=photo)
                        img_label_widget[0].image = photo  # 참조 유지
                        img_label_widget[0].pack()

                    # 캔버스 스크롤 영역 업데이트
                    frame.update_idletasks()
                    canvas.configure(scrollregion=canvas.bbox("all"))

                except Exception as e:
                    print(f"Error redrawing image: {e}")
                    import traceback
                    traceback.print_exc()

            def toggle_labels():
                """라벨 표시 토글"""
                show_labels_var.set(not show_labels_var.get())
                toggle_button.config(text="라벨 보기" if not show_labels_var.get() else "라벨 숨기기")
                redraw_image()

            # 토글 버튼 command 설정
            toggle_button.config(command=toggle_labels)

            # 초기 이미지 그리기
            try:
                redraw_image()
            except Exception as e:
                print(f"Error drawing boxes: {e}")
                import traceback
                traceback.print_exc()
            
            # 하단 버튼 프레임
            button_frame = tk.Frame(detail_window)
            button_frame.pack(fill="x", padx=10, pady=10)
            
            # 닫기 버튼
            close_button = tk.Button(button_frame, text="닫기", command=detail_window.destroy, 
                                width=10, height=2)
            close_button.pack(side="right", padx=10)
            
            # Update canvas scroll region
            frame.update_idletasks()
            canvas.configure(scrollregion=canvas.bbox("all"))

            detail_window.mousewheel_bound = True

            # Add mousewheel scrolling
            def on_mousewheel(event):
                if not detail_window.winfo_exists():
                    return
                if canvas.winfo_exists():
                    canvas.yview_scroll(-1 * (event.delta // 120), "units")
            
            # 현재 캔버스에만 바인딩하고 전역 바인딩 사용 안 함
            canvas.bind("<MouseWheel>", on_mousewheel)
            
            # Clean up on window close
            def on_closing():
                # 바인딩 모두 해제
                try:
                    canvas.unbind("<MouseWheel>")
                    # 전역 바인딩 제거 (bind_all 사용 시)
                    detail_window.unbind_all("<MouseWheel>")
                except:
                    pass
                
                # 메인 윈도우 포커스 복원
                self.root.focus_set()

                self.canvas.bind_all("<MouseWheel>", self.on_mousewheel)
                self.root.update()
                # 창 닫기
                detail_window.destroy()

                self.root.after(100, self.refresh_bindings)
            
            # 창 닫기 이벤트 핸들러 설정
            detail_window.protocol("WM_DELETE_WINDOW", on_closing)
            # ESC 키로도 창 닫기
            detail_window.bind("<Escape>", lambda e: on_closing())
            
        except Exception as e:
            print(f"Error showing full image: {e}")
            import traceback
            traceback.print_exc()
            if 'detail_window' in locals():
                detail_window.destroy()
    def refresh_bindings(self):
        """이벤트 바인딩 새로 고침"""
        self._last_click_time = 0

        # 기존 바인딩 해제
        try:
            self.canvas.unbind_all("<MouseWheel>")
            self.root.unbind_all("<MouseWheel>")
            self.root.unbind_all("<KeyPress>")
            self.root.unbind_all("<KeyRelease>")
            self.root.unbind_all("<KeyPress-Shift_L>")
            self.root.unbind_all("<KeyRelease-Shift_L>")
            self.root.unbind_all("<KeyPress-Shift_R>")
            self.root.unbind_all("<KeyRelease-Shift_R>")
            self.root.unbind_all("<KeyPress-Caps_Lock>")
            self.root.unbind_all("<KeyRelease-Caps_Lock>")
            self.root.unbind_all("<Button-1>")
        except:
            pass
        
        # 기본 이벤트 바인딩 다시 설정
        self.canvas.bind_all("<MouseWheel>", self.on_mousewheel)
        self.canvas.bind("<Configure>", self.on_canvas_configure)
        self.root.bind("<Button-1>", self.handle_left_click)
        
        # 키보드 이벤트 재설정
        self.root.bind('<KeyPress>', self.on_key_press)
        self.root.bind('<KeyRelease>', self.on_key_release)
        self.root.bind("<KeyPress-Shift_L>", self.on_shift_press)
        self.root.bind("<KeyRelease-Shift_L>", self.on_shift_release)
        self.root.bind("<KeyPress-Shift_R>", self.on_shift_press)
        self.root.bind("<KeyRelease-Shift_R>", self.on_shift_release)
        self.root.bind("<KeyPress-Caps_Lock>", self.on_caps_lock_press)
        self.root.bind("<KeyRelease-Caps_Lock>", self.on_caps_lock_release)
        
        # 프레임의 모든 라벨 위젯에 대해 클릭 이벤트 다시 바인딩
        for widget in self.frame.winfo_children():
            if isinstance(widget, tk.Label) and hasattr(widget, 'label_path'):
                img_path = self.convert_labels_to_jpegimages(widget.label_path)

                # 드래그 선택 이벤트 바인딩 (Shift + 클릭/드래그 포함)
                self.setup_drag_select_events(widget, widget.label_path)

                # 오른쪽 클릭 - 전체 이미지 보기
                widget.bind("<Button-3>", lambda event,
                        img_path=img_path,
                        label_path=widget.label_path,
                        ln_idx=getattr(widget, 'line_idx', None):
                        self.show_full_image(img_path, label_path, ln_idx))
            
    def draw_boxes_on_full_image(self, image, label_path, parent_frame, class_idx, overlap_class=None, selected_line_idx=None):
        """원본 크기 이미지에 모든 바운딩 박스 표시

        Args:
            image: PIL 이미지 객체
            label_path: 라벨 파일 경로
            parent_frame: 부모 프레임
            class_idx: 선택된 클래스 인덱스
            overlap_class: 겹침 클래스
            selected_line_idx: 선택된 라벨의 라인 인덱스 (강조 표시용)
        """
        from PIL import ImageDraw, ImageFont

        # 원본 이미지 복사본에 그리기
        draw = ImageDraw.Draw(image)
        
        # 이미지 경로 생성
        img_path = self.get_image_path_from_label(label_path)
        
        # 겹침 정보 가져오기
        has_overlap = False
        max_iou = 0.0
        overlap_info = []
        all_boxes_info = []
        
        if overlap_class != "선택 안함":
            try:
                overlap_class_idx = int(float(overlap_class))
                has_overlap, max_iou, overlap_info, all_boxes_info = self.check_box_overlap(
                    label_path, class_idx, overlap_class_idx)
            except:
                pass
        
        # 텍스트 폰트 설정 시도 (폰트가 없을 경우 기본 폰트 사용)
        try:
            font = ImageFont.truetype("arial.ttf", 14)
        except:
            font = ImageFont.load_default()
        
        # 바운딩 박스 정보 읽기
        try:
            # 라벨 파일에서 모든 박스 정보 읽기
            boxes_by_class = {}
            
            if os.path.isfile(label_path):
                with open(label_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    for i, line in enumerate(lines):
                        parts = line.split()
                        if not parts:
                            continue
                        
                        try:
                            class_index = int(float(parts[0]))
                            x_center, y_center, width, height = map(float, parts[1:5])
                            
                            # 이미지 기준 픽셀 좌표로 변환
                            x1 = int((x_center - width/2) * image.width)
                            y1 = int((y_center - height/2) * image.height)
                            x2 = int((x_center + width/2) * image.width)
                            y2 = int((y_center + height/2) * image.height)
                            
                            # 클래스별 박스 정보 저장
                            if class_index not in boxes_by_class:
                                boxes_by_class[class_index] = []
                                
                            boxes_by_class[class_index].append({
                                "coords": [x1, y1, x2, y2],
                                "class": class_index,
                                "center": (x_center, y_center),
                                "size": (width, height),
                                "index": i
                            })
                        except:
                            continue
            
            # 박스 그리기
            for class_id, boxes in boxes_by_class.items():
                # 해당 클래스의 모든 박스 그리기
                for box in boxes:
                    # 기본 색상 및 두께 설정
                    color = "green"
                    thickness = 1

                    # 선택된 특정 라벨인 경우 (가장 우선순위 높음)
                    if selected_line_idx is not None and box['index'] == selected_line_idx:
                        color = "yellow"  # 선택된 라벨은 노란색으로 강조
                        thickness = 3
                    # 선택된 클래스인 경우
                    elif class_id == class_idx:
                        color = "red"
                        thickness = 2
                    # 겹침 대상 클래스인 경우
                    elif overlap_class != "선택 안함" and class_id == int(float(overlap_class)):
                        color = "blue"
                        thickness = 2

                    # 박스 좌표
                    x1, y1, x2, y2 = box["coords"]

                    # 박스 그리기
                    draw.rectangle([x1, y1, x2, y2], outline=color, width=thickness)

                    # 클래스 텍스트 표시
                    label_text = f"Class: {class_id}"
                    if class_id == class_idx:
                        # 선택된 클래스의 박스에 인덱스 정보 추가
                        label_text += f" #{box['index']}"

                    # 선택된 라벨은 "SELECTED" 표시
                    if selected_line_idx is not None and box['index'] == selected_line_idx:
                        label_text += " [SELECTED]"

                    # 텍스트 배경 그리기
                    text_bbox = draw.textbbox((x1, y1-20), label_text, font=font)
                    draw.rectangle(text_bbox, fill="white")

                    # 텍스트 그리기
                    draw.text((x1, y1-20), label_text, fill=color, font=font)
                    
            # 겹치는 박스들 사이에 연결선 표시
            if has_overlap and overlap_info:
                for item in overlap_info:
                    # 겹치는 박스 정보 추출
                    main_box_idx = item['main_box_index']
                    
                    for overlap_item in item['overlapping_boxes']:
                        target_box_idx = overlap_item['target_box_index']
                        iou_value = overlap_item['iou']
                        
                        # 관련 박스 찾기
                        main_box = None
                        target_box = None
                        
                        # 메인 박스 찾기
                        if class_idx in boxes_by_class:
                            for box in boxes_by_class[class_idx]:
                                if box['index'] == main_box_idx:
                                    main_box = box
                                    break
                                    
                        # 대상 박스 찾기
                        overlap_class_idx = int(float(overlap_class))
                        if overlap_class_idx in boxes_by_class:
                            for box in boxes_by_class[overlap_class_idx]:
                                if box['index'] == target_box_idx:
                                    target_box = box
                                    break
                                    
                        # 두 박스 사이 연결선 그리기
                        if main_box and target_box:
                            # 중심점 계산
                            main_center = (
                                (main_box['coords'][0] + main_box['coords'][2]) // 2,
                                (main_box['coords'][1] + main_box['coords'][3]) // 2
                            )
                            target_center = (
                                (target_box['coords'][0] + target_box['coords'][2]) // 2,
                                (target_box['coords'][1] + target_box['coords'][3]) // 2
                            )
                            
                            # IoU 값에 따른 색상
                            line_color = self.get_iou_color(iou_value)
                            
                            # 점선 효과 (5픽셀 간격의 작은 원들)
                            line_length = ((target_center[0] - main_center[0]) ** 2 + 
                                        (target_center[1] - main_center[1]) ** 2) ** 0.5
                            dx = (target_center[0] - main_center[0]) / line_length
                            dy = (target_center[1] - main_center[1]) / line_length
                            
                            for d in range(0, int(line_length), 10):
                                x = int(main_center[0] + dx * d)
                                y = int(main_center[1] + dy * d)
                                draw.ellipse((x-2, y-2, x+2, y+2), fill=line_color)
                            
                            # IoU 값 표시 (선의 중앙)
                            text_x = int(main_center[0] + dx * line_length / 2) - 20
                            text_y = int(main_center[1] + dy * line_length / 2) - 10
                            iou_text = f"IoU: {iou_value:.2f}"
                            
                            # 텍스트 배경
                            text_bbox = draw.textbbox((text_x, text_y), iou_text, font=font)
                            draw.rectangle(text_bbox, fill="white")
                            
                            # IoU 값 텍스트
                            draw.text((text_x, text_y), iou_text, fill=line_color, font=font)
            
            # 이미지를 PhotoImage로 변환
            photo = ImageTk.PhotoImage(image)
            
            # 이미지 표시
            img_label = tk.Label(parent_frame, image=photo)
            img_label.image = photo  # 참조 유지
            img_label.pack(padx=10, pady=10)
            
            return img_label
            
        except Exception as e:
            print(f"Error drawing boxes on full image: {e}")
            import traceback
            traceback.print_exc()
            
            # 오류 시 원본 이미지만 표시
            photo = ImageTk.PhotoImage(image)
            img_label = tk.Label(parent_frame, image=photo)
            img_label.image = photo
            img_label.pack(padx=10, pady=10)
            
            # 오류 메시지 표시
            error_label = tk.Label(parent_frame, text=f"바운딩 박스 그리기 오류: {e}", 
                                fg="red", bg="white")
            error_label.pack(pady=5)
            
            return img_label
    def on_image_click(self, label, label_path, event=None, img_path=None, line_idx=None):
        """
        이미지 또는 바운딩 박스 클릭 처리
        
        Parameters:
            label (tk.Label): 클릭된 라벨 위젯
            label_path (str): 라벨 파일 경로
            event (Event): 클릭 이벤트 객체
            img_path (str, optional): 이미지 파일 경로
            line_idx (int, optional): 바운딩 박스 인덱스 (박스 뷰에서 클릭한 경우)
        """
        current_time = time.time()
        is_duplicate_click = False

        if hasattr(self, '_last_clicked_label') and self._last_clicked_label == label:
            if hasattr(self, '_last_click_time') and (current_time - self._last_click_time < 0.3):
                # 같은 라벨에 대한 중복 클릭 감지
                is_duplicate_click = True

        # 현재 클릭 정보 저장
        self._last_clicked_label = label
        self._last_click_time = current_time

        # 중복 클릭이거나 이미 처리 중이면 무시
        if is_duplicate_click:
            return

        if hasattr(self, '_processing_click') and self._processing_click:
            # 처리 중인 상태를 스스로 해제하는 타이머 추가 (데드락 방지)
            if hasattr(self, '_processing_timer') and self._processing_timer:
                self.root.after_cancel(self._processing_timer)
            self._processing_timer = self.root.after(1000, self._reset_click_processing)
            return

        # 클릭 처리 상태 설정
        self._processing_click = True

        # 클릭 처리를 1초 후 자동으로 해제하는 타이머 설정 (안전 장치)
        if hasattr(self, '_processing_timer') and self._processing_timer:
            self.root.after_cancel(self._processing_timer)
        self._processing_timer = self.root.after(1000, self._reset_click_processing)
        try:
            print(f"이미지 클릭: {label_path}, 라인 인덱스: {line_idx}")
            
            # 위젯에서 line_idx 속성이 있는지 확인하고 있으면 사용
            if line_idx is None and hasattr(label, 'line_idx'):
                line_idx = label.line_idx
            print(f"이미지 클릭: {label_path}, 라인 인덱스: {line_idx}")

            # 이미지 뷰어 열기
            if self.shift_pressed:
                # 드래그 선택은 on_drag_start, on_drag_motion, on_drag_end에서 처리됨
                # 여기서는 단일 클릭 처리만 수행
                self._toggle_image_selection(label, label_path, line_idx)
                
            # Caps Lock 키가 눌려진 경우 - 범위 선택 모드
            elif self.caps_locked:
                # 현재 페이지의 모든 라벨 찾기
                page_labels = [widget for widget in self.frame.winfo_children() 
                            if isinstance(widget, tk.Label) and hasattr(widget, 'label_path')]
                
                # 현재 이미지의 인덱스 찾기
                if label in page_labels:
                    current_index = page_labels.index(label)
                else:
                    # 라벨이 리스트에 없는 경우 일반 클릭으로 처리
                    self._toggle_image_selection(label, label_path, line_idx)
                    return
                
                # 첫 선택 시 현재 라벨을 시작점으로 설정
                if not hasattr(self, 'multi_select_start') or self.multi_select_start is None:
                    self.multi_select_start = current_index
                    print(f"Multi-select start set to index {current_index}")
                
                # 시작점과 현재 클릭한 지점 사이의 범위 선택
                start, end = sorted([self.multi_select_start, current_index])
                
                # 이전 선택 해제
                for l in page_labels:
                    if l in self.checklist:
                        l.config(highlightbackground="white", highlightthickness=2)
                        l.config(bg="white")
                        if hasattr(l, 'label_path') and l.label_path in self.selected_image_labels:
                            self.selected_image_labels.remove(l.label_path)
                        if l in self.checklist:
                            self.checklist.remove(l)
                
                # 범위 내 모든 이미지/박스의 선택 정보 초기화
                self.selected_label_info = []
                
                # 새 범위 선택
                for i in range(start, end + 1):
                    if i < len(page_labels):
                        l = page_labels[i]
                        if hasattr(l, 'label_path'):
                            # 선택 로직
                            l.config(highlightbackground="red", highlightthickness=4)
                            l.config(bg="#ffdddd")
                            
                            # 라인 인덱스가 있는 경우 (박스 뷰)
                            if hasattr(l, 'line_idx'):
                                self.save_selected_label_info(l.label_path, l.line_idx)
                            else:
                                # 전체 이미지인 경우
                                self.save_selected_label_info(l.label_path)
                            
                            if l.label_path not in self.selected_image_labels:
                                self.selected_image_labels.append(l.label_path)
                            if l not in self.checklist:
                                self.checklist.append(l)
                
                # 선택 정보 업데이트
                self.update_selection_info()
            
            # Ctrl 키가 눌려진 경우 - 기준 라벨 선택
            elif hasattr(self, 'ctrl_pressed') and self.ctrl_pressed:
                self.select_reference_label(label, label_path)
            
            # 일반 클릭 - 선택/해제 토글
            else:
                is_selected = label in self.checklist
                        
                if is_selected:
                    # 선택 해제
                    label.config(bd=2, highlightbackground="white", highlightthickness=2)
                    label.config(bg="white")
                    
                    # 이미지 선택 목록에서 제거
                    if label_path in self.selected_image_labels:
                        self.selected_image_labels.remove(label_path)
                    
                    # 선택 정보에서 제거
                    if line_idx is not None:
                        # 특정 박스만 제거
                        for info in self.selected_label_info[:]:
                            if info['path'] == label_path:
                                # 해당 박스만 제거하고 다른 박스는 유지
                                info['boxes'] = [box for box in info['boxes'] 
                                                if box.get('line_idx') != line_idx]
                                
                                # 박스가 모두 제거되면 항목 자체를 제거
                                if not info['boxes']:
                                    self.selected_label_info.remove(info)
                    else:
                        # 해당 이미지 관련 모든 정보 제거
                        self.selected_label_info = [info for info in self.selected_label_info 
                                                if info['path'] != label_path]
                    
                    # 체크리스트에서 제거
                    if label in self.checklist:
                        self.checklist.remove(label)
                if not is_selected:
                    # 선택
                    label.config(bd=2, highlightbackground="red", highlightthickness=4)
                    label.config(bg="#ffdddd")  # 연한 빨간색 배경
                    
                    # 박스 인덱스가 있으면 특정 박스만, 아니면 전체 이미지 선택
                    self.save_selected_label_info(label_path, line_idx)
                    
                    # 이미지 선택 목록에 추가
                    if label_path not in self.selected_image_labels:
                        self.selected_image_labels.append(label_path)
                    
                    # 체크리스트에 추가
                    if label not in self.checklist:
                        self.checklist.append(label)
                
                # 선택 정보 업데이트
                self.update_selection_info()
                
                # UI 피드백 추가 (깜빡임 효과와 상태 메시지)
                if hasattr(self, 'flash_widget'):
                    self.flash_widget(label, "lightblue" if not is_selected else "lightyellow")
                
                if hasattr(self, 'show_status_message'):
                    action = "선택 해제" if is_selected else "선택"
                    file_name = os.path.basename(label_path)
                    box_info = f" (박스 {line_idx})" if line_idx is not None else ""
                    self.show_status_message(f"{action}: {file_name}{box_info}")
        except TclError as e:
            print(f"Error handling image click: {e}")
            if hasattr(self, 'show_status_message'):
                self.show_status_message(f"오류 발생: {e}", duration=5000)
        finally:
        # 처리 완료 표시
            self._processing_click = False    
    def _reset_click_processing(self):
        """클릭 처리 상태를 초기화하는 안전 장치"""
        if hasattr(self, '_processing_click'):
            self._processing_click = False
        if hasattr(self, '_processing_timer'):
            self._processing_timer = None
    def _toggle_image_selection(self, label, label_path, line_idx=None):
        """
        이미지 또는 바운딩 박스 선택/해제 토글 기능을 수행하는 상세 구현 메서드
        
        Parameters:
            label (tk.Label): 토글할 이미지 라벨 위젯
            label_path (str): 이미지 라벨에 연결된 라벨 파일 경로
            line_idx (int, optional): 바운딩 박스 인덱스 (특정 박스만 토글할 경우)
        """
        try:
            # 디버깅 정보 출력
            print(f"Toggling selection for: {os.path.basename(label_path)}" + 
                (f", line {line_idx}" if line_idx is not None else ""))
            
            # 이미 선택된 이미지인지 확인
            is_selected = label in self.checklist
            
            if is_selected:
                # 선택 해제 프로세스
                print(f"  - Deselecting {('box ' + str(line_idx)) if line_idx is not None else 'image'}")
                
                # 시각적 스타일 리셋
                label.config(highlightbackground="white", highlightthickness=2)
                label.config(bg="white")
                
                # 모든 자식 위젯 제거 (체크마크 표시 등)
                for child in label.winfo_children():
                    if hasattr(child, 'selection_indicator'):
                        child.destroy()
                
                # 선택 리스트에서 제거
                if label_path in self.selected_image_labels:
                    # 특정 박스만 선택 해제하는 경우, 다른 박스가 선택되어 있는지 확인
                    if line_idx is not None:
                        # 해당 라벨의 정보 찾기
                        label_info = next((info for info in self.selected_label_info 
                                        if info['path'] == label_path), None)
                        
                        if label_info:
                            # 선택된 박스만 제거
                            label_info['boxes'] = [box for box in label_info['boxes'] 
                                                if box.get('line_idx') != line_idx]
                            
                            # 박스가 모두 제거되면 이미지도 선택 목록에서 제거
                            if not label_info['boxes']:
                                self.selected_image_labels.remove(label_path)
                                # 라벨 정보 목록에서도 제거
                                self.selected_label_info.remove(label_info)
                                print(f"  - Removed from selected_image_labels, new count: {len(self.selected_image_labels)}")
                    else:
                        # 이미지 전체 선택 해제
                        self.selected_image_labels.remove(label_path)
                        # 라벨 정보 목록에서도 제거
                        self.selected_label_info = [info for info in self.selected_label_info 
                                                if info['path'] != label_path]
                        print(f"  - Removed from selected_image_labels, new count: {len(self.selected_image_labels)}")
                
                if label in self.checklist:
                    self.checklist.remove(label)
                    print(f"  - Removed from checklist, new count: {len(self.checklist)}")
            else:
                # 선택 프로세스
                print(f"  - Selecting {('box ' + str(line_idx)) if line_idx is not None else 'image'}")
                
                # 시각적 스타일 적용
                label.config(highlightbackground="red", highlightthickness=4)
                label.config(bg="#ffdddd")  # 연한 빨간색 배경
                
                # 기존 체크마크 제거 (중복 방지)
                for child in label.winfo_children():
                    if hasattr(child, 'selection_indicator'):
                        child.destroy()
                
                # 체크마크 추가
                check_mark = tk.Label(
                    label, 
                    text="✓", 
                    font=("Arial", 12, "bold"), 
                    fg="red", 
                    bg="#ffdddd"
                )
                check_mark.selection_indicator = True  # 커스텀 속성으로 체크마크 표시자 식별
                check_mark.place(x=5, y=5)  # 좌측 상단에 배치
                
                # 바운딩 박스 정보 저장
                self.save_selected_label_info(label_path, line_idx)
                
                # 선택 리스트에 추가
                if label_path not in self.selected_image_labels:
                    self.selected_image_labels.append(label_path)
                    print(f"  - Added to selected_image_labels, new count: {len(self.selected_image_labels)}")
                
                if label not in self.checklist:
                    self.checklist.append(label)
                    print(f"  - Added to checklist, new count: {len(self.checklist)}")
            
            # UI 피드백 - 깜빡임 효과
            if hasattr(self, 'flash_widget'):
                self.flash_widget(label, "lightblue" if not is_selected else "lightyellow")
        
            # 상태 표시줄에 메시지 표시
            if hasattr(self, 'show_status_message'):
                action = "선택 해제" if is_selected else "선택"
                file_name = os.path.basename(label_path)
                box_info = f" (박스 {line_idx})" if line_idx is not None else ""
                self.show_status_message(f"{action}: {file_name}{box_info}")

            # Caps Lock 다중 선택 모드 관련 처리
            # 단일 선택 모드에서만 다중 선택 시작점 초기화
            if not self.caps_locked and hasattr(self, 'multi_select_start'):
                print(f"  - Resetting multi-select start point")
                self.multi_select_start = None
            
            # 선택 상태가 변경되었음을 알림
            self.selection_modified = True
            
            # 선택 정보 업데이트
            self.update_selection_info()
            
            # 후속 작업 - 자동 스크롤 등이 필요한 경우
            if hasattr(self, 'auto_scroll_on_select') and self.auto_scroll_on_select:
                # 현재 선택된 항목의 위치로 자동 스크롤
                self.scroll_to_widget(label)
        
        except Exception as e:
            print(f"Error in _toggle_image_selection: {e}")
            # 오류 발생 시 상태 표시줄에 메시지 표시
            if hasattr(self, 'show_status_message'):
                self.show_status_message(f"선택 토글 오류: {e}", duration=5000)
            import traceback
            traceback.print_exc()
    def scroll_to_widget(self, widget):
        """
        캔버스 내에서 특정 위젯이 보이도록 스크롤 조정
        
        Parameters:
            widget (tk.Widget): 스크롤할 대상 위젯
        """
        try:
            # 위젯의 캔버스 상 좌표 계산
            x = widget.winfo_x()
            y = widget.winfo_y()
            width = widget.winfo_width()
            height = widget.winfo_height()
            
            # 캔버스의 현재 스크롤 영역
            canvas_height = self.canvas.winfo_height()
            scroll_top = self.canvas.canvasy(0)  # 현재 스크롤 위치
            scroll_bottom = scroll_top + canvas_height
            
            # 위젯이 현재 보이는 영역을 벗어났는지 확인
            if y < scroll_top or y + height > scroll_bottom:
                # 스크롤 위치 계산 - 위젯이 중앙에 오도록
                target_y = y - (canvas_height - height) / 2
                
                # 스크롤 이동 (부드러운 이동을 위해 점진적으로)
                current_top = self.canvas.canvasy(0)
                distance = target_y - current_top
                steps = 10  # 이동 단계 수
                
                def animate_scroll(step=0):
                    if step < steps:
                        move_amount = distance * (step + 1) / steps
                        self.canvas.yview_moveto((current_top + move_amount) / self.canvas.winfo_height())
                        self.root.after(10, lambda: animate_scroll(step + 1))
                
                animate_scroll()
            
            print(f"Scrolled to widget at y={y}")
        
        except Exception as e:
            print(f"Error in scroll_to_widget: {e}")
    def add_keyboard_help_info(self):
        """키보드 단축키 안내 정보 추가"""
        help_frame = tk.LabelFrame(self.control_panel, text="단축키 안내")
        help_frame.pack(side=tk.LEFT, padx=5, fill="y")
        
        # 간단한 도움말 텍스트
        help_text = (
            "Ctrl+클릭: 기준 라벨 선택\n"
            "Shift+드래그: 영역 선택\n"
            "Caps Lock+클릭: 범위 선택"
        )
        
        help_label = tk.Label(help_frame, text=help_text, justify=tk.LEFT,
                        font=("Arial", 8))
        help_label.pack(padx=5, pady=5)
    def delete_selected_labels(self):
        """선택한 이미지의 특정 바운딩 박스만 삭제 - 인덱스 일관성 개선 버전"""
        if not self.selected_image_labels:
            print("삭제할 이미지가 선택되지 않았습니다.")
            tk.messagebox.showwarning("선택 오류", "삭제할 이미지를 먼저 선택하세요.")
            return
        if not self.selected_label_info:
            print("삭제할 라벨이 선택되지 않았습니다.")
            tk.messagebox.showwarning("선택 오류", "삭제할 라벨을 먼저 선택하세요.")
            return
                        
        # 현재 클래스와 페이지 저장
        current_class = self.class_selector.get()
        current_page = self.current_page
        
        # 선택된 바운딩 박스 수 계산
        total_boxes = sum(len(info['boxes']) for info in self.selected_label_info)
        
        # 경고 메시지 표시
        tk.messagebox.showinfo("알림", "참조 라벨 선택이 초기화되었습니다.")

        # 수정 후
        if hasattr(self, 'show_status_message'):
            self.show_status_message("참조 라벨 선택 초기화 완료", duration=3000)
        
        # 진행 상황을 보여주는 창 생성
        progress_window = tk.Toplevel(self.root)
        progress_window.title("라벨 삭제 중")
        progress_window.geometry("400x200")
        progress_window.transient(self.root)
        progress_window.grab_set()  # 모달 창으로 설정
        
        # 진행 상황 표시 요소
        progress_label = tk.Label(progress_window, text="선택한 바운딩 박스 삭제 중...", font=("Arial", 10, "bold"))
        progress_label.pack(pady=(15, 5))
        
        info_label = tk.Label(progress_window, text=f"총 {total_boxes}개의 바운딩 박스를 삭제합니다")
        info_label.pack(pady=5)
        
        progress_bar = ttk.Progressbar(progress_window, length=350)
        progress_bar.pack(pady=10)
        progress_bar["maximum"] = len(self.selected_label_info)
        
        status_label = tk.Label(progress_window, text="0/0 처리 완료")
        status_label.pack(pady=5)
        
        result_label = tk.Label(progress_window, text="")
        result_label.pack(pady=5)
        
        progress_window.update()
        
        # 삭제 작업 수행
        deleted_count = 0
        error_count = 0
        deleted_boxes_count = 0
        
        # 처리된 파일 목록 관리 (추가된 부분)
        processed_files = set()
        
        # 선택된 라벨 정보 별로 처리
        for i, label_info in enumerate(self.selected_label_info):
            try:
                label_path = label_info['path']
                
                # 진행 상황 업데이트
                progress_bar["value"] = i + 1
                status_label.config(text=f"{i+1}/{len(self.selected_label_info)} 처리 완료")
                result_label.config(text=f"삭제: {deleted_count}, 오류: {error_count}")
                progress_window.update()
                
                # 파일 존재 확인 - 오류 메시지 추가
                if not os.path.isfile(label_path):
                    error_count += 1
                    result_label.config(text=f"오류: 파일이 존재하지 않음 - {os.path.basename(label_path)}")
                    progress_window.update()
                    continue
                
                # 라벨 파일 읽기 - 인코딩 오류 처리 추가
                try:
                    with open(label_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                except UnicodeDecodeError:
                    try:
                        with open(label_path, 'r', encoding='cp949') as f:
                            lines = f.readlines()
                    except Exception as enc_error:
                        error_count += 1
                        result_label.config(text=f"오류: 파일 인코딩 문제 - {os.path.basename(label_path)}")
                        progress_window.update()
                        continue
                        
                # 삭제할 라인 인덱스 목록 생성
                lines_to_delete = []
                for box in label_info['boxes']:
                    if 'line_idx' in box:
                        lines_to_delete.append(box['line_idx'])

                # 디버깅 정보
                print(f"\n파일: {os.path.basename(label_path)}")
                print(f"삭제 요청된 라인 인덱스 (중복 포함): {lines_to_delete}")
                print(f"파일 전체 라인 수: {len(lines)}")

                # 중복 제거 및 정렬 (큰 인덱스부터 삭제해야 인덱스 변화 영향 없음)
                lines_to_delete = sorted(set(lines_to_delete), reverse=True)

                print(f"삭제할 라인 인덱스 (중복 제거 후): {lines_to_delete}")

                # 파일 내용 수정이 필요한지 확인
                if lines_to_delete:
                    # 유효한 라인 인덱스 필터링
                    valid_indices = [idx for idx in lines_to_delete if 0 <= idx < len(lines)]

                    print(f"유효한 라인 인덱스: {valid_indices}")

                    # 삭제된 박스 수 기록
                    deleted_boxes_count += len(valid_indices)

                    # 역순으로 해당 라인 삭제
                    for idx in valid_indices:
                        print(f"  라인 {idx} 삭제 중...")
                        del lines[idx]

                    print(f"삭제 후 남은 라인 수: {len(lines)}")

                    # 수정된 내용으로 파일 다시 쓰기
                    with open(label_path, 'w', encoding='utf-8') as f:
                        f.writelines(lines)
                        
                    deleted_count += 1

                    # 캐시된 라벨 정보가 있다면 업데이트
                    if hasattr(self, 'label_cache') and label_path in self.label_cache:
                        del self.label_cache[label_path]
                        # 접근 순서 목록에서도 제거
                        if hasattr(self, 'label_cache_access_order') and label_path in self.label_cache_access_order:
                            self.label_cache_access_order.remove(label_path)
                    
                    # 2. 겹침 캐시 무효화 (이 라벨이 관련된 모든 항목)
                    if hasattr(self, 'overlap_cache'):
                        keys_to_remove = []
                        for cache_key in self.overlap_cache.keys():
                            if isinstance(cache_key, tuple) and len(cache_key) > 0 and cache_key[0] == label_path:
                                keys_to_remove.append(cache_key)
                        
                        for key in keys_to_remove:
                            del self.overlap_cache[key]
                    
                    # 3. 이미지 캐시 관련 항목 무효화
                    img_path = self.get_image_path_from_label(label_path)

                    if hasattr(self, 'image_cache'):
                        keys_to_remove = []
                        for cache_key in self.image_cache.keys():
                            if isinstance(cache_key, str) and cache_key.startswith(img_path):
                                keys_to_remove.append(cache_key)
                        
                        for key in keys_to_remove:
                            del self.image_cache[key]
                            # 접근 순서 목록에서도 제거
                            if hasattr(self, 'image_cache_access_order') and key in self.image_cache_access_order:
                                self.image_cache_access_order.remove(key)
                    
                    # 4. 인코딩 캐시 무효화
                    if hasattr(self, 'file_encoding_cache') and label_path in self.file_encoding_cache:
                        del self.file_encoding_cache[label_path]
                    
                    # 로그 남기기
                    print(f"모든 캐시 무효화 완료: {os.path.basename(label_path)}")

                    # 이 파일에 대한 인덱스 재계산 실행
                    self.recalculate_indices(label_path, valid_indices)
                    
                    # 처리된 파일 추적 (추가된 부분)
                    processed_files.add(label_path)
                    
                # 처리 상태 업데이트
                result_label.config(text=f"삭제: {deleted_count}, 오류: {error_count}, 박스: {deleted_boxes_count}개")
                
            except Exception as e:
                error_count += 1
                print(f"라벨 삭제 중 오류 발생: {e}")
                result_label.config(text=f"오류: {str(e)[:50]}...")
                
                # 상태 표시줄에 오류 메시지 표시
                if hasattr(self, 'show_status_message'):
                    self.show_status_message(f"라벨 삭제 오류: {str(e)}", duration=5000)
                
                import traceback
                traceback.print_exc()
                
            # 주기적으로 UI 업데이트
            if i % 10 == 0 or i == len(self.selected_label_info) - 1:
                progress_window.update()
        
        # 인덱스 불일치 방지를 위한 후처리 (추가된 부분)
        if processed_files:
            # 처리된 파일의 인덱스 정보 업데이트
            self.update_file_indices(processed_files)
            
            # 로그 메시지
            if hasattr(self, 'logger'):
                self.logger.info(f"{len(processed_files)}개 파일의 인덱스 정보 업데이트됨")
            else:
                print(f"{len(processed_files)}개 파일의 인덱스 정보 업데이트됨")
        
        # 작업 완료 후 표시
        progress_label.config(text="바운딩 박스 삭제 완료!")
        result_summary = f"총 {len(self.selected_label_info)}개 이미지 중 {deleted_count}개 파일에서 {deleted_boxes_count}개 바운딩 박스 삭제 완료, 오류: {error_count}개"
        result_label.config(text=result_summary)
        
        # 상태 표시줄에 완료 메시지 표시
        if hasattr(self, 'show_status_message'):
            self.show_status_message(f"{deleted_boxes_count}개 바운딩 박스 삭제 완료", duration=3000)
        
        # 선택 상태 초기화
        self.deselect_all_images()

        # 화면의 모든 썸네일 제거 (UI 클리어)
        for widget in self.frame.winfo_children():
            widget.destroy()

        # 클래스 정보 갱신 (라벨 개수가 변경되었으므로)
        # 클래스 정보 완전히 재구성 (더 철저한 갱신)
        self.labelsdata = [[] for _ in range(100)]  # 클래스별 라벨 데이터 완전 초기화

        # 먼저 캐시 초기화 (중요!)
        if hasattr(self, 'label_cache'):
            self.label_cache.clear()
        if hasattr(self, 'label_cache_access_order'):
            self.label_cache_access_order.clear()
        if hasattr(self, 'overlap_cache'):
            self.overlap_cache.clear()
        if hasattr(self, 'file_encoding_cache'):
            self.file_encoding_cache.clear()

        print("모든 캐시 및 라벨 데이터 초기화 완료")

        # 클래스 정보 완전히 새로 구성 - completion_callback 추가
        def on_update_complete():
            """클래스 드롭다운 업데이트 완료 후 호출"""
            # 추가 검증 - 삭제된 라벨이 여전히 남아있는지 확인
            for label_info in self.selected_label_info:
                label_path = label_info['path']
                if os.path.isfile(label_path):
                    with open(label_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        if not lines:  # 빈 파일은 클래스 데이터에서 제거
                            for class_idx in range(len(self.labelsdata)):
                                if label_path in self.labelsdata[class_idx]:
                                    self.labelsdata[class_idx].remove(label_path)
                                    print(f"빈 파일 제거: {os.path.basename(label_path)}")

            print("클래스 정보 재구성 완료")

            # 원래 클래스로 복원
            if current_class != "Select Class":
                self.class_selector.set(current_class)

            # 페이지 번호 조정 (기존 페이지가 전체 페이지보다 크면 마지막 페이지로 조정)
            self.current_page = min(current_page, self.total_pages - 1) if self.total_pages > 0 else 0
            if self.current_page < 0:
                self.current_page = 0

            # 디스플레이 업데이트
            self.update_display()

            # progress_window 닫기
            if progress_window and progress_window.winfo_exists():
                progress_window.destroy()

        # 클래스 드롭다운 업데이트 (비동기, 완료 후 on_update_complete 호출)
        self.update_class_dropdown(completion_callback=on_update_complete)
    def recalculate_indices(self, label_path, deleted_indices):
        """
        파일 수정 후 인덱스를 재계산하고 모든 참조를 업데이트합니다.
        
        Parameters:
            label_path (str): 수정된 라벨 파일 경로
            deleted_indices (list): 삭제된 라인 인덱스 목록 (내림차순 정렬됨)
        """
        # 삭제된 인덱스를 내림차순으로 정렬 (이미 정렬되어 있을 수 있음)
        deleted_indices = sorted(deleted_indices, reverse=True)
        
        # 1. 위젯의 라인 인덱스 업데이트
        for widget in self.frame.winfo_children():
            if isinstance(widget, tk.Label) and hasattr(widget, 'label_path') and widget.label_path == label_path:
                if hasattr(widget, 'line_idx'):
                    line_idx = widget.line_idx
                    
                    # 이 라인이 삭제된 경우 속성 제거
                    if line_idx in deleted_indices:
                        delattr(widget, 'line_idx')
                        continue
                    
                    # 인덱스 조정 - 삭제된 각 라인에 대해 인덱스 조정
                    new_idx = line_idx
                    for del_idx in deleted_indices:
                        if del_idx < line_idx:  # 현재 라인 이전에 삭제된 경우만 조정
                            new_idx -= 1
                    
                    # 수정된 인덱스 저장
                    widget.line_idx = new_idx
        
        # 2. 선택된 라벨 정보 업데이트
        for info in self.selected_label_info[:]:
            if info['path'] == label_path:
                updated_boxes = []
                
                for box in info['boxes']:
                    if 'line_idx' in box:
                        line_idx = box['line_idx']
                        
                        # 삭제된 라인인 경우 건너뛰기
                        if line_idx in deleted_indices:
                            continue
                        
                        # 인덱스 조정
                        new_idx = line_idx
                        for del_idx in deleted_indices:
                            if del_idx < line_idx:
                                new_idx -= 1
                        
                        # 수정된 인덱스로 업데이트
                        box['line_idx'] = new_idx
                        updated_boxes.append(box)
                    else:
                        updated_boxes.append(box)
                
                # 업데이트된 박스 목록 저장
                info['boxes'] = updated_boxes
                
                # 모든 박스가 삭제된 경우 라벨 정보 자체를 제거
                if not updated_boxes:
                    self.selected_label_info.remove(info)
        
        # 3. labelsdata 배열 업데이트 (클래스별 라벨 경로)
        # 인덱스 자체는 영향 받지 않지만, 일관성을 위해 캐시 갱신
        self.refresh_label_data_cache(label_path)
    def update_file_indices(self, file_paths, deleted_line_indices=None):
        """
        파일 수정 후 인덱스 정보를 업데이트합니다.
        
        Parameters:
            file_paths (set): 업데이트할 파일 경로 집합
            deleted_line_indices (dict, optional): 파일별 삭제된 라인 인덱스 (파일 경로: 인덱스 목록)
        """
        if deleted_line_indices is None:
            deleted_line_indices = {}
        
        # 현재 표시된 위젯에서 수정된 파일과 관련된 위젯 찾기
        affected_widgets = [widget for widget in self.frame.winfo_children() 
                        if isinstance(widget, tk.Label) and 
                        hasattr(widget, 'label_path') and 
                        widget.label_path in file_paths]
        
        # 위젯의 라인 인덱스 정보 업데이트
        for widget in affected_widgets:
            if hasattr(widget, 'line_idx'):
                label_path = widget.label_path
                current_line_idx = widget.line_idx
                
                # 파일에서 해당 라인이 여전히 존재하는지 확인
                file_lines = self._get_label_data(label_path)
                
                # 직접 삭제된 라인인 경우
                if label_path in deleted_line_indices and current_line_idx in deleted_line_indices[label_path]:
                    # 라인이 삭제되었으므로 위젯에서 line_idx 속성 제거
                    delattr(widget, 'line_idx')
                    continue
                
                # 삭제된 라인으로 인한 인덱스 조정
                if label_path in deleted_line_indices:
                    new_idx = current_line_idx
                    # 현재 라인 이전에 삭제된 라인 수만큼 인덱스 감소
                    for del_idx in deleted_line_indices[label_path]:
                        if del_idx < current_line_idx:
                            new_idx -= 1
                    
                    # 새 인덱스가 유효한지 확인
                    if 0 <= new_idx < len(file_lines):
                        widget.line_idx = new_idx
                    else:
                        # 유효하지 않은 인덱스가 되면 속성 제거
                        delattr(widget, 'line_idx')
        
        # 메모리에 있는 선택된 라벨 정보 업데이트
        updated_label_info = []
        
        for info in self.selected_label_info:
            label_path = info['path']
            if label_path in file_paths:
                # 파일 다시 읽기
                file_lines = self._get_label_data(label_path)
                
                # 유효한 박스만 유지하고 인덱스 조정
                valid_boxes = []
                for box in info['boxes']:
                    if 'line_idx' in box:
                        current_line_idx = box['line_idx']
                        
                        # 직접 삭제된 라인인 경우 건너뛰기
                        if label_path in deleted_line_indices and current_line_idx in deleted_line_indices[label_path]:
                            continue
                        
                        # 삭제된 라인으로 인한 인덱스 조정
                        if label_path in deleted_line_indices:
                            new_idx = current_line_idx
                            for del_idx in deleted_line_indices[label_path]:
                                if del_idx < current_line_idx:
                                    new_idx -= 1
                            
                            # 새 인덱스가 유효한지 확인
                            if 0 <= new_idx < len(file_lines):
                                box['line_idx'] = new_idx
                                valid_boxes.append(box)
                        else:
                            # 삭제가 없는 경우 원래 인덱스가 유효한지만 확인
                            if 0 <= current_line_idx < len(file_lines):
                                valid_boxes.append(box)
                    else:
                        # line_idx가 없는 경우는 그대로 유지
                        valid_boxes.append(box)
                
                # 유효한 박스가 있는 경우만 정보 유지
                if valid_boxes:
                    info['boxes'] = valid_boxes
                    updated_label_info.append(info)
            else:
                # 수정되지 않은 파일은 그대로 유지
                updated_label_info.append(info)
        
        # 업데이트된 정보로 교체
        self.selected_label_info = updated_label_info
        
        # 로깅
        if hasattr(self, 'logger'):
            self.logger.info(f"인덱스 업데이트: {len(affected_widgets)}개 위젯, {len(updated_label_info)}개 라벨 정보")
        else:
            print(f"인덱스 업데이트: {len(affected_widgets)}개 위젯, {len(updated_label_info)}개 라벨 정보")
    def update_selection_info(self):
        """Update the selection counter display with detailed information"""
        # 이미지 선택 개수
        selected_images = len(self.selected_image_labels)
        
        # 선택된 바운딩 박스 개수
        selected_boxes = sum(len(info['boxes']) for info in self.selected_label_info)
        
        # 선택된 클래스별 개수 계산
        class_counts = {}
        for info in self.selected_label_info:
            for box in info['boxes']:
                class_id = box['class_id']
                class_counts[class_id] = class_counts.get(class_id, 0) + 1
        
        # 클래스 정보 문자열 생성
        if class_counts:
            class_info = ", ".join([f"Class {cls}: {cnt}" for cls, cnt in sorted(class_counts.items())])
        else:
            class_info = "No classes selected"
        
        # 선택 정보 업데이트
        if selected_boxes > 0:
            self.selection_info_label.config(
                text=f"Selected: {selected_images} images, {selected_boxes} boxes"
            )
            
            # 상세 클래스 정보를 표시할 툴팁 설정
            if hasattr(self, 'selection_tooltip'):
                self.selection_tooltip.destroy()
            
            # 간단한 툴팁 기능 구현 (마우스 오버 시 상세 정보 표시)
            def show_tooltip(event):
                if hasattr(self, 'selection_tooltip') and self.selection_tooltip.winfo_exists():
                    return
                    
                self.selection_tooltip = tk.Toplevel(self.root)
                self.selection_tooltip.wm_overrideredirect(True)  # 타이틀 바 제거
                
                # 마우스 위치에 표시
                x, y = self.root.winfo_pointerxy()
                self.selection_tooltip.geometry(f"+{x+10}+{y+10}")
                
                # 툴팁 내용 설정
                tooltip_text = f"Selected images: {selected_images}\n"
                tooltip_text += f"Selected boxes: {selected_boxes}\n\n"
                tooltip_text += f"Classes:\n"
                for cls, cnt in sorted(class_counts.items()):
                    tooltip_text += f"  - Class {cls}: {cnt} boxes\n"
                
                label = tk.Label(
                    self.selection_tooltip, 
                    text=tooltip_text, 
                    justify=tk.LEFT,
                    background="#ffffe0", 
                    relief="solid", 
                    borderwidth=1,
                    font=("Arial", 9)
                )
                label.pack(padx=5, pady=5)
                
                # 툴팁 자동 제거
                def hide_tooltip():
                    if hasattr(self, 'selection_tooltip') and self.selection_tooltip.winfo_exists():
                        self.selection_tooltip.destroy()
                        
                self.selection_info_label.after(3000, hide_tooltip)  # 3초 후 제거
                
            def hide_tooltip(event):
                if hasattr(self, 'selection_tooltip') and self.selection_tooltip.winfo_exists():
                    self.selection_tooltip.destroy()
                    
            # 툴팁 이벤트 바인딩
            self.selection_info_label.bind("<Enter>", show_tooltip)
            self.selection_info_label.bind("<Leave>", hide_tooltip)
        else:
            self.selection_info_label.config(text=f"Selected Images: {selected_images}")

    def update_pagination_controls(self):
        """페이지네이션 컨트롤 상태 업데이트"""
        # 전체 파일 개수 업데이트
        total_files = len(self.image_paths)
        self.total_files_label.config(text=f"{total_files}개")

        # 페이지 입력 필드와 전체 페이지 레이블 업데이트
        self.page_entry.delete(0, tk.END)  # 기존 내용 삭제
        self.page_entry.insert(0, str(self.current_page + 1))  # 1부터 시작하는 페이지 번호 삽입
        self.total_pages_label.config(text=f"/{self.total_pages}")

        # 현재 페이지 범위 계산 및 표시
        if total_files > 0:
            start_idx = self.current_page * self.page_size + 1
            end_idx = min((self.current_page + 1) * self.page_size, total_files)
            self.page_range_label.config(text=f"({start_idx}-{end_idx})")
        else:
            self.page_range_label.config(text="(0-0)")

        # 버튼 활성화/비활성화 상태 업데이트
        self.prev_button.config(state="normal" if self.current_page > 0 else "disabled")
        self.next_button.config(state="normal" if self.current_page < self.total_pages - 1 else "disabled")

    def apply_page_size(self):
        """페이지 크기 적용"""
        try:
            new_page_size = int(self.page_size_entry.get())
            if new_page_size <= 0:
                tk.messagebox.showerror("오류", "페이지 크기는 1 이상이어야 합니다.")
                return
            if new_page_size > 10000:
                tk.messagebox.showerror("오류", "페이지 크기는 10000 이하여야 합니다.")
                return

            # 페이지 크기 업데이트
            self.page_size = new_page_size

            # 전체 페이지 수 재계산
            self.total_pages = (len(self.image_paths) + self.page_size - 1) // self.page_size

            # 현재 페이지가 유효한 범위 내에 있는지 확인
            if self.current_page >= self.total_pages:
                self.current_page = max(0, self.total_pages - 1)

            # 화면 업데이트
            self.update_display()

            print(f"페이지 크기 변경: {new_page_size}개, 전체 페이지: {self.total_pages}개")

        except ValueError:
            tk.messagebox.showerror("오류", "페이지 크기는 숫자여야 합니다.")

    def next_page(self):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.update_display()

    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_display()
    def on_class_changed(self, *args):
        """Handle class selection changes"""
        # 페이지 번호 초기화
        self.current_page = 0
        # 디스플레이 업데이트
        self.update_display()
    def select_all_images(self):
        """현재 화면에 표시된 모든 이미지와 그 안의 모든 박스를 선택 상태로 변경"""
        try:
            # 현재 화면에 표시된 모든 이미지를 선택 상태로 변경
            for widget in self.frame.winfo_children():
                if isinstance(widget, tk.Label) and hasattr(widget, 'image'):
                    # 이미 선택된 이미지는 건너뛰기
                    if widget in self.checklist:
                        continue
                    
                    # 이미지 테두리를 빨간색으로 변경
                    widget.config(bd=2, highlightbackground="red", highlightthickness=4)
                    widget.config(bg="#ffdddd")  # 연한 빨간색 배경
                    
                    # self.checklist에 위젯 추가
                    self.checklist.append(widget)
                    
                    # label_path 속성이 있다면 selected_image_labels에 추가
                    if hasattr(widget, 'label_path') and widget.label_path not in self.selected_image_labels:
                        label_path = widget.label_path
                        self.selected_image_labels.append(label_path)
                        
                        # 중요: 라벨 내의 모든 박스 정보도 함께 저장
                        # 여기가 기존 함수에서 누락된 부분
                        self.save_all_boxes_info(label_path)
            
            # 선택 정보 업데이트
            self.update_selection_info()
        
        except Exception as e:
            print(f"Error selecting all images: {e}")
            import traceback
            traceback.print_exc()
    # 3. 전체 해제 기능 메소드 추가
    def save_all_boxes_info(self, label_path):
        """
        라벨 파일의 모든 박스 정보를 selected_label_info에 저장합니다.
        
        Parameters:
            label_path (str): 라벨 파일의 경로
        """
        try:
            # 파일 존재 확인
            if not os.path.isfile(label_path):
                print(f"라벨 파일이 존재하지 않습니다: {label_path}")
                return
            
            # 현재 선택된 클래스 확인
            if self.class_selector.get() == "Select Class":
                print("클래스가 선택되지 않았습니다.")
                return
                
            selected_class = int(float(self.class_selector.get()))
            
            # 라벨 파일 읽기
            with open(label_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 해당 클래스의 모든 박스 정보 추출
            boxes_info = []
            
            for line_idx, line in enumerate(lines):
                parts = line.strip().split()
                if not parts or len(parts) < 5:
                    continue
                    
                try:
                    # 박스 정보 추출
                    class_id = int(float(parts[0]))
                    
                    # 현재 선택된 클래스만 처리
                    if class_id != selected_class:
                        continue
                        
                    x_center = float(parts[1])
                    y_center = float(parts[2])
                    width = float(parts[3])
                    height = float(parts[4])
                    
                    # 박스 정보 생성
                    box_info = {
                        'class_id': class_id,
                        'x_center': x_center,
                        'y_center': y_center,
                        'width': width,
                        'height': height,
                        'line_idx': line_idx
                    }
                    
                    boxes_info.append(box_info)
                    
                except (ValueError, IndexError) as e:
                    print(f"라인 파싱 중 오류 ({line_idx}): {e}")
                    continue
            
            # 박스 정보가 있으면 라벨 정보 저장/업데이트
            if boxes_info:
                # 이미 저장된 라벨인지 확인
                existing_label = next((info for info in self.selected_label_info 
                                    if info['path'] == label_path), None)
                
                if existing_label:
                    # 기존 정보 업데이트 (중복 방지)
                    existing_line_indices = {box['line_idx'] for box in existing_label['boxes']}
                    
                    for box in boxes_info:
                        if box['line_idx'] not in existing_line_indices:
                            existing_label['boxes'].append(box)
                else:
                    # 새 라벨 정보 생성
                    new_label_info = {
                        'path': label_path,
                        'boxes': boxes_info
                    }
                    self.selected_label_info.append(new_label_info)
                
                print(f"전체 선택: {label_path}에서 {len(boxes_info)}개의 박스 정보 저장")
                
        except Exception as e:
            print(f"라벨 정보 저장 중 오류: {e}")
            import traceback
            traceback.print_exc()
    def deselect_all_images(self):
        """모든 선택된 이미지와 라벨 정보를 초기화합니다."""
        try:
            # 모든 선택된 이미지 라벨의 스타일 초기화
            for label in self.checklist:
                if label.winfo_exists():
                    label.config(bd=2, highlightbackground="white", highlightthickness=2)
                    label.config(bg="white")
            
            # 선택 목록 초기화
            self.selected_image_labels.clear()
            self.checklist.clear()
            
            # 선택된 라벨 정보도 초기화 (이 부분이 누락되어 있었음)
            if hasattr(self, 'selected_label_info'):
                self.selected_label_info.clear()
            
            # 선택 정보 업데이트
            self.update_selection_info()
            
            print("모든 선택 정보가 초기화되었습니다.")
        
        except Exception as e:
            print(f"이미지 선택 해제 중 오류 발생: {e}")
            import traceback
            traceback.print_exc()

    def refresh_data(self):
        """현재 로드된 데이터를 다시 로드하고 화면을 갱신"""
        if not self.image_paths:
            print("로드된 데이터가 없습니다.")
            tk.messagebox.showinfo("알림", "먼저 이미지 데이터를 로드하세요.")
            return
        
        # 로그 파일 준비
        log_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"refresh_log_{log_timestamp}.txt"
        log_path = os.path.join(os.path.dirname(self.rootpath) if self.rootpath else os.getcwd(), log_filename)
        
        with open(log_path, 'w', encoding='utf-8') as log_file:
            log_file.write(f"===== 데이터 리프레시 로그 시작: {log_timestamp} =====\n\n")
            log_file.write(f"현재 rootpath: {self.rootpath}\n")
            log_file.write(f"현재 filename: {self.filename}\n")
            log_file.write(f"현재 이미지 경로 개수: {len(self.image_paths)}\n")
            log_file.write(f"현재 라벨 경로 개수: {len(self.labels)}\n")
            log_file.write(f"현재 선택된 클래스: {self.class_selector.get()}\n")
            log_file.write(f"현재 페이지: {self.current_page}/{self.total_pages}\n\n")
            
            # 유사 라벨 필터링 상태 기록
            log_file.write("필터링 모드 상태:\n")
            log_file.write(f"show_only_similar 속성 존재: {hasattr(self, 'show_only_similar')}\n")
            if hasattr(self, 'show_only_similar'):
                log_file.write(f"show_only_similar 값: {self.show_only_similar}\n")
            log_file.write(f"current_filtered_labels 속성 존재: {hasattr(self, 'current_filtered_labels')}\n")
            if hasattr(self, 'current_filtered_labels'):
                log_file.write(f"current_filtered_labels 길이: {len(self.current_filtered_labels)}\n")
            log_file.write(f"filtered_similar_labels 속성 존재: {hasattr(self, 'filtered_similar_labels')}\n")
            if hasattr(self, 'filtered_similar_labels'):
                log_file.write(f"filtered_similar_labels 길이: {len(self.filtered_similar_labels)}\n")
            log_file.write(f"reference_label 속성 존재: {hasattr(self, 'reference_label')}\n\n")
            
            # 클래스별 라벨 개수 기록
            log_file.write("클래스별 라벨 개수 (리프레시 전):\n")
            for i, labels in enumerate(self.labelsdata):
                if labels:
                    log_file.write(f"클래스 {i}: {len(labels)}개\n")
                
        # 진행 창 생성
        progress_window = tk.Toplevel(self.root)
        progress_window.title("데이터 리프레시")
        progress_window.geometry("400x200")
        progress_window.transient(self.root)
        progress_window.grab_set()
        
        # 진행 창에 로그 파일 경로 표시
        log_info_label = tk.Label(progress_window, text=f"로그 파일: {log_filename}", font=("Arial", 8))
        log_info_label.pack(pady=2)
        
        # 진행 상황 표시 요소
        progress_label = tk.Label(progress_window, text="데이터 리프레시 중...", font=("Arial", 10, "bold"))
        progress_label.pack(pady=(5, 5))
        
        info_label = tk.Label(progress_window, text="클래스 정보 및 라벨 파일 다시 로드 중")
        info_label.pack(pady=5)
        
        progress_bar = ttk.Progressbar(progress_window, length=350)
        progress_bar.pack(pady=10)
        progress_bar["maximum"] = 100
        
        status_label = tk.Label(progress_window, text="라벨 파일 분석 중...")
        status_label.pack(pady=5)
        
        result_label = tk.Label(progress_window, text="")
        result_label.pack(pady=5)
        
        progress_window.update()
        
        try:
            with open(log_path, 'a', encoding='utf-8') as log_file:
                log_file.write("\n===== 리프레시 과정 시작 =====\n")
                
                # 기존 데이터 백업
                orig_page = self.current_page
                orig_selected_class = self.class_selector.get()
                log_file.write(f"백업 - 원래 페이지: {orig_page}, 원래 선택 클래스: {orig_selected_class}\n")
                
                # 진행 상황 업데이트 (25%)
                progress_bar["value"] = 25
                status_label.config(text="이미지 정보 갱신 중...")
                progress_window.update()
                
                # 유사 라벨 필터링 모드 초기화
                log_file.write("필터링 모드 초기화 시작...\n")
                if hasattr(self, 'show_only_similar'):
                    log_file.write(f"show_only_similar 속성 삭제: {self.show_only_similar}\n")
                    delattr(self, 'show_only_similar')
                if hasattr(self, 'current_filtered_labels'):
                    log_file.write(f"current_filtered_labels 속성 삭제 (길이: {len(self.current_filtered_labels)})\n")
                    delattr(self, 'current_filtered_labels')
                if hasattr(self, 'filtered_similar_labels'):
                    log_file.write(f"filtered_similar_labels 속성 삭제 (길이: {len(self.filtered_similar_labels)})\n")
                    delattr(self, 'filtered_similar_labels')
                if hasattr(self, 'reference_label'):
                    log_file.write("reference_label 속성 삭제\n")
                    delattr(self, 'reference_label')
                log_file.write("필터링 모드 초기화 완료\n\n")
                
                # 기존 라벨 데이터 상태 기록
                log_file.write("기존 labelsdata 정보:\n")
                for i, labels in enumerate(self.labelsdata):
                    if labels:
                        log_file.write(f"클래스 {i}: {len(labels)}개\n")
                        # 샘플 라벨 경로 기록 (최대 3개)
                        for j, label_path in enumerate(labels[:3]):
                            log_file.write(f"  - 샘플 {j+1}: {label_path}\n")
                        if len(labels) > 3:
                            log_file.write(f"  - ... 외 {len(labels)-3}개\n")
                
                # 라벨 데이터 초기화 및 다시 로드
                log_file.write("\n라벨 데이터 초기화 시작...\n")
                self.labelsdata = [[] for _ in range(100)]
                self.overlap_cache = {}
                log_file.write("labelsdata 및 overlap_cache 초기화 완료\n")
                
                # 진행 상황 업데이트 (50%)
                progress_bar["value"] = 50
                status_label.config(text="클래스 정보 갱신 중...")
                progress_window.update()
                
                # 클래스 정보 업데이트 전 현재 상태 기록
                log_file.write("\n클래스 드롭다운 업데이트 전 상태:\n")
                log_file.write(f"라벨 파일 개수: {len(self.labels)}\n")
                log_file.write(f"이미지 파일 개수: {len(self.image_paths)}\n")
                
                # 클래스 정보 업데이트
                log_file.write("\n클래스 정보 업데이트 시작...\n")
                self.update_class_dropdown()
                log_file.write("클래스 정보 업데이트 완료\n")
                
                # 업데이트 후 라벨 데이터 상태 기록
                log_file.write("\n업데이트 후 labelsdata 정보:\n")
                for i, labels in enumerate(self.labelsdata):
                    if labels:
                        log_file.write(f"클래스 {i}: {len(labels)}개\n")
                        # 샘플 라벨 경로 기록 (최대 3개)
                        for j, label_path in enumerate(labels[:3]):
                            log_file.write(f"  - 샘플 {j+1}: {label_path}\n")
                        if len(labels) > 3:
                            log_file.write(f"  - ... 외 {len(labels)-3}개\n")
                
                # 페이지네이션 초기화
                log_file.write(f"\n페이지네이션 초기화: 원래 페이지 {orig_page}, 전체 페이지 {self.total_pages}\n")
                self.current_page = min(orig_page, self.total_pages - 1)
                if self.current_page < 0:
                    self.current_page = 0
                log_file.write(f"초기화 후 현재 페이지: {self.current_page}\n")
                    
                # 선택 상태 초기화
                log_file.write(f"\n선택 상태 초기화: 선택된 이미지 수 {len(self.selected_image_labels)}\n")
                self.deselect_all_images()
                log_file.write(f"초기화 후 선택된 이미지 수: {len(self.selected_image_labels)}\n")
                
                # 진행 상황 업데이트 (75%)
                progress_bar["value"] = 75
                status_label.config(text="디스플레이 갱신 중...")
                progress_window.update()
                
                # 클래스 선택자 복원
                log_file.write(f"\n클래스 선택자 복원: {orig_selected_class}\n")
                if orig_selected_class != "Select Class":
                    self.class_selector.set(orig_selected_class)
                    log_file.write(f"복원 후 선택된 클래스: {self.class_selector.get()}\n")
                
                # 디스플레이 업데이트 전 상태 기록
                log_file.write("\n디스플레이 업데이트 전 상태:\n")
                log_file.write(f"총 페이지 수: {self.total_pages}\n")
                log_file.write(f"현재 페이지: {self.current_page}\n")
                log_file.write(f"선택된 클래스: {self.class_selector.get()}\n")
                
                log_file.write("\n디스플레이 업데이트 시작...\n")
            
            # 디스플레이 업데이트
            self.update_display()
            
            with open(log_path, 'a', encoding='utf-8') as log_file:
                log_file.write("디스플레이 업데이트 완료\n")
                
                # 최종 상태 기록
                log_file.write("\n===== 리프레시 완료 후 최종 상태 =====\n")
                log_file.write(f"총 이미지 수: {len(self.image_paths)}\n")
                log_file.write(f"총 라벨 파일 수: {len(self.labels)}\n")
                log_file.write(f"총 페이지 수: {self.total_pages}\n")
                log_file.write(f"현재 페이지: {self.current_page}\n")
                log_file.write(f"선택된 클래스: {self.class_selector.get()}\n")
                
                # 클래스별 라벨 개수 기록
                log_file.write("\n클래스별 라벨 개수 (리프레시 후):\n")
                for i, labels in enumerate(self.labelsdata):
                    if labels:
                        log_file.write(f"클래스 {i}: {len(labels)}개\n")
                
                log_file.write("\n===== 데이터 리프레시 로그 종료 =====\n")
            
            # 완료
            progress_bar["value"] = 100
            progress_label.config(text="리프레시 완료!")
            status_label.config(text="모든 데이터가 성공적으로 갱신되었습니다.")
            result_label.config(text=f"총 {len(self.image_paths)}개 이미지, {self.total_pages}개 페이지")
            
            # 로그 파일 경로 안내
            log_info_label.config(text=f"로그 파일 저장됨: {log_filename}", fg="blue")
            
            # 닫기 버튼 추가
            close_button = tk.Button(progress_window, text="닫기", command=progress_window.destroy)
            close_button.pack(pady=10)
            
            progress_window.update()
            
        except Exception as e:
            print(f"Error refreshing data: {e}")
            import traceback
            error_traceback = traceback.format_exc()
            
            # 오류 정보를 로그 파일에 기록
            with open(log_path, 'a', encoding='utf-8') as log_file:
                log_file.write(f"\n===== 오류 발생 =====\n")
                log_file.write(f"오류 메시지: {str(e)}\n")
                log_file.write(f"오류 세부 정보:\n{error_traceback}\n")
                log_file.write("\n===== 데이터 리프레시 로그 종료 (오류로 인한 중단) =====\n")
            
            # 오류 메시지 표시
            progress_label.config(text="리프레시 오류!")
            status_label.config(text=f"오류 발생: {str(e)}")
            log_info_label.config(text=f"오류 로그 저장됨: {log_filename}", fg="red")
            
            # 닫기 버튼 추가
            close_button = tk.Button(progress_window, text="닫기", command=progress_window.destroy)
            close_button.pack(pady=10)
    def save_selected_label_info(self, label_path, line_idx=None):
        """
        선택한 라벨의 박스 정보를 저장합니다.
        
        Parameters:
            label_path (str): 선택된 라벨 파일의 경로
            line_idx (int, optional): 라벨 파일에서의 라인 인덱스 (특정 박스 선택 시)
                                    주의: None이면 현재 클래스의 모든 박스를 처리
        """
        try:
            print(f"박스 정보 저장 시도: {label_path}, 라인 인덱스: {line_idx}")
            
            if not os.path.isfile(label_path):
                print(f"파일 존재하지 않음: {label_path}")
                return False
                    
            # 파일 읽기
            lines = self._get_label_data(label_path)
            if not lines:
                print(f"라벨 파일을 읽을 수 없음: {label_path}")
                return False
            
            # 이미 저장된 라벨인지 확인
            existing_label = next((info for info in self.selected_label_info if info['path'] == label_path), None)
            
            # 현재 선택된 클래스 확인
            selected_class = None
            if hasattr(self, 'class_selector') and self.class_selector.get() != "Select Class":
                try:
                    selected_class = int(float(self.class_selector.get()))
                    print(f"현재 선택된 클래스: {selected_class}")
                except ValueError:
                    selected_class = None
            
            # line_idx가 지정된 경우 - 특정 박스만 처리
            if line_idx is not None:
                # 중요: line_idx가 명시적으로 지정된 경우 해당 라인만 처리
                if line_idx < 0 or line_idx >= len(lines):
                    print(f"유효하지 않은 라인 인덱스: {line_idx}, 최대: {len(lines)-1}")
                    return False
                
                # 현재 라인 파싱
                line = lines[line_idx]
                parts = line.strip().split()
                
                if not parts or len(parts) < 5:
                    print(f"유효하지 않은 박스 데이터: {line}")
                    return False
                    
                # 박스 정보 추출
                try:
                    current_class_id = int(float(parts[0]))
                    print(f"파일에서 읽은 클래스 ID: {current_class_id}, 라인 {line_idx}")
                    
                    # 클래스 변경 작업인지 확인 (선택된 클래스와 현재 클래스가 다른 경우)
                    is_class_change = (selected_class is not None and 
                                    current_class_id != selected_class and
                                    hasattr(self, 'changing_class') and 
                                    self.changing_class)
                    
                    # # 중요: 현재 선택된 클래스와 파일에서 읽은 클래스가 다른 경우 확인
                    # if selected_class is not None and current_class_id != selected_class:
                    #     if not is_class_change:
                    #         print(f"경고: 읽은 클래스({current_class_id})가 선택된 클래스({selected_class})와 다릅니다")
                            
                    #         # 일반 선택 작업인 경우, 클래스가 다르면 무시
                    #         if hasattr(self, 'strict_class_filtering') and self.strict_class_filtering:
                    #             print(f"클래스 불일치로 선택 무시")
                    #             return False
                    
                    # 클래스 변경 작업인 경우, 선택된 클래스로 클래스 ID 변경
                    if is_class_change:
                        print(f"클래스 변경 작업: {current_class_id} → {selected_class}")
                        current_class_id = selected_class
                    
                except ValueError:
                    print(f"클래스 ID 변환 오류: {parts[0]}")
                    return False
                    
                x_center = float(parts[1])
                y_center = float(parts[2])
                width = float(parts[3])
                height = float(parts[4])
                
                # 박스 정보 생성 - 파일에서 읽은 실제 클래스 ID 저장
                box_info = {
                    'class_id': current_class_id,
                    'x_center': x_center,
                    'y_center': y_center,
                    'width': width,
                    'height': height,
                    'line_idx': line_idx
                }
                
                # 라벨 정보 추가 또는 업데이트
                if existing_label:
                    # 이미 같은 라인의 박스가 있는지 확인
                    existing_box = next((box for box in existing_label['boxes'] 
                                    if box['line_idx'] == line_idx), None)
                    
                    if existing_box:
                        # 이미 있는 박스는 업데이트
                        existing_box.update(box_info)
                        print(f"기존 박스 업데이트: 라인 {line_idx}, 클래스 {current_class_id}")
                    else:
                        # 없으면 새로 추가
                        existing_label['boxes'].append(box_info)
                        print(f"새 박스 추가: 라인 {line_idx}, 클래스 {current_class_id}")
                else:
                    # 새 라벨 정보 생성
                    new_label_info = {
                        'path': label_path,
                        'boxes': [box_info]
                    }
                    self.selected_label_info.append(new_label_info)
                    print(f"새 라벨 정보 생성: {label_path}, 클래스 {current_class_id}")
                
                return True
                
            else:
                # line_idx가 None인 경우 - 현재 선택한 클래스의 모든 박스 처리
                print(f"파일의 모든 박스 처리: {os.path.basename(label_path)}")
                
                # 중요: 선택된 클래스가 없으면 처리하지 않음
                if selected_class is None:
                    print("선택된 클래스가 없어 처리할 수 없습니다.")
                    return False
                    
                # 모든 박스 정보 수집
                boxes = []
                
                # 같은 클래스의 여러 박스 처리를 위한 카운터
                same_class_count = 0
                
                for idx, line in enumerate(lines):
                    parts = line.strip().split()
                    if not parts or len(parts) < 5:
                        continue
                    
                    try:
                        # 박스 정보 추출
                        class_id = int(float(parts[0]))
                        
                        # 중요: 선택된 클래스와 일치하는 박스만 처리
                        if class_id != selected_class:
                            print(f"무시된 다른 클래스 박스: 라인 {idx}, 클래스 {class_id} (선택됨: {selected_class})")
                            continue
                            
                        same_class_count += 1
                        print(f"같은 클래스({selected_class}) 박스 #{same_class_count} 처리 중: 라인 {idx}")
                            
                        x_center = float(parts[1])
                        y_center = float(parts[2])
                        width = float(parts[3])
                        height = float(parts[4])
                        
                        box_info = {
                            'class_id': class_id,
                            'x_center': x_center,
                            'y_center': y_center,
                            'width': width,
                            'height': height,
                            'line_idx': idx
                        }
                        boxes.append(box_info)
                        print(f"박스 정보 추가: 라인 {idx}, 클래스 {class_id}")
                    except ValueError:
                        print(f"잘못된 박스 형식 무시: 라인 {idx}")
                        continue
                
                # 라벨 정보 추가 또는 업데이트
                if boxes:
                    if existing_label:
                        # 기존 라벨 정보가 있는 경우, 새 박스 정보 병합
                        existing_line_indices = {box['line_idx'] for box in existing_label['boxes']}
                        
                        for box in boxes:
                            if box['line_idx'] not in existing_line_indices:
                                existing_label['boxes'].append(box)
                                existing_line_indices.add(box['line_idx'])
                        
                        print(f"기존 라벨 정보 업데이트: {os.path.basename(label_path)}, "
                            f"총 {len(existing_label['boxes'])}개 박스")
                    else:
                        # 새 라벨 정보 생성
                        new_label_info = {
                            'path': label_path,
                            'boxes': boxes
                        }
                        self.selected_label_info.append(new_label_info)
                        print(f"새 라벨 정보 생성: {os.path.basename(label_path)}, {len(boxes)}개 박스")
                    
                    return True
                else:
                    print(f"파일에 처리할 박스가 없음: {os.path.basename(label_path)}")
                    return False
        
        except Exception as e:
            print(f"라벨 정보 저장 중 오류: {e}")
            import traceback
            traceback.print_exc()
            return False
    def change_class_labels(self):
        """선택한 이미지의 특정 바운딩 박스 클래스만 변경"""
        if not self.selected_image_labels:
            print("변경할 이미지가 선택되지 않았습니다.")
            tk.messagebox.showwarning("선택 오류", "변경할 이미지를 먼저 선택하세요.")
            return
        
        if not self.selected_label_info:
            print("변경할 라벨이 선택되지 않았습니다.")
            tk.messagebox.showwarning("선택 오류", "변경할 라벨을 먼저 선택하세요.")
            return
        self.changing_class = True  # 클래스 변경 모드 활성화
        print("클래스 변경 모드 활성화")

        # 선택된 바운딩 박스 수 계산
        total_boxes = sum(len(info['boxes']) for info in self.selected_label_info)
        
        # 실제 데이터 구조 출력 (디버깅용)
        print("===== 선택된 라벨 정보 =====")
        for i, info in enumerate(self.selected_label_info):
            print(f"라벨 {i+1}: {os.path.basename(info['path'])}")
            for j, box in enumerate(info['boxes']):
                print(f"  박스 {j+1}: 클래스={box.get('class_id', '?')}, 라인={box.get('line_idx', '?')}")
        
        # 선택된 클래스 ID 목록 가져오기
        selected_class_ids = []
        for label_info in self.selected_label_info:
            for box in label_info['boxes']:
                if 'class_id' in box:
                    selected_class_ids.append(box['class_id'])
        
        # 빈 목록이면 기본값 지정
        if not selected_class_ids:
            selected_class_ids = [0]
        
        print(f"선택된 클래스 ID 목록: {selected_class_ids}")
        
        # 가장 많이 등장하는 클래스 ID 찾기 (기본값으로 사용)
        most_common_class = 0
        if selected_class_ids:
            from collections import Counter
            counter = Counter(selected_class_ids)
            most_common_class = counter.most_common(1)[0][0]
        
        print(f"가장 많이 등장하는 클래스 ID: {most_common_class}")

        # 클래스 변경 대화상자 생성
        change_dialog = tk.Toplevel(self.root)
        change_dialog.title("클래스 변경")
        change_dialog.geometry("400x300")
        change_dialog.transient(self.root)
        change_dialog.grab_set()  # 모달 창으로 설정
        
        # 변수 설정 - 가장 많이 등장하는 클래스 ID로 초기화
        target_class = tk.StringVar(value=str(most_common_class))
        
        # 다이얼로그 UI 구성
        ttk.Label(change_dialog, text=f"선택한 {total_boxes}개의 바운딩 박스 클래스 변경", 
                font=("Arial", 12, "bold")).pack(pady=(15, 10))
        
        # 현재 선택된 박스 정보 표시
        selected_info = ttk.Frame(change_dialog)
        selected_info.pack(fill="x", padx=20, pady=5)
        
        # 선택된 클래스 ID 텍스트 생성 (중복 제거 및 정렬)
        unique_class_ids = sorted(set(selected_class_ids))
        current_classes_text = ", ".join(map(str, unique_class_ids))
        ttk.Label(selected_info, text=f"현재 선택된 클래스: {current_classes_text}", 
                font=("Arial", 10)).pack(pady=5)
        
        # 대상 클래스 선택 프레임
        target_frame = ttk.Frame(change_dialog)
        target_frame.pack(fill="x", padx=20, pady=5)
        
        ttk.Label(target_frame, text="새 클래스:").pack(side="left", padx=(0, 5))
        
        # 클래스 목록 생성
        class_list = [str(i) for i in range(10)] + ["직접 입력"]
        
        target_combo = ttk.Combobox(target_frame, textvariable=target_class, width=15)
        target_combo['values'] = class_list
        target_combo.pack(side="left", padx=5)
        
        # 현재 선택된 클래스를 위젯에 표시
        target_combo.set(str(most_common_class))
        
        # 버튼 프레임
        button_frame = ttk.Frame(change_dialog)
        button_frame.pack(fill="x", padx=20, pady=20)
        
        # 결과 레이블
        result_label = ttk.Label(change_dialog, text="")
        result_label.pack(pady=10)
        
        def on_target_selected(event):
            if target_class.get() == "직접 입력":
                target_class.set("")

        target_combo.bind("<<ComboboxSelected>>", on_target_selected)
        
        # 변경 실행 함수
        def execute_change():
            tgt_class = target_class.get().strip()
            current_class = self.class_selector.get()
            current_page = self.current_page
            if not tgt_class:
                result_label.config(text="새 클래스를 입력하세요", foreground="red")
                return
            
            try:
                tgt_class_idx = int(tgt_class)
            except ValueError:
                result_label.config(text="클래스 ID는 정수여야 합니다", foreground="red")
                return
            
            # 진행 상황 표시를 위한 프로그레스바
            progress = ttk.Progressbar(change_dialog, orient="horizontal", length=350, mode="determinate")
            progress.pack(pady=10)
            progress["maximum"] = len(self.selected_label_info)
            
            # 변경 작업 실행
            label_paths_to_refresh = []

            # 변경 작업 실행
            processed = 0
            changed = 0
            changed_boxes = 0

            for i, label_info in enumerate(self.selected_label_info):
                label_path = label_info['path']
                
                if not os.path.isfile(label_path):
                    continue
                
                try:
                    # 라벨 파일 읽기
                    with open(label_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    
                    # 변경될 라인 인덱스 목록 - 딕셔너리로 저장 (라인 인덱스: 새 클래스 ID)
                    lines_to_change = {}
                    
                    # 선택된 박스의 라인 인덱스 수집
                    for box in label_info['boxes']:
                        if 'line_idx' in box:
                            line_idx = box['line_idx']
                            # 유효한 라인 인덱스인지 확인
                            if 0 <= line_idx < len(lines):
                                lines_to_change[line_idx] = tgt_class_idx
                                # 내부 데이터 구조도 업데이트 (중요!)
                                box['class_id'] = tgt_class_idx
                    
                    # 파일 내용 수정이 필요한지 확인
                    if lines_to_change:
                        # 새 내용 생성
                        new_lines = []
                        for line_idx, line in enumerate(lines):
                            if line_idx in lines_to_change:
                                # 선택된 박스의 라인만 변경
                                parts = line.strip().split()
                                if parts:  # 라인이 비어있지 않은지 확인
                                    # 클래스 ID만 변경하고 나머지는 유지
                                    parts[0] = str(lines_to_change[line_idx])
                                    new_line = " ".join(parts) + "\n"
                                    new_lines.append(new_line)
                                    changed_boxes += 1
                                    print(f"라인 {line_idx}의 클래스를 {parts[0]}로 변경")
                                else:
                                    # 빈 라인은 그대로 유지
                                    new_lines.append(line)
                            else:
                                # 선택되지 않은 라인은 그대로 유지
                                new_lines.append(line)
                        
                        # 파일에 쓰기
                        with open(label_path, 'w', encoding='utf-8') as f:
                            f.writelines(new_lines)
                        
                        # 변경된 라벨 경로 추적
                        label_paths_to_refresh.append(label_path)
                        
                        changed += 1
                    
                    processed += 1
                    
                    # 진행 상황 업데이트
                    progress["value"] = i + 1
                    result_label.config(
                        text=f"처리 중: {processed}/{len(self.selected_label_info)}, 변경된 파일: {changed}",
                        foreground="blue"
                    )
                    change_dialog.update()
                    
                except Exception as e:
                    print(f"Error processing {label_path}: {e}")
                    import traceback
                    traceback.print_exc()
                
            # 완료 메시지
            result_label.config(
                text=f"완료: {processed}개 파일 처리, {changed}개 파일에서 {changed_boxes}개의 바운딩 박스 클래스를 {tgt_class_idx}로 변경했습니다",
                foreground="green",
                font=("Arial", 10, "bold")
            )

            # 상태 바에 알림 추가
            if hasattr(self, 'show_status_message'):
                self.show_status_message(f"클래스 변경 완료: {changed_boxes}개 박스를 클래스 {tgt_class_idx}로 변경", duration=3000)

            # 창 자동 닫기 (2초 후)
            if changed > 0:  # 변경된 파일이 있는 경우에만
                self.root.after(2000, change_dialog.destroy)
                
                # 창이 곧 닫힌다는 알림 추가
                auto_close_label = tk.Label(
                    change_dialog, 
                    text="창이 곧 자동으로 닫힙니다...",
                    font=("Arial", 9, "italic"),
                    fg="gray"
                )
                auto_close_label.pack(pady=(0, 10))
            # 캐시 무효화
            for label_path in set(label_paths_to_refresh):
                self.invalidate_caches_for_label(label_path)

            # 라벨 데이터 캐시도 갱신
            self.refresh_label_data_cache()
            self.deselect_all_images()

            # 화면의 모든 썸네일 제거 (UI 클리어)
            for widget in self.frame.winfo_children():
                widget.destroy()

            # 클래스 정보 업데이트 완료 후 호출될 콜백 정의
            def on_update_complete():
                """클래스 드롭다운 업데이트 완료 후 호출"""
                # 원래 클래스로 복원
                if current_class != "Select Class":
                    self.class_selector.set(current_class)

                # 페이지 번호 조정
                self.current_page = min(current_page, self.total_pages - 1) if self.total_pages > 0 else 0
                if self.current_page < 0:
                    self.current_page = 0

                # 클래스 변경 모드 비활성화
                self.changing_class = False
                print("클래스 변경 모드 비활성화")

                # 화면 갱신
                self.update_display()

            # 클래스 정보와 디스플레이 업데이트 (비동기)
            self.update_class_dropdown(completion_callback=on_update_complete)
        
        # 버튼 추가
        ttk.Button(button_frame, text="변경", command=execute_change).pack(side="left", padx=5)
        ttk.Button(button_frame, text="취소", command=change_dialog.destroy).pack(side="right", padx=5)
    def refresh_label_data_cache(self, specific_paths=None):
        """
        라벨 데이터 캐시를 갱신합니다.
        
        Args:
            specific_paths (list, optional): 특정 경로만 갱신할 경우 경로 목록
        """
        start_time = time.time()
        
        # 로깅
        if hasattr(self, 'logger'):
            if specific_paths:
                self.logger.info(f"라벨 데이터 캐시 갱신 - {len(specific_paths)}개 파일")
            else:
                self.logger.info("전체 라벨 데이터 캐시 갱신")
        
        try:
            # 전체 갱신 또는 특정 파일만 갱신
            paths_to_process = specific_paths if specific_paths else self.labels
            processed_count = 0
            updated_count = 0
            
            # 클래스별 파일 개수 기록 (이전)
            before_counts = {}
            for class_idx, paths in enumerate(self.labelsdata):
                if paths:  # 비어있지 않은 경우만
                    before_counts[class_idx] = len(paths)
            
            # 특정 파일만 갱신하는 경우 - 해당 파일 제거
            if specific_paths:
                # 기존 labelsdata에서 해당 파일 제거
                for class_idx, paths in enumerate(self.labelsdata):
                    self.labelsdata[class_idx] = [p for p in paths if p not in specific_paths]
            
            # 파일 처리
            for label_path in paths_to_process:
                if not os.path.isfile(label_path):
                    continue
                    
                processed_count += 1
                
                try:
                    # 파일 읽기
                    lines = self._get_label_data(label_path)
                    
                    for line in lines:
                        parts = line.strip().split()
                        if not parts:
                            continue
                            
                        try:
                            class_index = int(float(parts[0]))
                            
                            # 클래스 인덱스 유효성 확인
                            if 0 <= class_index < len(self.labelsdata):
                                # 중복 방지
                                if label_path not in self.labelsdata[class_index]:
                                    self.labelsdata[class_index].append(label_path)
                                    updated_count += 1
                        except (ValueError, IndexError):
                            continue
                except Exception as e:
                    print(f"라벨 파일 처리 중 오류 ({label_path}): {e}")
            
            # 클래스별 파일 개수 변화 기록
            after_counts = {}
            for class_idx, paths in enumerate(self.labelsdata):
                if paths:  # 비어있지 않은 경우만
                    after_counts[class_idx] = len(paths)
            
            # 변경 사항 로그
            changes = []
            for class_idx in set(list(before_counts.keys()) + list(after_counts.keys())):
                before = before_counts.get(class_idx, 0)
                after = after_counts.get(class_idx, 0)
                if before != after:
                    changes.append(f"클래스 {class_idx}: {before} → {after}")
            
            # 소요 시간 및 결과 로깅
            elapsed_time = time.time() - start_time
            
            if hasattr(self, 'logger'):
                self.logger.info(f"라벨 데이터 캐시 갱신 완료: {elapsed_time:.3f}초, {processed_count}개 처리, {updated_count}개 추가/갱신")
                if changes:
                    self.logger.info(f"클래스별 변경: {', '.join(changes)}")
            
            print(f"라벨 데이터 캐시 갱신 완료: {elapsed_time:.3f}초")
            if changes:
                print(f"클래스별 변경: {', '.join(changes)}")
            
        except Exception as e:
            print(f"라벨 데이터 캐시 갱신 중 오류: {e}")
            import traceback
            traceback.print_exc()
            
            if hasattr(self, 'logger'):
                self.logger.error(f"라벨 데이터 캐시 갱신 오류: {e}")
    # 변경 작업 완료 후 캐시 무효화 추가
    def invalidate_caches_for_label(self, label_path):
        """라벨 변경 후 관련 캐시를 무효화합니다."""
        # 라벨 캐시 무효화
        if hasattr(self, 'label_cache') and label_path in self.label_cache:
            del self.label_cache[label_path]
            # 접근 순서 목록에서도 제거
            if hasattr(self, 'label_cache_access_order') and label_path in self.label_cache_access_order:
                self.label_cache_access_order.remove(label_path)
        
        # 겹침 캐시 무효화
        if hasattr(self, 'overlap_cache'):
            keys_to_remove = []
            for cache_key in self.overlap_cache.keys():
                if isinstance(cache_key, tuple) and len(cache_key) > 0 and cache_key[0] == label_path:
                    keys_to_remove.append(cache_key)
            
            for key in keys_to_remove:
                del self.overlap_cache[key]
        
        # 인코딩 캐시 무효화
        if hasattr(self, 'file_encoding_cache') and label_path in self.file_encoding_cache:
            del self.file_encoding_cache[label_path]
        
        # 로깅
        print(f"캐시 무효화 완료: {os.path.basename(label_path)}")
    def setup_memory_monitoring(self):
        """정기적인 메모리 모니터링 설정"""
        # 초기 메모리 사용량 기록
        self.initial_memory_usage = self.get_memory_usage()
        self.memory_check_counter = 0
        self.memory_check_interval = 60  # 60초마다 체크
        
        # 첫 번째 메모리 체크 예약
        self.root.after(self.memory_check_interval * 1000, self.check_memory_usage)
        
        if hasattr(self, 'logger'):
            self.logger.info(f"초기 메모리 사용량: {self.initial_memory_usage:.2f}MB")

    def get_memory_usage(self):
        """현재 프로세스의 메모리 사용량을 MB 단위로 반환"""
        try:
            import psutil
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            return memory_info.rss / 1024 / 1024  # RSS를 MB 단위로 변환
        except ImportError:
            # psutil이 없으면 기본값 반환
            return 0

    def check_memory_usage(self):
        """정기적으로 메모리 사용량을 확인하고 필요시 정리"""
        try:
            current_memory = self.get_memory_usage()
            
            # 초기 사용량 대비 증가량 계산
            memory_increase = current_memory - self.initial_memory_usage
            memory_increase_percent = (memory_increase / self.initial_memory_usage) * 100 if self.initial_memory_usage > 0 else 0
            
            if hasattr(self, 'logger') and self.memory_check_counter % 10 == 0:
                # 10번마다 로깅 (너무 많은 로그 방지)
                self.logger.info(f"메모리 사용량: {current_memory:.2f}MB (초기 대비: {memory_increase_percent:.1f}% 증가)")
            
            # 메모리 사용량이 초기보다 50% 이상 증가했고, 1GB 이상인 경우 메모리 정리
            if memory_increase_percent > 50 and current_memory > 1024:
                if hasattr(self, 'logger'):
                    self.logger.warning(f"높은 메모리 사용량 감지: {current_memory:.2f}MB - 메모리 정리 수행")
                    
                # 메모리 정리 수행
                self.perform_memory_cleanup()
                
                # 정리 후 메모리 사용량 다시 체크
                after_cleanup = self.get_memory_usage()
                memory_reduction = current_memory - after_cleanup
                
                if hasattr(self, 'logger'):
                    self.logger.info(f"메모리 정리 완료: {memory_reduction:.2f}MB 감소 ({after_cleanup:.2f}MB)")
                self.memory_check_counter += 1
        
        # 다음 메모리 체크 예약
                self.root.after(self.memory_check_interval * 1000, self.check_memory_usage)
        
        except Exception as e:
            print(f"메모리 모니터링 오류: {e}")
            # 오류가 발생해도 다음 체크는 계속 예약
            self.root.after(self.memory_check_interval * 1000, self.check_memory_usage)

        

if __name__ == "__main__":
    root = tk.Tk()
    app = ImageViewer(root)
    root.mainloop()