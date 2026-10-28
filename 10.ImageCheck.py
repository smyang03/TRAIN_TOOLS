import tkinter as tk
from tkinter import TclError, filedialog, ttk, messagebox
from tkinter import simpledialog
from PIL import Image, ImageTk
import os
from datetime import datetime
import time
import random
import gc
import csv
import json

class ImageViewer:
    def __init__(self, root):
        self.root = root
        self.rootpath = ""
        self.filename = ""
        self.current_datetime = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.root.title("Image Viewer")
        root.attributes('-fullscreen', True)  # 진정한 전체 화면 (타이틀바 없음)
        # 체크박스 기능 추가
        self.auto_check_var = tk.IntVar(value=0)  # 체크 여부를 저장하는 변수
        self.preview_cache = {}
        # 단축키 추가 (1,2,3)
        self.root.bind('1', lambda event: self.save_selected_images("주간"))
        self.root.bind('2', lambda event: self.save_selected_images("야간"))
        self.root.bind('3', lambda event: self.save_selected_images("열화상"))
        self.user_filter_lists = {}

        # Pagination related variables
        self.page_size = 100  # 한 페이지에 표시되는 이미지 수를 500으로 증가
        self.current_page = 0
        self.total_pages = 0
        self.current_images = []  # Store current page's images
        
        self.preview_cache = {}  # 미리보기 캐시
        self.thumbnail_cache = {}  # 썸네일 캐시
        self.max_cache_size = 100  # 최대 캐시 크기

        self.last_clicked_label = None  # 마지막으로 클릭된 라벨 추적
        self.caps_locked = False  # Caps Lock 상태 추적


        # Data storage
        self.image_paths = []
        self.labels = []
        self.selected_image_paths = []
        self.checklist = []
        
        # 저장 처리된 이미지 기록
        self.processed_images = {}  # {이미지경로: 카테고리} 형태로 저장
        try:
            system_theme = self.root.tk.call('tk', 'windowingsystem')
            if system_theme == 'win32':
                # Windows 특정 조정
                self.SELECTED_BG = "#FF6666"
                self.SELECTED_THICKNESS = 5
        except Exception:
            pass  # 감지에 실패하면 기본값으로 돌아감
        self.setup_ui()
        self.setup_preview_features()  # 이 함수 호출 추가
    
    def setup_ui(self):
        """정리된 사용자 인터페이스 설정"""
        # 메뉴바 설정
        self.menu_bar = tk.Menu(self.root)
        self.root.config(menu=self.menu_bar)
        
        # 파일 메뉴
        file_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="파일", menu=file_menu)
        file_menu.add_command(label="데이터 로드", command=self.load_data)
        file_menu.add_separator()
        file_menu.add_command(label="세션 저장", command=self.save_session)
        file_menu.add_command(label="세션 로드", command=self.load_session)
        file_menu.add_separator()
        file_menu.add_command(label="종료", command=self.on_closing)
        
        # 도구 메뉴
        tools_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="도구", menu=tools_menu)
        tools_menu.add_command(label="통계 대시보드", command=self.show_stats_dashboard)
        tools_menu.add_command(label="미리보기 캐시 정리", command=self.clear_preview_cache)
        
        self.control_panel = tk.Frame(self.root, padx=5, pady=5)
        self.control_panel.pack(fill="x")
        
        # 1. 데이터 관리 그룹 (왼쪽)
        self.data_frame = tk.LabelFrame(self.control_panel, text="데이터 관리", padx=5, pady=5)
        self.data_frame.pack(side=tk.LEFT, padx=5, fill="y")
        
        # 데이터 로드 버튼
        self.load_button = tk.Button(self.data_frame, text="Load Data", width=10, command=self.load_data)
        self.load_button.pack(pady=3)
        
        # 자동 체크 기능
        self.auto_check_checkbutton = tk.Checkbutton(self.data_frame, 
                                            text="자동 체크", 
                                            variable=self.auto_check_var,
                                            command=self.update_display)
        self.auto_check_checkbutton.pack(pady=3)
        
        # 2. 이미지 분류 그룹
        self.classify_frame = tk.LabelFrame(self.control_panel, text="이미지 분류", padx=5, pady=5)
        self.classify_frame.pack(side=tk.LEFT, padx=5, fill="y")
        
        # 분류 버튼
        button_frame = tk.Frame(self.classify_frame)
        button_frame.pack(pady=3)
        
        self.save_day_button = tk.Button(button_frame, text="주간 (1)", width=10, 
                                        command=lambda: self.save_selected_images("주간"),
                                        bg="#ddddff")
        self.save_day_button.pack(side=tk.LEFT, padx=2)
        
        self.save_night_button = tk.Button(button_frame, text="야간 (2)", width=10, 
                                        command=lambda: self.save_selected_images("야간"),
                                        bg="#ffddff")
        self.save_night_button.pack(side=tk.LEFT, padx=2)
        
        self.save_thermal_button = tk.Button(button_frame, text="열화상 (3)", width=10, 
                                        command=lambda: self.save_selected_images("열화상"),
                                        bg="#ffeecc")
        self.save_thermal_button.pack(side=tk.LEFT, padx=2)
        
        # 처리 완료 초기화 버튼
        self.reset_processed_button = tk.Button(self.classify_frame, text="처리완료 초기화", 
                                            width=15, command=self.reset_processed_images)
        self.reset_processed_button.pack(pady=3)
        
        # 3. 통합된 선택 및 필터 옵션 그룹
        selection_filter_frame = tk.Frame(self.control_panel)
        selection_filter_frame.pack(side=tk.LEFT, padx=5, fill="y")
        
        # 3.1 선택 옵션 하위 그룹
        self.selection_frame = tk.LabelFrame(selection_filter_frame, text="선택 옵션", padx=5, pady=5)
        self.selection_frame.pack(fill="x", pady=(0, 5))
        
        # 선택 버튼 가로 배치
        self.select_buttons_frame = tk.Frame(self.selection_frame)
        self.select_buttons_frame.pack(fill="x", pady=3)
        
        self.select_all_button = tk.Button(self.select_buttons_frame, text="전체 선택", 
                                        width=10, command=self.select_all_images)
        self.select_all_button.pack(side=tk.LEFT, padx=2)
        
        self.deselect_all_button = tk.Button(self.select_buttons_frame, text="전체 해제", 
                                        width=10, command=self.deselect_all_images)
        self.deselect_all_button.pack(side=tk.LEFT, padx=2)
        
        # 3.2 필터 옵션 하위 그룹
        self.filter_frame = tk.LabelFrame(selection_filter_frame, text="필터", padx=5, pady=5)
        self.filter_frame.pack(fill="x")
        
        # 미처리 이미지만 표시 체크박스와 버튼을 함께 배치
        filter_inner_frame = tk.Frame(self.filter_frame)
        filter_inner_frame.pack(fill="x")
        
        self.show_unprocessed_only = tk.IntVar(value=0)
        self.unprocessed_check = tk.Checkbutton(
            filter_inner_frame, 
            text="미처리 이미지만 표시", 
            variable=self.show_unprocessed_only
        )
        self.unprocessed_check.pack(side=tk.LEFT, padx=5)
        
        # 필터 적용 및 초기화 버튼
        filter_buttons_frame = tk.Frame(self.filter_frame)
        filter_buttons_frame.pack(fill="x", pady=3)
        
        tk.Button(
            filter_buttons_frame, 
            text="필터 적용", 
            command=self.apply_simplified_filters,
            width=10
        ).pack(side=tk.LEFT, padx=2)
        
        tk.Button(
            filter_buttons_frame, 
            text="필터 초기화", 
            command=self.reset_simplified_filters,
            width=10
        ).pack(side=tk.LEFT, padx=2)
        
        # 4. 페이지 네비게이션 그룹 (오른쪽)
        self.nav_frame = tk.Frame(self.control_panel)
        self.nav_frame.pack(side=tk.RIGHT, padx=5)
        
        # 페이지 컨트롤
        self.pagination_frame = tk.Frame(self.nav_frame)
        self.pagination_frame.pack(pady=3)
        
        self.prev_button = tk.Button(self.pagination_frame, text="Previous", width=8, command=self.prev_page)
        self.prev_button.pack(side=tk.LEFT)
        
        self.page_label = tk.Label(self.pagination_frame, text="Page 0/0", width=10)
        self.page_label.pack(side=tk.LEFT, padx=5)
        
        self.next_button = tk.Button(self.pagination_frame, text="Next", width=8, command=self.next_page)
        self.next_button.pack(side=tk.LEFT)
        
        # 선택 및 처리 정보
        self.info_frame = tk.Frame(self.nav_frame)
        self.info_frame.pack(pady=3)
        
        self.processed_info_label = tk.Label(self.info_frame, text="처리됨: 0", width=10)
        self.processed_info_label.pack(side=tk.LEFT, padx=2)
        
        self.selection_info_label = tk.Label(self.info_frame, text="선택됨: 0", width=10)
        self.selection_info_label.pack(side=tk.LEFT, padx=2)
        
        # 필터 상태 표시를 info_frame에 추가
        self.filter_status_label = tk.Label(self.info_frame, text="")
        self.filter_status_label.pack(side=tk.LEFT, padx=10)
                
        # 메인 디스플레이 영역
        self.canvas_frame = tk.Frame(self.root)
        self.canvas_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.canvas = tk.Canvas(self.canvas_frame, borderwidth=0, background="white")
        self.scrollbar = tk.Scrollbar(self.canvas_frame, orient="vertical", command=self.canvas.yview)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.frame = tk.Frame(self.canvas)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.frame, anchor="nw")
        
        # 상태바 추가
        self.status_bar = tk.Label(self.root, text="준비", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
            # 드래그 선택을 위한 변수 추가
        self.shift_pressed = False
        self.drag_start = None
        self.drag_rectangle = None
        # 이벤트 바인딩
        self.canvas.bind("<Configure>", self.on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self.on_mousewheel)

        self.root.bind("<KeyPress-Shift_L>", self.on_shift_press)
        self.root.bind("<KeyRelease-Shift_L>", self.on_shift_release)
        self.root.bind("<KeyPress-Shift_R>", self.on_shift_press)
        self.root.bind("<KeyRelease-Shift_R>", self.on_shift_release)

        self.root.bind("<KeyPress-Caps_Lock>", self.on_caps_lock_press)
        self.root.bind("<KeyRelease-Caps_Lock>", self.on_caps_lock_release)

            
        # 키보드 단축키 추가
        self.root.bind("<Left>", lambda event: self.prev_page())
        self.root.bind("<Right>", lambda event: self.next_page())
        self.root.bind("1", lambda event: self.save_selected_images("주간"))
        self.root.bind("2", lambda event: self.save_selected_images("야간"))
        self.root.bind("3", lambda event: self.save_selected_images("열화상"))
        self.root.bind("<Control-s>", lambda event: self.save_session())
        self.root.bind("<Control-o>", lambda event: self.load_session())



        
    def reset_processed_images(self):
        """처리 완료된 이미지 상태를 초기화"""
        if hasattr(self, 'processed_images') and self.processed_images:
            result = tk.messagebox.askyesno("확인", "모든 처리 완료 상태를 초기화하시겠습니까?")
            if result:
                self.processed_images.clear()
                self.update_display()
                self.update_processed_info()
    
    def initial_setup(self, file_path):
        """Initialize/reset all instance variables when loading new data"""
        # Reset paths and file info
        if os.path.isfile(file_path):
            self.rootpath = os.path.dirname(file_path)
            self.filename = os.path.basename(file_path)
        else:
            # 폴더인 경우
            self.rootpath = file_path
            self.filename = os.path.basename(file_path)
        self.current_datetime = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Reset data structures
        self.image_paths = []
        self.labels = []
        self.selected_image_paths = []
        
        # Reset selection state
        for widget in self.checklist:
            if widget.winfo_exists():
                widget.destroy()
        self.checklist = []
        
        # Reset pagination
        self.current_page = 0
        self.total_pages = 0
        
        # Clear display
        for widget in self.frame.winfo_children():
            widget.destroy()
        
        # Force garbage collection
        gc.collect()
    
    def setup_simplified_filter_controls(self):
        """간소화된 필터 컨트롤 설정"""
        # 필터 프레임 생성
        self.filter_frame = tk.LabelFrame(self.root, text="필터", padx=5, pady=5)
        self.filter_frame.pack(fill="x", padx=10, pady=5)
        
        # 필터 컨트롤 내부 프레임
        filter_inner_frame = tk.Frame(self.filter_frame)
        filter_inner_frame.pack(fill="x")
        
        # 미처리 이미지만 표시 체크박스
        self.show_unprocessed_only = tk.IntVar(value=0)
        self.unprocessed_check = tk.Checkbutton(
            filter_inner_frame, 
            text="미처리 이미지만 표시", 
            variable=self.show_unprocessed_only
        )
        self.unprocessed_check.pack(side=tk.LEFT, padx=10)
        
        # 필터 적용 버튼
        tk.Button(
            filter_inner_frame, 
            text="필터 적용", 
            command=self.apply_simplified_filters,
            width=10
        ).pack(side=tk.LEFT, padx=10)
        
        # 필터 초기화 버튼
        tk.Button(
            filter_inner_frame, 
            text="필터 초기화", 
            command=self.reset_simplified_filters,
            width=10
        ).pack(side=tk.LEFT, padx=10)
        
        # 필터 상태 표시
        self.filter_status_label = tk.Label(filter_inner_frame, text="")
        self.filter_status_label.pack(side=tk.RIGHT, padx=10)
    def apply_simplified_filters(self):
        """간소화된 필터 적용"""
        # 원본 이미지 경로 복원
        if hasattr(self, '_original_image_paths'):
            self.image_paths = self._original_image_paths.copy()
        else:
            self._original_image_paths = self.image_paths.copy()
        
        filtered_paths = self.image_paths.copy()
        filter_applied = False
        
        # 미처리 이미지만 표시
        if self.show_unprocessed_only.get() == 1:
            if hasattr(self, 'processed_images') and self.processed_images:
                filtered_paths = [path for path in filtered_paths if path not in self.processed_images]
                filter_applied = True
        
        # 필터링 결과 적용
        self.image_paths = filtered_paths
        
        # 페이지네이션 재계산
        if self.image_paths:  # 필터링 결과가 있는 경우에만
            self.total_pages = (len(self.image_paths) + self.page_size - 1) // self.page_size
        else:
            self.total_pages = 1  # 표시할 이미지가 없어도 최소 1페이지는 유지
        
        self.current_page = 0  # 첫 페이지로 이동
        
        # 상태 업데이트
        if filter_applied:
            self.filter_status_label.config(text=f"표시: {len(filtered_paths)}/{len(self._original_image_paths)} 이미지")
        else:
            self.filter_status_label.config(text="표시: 전체 이미지")
        
        # 화면 업데이트
        self.update_pagination_controls()
        self.update_display()
        
        # 상태바 업데이트
        self.status_bar.config(text=f"필터 적용됨: {len(filtered_paths)}개 이미지 표시 중")

    def reset_simplified_filters(self):
        """간소화된 필터 초기화"""
        # 필터 설정 초기화
        self.show_unprocessed_only.set(0)
        
        # 원본 이미지 경로 복원
        if hasattr(self, '_original_image_paths'):
            self.image_paths = self._original_image_paths.copy()
        
        # 페이지네이션 재계산
        self.total_pages = (len(self.image_paths) + self.page_size - 1) // self.page_size
        self.current_page = 0  # 첫 페이지로 이동
        
        # 상태 업데이트
        self.filter_status_label.config(text="표시: 전체 이미지")
        
        # 화면 업데이트
        self.update_pagination_controls()
        self.update_display()
        
        # 상태바 업데이트
        self.status_bar.config(text="필터 초기화됨")
        
    def on_canvas_configure(self, event):
        # 지연된 업데이트로 성능 개선
        if hasattr(self, '_canvas_configure_timer'):
            self.root.after_cancel(self._canvas_configure_timer)
        
        self._canvas_configure_timer = self.root.after(100, self.update_scroll_region)
    def update_scroll_region(self):
        """지연된 스크롤 영역 업데이트"""
        try:
            bbox = self.canvas.bbox("all")
            if bbox:
                # 하단 여백 추가
                x1, y1, x2, y2 = bbox
                y2 += 20
                self.canvas.configure(scrollregion=(x1, y1, x2, y2))
                
            # 열 수 재계산
            current_width = self.canvas.winfo_width()
            if hasattr(self, 'last_width') and abs(current_width - self.last_width) > 50:
                # 큰 너비 변화가 있으면 디스플레이 갱신
                self.last_width = current_width
                self.update_display()
            else:
                self.last_width = current_width
        except Exception as e:
            print(f"Error updating scroll region: {e}")

    def on_mousewheel(self, event):
        """Handle mouse wheel scrolling"""
        self.canvas.yview_scroll(-1*(event.delta//120), "units")
    
    def load_data(self):
        """Load image data from text file or directly from folder"""
        # 사용자에게 로드 방식 선택 옵션 제공
        option_window = tk.Toplevel(self.root)
        option_window.title("로드 방식 선택")
        option_window.geometry("300x150")
        option_window.transient(self.root)
        option_window.grab_set()
        
        # 로드 방식 선택 라벨
        tk.Label(option_window, text="이미지 데이터 로드 방식을 선택하세요:", 
                font=("Arial", 10)).pack(pady=(15, 10))
        
        # 파일에서 로드 함수
        def load_from_file():
            option_window.destroy()
            file_path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
            if not file_path:
                return
            self._process_file_load(file_path)
        
        # 폴더에서 직접 로드 함수
        def load_from_folder():
            option_window.destroy()
            folder_path = filedialog.askdirectory()
            if not folder_path:
                return
            self._process_folder_load(folder_path)
        
        # 버튼 생성
        tk.Button(option_window, text="텍스트 파일에서 로드", 
                command=load_from_file, width=20).pack(pady=5)
        tk.Button(option_window, text="이미지 폴더에서 직접 로드", 
                command=load_from_folder, width=20).pack(pady=5)
    
    def _process_file_load(self, file_path):
        """텍스트 파일에서 이미지 경로 로드"""
        if not file_path:
            return
            
        self.initial_setup(file_path)
        
        try:
            # Create progress window
            progress_window = tk.Toplevel(self.root)
            progress_window.title("Loading Data")
            
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
            file_label = tk.Label(progress_window, text="Reading files...", anchor='w')
            file_label.pack(padx=20, pady=(10,0), fill='x')
            
            progress_bar = ttk.Progressbar(progress_window, length=360, mode='determinate')
            progress_bar.pack(padx=20, pady=(5,0))
            
            status_label = tk.Label(progress_window, text="")
            status_label.pack(padx=20, pady=(5,0), fill='x')
            
            detail_label = tk.Label(progress_window, text="", anchor='w')
            detail_label.pack(padx=20, pady=(5,10), fill='x')
            
            progress_window.update()
            
            # First phase: Read file and count lines - Try multiple encodings
            encodings_to_try = ['utf-8', 'cp949', 'euc-kr', 'latin-1']
            lines = None
            
            for encoding in encodings_to_try:
                try:
                    file_label.config(text=f"Reading files with {encoding} encoding...")
                    progress_window.update()
                    
                    with open(file_path, encoding=encoding) as f:
                        lines = [line.strip() for line in f.readlines() if line.strip()]
                    
                    print(f"Successfully loaded with {encoding} encoding")
                    break  # If successful, exit the loop
                except UnicodeDecodeError:
                    print(f"Failed to read with {encoding} encoding, trying next...")
                    continue
            
            if lines is None:
                raise ValueError(f"Could not decode file {file_path} with any of the attempted encodings")
            
            total_lines = len(lines)
            progress_bar['maximum'] = total_lines
            
            # Second phase: Process files
            for i, line in enumerate(lines, 1):
                # Update progress
                modified_line = line.replace('miss_detectionJPEGImages', 'miss_detection/JPEGImages')
                modified_line = line.replace('false_detectionJPEGImages', 'false_detection/JPEGImages')
                self.image_paths.append(modified_line)
                progress = (i / total_lines) * 100
                file_label.config(text="Processing files...")
                status_label.config(text=f"Progress: {progress:.1f}% ({i}/{total_lines} files)")
                detail_label.config(text=f"Current file: {os.path.basename(line)}")
                progress_bar['value'] = i

                
                # Update UI every 10 files or on last file
                if i % 10 == 0 or i == total_lines:
                    progress_window.update()
            
            # Calculate total pages
            self.total_pages = (len(self.image_paths) + self.page_size - 1) // self.page_size
            self.update_pagination_controls()
            
            # Show completion
            file_label.config(text="Loading complete!")
            status_label.config(text=f"Loaded {total_lines} files successfully")
            detail_label.config(text=f"Total pages: {self.total_pages}")
            progress_bar['value'] = progress_bar['maximum']
            progress_window.update()
            
            # Update display with loaded images
            self.update_display()
            
            # Close progress window after a delay
            self.root.after(1500, progress_window.destroy)
            
            print(f"Data loaded: {len(self.image_paths)} images, {self.total_pages} pages")
            
        except Exception as e:
            print(f"Error loading data: {e}")
            if 'progress_window' in locals():
                progress_window.destroy()
            import traceback
            traceback.print_exc()
    
    def _process_folder_load(self, folder_path):
        """폴더에서 직접 이미지 파일을 찾아 로드"""
        if not folder_path:
            return
            
        self.initial_setup(folder_path)
        
        try:
            # 진행 창 생성
            progress_window = tk.Toplevel(self.root)
            progress_window.title("폴더에서 이미지 로드 중")
            window_width = 400
            window_height = 150
            position_right = int(self.root.winfo_x() + (self.root.winfo_width() - window_width) / 2)
            position_down = int(self.root.winfo_y() + (self.root.winfo_height() - window_height) / 2)
            progress_window.geometry(f"{window_width}x{window_height}+{position_right}+{position_down}")
            progress_window.transient(self.root)
            progress_window.grab_set()
            
            # 진행 상황 표시
            file_label = tk.Label(progress_window, text="이미지 폴더 스캔 중...", anchor='w')
            file_label.pack(padx=20, pady=(10,0), fill='x')
            
            progress_bar = ttk.Progressbar(progress_window, length=360, mode='indeterminate')
            progress_bar.pack(padx=20, pady=(5,0))
            progress_bar.start(10)
            
            status_label = tk.Label(progress_window, text="")
            status_label.pack(padx=20, pady=(5,0), fill='x')
            
            detail_label = tk.Label(progress_window, text="", anchor='w')
            detail_label.pack(padx=20, pady=(5,10), fill='x')
            
            progress_window.update()
            
            # 폴더 내 모든 jpg 파일 찾기 (하위 폴더 포함)
            found_images = []
            status_label.config(text="이미지 파일 검색 중...")
            progress_window.update()
            
            for root, dirs, files in os.walk(folder_path):
                for file in files:
                    if file.lower().endswith(('.jpg', '.jpeg')):
                        img_path = os.path.join(root, file)
                        modified_img_path = img_path.replace('miss_detectionJPEGImages', 'miss_detection/JPEGImages')
                        modified_img_path = img_path.replace('false_detectionJPEGImages', 'false_detection/JPEGImages')
                        found_images.append(modified_img_path)
                        
                        # 진행 상황 업데이트 (매 10개 파일마다)
                        if len(found_images) % 10 == 0:
                            detail_label.config(text=f"발견된 이미지: {len(found_images)}개")
                            progress_window.update()
            
            progress_bar.stop()
            progress_bar['mode'] = 'determinate'
            progress_bar['maximum'] = len(found_images)
            
            # 발견된 이미지가 없는 경우
            if not found_images:
                status_label.config(text="발견된 이미지가 없습니다!")
                progress_window.update()
                self.root.after(1500, progress_window.destroy)
                return
                
            # 이미지 및 해당 라벨 파일 처리
            status_label.config(text=f"발견된 {len(found_images)}개 이미지 처리 중...")
            progress_window.update()
            
            for i, img_path in enumerate(found_images):
                # 이미지 경로 저장
                self.image_paths.append(img_path)
                
                # 라벨 파일 경로 생성 (.jpg -> .txt)
                label_path = img_path.replace('.jpg', '.txt').replace('.jpeg', '.txt')
                
                # JPEGImages 폴더를 labels 폴더로 대체 (일반적인 객체 감지 데이터셋 구조)
                if "JPEGImages" in label_path:
                    label_path = label_path.replace("JPEGImages", "labels")
                    
                # 라벨 파일이 없으면 동일 위치에 있는지 확인
                if not os.path.isfile(label_path):
                    label_dir = os.path.dirname(img_path)
                    label_name = os.path.basename(img_path).replace('.jpg', '.txt').replace('.jpeg', '.txt')
                    alt_label_path = os.path.join(label_dir, label_name)
                    
                    if os.path.isfile(alt_label_path):
                        label_path = alt_label_path
                
                self.labels.append(label_path)
                
                # 진행 상황 업데이트
                progress_bar['value'] = i + 1
                if i % 10 == 0 or i == len(found_images) - 1:
                    detail_label.config(text=f"처리 중: {i+1}/{len(found_images)} - {os.path.basename(img_path)}")
                    progress_window.update()
            
            # 페이지네이션 및 클래스 정보 업데이트
            self.total_pages = (len(self.image_paths) + self.page_size - 1) // self.page_size
            self.update_pagination_controls()
            
            # 완료 메시지
            status_label.config(text="이미지 로드 완료!")
            detail_label.config(text=f"{len(found_images)}개 이미지, {self.total_pages}개 페이지 로드됨")
            progress_bar['value'] = progress_bar['maximum']
            progress_window.update()
            
            # 디스플레이 업데이트
            self.update_display()
            
            # 진행 창 닫기
            self.root.after(1500, progress_window.destroy)
            
        except Exception as e:
            print(f"Error loading from folder: {e}")
            if 'progress_window' in locals():
                progress_window.destroy()
            import traceback
            traceback.print_exc()
    
    def update_class_dropdown(self):
        """이 메소드는 더 이상 사용하지 않지만 호환성을 위해 유지"""
        pass
    
    def update_display(self):
        """현재 페이지의 이미지 표시 업데이트 - 성능 최적화"""
        # 상태바 업데이트
        self.status_bar.config(text="이미지 로딩 중...")
        self.root.update_idletasks()
        
        # Clear existing images and free memory
        for widget in self.frame.winfo_children():
            widget.destroy()
        gc.collect()  # Force garbage collection
        
        # Get current page's worth of images
        start_idx = self.current_page * self.page_size
        end_idx = min(start_idx + self.page_size, len(self.image_paths))
        current_images = self.image_paths[start_idx:end_idx]
        
        self.current_images = current_images
        
        if not current_images:
            empty_label = tk.Label(self.frame, text="No images to display", font=("Arial", 14))
            empty_label.pack(pady=50)
            self.status_bar.config(text="준비")
            return
        
        # Update pagination display
        self.update_pagination_controls()
        
        # Calculate grid dimensions
        thumbnail_size = 150
        padding = 10
        canvas_width = self.canvas.winfo_width()
        if canvas_width <= 1:
            canvas_width = self.root.winfo_width() - 30
        
        columns = max(1, canvas_width // (thumbnail_size + padding))
        
        # 자동 선택 모드 확인
        auto_check = self.auto_check_var.get() == 1
        
        # 배치 처리를 위한 설정
        batch_size = 20  # 한 번에 처리할 이미지 수
        loaded_count = 0
        total_to_load = len(current_images)
        
        # 그리드 구성 최적화
        self.frame.grid_columnconfigure(tuple(range(columns)), weight=0)
        total_rows = (len(current_images) + columns - 1) // columns
        self.frame.grid_rowconfigure(tuple(range(total_rows * 2)), weight=0)
        
        # 배치 로딩 함수
        def load_batch(start_idx, remaining):
            nonlocal loaded_count
            
            end_idx = min(start_idx + batch_size, len(current_images))
            
            # 현재 배치의 이미지 로드
            for i in range(start_idx, end_idx):
                img_path = current_images[i]
                row = i // columns
                col = i % columns
                
                if not os.path.isfile(img_path):
                    print(f"File not found: {img_path}")
                    loaded_count += 1
                    continue
                
                try:
                    if img_path in self.thumbnail_cache:
                        photo = self.thumbnail_cache[img_path]
                    else:
                    # 이미지 로드 최적화
                        img = Image.open(img_path)
                        img.thumbnail((thumbnail_size, thumbnail_size), Image.LANCZOS)
                        photo = ImageTk.PhotoImage(img)
                        
                        # 위젯 생성 및 구성
                        label = tk.Label(self.frame, image=photo, bg="white")
                        label.image = photo
                        label.img_path = img_path
                        
                        # 현재 이미지 상태 확인
                        processed_category = None
                        if img_path in self.processed_images:
                            processed_category = self.processed_images[img_path]
                        
                        # 스타일 적용
                        label.config(relief="solid", bd=1, highlightthickness=2)
                        
                        if processed_category:
                            # 저장 처리된 이미지는 특별한 색상으로 표시
                            if processed_category == "주간":
                                label.config(highlightbackground="blue", bg="#ddddff")
                            elif processed_category == "야간":
                                label.config(highlightbackground="purple", bg="#ffddff")
                            elif processed_category == "열화상":
                                label.config(highlightbackground="orange", bg="#ffeecc")
                        elif auto_check or img_path in self.selected_image_paths:
                            label.config(highlightbackground="#FF0000", highlightthickness=5, bg="#ffdddd")
                            
                            # 체크마크 추가
                            corner_label = tk.Label(label, text="✓", font=("Arial", 12, "bold"), fg="red", bg="#ffdddd")
                            corner_label.place(x=5, y=5)
                            
                            if img_path not in self.selected_image_paths:
                                self.selected_image_paths.append(img_path)
                            if label not in self.checklist:
                                self.checklist.append(label)
                        else:
                            label.config(highlightbackground="white", bg="white")
                        
                        # 인덱스 표시
                        abs_idx = self.current_page * self.page_size + i
                        idx_text = f"{abs_idx+1}"
                        if processed_category:
                            idx_text += f" ({processed_category})"
                        
                        idx_label = tk.Label(self.frame, text=idx_text, bg="#ffffff", font=("Arial", 8))
                        
                        # 그리드 배치
                        idx_label.grid(row=row*2, column=col, padx=5, pady=(5,0), sticky="s")
                        label.grid(row=row*2+1, column=col, padx=5, pady=(0,5), sticky="n")
                        
                        # 이벤트 바인딩
                        label.bind("<Button-1>", lambda event, label=label, img_path=img_path: 
                                self.on_image_click(label, img_path))
                        label.bind("<Double-Button-1>", lambda event, img_path=img_path: 
                                self.show_full_image(img_path))
                        
                        self.setup_image_hover_events(label, img_path)
                        self.setup_drag_select_events(label, img_path)
                        
                        loaded_count += 1
                    
                except Exception as e:
                    print(f"Error processing image {img_path}: {e}")
                    loaded_count += 1
                    continue
            
            # 진행 상황 업데이트
            self.status_bar.config(text=f"이미지 로딩 중... ({loaded_count}/{total_to_load})")
            self.root.update_idletasks()
            
            # 다음 배치 처리
            if end_idx < len(current_images):
                self.root.after(1, lambda: load_batch(end_idx, total_to_load - loaded_count))
            else:
                # 모든 이미지 로드 완료
                self.frame.update_idletasks()
                self.canvas.configure(scrollregion=self.canvas.bbox("all"))
                
                # 선택 정보 업데이트
                self.update_selection_info()
                
                # 세션 수정됨 표시
                self.session_modified = True
                
                # 상태바 업데이트
                total_images = len(self.image_paths)
                processed_count = len(self.processed_images) if hasattr(self, 'processed_images') else 0
                self.status_bar.config(text=f"준비 | 총 {total_images}개 이미지, {processed_count}개 처리됨 | 페이지 {self.current_page + 1}/{self.total_pages}")
        
        # 배치 처리 시작
        load_batch(0, total_to_load)
    def on_image_click(self, label, img_path):
        try:
            # Caps Lock이 눌러진 상태에서의 다중 선택 로직
            if self.caps_locked:
                # 현재 페이지의 모든 라벨 찾기
                page_labels = [widget for widget in self.frame.winfo_children() 
                            if isinstance(widget, tk.Label) and hasattr(widget, 'img_path')]
                
                # 현재 이미지의 인덱스 찾기
                current_index = page_labels.index(label)
                
                # 첫 선택 시 현재 라벨을 시작점으로 설정
                if not hasattr(self, 'multi_select_start'):
                    self.multi_select_start = current_index
                
                # 시작점과 현재 클릭한 지점 사이의 범위 선택
                start, end = sorted([self.multi_select_start, current_index])
                
                # 이전 선택 해제
                for l in page_labels:
                    if l in self.checklist:
                        l.config(bd=2, highlightbackground="white", highlightthickness=2)
                        l.config(bg="white")
                        if l.img_path in self.selected_image_paths:
                            self.selected_image_paths.remove(l.img_path)
                        if l in self.checklist:
                            self.checklist.remove(l)
                        for child in l.winfo_children():
                            if hasattr(child, 'selection_indicator'):
                                child.destroy()
                
                # 새 범위 선택
                for l in page_labels[start:end+1]:
                    img_path = l.img_path
                    
                    # 이미 처리된 이미지는 건너뛰기
                    if hasattr(self, 'processed_images') and img_path in self.processed_images:
                        continue
                    
                    # 선택 로직
                    l.config(bd=2, highlightbackground="red", highlightthickness=4)
                    l.config(bg="#ffdddd")
                    
                    if img_path not in self.selected_image_paths:
                        self.selected_image_paths.append(img_path)
                    
                    if l not in self.checklist:
                        self.checklist.append(l)
                        indicator = tk.Label(l, text="✓", font=("Arial", 12, "bold"), 
                                fg="red", bg="#ffdddd")
                        indicator.selection_indicator = True
                        indicator.place(x=5, y=5)
                
                # 선택 정보 업데이트
                self.update_selection_info()
            
            else:
                # Caps Lock이 눌리지 않은 경우의 일반 클릭 로직
                if label in self.checklist:
                    # 선택 해제 시
                    label.config(bd=2, highlightbackground="white", highlightthickness=2)
                    label.config(bg="white")
                    if img_path in self.selected_image_paths:
                        self.selected_image_paths.remove(img_path)
                    if label in self.checklist:
                        self.checklist.remove(label)
                    for child in label.winfo_children():
                        if hasattr(child, 'selection_indicator'):
                            child.destroy()
                else:
                    # 선택 시
                    label.config(bd=2, highlightbackground="red", highlightthickness=4)
                    label.config(bg="#ffdddd")
                    self.selected_image_paths.append(img_path)
                    if label not in self.checklist:
                        self.checklist.append(label)
                        indicator = tk.Label(label, text="✓", font=("Arial", 12, "bold"), 
                                fg="red", bg="#ffdddd")
                        indicator.selection_indicator = True
                        indicator.place(x=5, y=5)
                
                # 선택 상태 초기화
                if hasattr(self, 'multi_select_start'):
                    delattr(self, 'multi_select_start')
            
            # 선택 정보 업데이트
            self.update_selection_info()
            
        except TclError as e:
            print(f"Error handling image click: {e}")
        
    def show_full_image(self, img_path):
        """Show full image in a new window without cropping"""
        try:
            # Create new window
            detail_window = tk.Toplevel(self.root)
            detail_window.title("Full Image View")
            
            # Center window on screen
            window_width = 800
            window_height = 600
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            x = (screen_width - window_width) // 2
            y = (screen_height - window_height) // 2
            detail_window.geometry(f"{window_width}x{window_height}+{x}+{y}")
            
            # Create canvas for scrollable image
            canvas = tk.Canvas(detail_window)
            scrollbar_y = tk.Scrollbar(detail_window, orient="vertical", command=canvas.yview)
            scrollbar_x = tk.Scrollbar(detail_window, orient="horizontal", command=canvas.xview)
            
            # Configure canvas
            canvas.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)
            
            # Grid layout
            canvas.grid(row=0, column=0, sticky="nsew")
            scrollbar_y.grid(row=0, column=1, sticky="ns")
            scrollbar_x.grid(row=1, column=0, sticky="ew")
            
            # Configure grid weights
            detail_window.grid_rowconfigure(0, weight=1)
            detail_window.grid_columnconfigure(0, weight=1)
            
            # Create frame inside canvas
            frame = tk.Frame(canvas)
            canvas.create_window((0, 0), window=frame, anchor="nw")
            
            # 처리 상태 정보 표시
            if hasattr(self, 'processed_images') and img_path in self.processed_images:
                category = self.processed_images[img_path]
                info_label = tk.Label(frame, text=f"이 이미지는 '{category}' 카테고리로 처리되었습니다.", 
                                font=("Arial", 10, "bold"), fg="blue", bg="#ddddff", pady=5)
                info_label.pack(fill="x", padx=5, pady=5)
            
            # Load and display image
            with Image.open(img_path) as img:
                photo = ImageTk.PhotoImage(img)
                
                # 상단에 이미지 파일명 표시
                filename = os.path.basename(img_path)
                name_label = tk.Label(frame, text=f"파일명: {filename}", font=("Arial", 10))
                name_label.pack(pady=5)
                
                # 이미지 크기 정보
                size_label = tk.Label(frame, text=f"크기: {img.width} x {img.height}", font=("Arial", 9))
                size_label.pack(pady=2)
                
                # 이미지 표시
                img_label = tk.Label(frame, image=photo)
                img_label.image = photo  # Keep a reference
                img_label.pack(padx=10, pady=10)
            
            # Update canvas scroll region
            frame.update_idletasks()
            canvas.configure(scrollregion=canvas.bbox("all"))
            
            # 단축키 추가
            detail_window.bind('1', lambda event: self.detail_window_save(detail_window, img_path, "주간"))
            detail_window.bind('2', lambda event: self.detail_window_save(detail_window, img_path, "야간"))
            detail_window.bind('3', lambda event: self.detail_window_save(detail_window, img_path, "열화상"))
            
            # 하단 버튼 프레임
            button_frame = tk.Frame(detail_window)
            button_frame.grid(row=2, column=0, columnspan=2, pady=10)
            
            # 저장 버튼 추가
            tk.Button(button_frame, text="주간 (1)", width=10, bg="#ddddff",
                    command=lambda: self.detail_window_save(detail_window, img_path, "주간")).pack(side=tk.LEFT, padx=5)
            tk.Button(button_frame, text="야간 (2)", width=10, bg="#ffddff",
                    command=lambda: self.detail_window_save(detail_window, img_path, "야간")).pack(side=tk.LEFT, padx=5)
            tk.Button(button_frame, text="열화상 (3)", width=10, bg="#ffeecc",
                    command=lambda: self.detail_window_save(detail_window, img_path, "열화상")).pack(side=tk.LEFT, padx=5)
            tk.Button(button_frame, text="닫기", width=15,height=2,font=('맑은 고딕', 10),relief=tk.RAISED,borderwidth=1,command=detail_window.destroy).pack(side=tk.LEFT, padx=10, pady=5)
            
            # Add mousewheel scrolling
            def on_mousewheel(event):
                canvas.yview_scroll(-1 * (event.delta // 120), "units")
            canvas.bind_all("<MouseWheel>", on_mousewheel)
            
            # Clean up on window close
            def on_detail_window_closing():
                canvas.unbind_all("<MouseWheel>")
                detail_window.destroy()
            detail_window.protocol("WM_DELETE_WINDOW", on_detail_window_closing)
        
        except Exception as e:
            print(f"Error showing full image: {e}")
            if 'detail_window' in locals():
                detail_window.destroy()
    def on_closing(self):
        """프로그램 종료 시 처리"""
        if hasattr(self, 'session_modified') and self.session_modified:
            result = tk.messagebox.askyesnocancel(
                "저장 확인", 
                "변경된 작업 세션이 있습니다. 저장하시겠습니까?"
            )
            
            if result is None:  # 취소
                return
            elif result:  # 예
                self.save_session()
        
        # 미리보기 창 닫기
        if hasattr(self, 'preview_window') and self.preview_window.winfo_exists():
            self.preview_window.destroy()
        
        # 통계 창 닫기
        if hasattr(self, 'stats_window') and self.stats_window.winfo_exists():
            self.stats_window.destroy()
        
        # 프로그램 종료
        self.root.destroy()

    def save_selected_images(self, category):
        """Save selected image paths to a category-specific file and mark them as processed"""
        
        if not self.selected_image_paths:
            print(f"No images selected to save for category: {category}")
            tk.messagebox.showinfo("알림", f"{category} 카테고리에 저장할 이미지가 선택되지 않았습니다.")
            return
            
        try:
            # Create progress window
            progress_window = tk.Toplevel(self.root)
            progress_window.title(f"Saving {category} Images")
            
            # Center the progress window
            window_width = 400
            window_height = 250  # 로그 정보를 보기 위해 높이 증가
            position_right = int(self.root.winfo_x() + (self.root.winfo_width() - window_width) / 2)
            position_down = int(self.root.winfo_y() + (self.root.winfo_height() - window_height) / 2)
            progress_window.geometry(f"{window_width}x{window_height}+{position_right}+{position_down}")
            
            # Make the window stay on top and modal
            progress_window.transient(self.root)
            progress_window.grab_set()
            
            # Create progress indicators
            status_label = tk.Label(progress_window, text=f"Saving selected images as {category}...", anchor='w')
            status_label.pack(padx=20, pady=(10,0), fill='x')
            
            progress_bar = ttk.Progressbar(progress_window, length=360, mode='determinate')
            progress_bar.pack(padx=20, pady=(5,0))
            
            detail_label = tk.Label(progress_window, text="", anchor='w')
            detail_label.pack(padx=20, pady=(5,10), fill='x')
            
            # 로그 정보를 표시할 텍스트 위젯 추가
            log_text = tk.Text(progress_window, height=5, width=45)
            log_text.pack(padx=20, pady=5)
            
            progress_window.update()
            
            # 로그 함수 정의
            def log_info(message):
                log_text.insert(tk.END, message + "\n")
                log_text.see(tk.END)
                progress_window.update()
            
            # 카테고리별 파일 경로
            category_files = {}
            for cat in ["주간", "야간", "열화상"]:
                file_path = os.path.join(self.rootpath, f"{self.filename}_{cat}_{self.current_datetime}.txt")
                category_files[cat] = file_path
                log_info(f"{cat} 파일 경로: {file_path}")
            
            # 선택된 이미지 정보 로그
            log_info(f"선택된 이미지 수: {len(self.selected_image_paths)}")
            
            # 1. 카테고리별 현재 내용 로드
            category_contents = {}
            for cat, file_path in category_files.items():
                if os.path.exists(file_path):
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            lines = [line.strip() for line in f.readlines()]
                            category_contents[cat] = set(lines)
                        log_info(f"{cat} 파일 현재 항목 수: {len(category_contents[cat])}")
                    except Exception as e:
                        log_info(f"{cat} 파일 읽기 오류: {e}")
                        category_contents[cat] = set()
                else:
                    log_info(f"{cat} 파일 없음, 새로 생성 예정")
                    category_contents[cat] = set()
            
            # 2. 선택된 이미지 처리
            unique_paths = list(set(self.selected_image_paths))
            total_paths = len(unique_paths)
            progress_bar['maximum'] = total_paths
            
            changed_from = {}  # 카테고리별 변경 이미지 수 추적

            def convert_path(img_path):
                img_path = img_path.replace('miss_detectionJPEGImages', 'miss_detection/JPEGImages')
                img_path = img_path.replace('false_detectionJPEGImages', 'false_detection/JPEGImages')
                return img_path
            
            converted_selected_paths = [convert_path(path) for path in self.selected_image_paths]

            unique_paths = list(set(converted_selected_paths))

            # 모든 선택된 이미지에 대해 처리
            for i, img_path in enumerate(unique_paths):
                # 현재 처리 중인 이미지 표시
                detail_label.config(text=f"처리 중: {os.path.basename(img_path)}")
                progress_bar['value'] = i + 1
                progress_window.update()
                
                # 이전 카테고리 확인
                prev_category = None
                if img_path in self.processed_images:
                    prev_category = self.processed_images[img_path]
                    log_info(f"이미지 '{os.path.basename(img_path)}' - 이전 카테고리: {prev_category}")
                    
                    # 같은 카테고리면 건너뛰기
                    if prev_category == category:
                        log_info(f"  - 동일 카테고리, 건너뜀")
                        continue
                    
                    # 이전 카테고리에서 제거
                    if prev_category in category_contents:
                        if img_path in category_contents[prev_category]:
                            category_contents[prev_category].remove(img_path)
                            log_info(f"  - {prev_category} 카테고리에서 제거됨")
                            
                            # 변경 통계 업데이트
                            if prev_category not in changed_from:
                                changed_from[prev_category] = 0
                            changed_from[prev_category] += 1
                        else:
                            log_info(f"  - {prev_category} 카테고리에 없음, 제거 불필요")
                
                # 새 카테고리에 추가
                category_contents[category].add(img_path)
                log_info(f"  - {category} 카테고리에 추가됨")
                
                # 처리 상태 업데이트
                self.processed_images[img_path] = category
            
            # 3. 모든 카테고리 파일 업데이트
            for cat, contents in category_contents.items():
                if contents:  # 내용이 있는 경우만 저장
                    with open(category_files[cat], 'w', encoding='utf-8') as f:
                        for path in contents:
                            f.write(f"{path}\n")
                    log_info(f"{cat} 파일 저장됨: {len(contents)}개 항목")
                else:
                    log_info(f"{cat} 파일 비어있음, 저장하지 않음")
                    # 빈 파일 생성 또는 기존 파일 삭제 옵션
                    if os.path.exists(category_files[cat]):
                        os.remove(category_files[cat])
                        log_info(f"{cat} 빈 파일 삭제됨")
            
            # 선택 해제
            self.selected_image_paths = []
            self.checklist = []
            
            # 결과 표시
            status_label.config(text="처리 완료!")
            result_text = f"{category} 카테고리에 {total_paths}개 이미지 저장됨"
            
            if changed_from:
                for prev_cat, count in changed_from.items():
                    result_text += f"\n{prev_cat}에서 {count}개 이미지 변경됨"
            
            detail_label.config(text=result_text)
            
            # 화면 업데이트
            self.update_selection_info()
            self.update_display()
            
            # 로그창 닫기 버튼
            tk.Button(progress_window, text="닫기", command=progress_window.destroy).pack(pady=10)
            
        except Exception as e:
            print(f"Error saving {category} data: {e}")
            if 'progress_window' in locals():
                progress_window.destroy()
            import traceback
            traceback.print_exc()
    def toggle_fullscreen(self, event=None):
        """전체 화면 토글 메서드"""
        is_fullscreen = self.root.attributes('-fullscreen')
        self.root.attributes('-fullscreen', not is_fullscreen)
    def file_slice(self):
        """Split input file into smaller chunks with random sampling"""
        file_path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
        if not file_path:
            return
            
        dirpath = os.path.dirname(file_path)
        filename = os.path.basename(file_path)
        lines_per_file = 100
        savepath = os.path.join(dirpath, "datalist")
        
        if not os.path.isdir(savepath):
            os.mkdir(savepath)
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                total_lines = len(lines)
                num_files = (total_lines // lines_per_file) + 1
                
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
                    
            print("Data slice complete!")
            
        except Exception as e:
            print(f"Error during file slicing: {e}")
    def select_all_images(self):
        """Select all currently displayed images that aren't already processed"""
        # Get current page's worth of images
        start_idx = self.current_page * self.page_size
        end_idx = min(start_idx + self.page_size, len(self.image_paths))
        current_images = self.image_paths[start_idx:end_idx]
        
        # Mark all current images as selected (except already processed ones)
        for widget in self.frame.winfo_children():
            if isinstance(widget, tk.Label) and hasattr(widget, 'img_path'):
                img_path = widget.img_path
                
                # 이미 처리된 이미지는 선택하지 않음
                if hasattr(self, 'processed_images') and img_path in self.processed_images:
                    continue
                    
                # 이미지 선택 표시
                widget.config(highlightbackground="red", highlightthickness=4, bg="#ffdddd")
                if img_path not in self.selected_image_paths:
                    self.selected_image_paths.append(img_path)
                if widget not in self.checklist:
                    self.checklist.append(widget)
                    for child in widget.winfo_children():
                        if hasattr(child, 'selection_indicator'):
                            child.destroy()
                    indicator = tk.Label(widget, text="✓", font=("Arial", 12, "bold"), fg="red", bg="#ffdddd")
                    indicator.selection_indicator = True
                    indicator.place(x=5, y=5)
        self.update_selection_info()
    def deselect_all_images(self):
        """Deselect all images"""
        # Clear selection list
        self.selected_image_paths.clear()
        
        # Update UI - 모든 이미지에 대해 체크마크 제거
        for widget in self.frame.winfo_children():
            if isinstance(widget, tk.Label) and hasattr(widget, 'img_path'):
                img_path = widget.img_path
                # 이미 처리된 이미지는 원래 상태 유지
                if hasattr(self, 'processed_images') and img_path in self.processed_images:
                    continue
                
                # 체크마크 제거
                for child in widget.winfo_children():
                    if hasattr(child, 'selection_indicator'):
                        child.destroy()
                        
                # 나머지 이미지는 선택 해제
                widget.config(highlightbackground="white", highlightthickness=2, bg="white")
        
        self.checklist.clear()
        self.update_selection_info()

    def prev_page(self):
        """Go to previous page"""
        if self.current_page > 0:
            self.current_page -= 1
            self.update_display()
    def next_page(self):
        """Go to next page"""
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.update_display()
    def update_pagination_controls(self):
        """Update pagination controls"""
        self.page_label.config(text=f"Page {self.current_page + 1}/{self.total_pages}")
        self.prev_button.config(state="normal" if self.current_page > 0 else "disabled")
        self.next_button.config(state="normal" if self.current_page < self.total_pages - 1 else "disabled")

    def update_selection_info(self):
        """Update the selection counter display"""
        selected_count = len(self.selected_image_paths)
        self.selection_info_label.config(text=f"Selected: {selected_count}")
        
        # 처리된 이미지 정보도 함께 업데이트
        self.update_processed_info()

    def update_processed_info(self):
        """처리된 이미지 정보 업데이트"""
        if hasattr(self, 'processed_images'):
            processed_count = len(self.processed_images)
            
            # 카테고리별 집계
            category_counts = {}
            for category in self.processed_images.values():
                if category in category_counts:
                    category_counts[category] += 1
                else:
                    category_counts[category] = 1
            
            # 기본 텍스트 설정
            info_text = f"처리됨: {processed_count}"
            
            # 카테고리별 상세 정보 툴팁 설정
            if processed_count > 0:
                tooltip_text = "\n".join([f"{cat}: {cnt}장" for cat, cnt in category_counts.items()])
                self.processed_info_label.tooltip = tooltip_text
                
                # 마우스 오버 이벤트 바인딩 (툴팁 표시용)
                if not hasattr(self.processed_info_label, 'tooltip_bound'):
                    self.processed_info_label.bind("<Enter>", self.show_processed_tooltip)
                    self.processed_info_label.bind("<Leave>", self.hide_tooltip)
                    self.processed_info_label.tooltip_bound = True
            
            self.processed_info_label.config(text=info_text)

    def show_processed_tooltip(self, event):
        """처리된 이미지 카테고리별 통계 툴팁 표시"""
        if hasattr(self.processed_info_label, 'tooltip'):
            x, y, _, _ = self.processed_info_label.bbox("all")
            x += self.processed_info_label.winfo_rootx() + 25
            y += self.processed_info_label.winfo_rooty() + 25
            
            # 툴팁 창 생성
            self.tooltip = tk.Toplevel(self.root)
            self.tooltip.wm_overrideredirect(True)
            self.tooltip.wm_geometry(f"+{x}+{y}")
            
            label = tk.Label(self.tooltip, text=self.processed_info_label.tooltip, 
                        justify='left', background="#ffffcc", relief="solid", borderwidth=1,
                        font=("Arial", 8, "normal"))
            label.pack(padx=3, pady=3)

    def hide_tooltip(self, event):
        """툴팁 숨기기"""
        if hasattr(self, 'tooltip') and self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None
    def setup_statistics_dashboard(self):
        """통계 및 진행 상황을 위한 대시보드 설정"""
        # 대시보드 창 생성
        self.stats_window = tk.Toplevel(self.root)
        self.stats_window.title("작업 통계 대시보드")
        self.stats_window.geometry("600x400")
        self.stats_window.protocol("WM_DELETE_WINDOW", self.hide_stats_dashboard)
        self.stats_window.withdraw()  # 처음에는 숨겨둠
        
        # 프레임 설정
        main_frame = tk.Frame(self.stats_window)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 진행률 표시
        progress_frame = tk.LabelFrame(main_frame, text="진행 상황")
        progress_frame.pack(fill="x", pady=5)
        
        self.total_progress = ttk.Progressbar(progress_frame, length=400)
        self.total_progress.pack(pady=5)
        
        self.progress_label = tk.Label(progress_frame, text="처리된 이미지: 0/0 (0%)")
        self.progress_label.pack(pady=5)
        
        # 카테고리별 통계
        stats_frame = tk.LabelFrame(main_frame, text="카테고리별 통계")
        stats_frame.pack(fill="x", pady=5)
        
        # 카테고리별 프로그레스 바
        self.category_progress = {}
        self.category_labels = {}
        
        for category, color in [("주간", "#ddddff"), ("야간", "#ffddff"), ("열화상", "#ffeecc")]:
            cat_frame = tk.Frame(stats_frame)
            cat_frame.pack(fill="x", pady=2)
            
            cat_label = tk.Label(cat_frame, text=f"{category}:", width=10, anchor="w")
            cat_label.pack(side="left", padx=5)
            
            self.category_progress[category] = ttk.Progressbar(cat_frame, length=300)
            self.category_progress[category].pack(side="left", padx=5)
            
            self.category_labels[category] = tk.Label(cat_frame, text="0/0 (0%)", width=15)
            self.category_labels[category].pack(side="left")
        
        # 시간 통계
        time_frame = tk.LabelFrame(main_frame, text="작업 시간")
        time_frame.pack(fill="x", pady=5)
        
        self.time_label = tk.Label(time_frame, text="작업 시간: 00:00:00")
        self.time_label.pack(side="left", padx=5)
        
        self.avg_time_label = tk.Label(time_frame, text="이미지당 평균 시간: 0초")
        self.avg_time_label.pack(side="left", padx=5)
        
        self.est_time_label = tk.Label(time_frame, text="예상 남은 시간: 00:00:00")
        self.est_time_label.pack(side="left", padx=5)
        
        # 버튼 프레임
        button_frame = tk.Frame(main_frame)
        button_frame.pack(fill="x", pady=10)
        
        tk.Button(button_frame, text="통계 내보내기", command=self.export_statistics).pack(side="left", padx=5)
        tk.Button(button_frame, text="닫기", command=self.hide_stats_dashboard).pack(side="right", padx=5)
        
        # 작업 시작 시간 기록
        self.start_time = time.time()
        self.last_update = self.start_time
        
        # 주기적 업데이트 설정
        self.update_statistics()

    def show_stats_dashboard(self):
        """통계 대시보드 표시"""
        if hasattr(self, 'stats_window'):
            self.stats_window.deiconify()
            self.update_statistics()
        else:
            self.setup_statistics_dashboard()

    def hide_stats_dashboard(self):
        """통계 대시보드 숨기기"""
        if hasattr(self, 'stats_window'):
            self.stats_window.withdraw()

    def update_statistics(self):
        """통계 정보 업데이트"""
        if not hasattr(self, 'stats_window') or not self.stats_window.winfo_exists():
            return
        
        # 전체 이미지 및 처리된 이미지 수
        total_images = len(self.image_paths)
        processed_count = len(self.processed_images) if hasattr(self, 'processed_images') else 0
        
        # 진행률 계산
        if total_images > 0:
            progress_percentage = (processed_count / total_images) * 100
        else:
            progress_percentage = 0
        
        # 전체 진행률 업데이트
        self.total_progress['maximum'] = total_images
        self.total_progress['value'] = processed_count
        self.progress_label.config(text=f"처리된 이미지: {processed_count}/{total_images} ({progress_percentage:.1f}%)")
        
        # 카테고리별 진행률
        category_counts = {}
        for category in ["주간", "야간", "열화상"]:
            category_counts[category] = sum(1 for cat in self.processed_images.values() if cat == category) if hasattr(self, 'processed_images') else 0
            
            if total_images > 0:
                cat_percentage = (category_counts[category] / total_images) * 100
            else:
                cat_percentage = 0
            
            self.category_progress[category]['maximum'] = total_images
            self.category_progress[category]['value'] = category_counts[category]
            self.category_labels[category].config(text=f"{category_counts[category]}/{total_images} ({cat_percentage:.1f}%)")
        
        # 시간 통계
        current_time = time.time()
        elapsed_time = current_time - self.start_time
        hours, remainder = divmod(elapsed_time, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        self.time_label.config(text=f"작업 시간: {int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}")
        
        # 이미지당 평균 처리 시간
        if processed_count > 0:
            avg_time = elapsed_time / processed_count
            self.avg_time_label.config(text=f"이미지당 평균 시간: {avg_time:.1f}초")
            
            # 예상 남은 시간
            remaining_images = total_images - processed_count
            if remaining_images > 0:
                est_remaining_time = avg_time * remaining_images
                est_hours, remainder = divmod(est_remaining_time, 3600)
                est_minutes, est_seconds = divmod(remainder, 60)
                
                self.est_time_label.config(text=f"예상 남은 시간: {int(est_hours):02d}:{int(est_minutes):02d}:{int(est_seconds):02d}")
            else:
                self.est_time_label.config(text="예상 남은 시간: 00:00:00")
        
        # 5초마다 업데이트
        self.stats_window.after(5000, self.update_statistics)

    def export_statistics(self):
        """현재 통계 정보를 CSV 파일로 내보내기"""
        if not hasattr(self, 'processed_images'):
            tk.messagebox.showinfo("알림", "내보낼 통계 정보가 없습니다.")
            return
        
        try:
            # 저장 경로 선택
            file_path = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                initialfile=f"image_classification_stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            )
            
            if not file_path:
                return
            
            # 통계 정보 수집
            total_images = len(self.image_paths)
            processed_count = len(self.processed_images)
            
            category_counts = {}
            for category in ["주간", "야간", "열화상"]:
                category_counts[category] = sum(1 for cat in self.processed_images.values() if cat == category)
            
            # 현재 시간 및 작업 시간
            current_time = time.time()
            elapsed_time = current_time - self.start_time
            hours, remainder = divmod(elapsed_time, 3600)
            minutes, seconds = divmod(remainder, 60)
            elapsed_time_str = f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"
            
            # CSV 파일 작성
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(["통계 항목", "값"])
                writer.writerow(["총 이미지 수", total_images])
                writer.writerow(["처리된 이미지 수", processed_count])
                writer.writerow(["진행률", f"{(processed_count/total_images*100 if total_images > 0 else 0):.2f}%"])
                
                for category in ["주간", "야간", "열화상"]:
                    writer.writerow([f"{category} 이미지 수", category_counts[category]])
                
                writer.writerow(["작업 시간", elapsed_time_str])
                
                if processed_count > 0:
                    writer.writerow(["이미지당 평균 처리 시간", f"{elapsed_time/processed_count:.2f}초"])
            
            tk.messagebox.showinfo("완료", f"통계 정보가 {file_path}에 저장되었습니다.")
            
        except Exception as e:
            tk.messagebox.showerror("오류", f"통계 내보내기 중 오류 발생: {e}")
    def setup_filter_controls(self):
        """필터링 기능을 위한 컨트롤 설정"""
        # 필터 프레임 생성
        self.filter_frame = tk.LabelFrame(self.control_panel, text="필터 옵션")
        self.filter_frame.pack(side=tk.LEFT, padx=10, fill="y")
        
        # 필터 변수들
        self.show_unprocessed_only = tk.IntVar(value=0)
        self.selected_filter_list = tk.StringVar(value="없음")
        
        # 미처리 이미지만 표시 체크박스
        self.unprocessed_check = tk.Checkbutton(
            self.filter_frame, 
            text="미처리 이미지만 표시", 
            variable=self.show_unprocessed_only,
            command=self.apply_filters
        )
        self.unprocessed_check.pack(anchor="w", padx=5, pady=2)
        
        # 사용자 리스트 필터링 영역
        list_filter_frame = tk.Frame(self.filter_frame)
        list_filter_frame.pack(fill="x", padx=5, pady=2)
        
        tk.Label(list_filter_frame, text="리스트 필터:").pack(side=tk.LEFT, padx=2)
        
        # 사용자 리스트 드롭다운
        self.filter_list_dropdown = ttk.Combobox(
            list_filter_frame, 
            textvariable=self.selected_filter_list,
            width=15
        )
        self.filter_list_dropdown['values'] = ["없음"]
        self.filter_list_dropdown.pack(side=tk.LEFT, padx=2)
        self.filter_list_dropdown.bind("<<ComboboxSelected>>", lambda e: self.apply_filters())
        
        # 리스트 관리 버튼
        tk.Button(
            list_filter_frame, 
            text="리스트 추가", 
            command=self.add_filter_list,
            width=8
        ).pack(side=tk.LEFT, padx=2)
        
        # 필터 적용 및 초기화 버튼
        filter_button_frame = tk.Frame(self.filter_frame)
        filter_button_frame.pack(fill="x", padx=5, pady=5)
        
        tk.Button(
            filter_button_frame, 
            text="필터 적용", 
            command=self.apply_filters,
            width=10
        ).pack(side=tk.LEFT, padx=2)
        
        tk.Button(
            filter_button_frame, 
            text="필터 초기화", 
            command=self.reset_filters,
            width=10
        ).pack(side=tk.LEFT, padx=2)
        
        # 필터링된 이미지 상태 레이블
        self.filter_status_label = tk.Label(self.filter_frame, text="표시: 전체 이미지")
        self.filter_status_label.pack(pady=5)


    def add_filter_list(self):
        """사용자 정의 필터 리스트 추가"""
        # 파일 선택 대화상자
        file_path = filedialog.askopenfilename(
            title="필터링할 이미지 리스트 선택",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        
        if not file_path:
            return
        
        # 리스트 이름 입력 대화상자
        list_name = simpledialog.askstring(
            "리스트 이름", 
            "이 필터 리스트의 이름을 입력하세요:",
            initialvalue=os.path.basename(file_path)
        )
        
        if not list_name:
            return
        
        try:
            # 파일에서 이미지 경로 로드
            image_paths = []
            encodings_to_try = ['utf-8', 'cp949', 'euc-kr', 'latin-1']
            
            for encoding in encodings_to_try:
                try:
                    with open(file_path, encoding=encoding) as f:
                        image_paths = [line.strip() for line in f.readlines() if line.strip()]
                    break  # 성공적으로 읽었으면 루프 종료
                except UnicodeDecodeError:
                    continue
            
            if not image_paths:
                raise ValueError("파일을 읽을 수 없거나 파일이 비어 있습니다.")
            
            # 리스트 저장
            self.user_filter_lists[list_name] = image_paths
            
            # 드롭다운 업데이트
            current_values = list(self.filter_list_dropdown['values'])
            if "없음" not in current_values:
                current_values = ["없음"] + current_values
            
            if list_name not in current_values:
                current_values.append(list_name)
                self.filter_list_dropdown['values'] = current_values
            
            # 새 리스트 선택
            self.selected_filter_list.set(list_name)
            
            # 필터 적용
            self.apply_filters()
            
            tk.messagebox.showinfo("성공", f"'{list_name}' 리스트가 추가되었습니다. ({len(image_paths)}개 이미지)")
            
        except Exception as e:
            tk.messagebox.showerror("오류", f"리스트 로드 중 오류 발생: {e}")

    def apply_filters(self):
        """현재 설정된 필터 조건 적용"""
        # 원본 이미지 경로 복원
        if hasattr(self, '_original_image_paths'):
            self.image_paths = self._original_image_paths.copy()
        else:
            self._original_image_paths = self.image_paths.copy()
        
        filtered_paths = self.image_paths.copy()
        filter_applied = False
        
        # 미처리 이미지만 표시
        if self.show_unprocessed_only.get() == 1:
            if hasattr(self, 'processed_images'):
                filtered_paths = [path for path in filtered_paths if path not in self.processed_images]
                filter_applied = True
        
        # 사용자 리스트 필터 적용
        selected_list = self.selected_filter_list.get()
        if selected_list != "없음" and selected_list in self.user_filter_lists:
            list_paths = self.user_filter_lists[selected_list]
            filtered_paths = [path for path in filtered_paths if path in list_paths]
            filter_applied = True
        
        # 필터링 결과 적용
        self.image_paths = filtered_paths
        
        # 페이지네이션 재계산
        self.total_pages = (len(self.image_paths) + self.page_size - 1) // self.page_size
        self.current_page = 0  # 첫 페이지로 이동
        
        # 상태 업데이트
        if filter_applied:
            self.filter_status_label.config(text=f"표시: {len(filtered_paths)}/{len(self._original_image_paths)}")
        else:
            self.filter_status_label.config(text="표시: 전체 이미지")
        
        # 화면 업데이트
        self.update_pagination_controls()
        self.update_display()

    def reset_filters(self):
        """모든 필터 초기화"""
        # 필터 설정 초기화
        self.show_unprocessed_only.set(0)
        self.selected_filter_list.set("없음")
        
        # 원본 이미지 경로 복원
        if hasattr(self, '_original_image_paths'):
            self.image_paths = self._original_image_paths.copy()
        
        # 페이지네이션 재계산
        self.total_pages = (len(self.image_paths) + self.page_size - 1) // self.page_size
        self.current_page = 0  # 첫 페이지로 이동
        
        # 상태 업데이트
        self.filter_status_label.config(text="표시: 전체 이미지")
        
        # 화면 업데이트
        self.update_pagination_controls()
        self.update_display()
    def save_session(self):
        """현재 작업 세션 상태 저장"""
        try:
            # 저장할 파일 경로 선택
            file_path = filedialog.asksaveasfilename(
                title="작업 세션 저장",
                defaultextension=".imgsession",
                filetypes=[("Image Session files", "*.imgsession"), ("All files", "*.*")],
                initialfile=f"image_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.imgsession"
            )
            
            if not file_path:
                return
            
            # 세션 정보 수집
            session_data = {
                "version": "1.0",  # 향후 호환성을 위한 버전 정보
                "timestamp": datetime.now().isoformat(),
                "rootpath": self.rootpath,
                "filename": self.filename,
                "processed_images": self.processed_images if hasattr(self, 'processed_images') else {},
                "selected_image_paths": self.selected_image_paths,
                "current_page": self.current_page,
                "filter_settings": {
                    "show_unprocessed_only": self.show_unprocessed_only.get() if hasattr(self, 'show_unprocessed_only') else 0,
                    "selected_filter_list": self.selected_filter_list.get() if hasattr(self, 'selected_filter_list') else "없음"
                },
                "user_filter_lists": self.user_filter_lists if hasattr(self, 'user_filter_lists') else {}
            }
            
            # JSON으로 저장
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)
            
            tk.messagebox.showinfo("완료", f"작업 세션이 {file_path}에 저장되었습니다.")
            
        except Exception as e:
            tk.messagebox.showerror("오류", f"세션 저장 중 오류 발생: {e}")

    def load_session(self):
        """저장된 작업 세션 불러오기 - 최적화 버전"""
        try:
            # 불러올 파일 선택
            file_path = filedialog.askopenfilename(
                title="작업 세션 불러오기",
                filetypes=[("Image Session files", "*.imgsession"), ("All files", "*.*")]
            )
            
            if not file_path:
                return
            
            # 진행 창 생성
            progress_window = tk.Toplevel(self.root)
            progress_window.title("세션 불러오기")
            progress_window.geometry("400x150")
            progress_window.transient(self.root)
            progress_window.grab_set()
            
            status_label = tk.Label(progress_window, text="세션 데이터 로드 중...")
            status_label.pack(pady=(20, 10))
            
            progress_bar = ttk.Progressbar(progress_window, length=350, mode='indeterminate')
            progress_bar.pack(pady=5)
            progress_bar.start(10)
            
            detail_label = tk.Label(progress_window, text="")
            detail_label.pack(pady=5)
            
            progress_window.update()
            
            # 비동기 처리를 위한 함수 정의
            def process_session_data():
                nonlocal file_path, progress_window, status_label, progress_bar, detail_label
                
                try:
                    # 저장된 데이터 로드
                    with open(file_path, 'r', encoding='utf-8') as f:
                        session_data = json.load(f)
                    
                    # 버전 확인
                    if "version" not in session_data:
                        raise ValueError("유효하지 않은 세션 파일입니다.")
                    
                    # 진행 상태 업데이트
                    self.root.after(0, lambda: detail_label.config(text="기본 세션 정보 로드 중..."))
                    self.root.after(0, lambda: progress_bar.stop())
                    self.root.after(0, lambda: progress_bar.config(mode='determinate', maximum=3, value=0))
                    
                    # 데이터 처리를 메인 스레드로 전달
                    self.root.after(100, lambda: apply_session_data(session_data))
                    
                except Exception as e:
                    self.root.after(0, lambda: handle_error(e))
            
            # 데이터 적용 함수
            def apply_session_data(session_data):
                nonlocal progress_window, status_label, progress_bar, detail_label
                
                try:
                    # 기본 세션 정보 복원
                    self.rootpath = session_data.get("rootpath", "")
                    self.filename = session_data.get("filename", "")
                    
                    # 필터 설정 복원
                    if hasattr(self, 'show_unprocessed_only') and "filter_settings" in session_data:
                        self.show_unprocessed_only.set(session_data["filter_settings"].get("show_unprocessed_only", 0))
                        self.selected_filter_list.set(session_data["filter_settings"].get("selected_filter_list", "없음"))
                    
                    # 사용자 필터 리스트 복원
                    if "user_filter_lists" in session_data:
                        self.user_filter_lists = session_data["user_filter_lists"]
                        
                        if hasattr(self, 'filter_list_dropdown'):
                            values = ["없음"] + list(self.user_filter_lists.keys())
                            self.filter_list_dropdown['values'] = values
                    
                    # 진행 상태 업데이트
                    progress_bar['value'] = 1
                    detail_label.config(text="처리된 이미지 정보 복원 중...")
                    progress_window.update()
                    
                    # 처리된 이미지 정보 복원
                    if "processed_images" in session_data:
                        self.processed_images = session_data["processed_images"]
                    
                    # 선택된 이미지 정보 복원 - 효율성을 위해 set 변환
                    progress_bar['value'] = 2
                    detail_label.config(text="선택된 이미지 정보 복원 중...")
                    progress_window.update()
                    
                    if "selected_image_paths" in session_data:
                        self.selected_image_paths = session_data["selected_image_paths"]
                    
                    # 페이지 정보 복원
                    if "current_page" in session_data:
                        self.current_page = session_data["current_page"]
                        # 페이지 범위 검증
                        self.current_page = max(0, min(self.current_page, 999))  # 안전 제한
                    
                    # 모든 복원 작업 완료
                    progress_bar['value'] = 3
                    detail_label.config(text="세션 복원 완료!")
                    progress_window.update()
                    
                    # 효율적인 업데이트 순서
                    self.update_pagination_controls()
                    
                    # 화면 업데이트는 지연 후 실행
                    self.root.after(50, lambda: finish_loading())
                    
                except Exception as e:
                    handle_error(e)
            
            # 최종 완료 함수
            def finish_loading():
                nonlocal progress_window
                
                try:
                    # 화면 업데이트 (무거운 작업)
                    self.update_display()
                    self.update_selection_info()
                    self.update_processed_info()
                    
                    # 잠시 후 진행 창 닫기
                    self.root.after(1000, progress_window.destroy)
                    
                    # 완료 메시지
                    tk.messagebox.showinfo("완료", "작업 세션이 성공적으로 로드되었습니다.")
                    
                except Exception as e:
                    handle_error(e)
            
            # 오류 처리 함수
            def handle_error(e):
                nonlocal progress_window
                
                if progress_window.winfo_exists():
                    progress_window.destroy()
                
                tk.messagebox.showerror("오류", f"세션 불러오기 중 오류 발생: {e}")
                print(f"Error loading session: {e}")
                import traceback
                traceback.print_exc()
            
            # 비동기 처리 시작
            self.root.after(10, process_session_data)
            
        except Exception as e:
            tk.messagebox.showerror("오류", f"세션 불러오기 초기화 오류: {e}")
            if 'progress_window' in locals() and progress_window.winfo_exists():
                progress_window.destroy()
    def setup_preview_features(self):
        """이미지 미리보기 기능 설정"""
        # 확대 미리보기 창 생성 (초기에는 보이지 않음)
        self.preview_window = tk.Toplevel(self.root)
        self.preview_window.title("미리보기")
        self.preview_window.geometry("600x600")
        self.preview_window.withdraw()  # 처음에는 숨겨둠
        self.preview_window.overrideredirect(True)  # 타이틀 바 제거
        
        # 미리보기 이미지 레이블
        self.preview_image_label = tk.Label(self.preview_window)
        self.preview_image_label.pack(expand=True, fill="both")
    def clear_memory(self):
        """메모리 사용량 줄이기"""
        # 사용하지 않는 캐시 정리
        MAX_CACHE_SIZE = 100
        
        # LRU 캐시 구현 (가장 오래된 항목부터 제거)
        if len(self.thumbnail_cache) > MAX_CACHE_SIZE:
            oldest_keys = list(self.thumbnail_cache.keys())[:MAX_CACHE_SIZE // 2]
            for key in oldest_keys:
                del self.thumbnail_cache[key]
        
        # 명시적 가비지 컬렉션
        gc.collect()
    def setup_image_hover_events(self, label, img_path):
        """개별 이미지에 마우스 오버 이벤트 설정"""
        # 마우스 진입 시 미리보기 표시
        label.bind("<Button-3>", lambda e, path=img_path: self.show_image_preview(e, path))
    def on_shift_press(self, event):
        """Shift 키가 눌렸을 때 호출"""
        print(f"Shift pressed: {event.keysym}")  # 디버깅용
        self.shift_pressed = True
        
    def on_shift_release(self, event):
        """Shift 키가 떼졌을 때 호출"""
        self.shift_pressed = False
    def on_caps_lock_press(self, event):
        """Caps Lock 키가 눌렸을 때 호출"""
        print("Caps Lock pressed")  # 디버깅용
        self.caps_locked = True

    def on_caps_lock_release(self, event):
        """Caps Lock 키가 떼졌을 때 호출"""
        print("Caps Lock released")  # 디버깅용
        self.caps_locked = False

    def show_image_preview(self, event, img_path):
        """이미지 확대 미리보기 표시 (마우스 오른쪽 버튼 클릭 시)"""
        try:
            # 이미지 경로가 유효한지 확인
            if not os.path.isfile(img_path):
                return
            
            # 캐시에서 미리보기 이미지 가져오기 또는 새로 생성
            if img_path in self.preview_cache:
                photo = self.preview_cache[img_path]
            else:
                # 이미지 로드 및 미리보기 크기로 조정
                with Image.open(img_path) as img:
                    preview_size = 600  # 미리보기 크기
                    # 원본 비율 유지
                    img.thumbnail((preview_size, preview_size))
                    photo = ImageTk.PhotoImage(img)
                    # 캐시에 저장 (최대 50개까지만 저장)
                    if len(self.preview_cache) > 50:
                        # 가장 오래된 항목 제거 (간단한 구현)
                        self.preview_cache.pop(next(iter(self.preview_cache)))
                    self.preview_cache[img_path] = photo
            
            # 미리보기 이미지 설정
            self.preview_image_label.configure(image=photo)
            self.preview_image_label.image = photo  # 참조 유지
            
            # 미리보기 창 위치 설정 - 마우스 클릭 위치 근처에 표시
            x, y = event.x_root, event.y_root
            
            # 미리보기 창 크기
            preview_width = 300
            preview_height = 300
            
            # 화면 크기
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            
            # 미리보기 창이 화면을 벗어나지 않도록 위치 조정
            if x + preview_width + 20 > screen_width:
                x = x - preview_width - 10  # 커서 왼쪽에 표시
            else:
                x = x + 20  # 커서 오른쪽에 표시
            
            if y + preview_height + 20 > screen_height:
                y = screen_height - preview_height - 10
            
            # 창 위치 설정
            self.preview_window.geometry(f"+{x}+{y}")
            
            # 미리보기 창 표시
            self.preview_window.deiconify()
            
            # 클릭 영역 벗어나면 미리보기 닫기 (다른 곳 클릭하면 닫히게)
            self.root.bind("<Button-1>", self.hide_image_preview)
            self.root.bind("<Button-3>", self.hide_image_preview)
            
        except Exception as e:
            print(f"미리보기 표시 오류: {e}")
    def setup_drag_select_events(self, label, img_path):
        """드래그 선택을 위한 이벤트 설정"""
        # 마우스 왼쪽 버튼 누름 이벤트
        label.bind("<ButtonPress-1>", lambda e, l=label, p=img_path: self.on_drag_start(e, l, p))
        
        # 마우스 이동 이벤트
        label.bind("<B1-Motion>", lambda e, l=label: self.on_drag_motion(e, l))
        
        # 마우스 왼쪽 버튼 뗌 이벤트
        label.bind("<ButtonRelease-1>", lambda e: self.on_drag_end(e))

    def on_drag_start(self, event, label, img_path):
        """드래그 시작 처리"""
        # Shift 키가 눌려있지 않으면 일반 클릭 처리
        if not self.shift_pressed:
            self.on_image_click(label, img_path)
            return
        
        # 드래그 시작 위치 저장
        self.drag_start = (event.x_root, event.y_root)
        
        # 선택 영역 사각형 생성 (아직 그리지 않음)
        self.drag_rectangle = None
        
        # 상태바에 드래그 선택 모드 표시
        self.status_bar.config(text="드래그 선택 모드: 여러 이미지 선택 중...")

    def on_drag_motion(self, event, label):
        """드래그 중 처리"""
        # Shift 키가 눌려있지 않거나 드래그 시작 위치가 없으면 무시
        if not self.shift_pressed or not self.drag_start:
            return
        
        current_pos = (event.x_root, event.y_root)
        
        # 이전에 그려진 사각형이 있으면 삭제
        if self.drag_rectangle:
            self.canvas.delete(self.drag_rectangle)
        
        # 드래그 영역 사각형 그리기
        self.drag_rectangle = self.canvas.create_rectangle(
            self.canvas.canvasx(self.drag_start[0] - self.root.winfo_rootx()),
            self.canvas.canvasy(self.drag_start[1] - self.root.winfo_rooty()),
            self.canvas.canvasx(current_pos[0] - self.root.winfo_rootx()),
            self.canvas.canvasy(current_pos[1] - self.root.winfo_rooty()),
            outline="red", width=2, dash=(4, 4)
        )

    def on_drag_end(self, event):
        """드래그 종료 처리 - 토글 선택 기능"""
        # Shift 키가 눌려있지 않거나 드래그 시작 위치가 없으면 무시
        if not self.shift_pressed or not self.drag_start:
            return
        
        # 카운터 변수 초기화 - 여기서 먼저 초기화해야 함
        selected_count = 0
        deselected_count = 0
        
        # 드래그 종료 위치
        end_pos = (event.x_root, event.y_root)
        
        # 드래그 영역 계산
        x1 = min(self.drag_start[0], end_pos[0])
        y1 = min(self.drag_start[1], end_pos[1])
        x2 = max(self.drag_start[0], end_pos[0])
        y2 = max(self.drag_start[1], end_pos[1])
        
        # 이전에 그려진 사각형이 있으면 삭제
        if self.drag_rectangle:
            self.canvas.delete(self.drag_rectangle)
            self.drag_rectangle = None
        
        # 드래그 영역 내의 이미지 라벨 찾아서 토글 선택
        for widget in self.frame.winfo_children():
            if isinstance(widget, tk.Label) and hasattr(widget, 'img_path'):
                # 이미 처리된 이미지는 건너뜀
                if hasattr(self, 'processed_images') and widget.img_path in self.processed_images:
                    continue
                    
                # 위젯의 전역 좌표 계산
                widget_x = widget.winfo_rootx()
                widget_y = widget.winfo_rooty()
                widget_width = widget.winfo_width()
                widget_height = widget.winfo_height()
                
                # 위젯이 드래그 영역과 겹치는지 확인 - 간단한 충돌 확인 로직
                if (widget_x < x2 and widget_x + widget_width > x1 and
                    widget_y < y2 and widget_y + widget_height > y1):
                    
                    # 토글 동작
                    if widget in self.checklist:
                        # 이미 선택된 상태면 선택 해제
                        widget.config(highlightbackground="white", highlightthickness=2, bg="white")
                        if widget.img_path in self.selected_image_paths:
                            self.selected_image_paths.remove(widget.img_path)
                        self.checklist.remove(widget)
                        deselected_count += 1
                    else:
                        # 선택되지 않은 상태면 선택
                        widget.config(highlightbackground="red", highlightthickness=4, bg="#ffdddd")
                        if widget.img_path not in self.selected_image_paths:
                            self.selected_image_paths.append(widget.img_path)
                        if widget not in self.checklist:
                            self.checklist.append(widget)
                            indicator = tk.Label(widget, text="✓", font=("Arial", 12, "bold"), fg="red", bg="#ffdddd")
                            indicator.selection_indicator = True
                            indicator.place(x=5, y=5)
                        selected_count += 1
        
        # 드래그 정보 초기화
        self.drag_start = None
        
        # 상태바 업데이트
        if selected_count > 0 or deselected_count > 0:
            status_text = "드래그 토글 선택: "
            if selected_count > 0:
                status_text += f"{selected_count}개 선택"
            if deselected_count > 0:
                status_text += f"{', ' if selected_count > 0 else ''}{deselected_count}개 해제"
            self.status_bar.config(text=status_text)
        else:
            self.status_bar.config(text="준비")
        
        # 선택 정보 업데이트
        self.update_selection_info()

    def update_preview_position(self, event):
        """마우스 위치에 따라 미리보기 창 위치 업데이트"""
        if not hasattr(self, 'preview_window') or not self.preview_window.winfo_exists():
            return
        
        # 마우스 커서 위치 가져오기
        x, y = event.x_root, event.y_root
        
        # 미리보기 창 크기
        preview_width = self.preview_window.winfo_width()
        preview_height = self.preview_window.winfo_height()
        
        # 화면 크기
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # 미리보기 창이 화면을 벗어나지 않도록 위치 조정
        if x + preview_width + 20 > screen_width:
            x = x - preview_width - 10  # 커서 왼쪽에 표시
        else:
            x = x + 20  # 커서 오른쪽에 표시
        
        if y + preview_height + 20 > screen_height:
            y = screen_height - preview_height - 10
        
        # 창 위치 설정
        self.preview_window.geometry(f"+{x}+{y}")

    def hide_image_preview(self, event=None):
        """이미지 미리보기 숨기기"""
        if hasattr(self, 'preview_window') and self.preview_window.winfo_exists():
            self.preview_window.withdraw()
            
            # 바인딩 제거
            self.root.unbind("<Button-1>")
            self.root.unbind("<Button-3>")

    def clear_preview_cache(self):
        """미리보기 캐시 정리"""
        if hasattr(self, 'preview_cache'):
            self.preview_cache.clear()
            import gc
            gc.collect()  # 메모리 회수
    def detail_window_save(self, detail_window, img_path, category):
        """상세 보기 창에서 이미지를 카테고리별로 저장"""
        try:
            # 이미지 처리 상태 업데이트
            self.processed_images[img_path] = category
            
            # 저장 경로 생성
            savepath = os.path.join(self.rootpath, 
                                f"{self.filename}_{category}_{self.current_datetime}.txt")
            
            # 저장 처리
            mode = 'a' if os.path.isfile(savepath) else 'w'
            with open(savepath, mode, encoding='utf-8') as f:
                f.write(f"{img_path}\n")
            
            # 상세 보기 창 닫기
            detail_window.destroy()
            
            # 선택 목록에서 제거
            if img_path in self.selected_image_paths:
                self.selected_image_paths.remove(img_path)
                self.checklist = [label for label in self.checklist 
                                if not hasattr(label, 'img_path') or label.img_path != img_path]
            
            # 디스플레이 업데이트
            self.update_selection_info()
            self.update_display()
            
            # 처리 완료 메시지 (2초 후 자동 닫힘)
            info_window = tk.messagebox.showinfo("처리 완료", f"이미지가 '{category}' 카테고리로 저장되었습니다.")

                        # 2초 후 메시지박스 닫기
            def close_messagebox():
                try:
                    info_window.destroy()
                except:
                    pass
            
            self.root.after(2000, close_messagebox)
            
        except Exception as e:
            tk.messagebox.showerror("오류", f"이미지 저장 중 오류 발생: {e}")
if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("1200x800")  # 초기 창 크기 설정
    app = ImageViewer(root)
    root.mainloop()