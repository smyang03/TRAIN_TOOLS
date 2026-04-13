import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import xml.etree.ElementTree as ET
import os
import subprocess
import threading
from datetime import datetime
import glob

class KISAVideoCutter:
    def __init__(self, root):
        self.root = root
        self.root.title("KISA 영상 자르기 도구")
        self.root.geometry("950x750")
        self.root.configure(bg='#f0f0f0')
        
        # 변수 초기화
        self.xml_files_data = []  # 여러 XML 파일을 저장할 리스트
        self.xml_folder_path = ""
        self.xml_file_path = ""
        self.input_folder = tk.StringVar()
        self.output_folder = tk.StringVar()
        self.start_offset = tk.IntVar(value=0)
        self.additional_duration = tk.IntVar(value=0)
        self.use_xml_folder = tk.BooleanVar(value=False)  # XML 폴더 사용 여부
        
        # 통계 변수
        self.total_files = 0
        self.processed_files = 0
        self.error_count = 0
        
        self.setup_ui()
        
    def setup_ui(self):
        """UI 구성"""
        # 메인 프레임
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 창 크기 조절 가능하도록 설정
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        row = 0
        
        # 제목
        title_label = ttk.Label(main_frame, text="🎬 KISA 영상 자르기 도구", 
                               font=('Arial', 16, 'bold'))
        title_label.grid(row=row, column=0, columnspan=3, pady=(0, 20))
        row += 1
        
        # XML 파일/폴더 선택 섹션
        xml_frame = ttk.LabelFrame(main_frame, text="📄 XML 메타데이터 선택", padding="10")
        xml_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        xml_frame.columnconfigure(2, weight=1)
        row += 1
        
        # XML 폴더/파일 선택 라디오 버튼
        radio_frame = ttk.Frame(xml_frame)
        radio_frame.grid(row=0, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        
        ttk.Radiobutton(radio_frame, text="단일 XML 파일", variable=self.use_xml_folder, 
                       value=False, command=self.on_xml_mode_change).grid(row=0, column=0, sticky=tk.W)
        ttk.Radiobutton(radio_frame, text="XML 폴더 (일괄처리)", variable=self.use_xml_folder, 
                       value=True, command=self.on_xml_mode_change).grid(row=0, column=1, sticky=tk.W, padx=(20, 0))
        
        # XML 파일 선택 버튼들
        self.xml_file_btn = ttk.Button(xml_frame, text="XML 파일 선택", 
                                      command=self.select_xml_file)
        self.xml_file_btn.grid(row=1, column=0, padx=(0, 10))
        
        self.xml_folder_btn = ttk.Button(xml_frame, text="XML 폴더 선택", 
                                        command=self.select_xml_folder, state=tk.DISABLED)
        self.xml_folder_btn.grid(row=1, column=1, padx=(0, 10))
        
        self.xml_path_label = ttk.Label(xml_frame, text="선택된 파일/폴더가 없습니다", 
                                       foreground="gray")
        self.xml_path_label.grid(row=1, column=2, sticky=(tk.W, tk.E))
        
        # XML 목록 표시 (폴더 모드에서 사용)
        self.xml_list_frame = ttk.Frame(xml_frame)
        self.xml_list_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(10, 0))
        self.xml_list_frame.columnconfigure(0, weight=1)
        
        ttk.Label(self.xml_list_frame, text="발견된 XML 파일들:").grid(row=0, column=0, sticky=tk.W)
        
        self.xml_listbox = tk.Listbox(self.xml_list_frame, height=4, selectmode=tk.EXTENDED)
        self.xml_listbox.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(5, 0))
        
        xml_scrollbar = ttk.Scrollbar(self.xml_list_frame, orient=tk.VERTICAL, command=self.xml_listbox.yview)
        xml_scrollbar.grid(row=1, column=1, sticky=(tk.N, tk.S), pady=(5, 0))
        self.xml_listbox.config(yscrollcommand=xml_scrollbar.set)
        
        # 초기에는 리스트박스 숨김
        self.xml_list_frame.grid_remove()
        
        # XML 미리보기
        self.xml_preview = scrolledtext.ScrolledText(xml_frame, height=4, width=80)
        self.xml_preview.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E), 
                             pady=(10, 0))
        self.xml_preview.config(state=tk.DISABLED)
        
        # 폴더 경로 설정 섹션
        folder_frame = ttk.LabelFrame(main_frame, text="📁 폴더 경로 설정", padding="10")
        folder_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        folder_frame.columnconfigure(1, weight=1)
        row += 1
        
        # 입력 폴더
        ttk.Label(folder_frame, text="입력 폴더:").grid(row=0, column=0, sticky=tk.W, pady=2)
        input_frame = ttk.Frame(folder_frame)
        input_frame.grid(row=0, column=1, columnspan=2, sticky=(tk.W, tk.E), padx=(10, 0))
        input_frame.columnconfigure(0, weight=1)
        
        ttk.Entry(input_frame, textvariable=self.input_folder).grid(row=0, column=0, 
                                                                   sticky=(tk.W, tk.E))
        ttk.Button(input_frame, text="찾기", 
                  command=self.select_input_folder).grid(row=0, column=1, padx=(5, 0))
        
        # 출력 폴더
        ttk.Label(folder_frame, text="출력 폴더:").grid(row=1, column=0, sticky=tk.W, pady=2)
        output_frame = ttk.Frame(folder_frame)
        output_frame.grid(row=1, column=1, columnspan=2, sticky=(tk.W, tk.E), padx=(10, 0))
        output_frame.columnconfigure(0, weight=1)
        
        ttk.Entry(output_frame, textvariable=self.output_folder).grid(row=0, column=0, 
                                                                     sticky=(tk.W, tk.E))
        ttk.Button(output_frame, text="찾기", 
                  command=self.select_output_folder).grid(row=0, column=1, padx=(5, 0))
        
        # 처리 옵션 섹션
        option_frame = ttk.LabelFrame(main_frame, text="⚙️ 처리 옵션", padding="10")
        option_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        row += 1
        
        ttk.Label(option_frame, text="추가 시작 오프셋 (초):").grid(row=0, column=0, 
                                                                sticky=tk.W, padx=(0, 10))
        ttk.Spinbox(option_frame, from_=-30, to=30, textvariable=self.start_offset, 
                   width=10).grid(row=0, column=1, sticky=tk.W)
        
        ttk.Label(option_frame, text="추가 길이 (초):").grid(row=0, column=2, 
                                                           sticky=tk.W, padx=(20, 10))
        ttk.Spinbox(option_frame, from_=0, to=60, textvariable=self.additional_duration, 
                   width=10).grid(row=0, column=3, sticky=tk.W)
        
        # 처리 시작 버튼과 진행률
        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        control_frame.columnconfigure(0, weight=1)
        row += 1
        
        self.process_btn = ttk.Button(control_frame, text="🚀 영상 처리 시작", 
                                     command=self.start_processing)
        self.process_btn.grid(row=0, column=0, sticky=(tk.W, tk.E))
        
        # 진행률 표시
        self.progress = ttk.Progressbar(control_frame, mode='determinate')
        self.progress.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(10, 0))
        
        self.progress_label = ttk.Label(control_frame, text="")
        self.progress_label.grid(row=2, column=0, pady=(5, 0))
        
        # 통계 섹션
        stats_frame = ttk.LabelFrame(main_frame, text="📊 처리 통계", padding="10")
        stats_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        row += 1
        
        self.stats_labels = {}
        stats_items = [("총 XML 파일", "xml_files"), ("총 알람", "total"), ("처리된 파일", "processed"), 
                      ("오류 파일", "error")]
        
        for i, (label_text, key) in enumerate(stats_items):
            ttk.Label(stats_frame, text=f"{label_text}:").grid(row=0, column=i*2, 
                                                              sticky=tk.W, padx=(0, 5))
            self.stats_labels[key] = ttk.Label(stats_frame, text="0", 
                                              font=('Arial', 12, 'bold'))
            self.stats_labels[key].grid(row=0, column=i*2+1, sticky=tk.W, padx=(0, 15))
        
        # 로그 섹션
        log_frame = ttk.LabelFrame(main_frame, text="📋 처리 로그", padding="10")
        log_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), 
                      pady=5)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        main_frame.rowconfigure(row, weight=1)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, width=80)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 초기 로그 메시지
        self.add_log("시스템이 준비되었습니다. XML 파일/폴더와 경로를 설정하고 처리를 시작하세요.", "INFO")
    
    def on_xml_mode_change(self):
        """XML 모드 변경 시 처리"""
        if self.use_xml_folder.get():
            # 폴더 모드
            self.xml_file_btn.config(state=tk.DISABLED)
            self.xml_folder_btn.config(state=tk.NORMAL)
            self.xml_list_frame.grid()
        else:
            # 파일 모드
            self.xml_file_btn.config(state=tk.NORMAL)
            self.xml_folder_btn.config(state=tk.DISABLED)
            self.xml_list_frame.grid_remove()
        
        # 기존 데이터 초기화
        self.xml_files_data = []
        self.xml_path_label.config(text="선택된 파일/폴더가 없습니다", foreground="gray")
        self.xml_preview.config(state=tk.NORMAL)
        self.xml_preview.delete(1.0, tk.END)
        self.xml_preview.config(state=tk.DISABLED)
        self.xml_listbox.delete(0, tk.END)
        self.update_stats()
    
    def add_log(self, message, level="INFO"):
        """로그 메시지 추가"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {level}: {message}\n"
        
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, log_message)
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        
        # UI 업데이트
        self.root.update_idletasks()
    
    def update_stats(self):
        """통계 업데이트"""
        xml_count = len(self.xml_files_data)
        total_alarms = sum(len(xml_data['alarms']) for xml_data in self.xml_files_data)
        
        self.stats_labels["xml_files"].config(text=str(xml_count))
        self.stats_labels["total"].config(text=str(total_alarms))
        self.stats_labels["processed"].config(text=str(self.processed_files))
        self.stats_labels["error"].config(text=str(self.error_count))
    
    def select_xml_file(self):
        """XML 파일 선택"""
        file_path = filedialog.askopenfilename(
            title="XML 파일 선택",
            filetypes=[("XML 파일", "*.xml"), ("모든 파일", "*.*")]
        )
        
        if file_path:
            self.xml_file_path = file_path
            self.xml_path_label.config(text=os.path.basename(file_path), foreground="black")
            self.load_single_xml_file(file_path)
    
    def select_xml_folder(self):
        """XML 폴더 선택"""
        folder_path = filedialog.askdirectory(title="XML 파일들이 있는 폴더 선택")
        
        if folder_path:
            self.xml_folder_path = folder_path
            self.xml_path_label.config(text=folder_path, foreground="black")
            self.load_xml_folder(folder_path)
    
    def load_single_xml_file(self, file_path):
        """단일 XML 파일 로드 및 분석"""
        try:
            tree = ET.parse(file_path)
            xml_root = tree.getroot()
            
            # XML 미리보기 표시
            with open(file_path, 'r', encoding='utf-8') as f:
                xml_content = f.read()
            
            self.xml_preview.config(state=tk.NORMAL)
            self.xml_preview.delete(1.0, tk.END)
            self.xml_preview.insert(1.0, xml_content[:1000] + 
                                   ("..." if len(xml_content) > 1000 else ""))
            self.xml_preview.config(state=tk.DISABLED)
            
            # 알람 정보 분석
            alarms = xml_root.findall(".//Alarm")
            clip = xml_root.find(".//Clip")
            filename_elem = clip.find(".//Filename") if clip is not None else None
            filename = filename_elem.text if filename_elem is not None else os.path.basename(file_path)
            
            # XML 파일 데이터 저장
            self.xml_files_data = [{
                'file_path': file_path,
                'xml_root': xml_root,
                'filename': filename,
                'alarms': alarms
            }]
            
            self.total_files = len(alarms)
            self.processed_files = 0
            self.error_count = 0
            self.update_stats()
            
            self.add_log(f"XML 파일이 로드되었습니다. {len(alarms)}개의 알람을 찾았습니다.", "SUCCESS")
            
            # 알람 정보 로그 출력
            for i, alarm in enumerate(alarms):
                start_time = alarm.find("StartTime")
                duration = alarm.find("AlarmDuration")
                description = alarm.find("AlarmDescription")
                
                start_time_text = start_time.text if start_time is not None else "Unknown"
                duration_text = duration.text if duration is not None else "Unknown"
                description_text = description.text if description is not None else "Unknown"
                
                self.add_log(f"  알람 {i+1}: {description_text} | 시작: {start_time_text} | 지속: {duration_text}")
                
        except Exception as e:
            self.add_log(f"XML 파일 로드 중 오류: {str(e)}", "ERROR")
            messagebox.showerror("오류", f"XML 파일을 읽을 수 없습니다:\n{str(e)}")
    
    def load_xml_folder(self, folder_path):
        """XML 폴더 로드 및 분석"""
        try:
            # XML 파일들 찾기
            xml_files = glob.glob(os.path.join(folder_path, "*.xml"))
            
            if not xml_files:
                self.add_log("선택한 폴더에서 XML 파일을 찾을 수 없습니다.", "ERROR")
                return
            
            self.xml_files_data = []
            self.xml_listbox.delete(0, tk.END)
            
            total_alarms = 0
            
            for xml_file in xml_files:
                try:
                    tree = ET.parse(xml_file)
                    xml_root = tree.getroot()
                    
                    # 알람 정보 분석
                    alarms = xml_root.findall(".//Alarm")
                    clip = xml_root.find(".//Clip")
                    filename_elem = clip.find(".//Filename") if clip is not None else None
                    filename = filename_elem.text if filename_elem is not None else os.path.basename(xml_file)
                    
                    # XML 파일 데이터 저장
                    self.xml_files_data.append({
                        'file_path': xml_file,
                        'xml_root': xml_root,
                        'filename': filename,
                        'alarms': alarms
                    })
                    
                    total_alarms += len(alarms)
                    
                    # 리스트박스에 추가
                    display_text = f"{os.path.basename(xml_file)} ({len(alarms)}개 알람)"
                    self.xml_listbox.insert(tk.END, display_text)
                    
                except Exception as e:
                    self.add_log(f"XML 파일 로드 실패 ({os.path.basename(xml_file)}): {str(e)}", "ERROR")
                    continue
            
            if self.xml_files_data:
                self.total_files = total_alarms
                self.processed_files = 0
                self.error_count = 0
                self.update_stats()
                
                self.add_log(f"XML 폴더에서 {len(self.xml_files_data)}개 파일, 총 {total_alarms}개 알람을 찾았습니다.", "SUCCESS")
                
                # 첫 번째 XML 파일 미리보기
                if self.xml_files_data:
                    first_xml = self.xml_files_data[0]['file_path']
                    with open(first_xml, 'r', encoding='utf-8') as f:
                        xml_content = f.read()
                    
                    self.xml_preview.config(state=tk.NORMAL)
                    self.xml_preview.delete(1.0, tk.END)
                    self.xml_preview.insert(1.0, f"[첫 번째 파일 미리보기: {os.path.basename(first_xml)}]\n\n")
                    self.xml_preview.insert(tk.END, xml_content[:800] + 
                                           ("..." if len(xml_content) > 800 else ""))
                    self.xml_preview.config(state=tk.DISABLED)
            else:
                self.add_log("유효한 XML 파일을 찾을 수 없습니다.", "ERROR")
                
        except Exception as e:
            self.add_log(f"XML 폴더 로드 중 오류: {str(e)}", "ERROR")
            messagebox.showerror("오류", f"XML 폴더를 처리할 수 없습니다:\n{str(e)}")
    
    def select_input_folder(self):
        """입력 폴더 선택"""
        folder = filedialog.askdirectory(title="입력 폴더 선택")
        if folder:
            self.input_folder.set(folder)
            self.add_log(f"입력 폴더 설정: {folder}")
    
    def select_output_folder(self):
        """출력 폴더 선택"""
        folder = filedialog.askdirectory(title="출력 폴더 선택")
        if folder:
            self.output_folder.set(folder)
            self.add_log(f"출력 폴더 설정: {folder}")
    
    def time_to_seconds(self, time_str):
        """시간 문자열을 초로 변환"""
        try:
            # HH:MM:SS 또는 H:M:S 형식 처리
            parts = time_str.split(':')
            if len(parts) == 3:
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = int(parts[2])
                return hours * 3600 + minutes * 60 + seconds
            else:
                return 0
        except:
            return 0
    
    def duration_to_seconds(self, duration_str):
        """지속시간 문자열을 초로 변환"""
        try:
            # 0:0:10 형식 처리
            parts = duration_str.split(':')
            if len(parts) == 3:
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = int(parts[2])
                return hours * 3600 + minutes * 60 + seconds
            else:
                return 10  # 기본값
        except:
            return 10
    
    def seconds_to_time(self, seconds):
        """초를 HH:MM:SS 형식으로 변환"""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
    def find_video_file(self, clip_filename):
        """클립 파일명에 해당하는 실제 비디오 파일 찾기"""
        input_dir = self.input_folder.get()
        base_name = os.path.splitext(clip_filename)[0]
        
        # 지원하는 비디오 확장자
        video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv']
        
        for ext in video_extensions:
            video_path = os.path.join(input_dir, base_name + ext)
            if os.path.exists(video_path):
                return video_path
        
        return None
    
    def cut_video(self, input_path, output_path, start_seconds, duration_seconds):
        """FFmpeg를 사용하여 비디오 자르기"""
        try:
            start_time = self.seconds_to_time(start_seconds)
            duration_time = self.seconds_to_time(duration_seconds)
            
            # FFmpeg 명령어 구성
            cmd = [
                'ffmpeg',
                '-i', input_path,
                '-ss', start_time,
                '-t', duration_time,
                '-c', 'copy',  # 재인코딩 없이 복사 (빠름)
                '-avoid_negative_ts', 'make_zero',
                output_path,
                '-y'  # 덮어쓰기
            ]
            
            # 환경변수 설정 (인코딩 문제 방지)
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            
            # FFmpeg 실행 (인코딩 문제 해결)
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, 
                                      creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                                      encoding='utf-8', errors='ignore', env=env, timeout=300)
            except subprocess.TimeoutExpired:
                return False, "처리 시간 초과 (5분)"
            except Exception as e:
                # 바이트 모드로 재시도
                try:
                    result = subprocess.run(cmd, capture_output=True,
                                          creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                                          env=env, timeout=300)
                    # 바이트를 안전하게 디코딩
                    stderr_text = result.stderr.decode('utf-8', errors='ignore') if result.stderr else ""
                    stdout_text = result.stdout.decode('utf-8', errors='ignore') if result.stdout else ""
                except Exception as e2:
                    return False, f"subprocess 실행 오류: {str(e2)}"
            else:
                stderr_text = result.stderr
                stdout_text = result.stdout
            
            if result.returncode == 0:
                return True, "성공"
            else:
                error_msg = stderr_text if stderr_text else "알 수 없는 오류"
                return False, error_msg[:200]  # 오류 메시지 길이 제한
                
        except FileNotFoundError:
            return False, "FFmpeg를 찾을 수 없습니다. FFmpeg가 설치되어 있고 PATH에 등록되어 있는지 확인하세요."
        except Exception as e:
            return False, f"예외 발생: {str(e)}"
    
    def process_videos(self):
        """비디오 처리 메인 함수"""
        try:
            if not self.xml_files_data:
                self.add_log("XML 파일이 로드되지 않았습니다.", "ERROR")
                return
            
            if not self.input_folder.get() or not self.output_folder.get():
                self.add_log("입력 폴더와 출력 폴더를 모두 설정해야 합니다.", "ERROR")
                return
            
            # 출력 폴더 생성
            os.makedirs(self.output_folder.get(), exist_ok=True)
            
            total_alarms = sum(len(xml_data['alarms']) for xml_data in self.xml_files_data)
            processed_count = 0
            
            # 각 XML 파일 처리
            for xml_idx, xml_data in enumerate(self.xml_files_data):
                xml_path = xml_data['file_path']
                xml_root = xml_data['xml_root']
                alarms = xml_data['alarms']
                
                self.add_log(f"\n=== XML 파일 처리: {os.path.basename(xml_path)} ===", "INFO")
                
                # 클립 정보 가져오기
                clip = xml_root.find(".//Clip")
                if clip is None:
                    self.add_log(f"클립 정보를 찾을 수 없습니다: {os.path.basename(xml_path)}", "ERROR")
                    continue
                
                filename_elem = clip.find(".//Filename")
                if filename_elem is None:
                    self.add_log(f"파일명 정보를 찾을 수 없습니다: {os.path.basename(xml_path)}", "ERROR")
                    continue
                
                clip_filename = filename_elem.text
                self.add_log(f"클립 파일명: {clip_filename}")
                
                # 실제 비디오 파일 찾기
                video_path = self.find_video_file(clip_filename)
                if not video_path:
                    self.add_log(f"비디오 파일을 찾을 수 없습니다: {clip_filename}", "ERROR")
                    self.error_count += len(alarms)
                    self.update_stats()
                    continue
                
                self.add_log(f"비디오 파일 발견: {video_path}")
                
                # 각 XML의 알람들 처리
                for alarm_idx, alarm in enumerate(alarms):
                    try:
                        # 진행률 업데이트
                        progress = (processed_count / total_alarms) * 100
                        self.progress['value'] = progress
                        self.progress_label.config(text=f"처리 중... {processed_count+1}/{total_alarms}")
                        self.root.update_idletasks()
                        
                        # 알람 정보 추출
                        start_time_elem = alarm.find("StartTime")
                        duration_elem = alarm.find("AlarmDuration")
                        description_elem = alarm.find("AlarmDescription")
                        
                        if start_time_elem is None or duration_elem is None:
                            self.add_log(f"  알람 {alarm_idx+1}: 시간 정보가 불완전합니다.", "ERROR")
                            self.error_count += 1
                            processed_count += 1
                            continue
                        
                        start_time_str = start_time_elem.text
                        duration_str = duration_elem.text
                        description = description_elem.text if description_elem is not None else "Alarm"
                        
                        # 시간 계산
                        start_seconds = self.time_to_seconds(start_time_str) + self.start_offset.get()
                        duration_seconds = self.duration_to_seconds(duration_str) + self.additional_duration.get()
                        
                        # 음수 시작 시간 방지
                        if start_seconds < 0:
                            duration_seconds += start_seconds  # 지속시간에서 차감
                            start_seconds = 0
                        
                        if duration_seconds <= 0:
                            self.add_log(f"  알람 {alarm_idx+1}: 유효하지 않은 지속시간", "ERROR")
                            self.error_count += 1
                            processed_count += 1
                            continue
                        
                        # 출력 파일명 생성
                        base_name = os.path.splitext(clip_filename)[0]
                        xml_base_name = os.path.splitext(os.path.basename(xml_path))[0]
                        output_filename = f"{base_name}_{xml_base_name}_alarm{alarm_idx+1:02d}_{description}_{start_time_str.replace(':', '')}.mp4"
                        output_path = os.path.join(self.output_folder.get(), output_filename)
                        
                        self.add_log(f"  알람 {alarm_idx+1} 처리 중: {start_time_str} -> {self.seconds_to_time(duration_seconds)}")
                        
                        # 비디오 자르기
                        success, message = self.cut_video(video_path, output_path, start_seconds, duration_seconds)
                        
                        if success:
                            self.add_log(f"  ✓ 알람 {alarm_idx+1} 완료: {output_filename}", "SUCCESS")
                            self.processed_files += 1
                        else:
                            self.add_log(f"  ✗ 알람 {alarm_idx+1} 실패: {message}", "ERROR")
                            self.error_count += 1
                        
                        processed_count += 1
                        self.update_stats()
                        
                    except Exception as e:
                        self.add_log(f"  ✗ 알람 {alarm_idx+1} 처리 중 오류: {str(e)}", "ERROR")
                        self.error_count += 1
                        processed_count += 1
                        self.update_stats()
            
            # 완료
            self.progress['value'] = 100
            self.progress_label.config(text="완료!")
            self.add_log(f"\n🎉 전체 처리 완료!", "SUCCESS")
            self.add_log(f"  • 처리된 XML 파일: {len(self.xml_files_data)}개", "SUCCESS")
            self.add_log(f"  • 생성된 비디오 파일: {self.processed_files}개", "SUCCESS")
            self.add_log(f"  • 오류 발생: {self.error_count}개", "SUCCESS" if self.error_count == 0 else "ERROR")
            
        except Exception as e:
            self.add_log(f"처리 중 치명적 오류: {str(e)}", "ERROR")
        finally:
            self.process_btn.config(state=tk.NORMAL, text="🚀 영상 처리 시작")
    
    def start_processing(self):
        """처리 시작 (별도 스레드에서 실행)"""
        self.process_btn.config(state=tk.DISABLED, text="처리 중...")
        self.progress['value'] = 0
        self.progress_label.config(text="")
        self.processed_files = 0
        self.error_count = 0
        self.update_stats()
        
        # 별도 스레드에서 처리 실행
        thread = threading.Thread(target=self.process_videos)
        thread.daemon = True
        thread.start()

def main():
    """메인 함수"""
    root = tk.Tk()
    
    # 아이콘 설정 (선택사항)
    try:
        root.iconbitmap(default='icon.ico')  # 아이콘 파일이 있을 경우
    except:
        pass
    
    app = KISAVideoCutter(root)
    root.mainloop()

if __name__ == "__main__":
    main()