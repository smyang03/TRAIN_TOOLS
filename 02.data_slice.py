import random
import os
import pathlib
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
import threading
import chardet
import re
from collections import defaultdict

class DataDistributorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("데이터 분배 프로그램")
        self.root.geometry("700x650")  # Slightly taller to accommodate new features
        self.root.resizable(True, True)
        
        self.input_files = []
        self.person_names = []
        self.list_file_path = None  # Variable to store the path to a list file
        
        # 파일 선택 프레임
        file_frame = tk.LabelFrame(root, text="입력 파일 선택", padx=10, pady=10)
        file_frame.pack(fill="x", padx=10, pady=5)
        
        self.file_listbox = tk.Listbox(file_frame, width=70, height=5)
        self.file_listbox.pack(side=tk.LEFT, fill="both", expand=True)
        
        file_scroll = tk.Scrollbar(file_frame)
        file_scroll.pack(side=tk.RIGHT, fill="y")
        
        self.file_listbox.config(yscrollcommand=file_scroll.set)
        file_scroll.config(command=self.file_listbox.yview)
        
        file_buttons_frame = tk.Frame(root)
        file_buttons_frame.pack(fill="x", padx=10, pady=5)
        
        tk.Button(file_buttons_frame, text="파일 추가", command=self.add_file).pack(side=tk.LEFT, padx=5)
        tk.Button(file_buttons_frame, text="파일 제거", command=self.remove_file).pack(side=tk.LEFT, padx=5)
        tk.Button(file_buttons_frame, text="모두 지우기", command=self.clear_files).pack(side=tk.LEFT, padx=5)
        tk.Button(file_buttons_frame, text="리스트 파일 로드", command=self.load_list_file).pack(side=tk.LEFT, padx=5)

        special_functions_frame = tk.LabelFrame(root, text="특수 기능", padx=10, pady=10)
        special_functions_frame.pack(fill="x", padx=10, pady=5)

        # 특수 기능 버튼들
        # 특수 기능 버튼들
        tk.Button(special_functions_frame, text="파일 줄 수 기준 분할", 
                command=self.split_file_by_count, bg="#4CAF50", 
                fg="white").pack(side=tk.LEFT, padx=5)
        # 인코딩 선택 프레임
        encoding_frame = tk.Frame(root)
        encoding_frame.pack(fill="x", padx=10, pady=5)
        
        tk.Label(encoding_frame, text="인코딩:").pack(side=tk.LEFT, padx=5)
        self.encoding_var = tk.StringVar(value="auto")
        self.encoding_combo = ttk.Combobox(encoding_frame, textvariable=self.encoding_var, 
                                           values=["auto", "utf-8", "cp949", "euc-kr", "utf-16"])
        self.encoding_combo.pack(side=tk.LEFT, padx=5)
        
        # 그룹화 전략 프레임 (신규 추가)
        grouping_frame = tk.LabelFrame(root, text="파일 그룹화 전략", padx=10, pady=10)
        grouping_frame.pack(fill="x", padx=10, pady=5)
        
        self.grouping_var = tk.StringVar(value="0")  # 기본값을 0으로 변경
        grouping_options = [
            ("전략 미사용 (모든 파일을 작업자에게 균등 분할)", "0"),  # 새 옵션 추가
            ("접두사 기반 (파일명의 시작 부분)", "1"),
            ("IP 주소와 날짜 기반 (Auto_IP-PORT_DATE 패턴)", "2"),
            ("디렉토리 경로 기반", "3"),
            ("파일명 정규식 패턴 직접 입력", "4"),
            ("자동 감지 (가장 일반적인 패턴 찾기)", "5"),
            ("파일 내용 기반 그룹화", "6"),  # 새로운 옵션 추가
            ("작업 유형 기반 그룹화 ([0]보강재(1) 등)", "7")  # 새로운 전략 추가
        ]
        
        for text, value in grouping_options:
            tk.Radiobutton(grouping_frame, text=text, variable=self.grouping_var, value=value).pack(anchor=tk.W, padx=5)
        
        # 정규식 패턴 입력 (그룹화 전략 4번에 사용)
        regex_frame = tk.Frame(grouping_frame)
        regex_frame.pack(fill="x", padx=5, pady=5)
        
        tk.Label(regex_frame, text="정규식 패턴:").pack(side=tk.LEFT, padx=5)
        self.regex_pattern = tk.Entry(regex_frame, width=40)
        self.regex_pattern.pack(side=tk.LEFT, padx=5)
        
        # 작업자 이름 프레임
        name_frame = tk.LabelFrame(root, text="작업자 이름 입력", padx=10, pady=10)
        name_frame.pack(fill="x", padx=10, pady=5)
        
        self.name_listbox = tk.Listbox(name_frame, width=70, height=5)
        self.name_listbox.pack(side=tk.LEFT, fill="both", expand=True)
        
        name_scroll = tk.Scrollbar(name_frame)
        name_scroll.pack(side=tk.RIGHT, fill="y")
        
        self.name_listbox.config(yscrollcommand=name_scroll.set)
        name_scroll.config(command=self.name_listbox.yview)
        
        name_entry_frame = tk.Frame(root)
        name_entry_frame.pack(fill="x", padx=10, pady=5)
        
        tk.Label(name_entry_frame, text="작업자 이름:").pack(side=tk.LEFT, padx=5)
        self.name_entry = tk.Entry(name_entry_frame, width=30)
        self.name_entry.pack(side=tk.LEFT, padx=5)
        
        # 작업자 수 직접 지정 (신규 추가)
        tk.Label(name_entry_frame, text="작업자 수:").pack(side=tk.LEFT, padx=5)
        self.num_workers_entry = tk.Entry(name_entry_frame, width=5)
        self.num_workers_entry.pack(side=tk.LEFT, padx=5)
        tk.Button(name_entry_frame, text="자동 생성", command=self.generate_workers).pack(side=tk.LEFT, padx=5)
        
        name_buttons_frame = tk.Frame(root)
        name_buttons_frame.pack(fill="x", padx=10, pady=5)
        
        tk.Button(name_buttons_frame, text="이름 추가", command=self.add_name).pack(side=tk.LEFT, padx=5)
        tk.Button(name_buttons_frame, text="이름 제거", command=self.remove_name).pack(side=tk.LEFT, padx=5)
        tk.Button(name_buttons_frame, text="모두 지우기", command=self.clear_names).pack(side=tk.LEFT, padx=5)
        
        # 실행 버튼
        tk.Button(root, text="데이터 분배 시작", command=self.start_distribution, bg="#4CAF50", fg="white", font=("Arial", 12, "bold"), padx=10, pady=5).pack(pady=10)
        
        # 로그 출력 영역
        log_frame = tk.LabelFrame(root, text="실행 로그", padx=10, pady=10)
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, width=80, height=10)
        self.log_text.pack(fill="both", expand=True)
        self.log_text.config(state=tk.DISABLED)

    def add_file(self):
        files = filedialog.askopenfilenames(filetypes=[("텍스트 파일", "*.txt")])
        if files:
            for file in files:
                if file not in self.input_files:
                    self.input_files.append(file)
                    self.file_listbox.insert(tk.END, file)
    
    def remove_file(self):
        try:
            selected_idx = self.file_listbox.curselection()[0]
            self.file_listbox.delete(selected_idx)
            self.input_files.pop(selected_idx)
        except IndexError:
            messagebox.showwarning("경고", "제거할 파일을 선택하세요")
    
    def clear_files(self):
        self.file_listbox.delete(0, tk.END)
        self.input_files = []
    
    def load_list_file(self):
        """리스트 파일을 로드하여 파일 목록을 가져옴"""
        list_file = filedialog.askopenfilename(filetypes=[("텍스트 파일", "*.txt")])
        if not list_file:
            return
        
        try:
            # 먼저 인코딩 감지
            encoding = self.detect_encoding(list_file)
            self.log(f"리스트 파일 인코딩: {encoding}")
            
            # 파일 읽기
            try:
                with open(list_file, 'r', encoding=encoding) as f:
                    file_paths = [line.strip() for line in f if line.strip()]
            except Exception as e:
                self.log(f"기본 방식으로 읽기 실패, 대체 방식 시도: {str(e)}")
                with open(list_file, 'rb') as f:
                    binary_data = f.read()
                    try:
                        text = binary_data.decode('utf-8', errors='replace')
                    except:
                        text = str(binary_data)
                    file_paths = [line.strip() for line in text.splitlines() if line.strip()]
            
            # 현재 목록 초기화
            self.clear_files()
            
            # 리스트 파일이 비어있는 경우
            if len(file_paths) == 0:
                self.log("리스트 파일이 비어있습니다.")
                messagebox.showwarning("경고", "리스트 파일이 비어있습니다.")
                return
            
            # 작업자 수 확인
            if not self.person_names:
                response = messagebox.askyesno("작업자 없음", 
                            "작업자가 정의되지 않았습니다. 작업자를 자동으로 생성하시겠습니까?")
                if response:
                    num_workers = simpledialog.askinteger("작업자 수", "몇 명의 작업자를 생성할까요?", 
                                                        initialvalue=3, minvalue=1, maxvalue=100)
                    if num_workers:
                        self.num_workers_entry.delete(0, tk.END)
                        self.num_workers_entry.insert(0, str(num_workers))
                        self.generate_workers()
                    else:
                        return
                else:
                    return
            
            # 작업자 수 기준으로 리스트 파일 분할
            self.split_list_by_workers(list_file, file_paths, encoding)
            
        except Exception as e:
            self.log(f"리스트 파일 로드 중 오류 발생: {str(e)}")
            messagebox.showerror("오류", f"리스트 파일 로드 중 오류 발생: {str(e)}")
    def split_list_by_workers(self, list_file, file_paths, encoding):
        """리스트 파일을 작업자 수에 맞게 분할하여 저장"""
        try:
            worker_count = len(self.person_names)
            total_files = len(file_paths)
            
            self.log(f"리스트 파일에서 {total_files}개 라인을 발견했습니다.")
            self.log(f"작업자 {worker_count}명에게 분할합니다.")
            
            # 각 작업자별로 할당할 라인 수 계산
            lines_per_worker = total_files // worker_count
            remainder = total_files % worker_count
            
            # 분할 정보 저장
            split_info = []
            start_idx = 0
            
            for i, name in enumerate(self.person_names):
                # 나머지 분배를 위한 추가 카운트
                extra = 1 if i < remainder else 0
                end_idx = start_idx + lines_per_worker + extra
                
                # 범위 검사
                if end_idx > total_files:
                    end_idx = total_files
                    
                # 현재 작업자에게 라인 할당
                worker_lines = file_paths[start_idx:end_idx]
                
                split_info.append({
                    'name': name,
                    'start_idx': start_idx,
                    'end_idx': end_idx,
                    'count': len(worker_lines),
                    'lines': worker_lines
                })
                
                start_idx = end_idx
            
            # 결과 저장 폴더 생성
            output_dir = os.path.join(os.path.dirname(list_file), "split_lists")
            os.makedirs(output_dir, exist_ok=True)
            
            # 각 작업자별로 파일 생성
            saved_files = []
            for info in split_info:
                # 작업자별 파일 생성
                output_file = os.path.join(output_dir, f"{info['name']}_파일목록.txt")
                
                with open(output_file, 'w', encoding=encoding) as f:
                    for line in info['lines']:
                        f.write(f"{line}\n")
                
                saved_files.append(output_file)
                self.log(f"{info['name']}: {info['count']}개 라인 할당 ({info['start_idx']+1}~{info['end_idx']} 라인)")
                
                # 생성된 파일을 입력 목록에 추가
                self.input_files.append(output_file)
                self.file_listbox.insert(tk.END, output_file)
            
            self.log(f"\n분할 완료: {worker_count}개의 파일이 생성되었습니다.")
            self.log(f"저장 위치: {output_dir}")
            
            # 분할 상세 정보 표시
            details = "\n".join([f"{info['name']}: {info['count']}개 라인" for info in split_info])
            messagebox.showinfo("분할 완료", 
                            f"리스트 파일이 {worker_count}개로 분할되었습니다.\n\n{details}")
            
        except Exception as e:
            self.log(f"리스트 분할 중 오류 발생: {str(e)}")
            messagebox.showerror("오류", f"리스트 분할 중 오류 발생: {str(e)}")
    def generate_workers(self):
        """지정된 수의 작업자를 자동 생성"""
        try:
            num_workers = int(self.num_workers_entry.get())
            if num_workers <= 0:
                messagebox.showwarning("경고", "작업자 수는 1 이상이어야 합니다.")
                return
            
            # 기존 목록 초기화
            self.clear_names()
            
            # 지정된 수만큼 작업자 생성
            for i in range(1, num_workers + 1):
                worker_name = f"작업자{i}"
                self.person_names.append(worker_name)
                self.name_listbox.insert(tk.END, worker_name)
            
            self.log(f"{num_workers}명의 작업자가 자동 생성되었습니다.")
            
        except ValueError:
            messagebox.showwarning("경고", "유효한 숫자를 입력하세요.")
    
    def add_name(self):
        name = self.name_entry.get().strip()
        if name:
            if name not in self.person_names:
                self.person_names.append(name)
                self.name_listbox.insert(tk.END, name)
                self.name_entry.delete(0, tk.END)
            else:
                messagebox.showwarning("경고", f"'{name}'은(는) 이미 목록에 있습니다")
        else:
            messagebox.showwarning("경고", "작업자 이름을 입력하세요")
    
    def remove_name(self):
        try:
            selected_idx = self.name_listbox.curselection()[0]
            self.name_listbox.delete(selected_idx)
            self.person_names.pop(selected_idx)
        except IndexError:
            messagebox.showwarning("경고", "제거할 이름을 선택하세요")
    
    def clear_names(self):
        self.name_listbox.delete(0, tk.END)
        self.person_names = []
    
    def log(self, message):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
    
    def detect_encoding(self, file_path):
        """파일의 인코딩을 감지하거나 선택된 인코딩을 반환합니다."""
        encoding = self.encoding_var.get()
        
        if encoding == "auto":
            # 파일 인코딩 자동 감지
            with open(file_path, 'rb') as f:
                raw_data = f.read(10000)  # 처음 10000바이트만 감지에 사용
                result = chardet.detect(raw_data)
                detected_encoding = result['encoding']
                confidence = result['confidence']
                self.log(f"감지된 인코딩: {detected_encoding} (신뢰도: {confidence:.2f})")
                
                # 신뢰도가 낮은 경우 cp949를 사용 (한국어 파일용)
                if confidence < 0.7:
                    self.log(f"신뢰도가 낮아 기본값으로 cp949를 사용합니다.")
                    return 'cp949'
                return detected_encoding
        else:
            return encoding
    
    def read_file_with_encoding(self, file_path, encoding):
        """지정된 인코딩으로 파일을 읽고, 실패 시 다른 인코딩을 시도합니다."""
        encodings_to_try = [encoding]
        
        # 기본 인코딩이 실패할 경우 시도할 인코딩 목록
        if encoding != 'cp949':
            encodings_to_try.append('cp949')
        if encoding != 'utf-8':
            encodings_to_try.append('utf-8')
        if encoding != 'ascii':
            encodings_to_try.append('ascii')
        
        for enc in encodings_to_try:
            try:
                with open(file_path, "r", encoding=enc) as file:
                    lines = file.readlines()
                self.log(f"인코딩 {enc}로 파일을 성공적으로 읽었습니다.")
                return lines
            except UnicodeDecodeError as e:
                self.log(f"인코딩 {enc}로 읽기 실패: {str(e)}")
        
        # 모든 인코딩 시도 실패 - 바이너리 읽기 시도
        try:
            self.log("텍스트 인코딩 실패, 바이너리 모드로 읽기 시도...")
            with open(file_path, "rb") as file:
                binary_data = file.read()
                # 바이너리 데이터를 문자열 라인으로 변환
                try:
                    text = binary_data.decode('utf-8', errors='replace')
                except:
                    text = str(binary_data)
                lines = text.splitlines(True)  # 줄바꿈 유지
                self.log(f"바이너리 모드로 {len(lines)}개 라인을 읽었습니다.")
                return lines
        except Exception as e:
            self.log(f"바이너리 읽기 실패: {str(e)}")
            
        # 최후의 수단: 빈 파일 가정
        self.log("경고: 파일을 읽을 수 없어 빈 리스트를 반환합니다.")
        return []
    
    # 파일 그룹화 메서드 - 패턴 목록 수정
    def group_files_by_pattern(self, file_paths):
        """선택된 그룹화 전략에 따라 파일을 그룹화"""
        groups = defaultdict(list)
        grouping_choice = self.grouping_var.get()
        
        self.log(f"그룹화 전략 {grouping_choice} 적용 중...")
        
        # 파일 내용 분석 (필요한 경우에만)
        file_contents = {}
        if grouping_choice in ["5", "6"]:  # 자동 감지나 내용 기반 그룹화에 필요
            for file_path in file_paths:
                try:
                    encoding = self.detect_encoding(file_path)
                    lines = self.read_file_with_encoding(file_path, encoding)
                    file_contents[file_path] = lines
                except Exception as e:
                    self.log(f"파일 '{file_path}' 읽기 중 오류: {str(e)}")
                    file_contents[file_path] = []
        
        # 1. 접두사 기반 그룹화
        if grouping_choice == "1":
            prefix_length = 10  # 기본값
            for file_path in file_paths:
                file_name = os.path.basename(file_path)
                prefix = file_name[:min(prefix_length, len(file_name))]
                groups[prefix].append(file_path)
                
        # 2. IP와 날짜 기반 그룹화 (개선됨)
        elif grouping_choice == "2":
            for file_path in file_paths:
                file_name = os.path.basename(file_path)
                # 개선된 정규식: Auto_IP-PORT_날짜시간 패턴
                match = re.search(r'Auto_([\d\.]+)-\d+_(\d{14})_', file_name)
                if match:
                    ip = match.group(1)
                    date = match.group(2)
                    # 날짜를 YYYYMMDD 형식으로 자름 (시간 제외)
                    date_only = date[:8]
                    group_key = f"{ip}_{date_only}"
                    groups[group_key].append(file_path)
                else:
                    # 매칭되지 않는 파일은 별도 그룹으로
                    groups['기타'].append(file_path)
                    
        # 3. 디렉토리 경로 기반 그룹화
        elif grouping_choice == "3":
            for file_path in file_paths:
                dir_path = os.path.dirname(file_path)
                # 가장 하위 디렉토리만 사용
                last_dir = os.path.basename(dir_path)
                groups[last_dir].append(file_path)
                
        # 4. 사용자 정의 정규식 패턴
        elif grouping_choice == "4":
            pattern = self.regex_pattern.get()
            if not pattern:
                messagebox.showwarning("경고", "정규식 패턴을 입력하세요.")
                return None
                
            for file_path in file_paths:
                file_name = os.path.basename(file_path)
                try:
                    match = re.search(pattern, file_name)
                    if match and match.groups():
                        # 정규식 그룹이 있는 경우 첫 번째 그룹 사용
                        group_key = match.group(1)
                        groups[group_key].append(file_path)
                    else:
                        groups['기타'].append(file_path)
                except re.error:
                    self.log(f"정규식 패턴 오류. 기본 그룹에 추가: {file_name}")
                    groups['기타'].append(file_path)
                    
        # 5. 자동 감지 (가장 일반적인 패턴 찾기) - 개선됨
        elif grouping_choice == "5":
            # 1. 샘플 파일 선택
            sample_size = min(50, len(file_paths))
            sample_files = random.sample(file_paths, sample_size) if len(file_paths) > 50 else file_paths
            sample_names = [os.path.basename(f) for f in sample_files]
            
            # 2. 여러 패턴 시도 (제공된 파일 형식에 맞게 패턴 조정)
            patterns = [
                # 패턴 이름을 한글로 변경하고 설명 추가
                (r'Auto_([\d\.]+)-\d+_(\d{8})', '아이피_날짜'),  # IP_날짜(YYYYMMDD) 패턴
                (r'Auto_([\d\.]+)-\d+_(\d{14})_(\d{14})', '아이피_시작종료시간'), # IP_시작시간_종료시간
                (r'\[(\d)\]Auto', '접두어_인덱스'),                # [0]Auto_ 같은 접두어
                (r'(\[\d\])[\w_-]+', '접두어'),                # [0]Auto_ 같은 접두어
                (r'_(\d{14})_', '날짜시간'),                      # YYYYMMDDHHMMSS
                (r'_(\d+)_(\d+)_(\d+)\.jpg$', '일련번호'),        # 끝부분 일련번호
                (r'_(\d{8})_', '날짜만'),                         # YYYYMMDD 날짜만
                (r'^([^_]+)', '첫_단어'),                         # 첫 단어
                (r'\[(\d)\](\w+)\((\d+)\)', '접두어_작업_번호'),   # [0]2용접(1) 같은 패턴
                (r'_(\d{14})_(\d{14})_', '시작종료시간'),          # 시작시간_종료시간
                (r'_(\d+)_(\d+)_(\d+)_(\d+)\.jpg$', '확장_일련번호'), # 끝부분에 일련번호가 4개인 패턴
                (r'^([^_]+)', '첫_단어')                             # 첫 단어(가장 일반적인 패턴은 마지막에 배치)
            ]
            
            # 3. 패턴별 성공률 테스트
            best_pattern = None
            best_success_rate = 0
            best_pattern_name = "기본"
            
            for pattern, pattern_name in patterns:
                success_count = 0
                for name in sample_names:
                    if re.search(pattern, name):
                        success_count += 1
                
                success_rate = success_count / len(sample_names) if sample_names else 0
                self.log(f"패턴 '{pattern_name}' 성공률: {success_rate:.1%}")
                
                if success_rate > best_success_rate:
                    best_success_rate = success_rate
                    best_pattern = pattern
                    best_pattern_name = pattern_name
            
            self.log(f"\n가장 효과적인 패턴: '{best_pattern_name}' (성공률: {best_success_rate:.1%})")
            
            # 4. 최적 패턴으로 그룹화
            if best_pattern and best_success_rate > 0.3:  # 30% 이상 매칭되면 사용
                for file_path in file_paths:
                    file_name = os.path.basename(file_path)
                    match = re.search(best_pattern, file_name)
                    if match and match.groups():
                        # 그룹이 여러 개인 경우 처리
                        if len(match.groups()) > 1:
                            if best_pattern_name == '작업유형':
                                # 작업명만 추출해서 그룹화 키로 사용
                                work_type = match.group(2).strip()  # '보강재' 또는 '콤프레셔실' 등 작업 유형
                                group_key = work_type
                            # 패턴이 '작업유형_시간'인 경우 특별 처리
                            elif best_pattern_name == '작업유형_시간':
                                # 작업명만 추출해서 그룹화 키로 사용
                                work_type = match.group(2).strip()  # '보강재' 또는 '콤프레셔실' 등 작업 유형
                                group_key = work_type
                            # 패턴이 '아이피_날짜'인 경우 특별 처리
                            if best_pattern_name == '아이피_날짜':
                                ip = match.group(1)
                                date = match.group(2)
                                group_key = f"{ip}_{date}"
                            elif best_pattern_name == '아이피_시작종료시간':
                                ip = match.group(1)
                                start_time = match.group(2)
                                date_only = start_time[:8]  # YYYYMMDD 부분만 추출
                                group_key = f"{ip}_{date_only}"
                            elif best_pattern_name == '일련번호':
                                # 마지막 숫자만으로 그룹화하면 너무 세분화될 수 있음
                                # 첫 두 숫자만 사용하여 적절히 그룹화
                                num1 = match.group(1)
                                num2 = match.group(2)
                                group_key = f"{num1}_{num2}"
                            elif best_pattern_name == '접두어_작업_번호':
                                # [0]2용접(1) 패턴 처리
                                prefix = match.group(1)
                                work_type = match.group(2)
                                num = match.group(3)
                                group_key = f"{prefix}_{work_type}"
                            elif best_pattern_name == '시작종료시간':
                                # 시작시간만 사용하여 그룹화
                                start_time = match.group(1)
                                date_only = start_time[:8]  # YYYYMMDD 부분만 추출
                                group_key = f"날짜_{date_only}"
                            elif best_pattern_name == '확장_일련번호':
                                # 첫 두 숫자만 사용
                                num1 = match.group(1)
                                num2 = match.group(2)
                                group_key = f"{num1}_{num2}"
                            else:
                                # 기본 처리: 모든 그룹을 연결
                                group_key = '_'.join(match.groups())
                        else:
                            group_key = match.group(1)
                        
                        groups[group_key].append(file_path)
                    else:
                        groups['기타'].append(file_path)
                
                # 그룹 수가 너무 많으면 일부 병합
                if len(groups) > 100:
                    self.log(f"그룹이 너무 많습니다 ({len(groups)}개). 일부 그룹을 병합합니다.")
                    new_groups = defaultdict(list)
                    
                    for group_name, files in groups.items():
                        if group_name == '기타':
                            new_groups['기타'].extend(files)
                            continue
                        
                        # 그룹명에서 접두어 또는 일부만 사용
                        if '_' in group_name:
                            main_group = group_name.split('_')[0]
                        else:
                            main_group = group_name[:min(5, len(group_name))]
                        
                        new_groups[main_group].extend(files)
                    
                    groups = new_groups
            else:
                # 유사성 또는 크기 기반 그룹화로 대체
                self.log("효과적인 패턴을 찾지 못했습니다. 대체 그룹화 방식 적용...")
                
                # 파일명 길이 기반 그룹화
                for file_path in file_paths:
                    file_name = os.path.basename(file_path)
                    length = len(file_name)
                    length_group = f"길이_{length//10*10}-{length//10*10+9}"  # 10 단위로 그룹화
                    groups[length_group].append(file_path)
        
        elif grouping_choice == "6":
            self.log("파일 내용 기반 그룹화를 시작합니다...")
            
            # 파일이 이미 읽혀있지 않으면 여기서 읽음
            if not file_contents:
                for file_path in file_paths:
                    try:
                        encoding = self.detect_encoding(file_path)
                        lines = self.read_file_with_encoding(file_path, encoding)
                        file_contents[file_path] = lines
                    except Exception as e:
                        self.log(f"파일 '{file_path}' 읽기 중 오류: {str(e)}")
                        file_contents[file_path] = []
            
            # 각 파일의 내용을 분석하여 그룹화
            for file_path, lines in file_contents.items():
                # 빈 파일 처리
                if not lines:
                    groups['빈_파일'].append(file_path)
                    continue
                
                # 내용 기반 그룹화를 위한 기준 분석
                content_type = self.analyze_file_content(lines, file_path)
                groups[content_type].append(file_path)
                
            # 그룹 정보 출력
            self.log(f"\n파일 내용에 따라 {len(groups)}개의 그룹으로 분류되었습니다:")
            for group_name, files in sorted(groups.items(), key=lambda x: len(x[1]), reverse=True):
                self.log(f"- {group_name}: {len(files)}개 파일")
        elif grouping_choice == "7":
            self.log("작업 유형 기반 그룹화를 시작합니다...")
            
            for file_path in file_paths:
                file_name = os.path.basename(file_path)
                # [0]보강재(1)_20250408 형태의 파일명에서 작업 유형 추출
                match = re.search(r'\[(\d)\]([^(]+)\((\d+)\)', file_name)
                
                if match:
                    # 작업 유형(보강재, 콤프레셔실 등)을 그룹화 키로 사용
                    work_type = match.group(2).strip()
                    groups[work_type].append(file_path)
                else:
                    # 매칭되지 않는 파일은 별도 그룹으로
                    groups['기타'].append(file_path)
        # 그룹화 결과가 없으면 모든 파일을 하나의 그룹으로
        if not groups:
            self.log("그룹화 실패. 모든 파일을 하나의 그룹으로 처리합니다.")
            groups['전체'] = file_paths.copy()
        
        # 그룹 통계 정보 출력
        self.log(f"\n파일명 패턴에 따라 {len(groups)}개의 그룹으로 분류되었습니다:")
        for group_name, files in sorted(groups.items(), key=lambda x: len(x[1]), reverse=True):
            self.log(f"- {group_name}: {len(files)}개 파일")
        
        # 작업자 수보다 그룹 수가 많은 경우 경고
        if len(groups) > len(self.person_names):
            self.log(f"\n경고: 그룹 수({len(groups)})가 작업자 수({len(self.person_names)})보다 많습니다.")
            self.log("일부 작업자는 여러 그룹의 파일을 처리해야 할 수 있습니다.")
        
        return groups

    def analyze_file_content(self, lines, file_path):
        """파일 내용을 분석하여 그룹화 기준을 반환합니다."""
        self.log(f"파일 '{os.path.basename(file_path)}'의 내용 분석 중...")
        
        # 분석에 사용할 최대 라인 수 (성능 향상을 위해)
        max_analyze_lines = min(1000, len(lines))
        sample_lines = lines[:max_analyze_lines]
        
        # 문자열로 합치기 (패턴 매칭용)
        content_sample = ''.join(sample_lines[:50])  # 처음 50줄만 사용
        
        # 1. 특정 키워드 기반 구분
        keywords = {
            '로그': ['log', 'error', 'warning', 'info', 'debug', 'exception'],
            'JSON': ['{"', '":', '"}', 'null', 'true', 'false'],
            'HTML': ['<html', '<body', '<div', '<span', '<p>', '</p>'],
            'XML': ['<?xml', '<tag', '</tag>', '<root>', '</root>'],
            'CSV': [',,,', '","', '","', '\n,'],
            '코드': ['function', 'class', 'def ', 'import ', 'from ', 'var ', 'const ', 'public ', 'private '],
            'SQL': ['SELECT ', 'FROM ', 'WHERE ', 'JOIN ', 'INSERT INTO', 'CREATE TABLE']
        }
        
        # 각 키워드 유형별 점수 계산
        scores = {k: 0 for k in keywords}
        for content_type, type_keywords in keywords.items():
            for kw in type_keywords:
                if kw.lower() in content_sample.lower():
                    scores[content_type] += 1
        
        # 최고 점수 확인
        max_score = max(scores.values()) if scores else 0
        best_types = [k for k, v in scores.items() if v == max_score and v > 0]
        
        if best_types:
            content_type = best_types[0]  # 가장 첫 번째 매칭 유형 선택
            self.log(f"  내용 분석 결과: '{content_type}' 유형으로 판단됨")
            return content_type
        
        # 2. 데이터 패턴 기반 분석
        # 숫자 비율 계산
        digit_count = sum(c.isdigit() for line in sample_lines for c in line)
        total_chars = sum(len(line) for line in sample_lines) or 1  # 0으로 나누기 방지
        digit_ratio = digit_count / total_chars
        
        # 줄 길이 패턴 분석
        line_lengths = [len(line.strip()) for line in sample_lines if line.strip()]
        avg_line_length = sum(line_lengths) / len(line_lengths) if line_lengths else 0
        
        # 3. 라인 패턴 기반 분석 (각 라인의 시작 패턴 확인)
        line_patterns = []
        for i, line in enumerate(sample_lines):
            if i >= 100:  # 처음 100줄만 확인
                break
            stripped = line.strip()
            if not stripped:
                continue
            
            # 라인의 첫 10자만 패턴으로 저장 (최대 20개)
            if len(line_patterns) < 20:
                pattern = stripped[:min(10, len(stripped))]
                if pattern and pattern not in line_patterns:
                    line_patterns.append(pattern)
        
        # 결과 결정
        if digit_ratio > 0.3:
            self.log(f"  내용 분석 결과: 숫자가 많은 데이터로 판단됨 (숫자 비율: {digit_ratio:.2f})")
            return "숫자_데이터"
        elif avg_line_length > 100:
            self.log(f"  내용 분석 결과: 긴 텍스트로 판단됨 (평균 줄 길이: {avg_line_length:.1f})")
            return "긴_텍스트"
        elif len(line_patterns) < 5 and len(sample_lines) > 20:
            self.log("  내용 분석 결과: 반복 패턴이 많은 데이터로 판단됨")
            return "반복_패턴"
        else:
            # 특별한 패턴이 발견되지 않으면 내용 분할 전략 적용
            # 파일 크기에 따라 그룹화
            total_lines = len(lines)
            if total_lines < 1000:
                return "작은_파일(1K미만)"
            elif total_lines < 10000:
                return "중간_파일(10K미만)"
            elif total_lines < 100000:
                return "큰_파일(100K미만)"
            else:
                return "매우큰_파일(100K이상)"
    def distribute_data(self):
        """파일 리스트 내의 파일 경로들을 그룹화하고 작업자에게 분배합니다."""
        if not self.input_files:
            messagebox.showerror("오류", "입력 파일을 하나 이상 추가하세요")
            return
        
        if not self.person_names:
            messagebox.showerror("오류", "작업자 이름을 하나 이상 추가하세요")
            return
        
        person_count = len(self.person_names)
        total_files = len(self.input_files)
        
        # 콘텐츠 분할 모드 선택 여부 확인
        content_split_mode = messagebox.askyesno("분배 방식 선택", 
                                            "파일 내용을 작업자 수에 맞게 분할하시겠습니까?\n\n"
                                            "'예': 각 파일의 내용을 작업자 수에 맞게 나눕니다.\n"
                                            "'아니오': 파일 단위로 작업자에게 분배합니다.")
        
        # ===== 1단계: 모든 리스트 파일에서 경로 수집 =====
        self.log("===== 1단계: 파일 리스트에서 경로 수집 =====")
        all_paths = []
        file_path_sources = {}  # 각 경로가 어느 파일에서 왔는지 추적
        
        for list_file in self.input_files:
            self.log(f"파일 '{os.path.basename(list_file)}' 읽는 중...")
            
            try:
                # 파일 인코딩 감지
                encoding = self.detect_encoding(list_file)
                
                # 파일 읽기
                lines = self.read_file_with_encoding(list_file, encoding)
                valid_paths = []
                
                # 각 줄을 경로로 처리
                for line in lines:
                    path = line.strip()
                    if path:  # 빈 줄 제외
                        valid_paths.append(path)
                        # 이 경로가 어느 파일에서 왔는지 저장
                        file_path_sources[path] = list_file
                
                self.log(f"총 {len(valid_paths)}개의 유효한 경로를 발견했습니다.")
                all_paths.extend(valid_paths)
                
            except Exception as e:
                self.log(f"파일 '{list_file}' 처리 중 오류 발생: {str(e)}")
        
        if not all_paths:
            self.log("유효한 경로를 찾지 못했습니다.")
            messagebox.showwarning("경고", "리스트 파일에서 유효한 경로를 찾지 못했습니다.")
            return
        
        self.log(f"\n총 {len(all_paths)}개의 경로를 수집했습니다.")
        
        # ===== 2단계: 선택된 패턴에 따라 경로 그룹화 =====
        self.log("\n===== 2단계: 경로를 패턴에 따라 그룹화 =====")
        grouping_choice = self.grouping_var.get()
        
        # 그룹화 전략 표시
        strategy_map = {
            "0": "전략 미사용 (균등 분할)",
            "1": "접두사 기반 분할",
            "2": "IP/날짜 기반 분할",
            "3": "디렉토리 경로 기반 분할",
            "4": "사용자 정의 정규식 패턴 분할",
            "5": "자동 감지 패턴 분할",
            "6": "파일 내용 기반 분할",
            "7": "작업 유형 기반 분할"
        }
        
        self.log(f"선택된 그룹화 전략: {strategy_map.get(grouping_choice, '알 수 없음')}")
        
        # 경로 그룹화
        path_groups = defaultdict(list)
        
        # 0. 전략 미사용 - 모든 파일을 하나의 그룹으로
        if grouping_choice == "0":
            path_groups["전체"] = all_paths
        
        # 1. 접두사 기반 그룹화
        elif grouping_choice == "1":
            prefix_length = 10  # 기본값
            for path in all_paths:
                file_name = os.path.basename(path)
                prefix = file_name[:min(prefix_length, len(file_name))]
                path_groups[prefix].append(path)
        
        # 2. IP와 날짜 기반 그룹화
        elif grouping_choice == "2":
            for path in all_paths:
                file_name = os.path.basename(path)
                # Auto_IP-PORT_날짜시간 패턴
                match = re.search(r'Auto_([\d\.]+)-\d+_(\d{14})_', file_name)
                if match:
                    ip = match.group(1)
                    date = match.group(2)
                    # 날짜를 YYYYMMDD 형식으로 자름 (시간 제외)
                    date_only = date[:8]
                    group_key = f"{ip}_{date_only}"
                    path_groups[group_key].append(path)
                else:
                    # 매칭되지 않는 파일은 별도 그룹으로
                    path_groups['기타'].append(path)
        
        # 3. 디렉토리 경로 기반 그룹화
        elif grouping_choice == "3":
            for path in all_paths:
                dir_path = os.path.dirname(path)
                # 가장 하위 디렉토리만 사용
                last_dir = os.path.basename(dir_path)
                path_groups[last_dir].append(path)
        
        # 4. 사용자 정의 정규식 패턴
        elif grouping_choice == "4":
            pattern = self.regex_pattern.get()
            if not pattern:
                messagebox.showwarning("경고", "정규식 패턴을 입력하세요.")
                return
            
            for path in all_paths:
                file_name = os.path.basename(path)
                try:
                    match = re.search(pattern, file_name)
                    if match and match.groups():
                        # 정규식 그룹이 있는 경우 첫 번째 그룹 사용
                        group_key = match.group(1)
                        path_groups[group_key].append(path)
                    else:
                        path_groups['기타'].append(path)
                except re.error:
                    self.log(f"정규식 패턴 오류. 기본 그룹에 추가: {file_name}")
                    path_groups['기타'].append(path)
        
        # 5. 자동 감지 (가장 일반적인 패턴 찾기)
        elif grouping_choice == "5":
            # 샘플 경로 선택
            sample_size = min(50, len(all_paths))
            sample_paths = random.sample(all_paths, sample_size) if len(all_paths) > 50 else all_paths
            sample_names = [os.path.basename(p) for p in sample_paths]
            
            # 여러 패턴 시도
            patterns = [
                # 작업 유형 기반 패턴
                (r'\[(\d)\]([^(]+)\((\d+)\)', '작업유형'),           # [0]보강재(1) 같은 패턴
                # IP 및 날짜 패턴
                (r'Auto_([\d\.]+)-\d+_(\d{8})', '아이피_날짜'),      # IP_날짜(YYYYMMDD) 패턴
                (r'Auto_([\d\.]+)-\d+_(\d{14})_(\d{14})', '아이피_시작종료시간'), # IP_시작시간_종료시간
                # 접두어 패턴
                (r'\[(\d)\]Auto', '접두어_인덱스'),                   # [0]Auto_ 같은 접두어
                (r'(\[\d\])[\w_-]+', '접두어'),                       # [0]Auto_ 같은 접두어
                # 날짜 패턴
                (r'_(\d{14})_', '날짜시간'),                         # YYYYMMDDHHMMSS
                (r'_(\d{8})_', '날짜만'),                           # YYYYMMDD 날짜만
                # 작업 관련 패턴
                (r'\[(\d)\](\w+)\((\d+)\)_(\d{14})_(\d{14})_', '작업유형_시간'),  # [0]보강재(1)_시작시간_종료시간
                (r'_(\d{14})_(\d{14})_', '시작종료시간'),             # 시작시간_종료시간
                # 일련번호 패턴
                (r'_(\d+)_(\d+)_(\d+)\.jpg$', '일련번호'),           # 끝부분 일련번호
                (r'_(\d+)_(\d+)_(\d+)_(\d+)$', '확장_일련번호'),      # 끝부분에 일련번호가 4개인 패턴
                # 기본 패턴
                (r'^([^_]+)', '첫_단어')                             # 첫 단어(가장 일반적인 패턴은 마지막에 배치)
            ]
            
            # 패턴별 성공률 테스트
            best_pattern = None
            best_success_rate = 0
            best_pattern_name = "기본"
            
            for pattern, pattern_name in patterns:
                success_count = 0
                for name in sample_names:
                    if re.search(pattern, name):
                        success_count += 1
                
                success_rate = success_count / len(sample_names) if sample_names else 0
                self.log(f"패턴 '{pattern_name}' 성공률: {success_rate:.1%}")
                
                if success_rate > best_success_rate:
                    best_success_rate = success_rate
                    best_pattern = pattern
                    best_pattern_name = pattern_name
            
            self.log(f"\n가장 효과적인 패턴: '{best_pattern_name}' (성공률: {best_success_rate:.1%})")
            
            # 최적 패턴으로 그룹화
            if best_pattern and best_success_rate > 0.3:  # 30% 이상 매칭되면 사용
                for path in all_paths:
                    file_name = os.path.basename(path)
                    match = re.search(best_pattern, file_name)
                    if match and match.groups():
                        # 그룹이 여러 개인 경우 처리
                        if len(match.groups()) > 1:
                            if best_pattern_name == '작업유형':
                                # 작업명만 추출해서 그룹화 키로 사용
                                work_type = match.group(2).strip()  # '보강재' 또는 '콤프레셔실' 등 작업 유형
                                group_key = work_type
                            elif best_pattern_name == '작업유형_시간':
                                # 작업명만 추출해서 그룹화 키로 사용
                                work_type = match.group(2).strip()  # '보강재' 또는 '콤프레셔실' 등 작업 유형
                                group_key = work_type
                            elif best_pattern_name == '아이피_날짜':
                                ip = match.group(1)
                                date = match.group(2)
                                group_key = f"{ip}_{date}"
                            elif best_pattern_name == '아이피_시작종료시간':
                                ip = match.group(1)
                                start_time = match.group(2)
                                date_only = start_time[:8]  # YYYYMMDD 부분만 추출
                                group_key = f"{ip}_{date_only}"
                            elif best_pattern_name == '일련번호':
                                # 마지막 숫자만으로 그룹화하면 너무 세분화될 수 있음
                                # 첫 두 숫자만 사용하여 적절히 그룹화
                                num1 = match.group(1)
                                num2 = match.group(2)
                                group_key = f"{num1}_{num2}"
                            elif best_pattern_name == '접두어_작업_번호':
                                # [0]2용접(1) 패턴 처리
                                prefix = match.group(1)
                                work_type = match.group(2)
                                num = match.group(3)
                                group_key = f"{work_type}"  # 작업 유형만 사용
                            elif best_pattern_name == '시작종료시간':
                                # 시작시간만 사용하여 그룹화
                                start_time = match.group(1)
                                date_only = start_time[:8]  # YYYYMMDD 부분만 추출
                                group_key = f"날짜_{date_only}"
                            elif best_pattern_name == '확장_일련번호':
                                # 첫 두 숫자만 사용
                                num1 = match.group(1)
                                num2 = match.group(2)
                                group_key = f"{num1}_{num2}"
                            else:
                                # 기본 처리: 모든 그룹을 연결
                                group_key = '_'.join(match.groups())
                        else:
                            group_key = match.group(1)
                        
                        path_groups[group_key].append(path)
                    else:
                        path_groups['기타'].append(path)
            else:
                # 유사성 또는 크기 기반 그룹화로 대체
                self.log("효과적인 패턴을 찾지 못했습니다. 대체 그룹화 방식 적용...")
                
                # 파일명 길이 기반 그룹화
                for path in all_paths:
                    file_name = os.path.basename(path)
                    length = len(file_name)
                    length_group = f"길이_{length//10*10}-{length//10*10+9}"  # 10 단위로 그룹화
                    path_groups[length_group].append(path)
        
        # 6. 파일 내용 기반 그룹화
        elif grouping_choice == "6":
            self.log("파일 내용 기반 그룹화를 시작합니다...")
            
            # 먼저 모든 파일의 내용을 읽어서 분석
            for path in all_paths:
                try:
                    # 파일이 실제로 존재하는지 확인
                    if not os.path.exists(path):
                        self.log(f"경로가 존재하지 않습니다: {path}")
                        path_groups['유효하지_않은_경로'].append(path)
                        continue
                    
                    # 파일 인코딩 감지 및 내용 읽기
                    encoding = self.detect_encoding(path)
                    with open(path, 'r', encoding=encoding) as f:
                        content = f.read(5000)  # 처음 5000자만 분석
                    
                    # 내용 분석
                    # 1. 특정 키워드 기반 구분
                    keywords = {
                        '로그': ['log', 'error', 'warning', 'info', 'debug', 'exception'],
                        'JSON': ['{"', '":', '"}', 'null', 'true', 'false'],
                        'HTML': ['<html', '<body', '<div', '<span', '<p>', '</p>'],
                        'XML': ['<?xml', '<tag', '</tag>', '<root>', '</root>'],
                        'CSV': [',,,', '","', '","', '\n,'],
                        '코드': ['function', 'class', 'def ', 'import ', 'from ', 'var ', 'const '],
                        'SQL': ['SELECT ', 'FROM ', 'WHERE ', 'JOIN ', 'INSERT INTO', 'CREATE TABLE']
                    }
                    
                    # 각 키워드 유형별 점수 계산
                    scores = {k: 0 for k in keywords}
                    for content_type, type_keywords in keywords.items():
                        for kw in type_keywords:
                            if kw.lower() in content.lower():
                                scores[content_type] += 1
                    
                    # 최고 점수 확인
                    max_score = max(scores.values()) if scores else 0
                    best_types = [k for k, v in scores.items() if v == max_score and v > 0]
                    
                    if best_types:
                        content_type = best_types[0]  # 가장 첫 번째 매칭 유형 선택
                        path_groups[content_type].append(path)
                    else:
                        # 숫자 비율 계산
                        digit_count = sum(c.isdigit() for c in content)
                        total_chars = len(content) or 1  # 0으로 나누기 방지
                        digit_ratio = digit_count / total_chars
                        
                        if digit_ratio > 0.3:
                            path_groups["숫자_데이터"].append(path)
                        elif len(content) > 1000:
                            path_groups["긴_텍스트"].append(path)
                        else:
                            path_groups["일반_텍스트"].append(path)
                
                except Exception as e:
                    self.log(f"파일 '{path}' 내용 분석 중 오류: {str(e)}")
                    path_groups['분석실패'].append(path)
        
        # 7. 작업 유형 기반 그룹화
        elif grouping_choice == "7":
            self.log("작업 유형 기반 그룹화를 시작합니다...")
            
            for path in all_paths:
                file_name = os.path.basename(path)
                # [0]보강재(1)_20250408 형태의 파일명에서 작업 유형 추출
                match = re.search(r'\[(\d)\]([^(]+)\((\d+)\)', file_name)
                
                if match:
                    # 작업 유형(보강재, 콤프레셔실 등)을 그룹화 키로 사용
                    work_type = match.group(2).strip()
                    path_groups[work_type].append(path)
                else:
                    # 매칭되지 않는 파일은 별도 그룹으로
                    path_groups['기타'].append(path)
        
        # 그룹화 결과가 없으면 모든 경로를 하나의 그룹으로
        if not path_groups:
            self.log("그룹화 실패. 모든 경로를 하나의 그룹으로 처리합니다.")
            path_groups['전체'] = all_paths.copy()
        
        # 그룹 통계 정보 출력
        self.log(f"\n경로가 {len(path_groups)}개의 그룹으로 분류되었습니다:")
        for group_name, paths in sorted(path_groups.items(), key=lambda x: len(x[1]), reverse=True):
            self.log(f"- {group_name}: {len(paths)}개 경로")
        
        # 작업자 수보다 그룹 수가 많은 경우 경고
        if len(path_groups) > person_count:
            self.log(f"\n경고: 그룹 수({len(path_groups)})가 작업자 수({person_count})보다 많습니다.")
        
        # ===== 3단계: 내용 분할 또는 파일 단위 분배 =====
        if content_split_mode:
            # 내용 분할 모드: 각 그룹의 경로들을 작업자 간에 균등하게 분할
            self.log("\n===== 3단계: 그룹 내용 분할 및 작업자 할당 =====")
            
            # 작업자별 할당 딕셔너리 초기화
            worker_assignments = {name: [] for name in self.person_names}
            
            # 큰 그룹부터 순서대로 처리
            sorted_groups = sorted(path_groups.items(), key=lambda x: len(x[1]), reverse=True)
            
            # 각 그룹을 작업자에게 분배
            for group_name, group_paths in sorted_groups:
                self.log(f"\n그룹 '{group_name}' ({len(group_paths)}개 경로) 분배 중...")
                
                # 그룹 내 경로를 섞어서 랜덤성 부여
                random.shuffle(group_paths)
                
                # 작업자 수에 맞게 경로 분할
                paths_per_worker = len(group_paths) // person_count
                remainder = len(group_paths) % person_count
                
                start_idx = 0
                for i, name in enumerate(self.person_names):
                    # 나머지 분배
                    extra = 1 if i < remainder else 0
                    end_idx = start_idx + paths_per_worker + extra
                    
                    # 범위 검사
                    if end_idx > len(group_paths):
                        end_idx = len(group_paths)
                    
                    # 현재 작업자에게 경로 할당
                    worker_paths = group_paths[start_idx:end_idx]
                    worker_assignments[name].extend(worker_paths)
                    
                    self.log(f"- {name}: {len(worker_paths)}개 경로 할당")
                    start_idx = end_idx
            
            # 작업자별 총 할당 수 출력
            self.log("\n작업자별 총 할당된 경로 수:")
            for name, paths in worker_assignments.items():
                self.log(f"{name}: {len(paths)}개 경로")
            
            # 작업자별 파일 생성
            self.log("\n===== 4단계: 작업자별 파일 생성 =====")
            
            # 결과 저장 폴더 생성
            save_dir = os.path.dirname(self.input_files[0])
            output_dir = os.path.join(save_dir, "split_paths")
            os.makedirs(output_dir, exist_ok=True)
            
            # 각 작업자별 파일 생성
            for name, paths in worker_assignments.items():
                if not paths:
                    self.log(f"{name}에게 할당된 경로가 없습니다.")
                    continue
                
                # 작업자 디렉토리 생성
                worker_dir = os.path.join(output_dir, name)
                os.makedirs(worker_dir, exist_ok=True)
                
                # 경로를 출처 파일별로 그룹화
                source_paths = defaultdict(list)
                for path in paths:
                    source_file = file_path_sources.get(path, "unknown")
                    source_name = os.path.basename(source_file)
                    source_paths[source_name].append(path)
                
                # 출처 파일별로 별도 파일 생성
                for source_name, source_group_paths in source_paths.items():
                    # 출력 파일명 생성
                    output_file = os.path.join(worker_dir, f"{source_name}_split.txt")
                    
                    # 경로 저장
                    with open(output_file, 'w', encoding='utf-8') as f:
                        for path in source_group_paths:
                            f.write(f"{path}\n")
                    
                    self.log(f"- {name}의 {source_name} 파일 저장 완료: {len(source_group_paths)}개 경로")
            
        else:
            # 파일 단위 분배 모드: 그룹 단위로 작업자 할당
            self.log("\n===== 3단계: 그룹 단위 작업자 할당 =====")
            
            # 작업자별 할당 딕셔너리 초기화
            worker_assignments = {name: [] for name in self.person_names}
            
            # 그룹 크기에 따라 내림차순 정렬
            sorted_groups = sorted(path_groups.items(), key=lambda x: len(x[1]), reverse=True)
            
            # 그룹을 작업자에게 할당 (그룹 보존)
            if len(sorted_groups) <= person_count:
                # 그룹 수가 작업자 수보다 적거나 같은 경우, 각 그룹을 한 명의 작업자에게 할당
                self.log("각 그룹을 개별 작업자에게 할당합니다.")
                
                for i, (group_name, group_paths) in enumerate(sorted_groups):
                    worker_name = self.person_names[i % person_count]
                    worker_assignments[worker_name].extend(group_paths)
                    self.log(f"- 그룹 '{group_name}'의 {len(group_paths)}개 경로를 {worker_name}에게 할당")
            else:
                # 그룹 수가 작업자 수보다 많은 경우, 큰 그룹부터 균등하게 분배
                self.log("그룹을 작업자에게 균등하게 할당합니다.")
                
                # 각 작업자에게 할당할 그룹 수 계산
                total_groups = len(sorted_groups)
                groups_per_worker = total_groups // person_count
                remainder = total_groups % person_count
                
                # 작업자별 그룹 할당
                worker_idx = 0
                assigned_groups = 0
                
                for group_name, group_paths in sorted_groups:
                    worker_name = self.person_names[worker_idx]
                    worker_assignments[worker_name].extend(group_paths)
                    self.log(f"- 그룹 '{group_name}'의 {len(group_paths)}개 경로를 {worker_name}에게 할당")
                    
                    # 다음 작업자로 이동 여부 결정
                    assigned_groups += 1
                    groups_for_current_worker = groups_per_worker + (1 if worker_idx < remainder else 0)
                    
                    if assigned_groups % groups_for_current_worker == 0:
                        worker_idx = (worker_idx + 1) % person_count
            
            # 작업자별 총 할당 수 출력
            self.log("\n작업자별 총 할당된 경로 수:")
            for name, paths in worker_assignments.items():
                self.log(f"{name}: {len(paths)}개 경로")
            
            # 불균형 체크
            empty_workers = [name for name, paths in worker_assignments.items() if not paths]
            if empty_workers:
                self.log(f"\n경고: {len(empty_workers)}명의 작업자에게 경로가 할당되지 않았습니다.")
                response = messagebox.askyesno("분배 불균형", 
                                            f"{', '.join(empty_workers)}에게 경로가 할당되지 않았습니다.\n"
                                            f"모든 작업자에게 균등하게 재분배하시겠습니까?")
                
                if response:
                    # 모든 경로를 다시 수집하여 순환 방식으로 재분배
                    all_paths_list = []
                    for paths in worker_assignments.values():
                        all_paths_list.extend(paths)
                    
                    # 순환 방식으로 재분배
                    self.log("\n모든 경로를 작업자에게 순환 방식으로 재분배합니다...")
                    random.shuffle(all_paths_list)  # 랜덤 분배
                    worker_assignments = {name: [] for name in self.person_names}
                    
                    for i, path in enumerate(all_paths_list):
                        worker_idx = i % person_count
                        name = self.person_names[worker_idx]
                        worker_assignments[name].append(path)

                    
                    # 재분배 결과
                    self.log("\n재분배 결과:")
                    for name, paths in worker_assignments.items():
                        self.log(f"{name}: {len(paths)}개 경로")
            
            # 작업자별 파일 생성
            self.log("\n===== 4단계: 작업자별 파일 생성 =====")
            
            # 결과 저장 폴더 생성
            save_dir = os.path.dirname(self.input_files[0])
            output_dir = os.path.join(save_dir, "assigned_paths")
            os.makedirs(output_dir, exist_ok=True)
            
            # 각 작업자별 파일 생성
            for name, paths in worker_assignments.items():
                if not paths:
                    self.log(f"{name}에게 할당된 경로가 없습니다.")
                    continue
                
                # 작업자 디렉토리 생성
                worker_dir = os.path.join(output_dir, name)
                os.makedirs(worker_dir, exist_ok=True)
                
                # 경로를 출처 파일별로 그룹화
                source_paths = defaultdict(list)
                for path in paths:
                    source_file = file_path_sources.get(path, "unknown")
                    source_name = os.path.basename(source_file)
                    source_paths[source_name].append(path)
                
                # 출처 파일별로 별도 파일 생성
                for source_name, source_group_paths in source_paths.items():
                    # 출력 파일명 생성
                    output_file = os.path.join(worker_dir, f"{source_name}_assigned.txt")
                    
                    # 경로 저장
                    with open(output_file, 'w', encoding='utf-8') as f:
                        for path in source_group_paths:
                            f.write(f"{path}\n")
                    
                    self.log(f"- {name}의 {source_name} 파일 저장 완료: {len(source_group_paths)}개 경로")
        
        # 작업 완료 메시지
        self.log("\n모든 작업이 완료되었습니다!")
        messagebox.showinfo("완료", f"파일 경로가 {person_count}명의 작업자에게 분배되었습니다!")
        return

    def split_file_by_count(self):
        """파일을 작업자 수 또는 지정한 개수로 균등하게 분할하는 함수"""
        # 파일 선택
        file_path = filedialog.askopenfilename(title="분할할 파일 선택", filetypes=[("텍스트 파일", "*.txt")])
        if not file_path:
            return
        
        # 분할 방식 선택
        split_mode = messagebox.askyesno("분할 방식 선택", 
                                    "분할 방식을 선택하세요.\n\n"
                                    "'예': 작업자 수에 맞게 균등하게 분할\n"
                                    "'아니오': 지정한 줄 수 단위로 분할")
        
        if split_mode:  # 작업자 수에 맞게 균등 분할
            if not self.person_names:
                # 작업자가 없는 경우 분할 개수 직접 입력
                from tkinter import simpledialog
                parts_count = simpledialog.askinteger("분할 개수 입력", "파일을 몇 개로 분할하시겠습니까?", 
                                                initialvalue=3, minvalue=2, maxvalue=100)
                if not parts_count:
                    return
            else:
                # 기존 작업자 수 사용
                parts_count = len(self.person_names)
                
            self.log(f"\n===== 파일을 {parts_count}개로 균등하게 분할 =====")
        else:  # 줄 수 단위로 분할
            from tkinter import simpledialog
            lines_per_file = simpledialog.askinteger("분할 줄 수 입력", "몇 줄 단위로 분할하시겠습니까?", 
                                                initialvalue=1000, minvalue=10, maxvalue=100000)
            if not lines_per_file:
                return
            self.log(f"\n===== 파일을 {lines_per_file}줄 단위로 분할 =====")
        
        file_name = os.path.basename(file_path)
        self.log(f"선택된 파일: {file_name}")
        
        try:
            # 파일 인코딩 감지
            encoding = self.detect_encoding(file_path)
            self.log(f"인코딩: {encoding}")
            
            # 파일 읽기
            lines = self.read_file_with_encoding(file_path, encoding)
            total_lines = len(lines)
            
            if total_lines == 0:
                self.log("파일이 비어있습니다.")
                messagebox.showwarning("경고", "파일이 비어있습니다.")
                return
            
            # 저장 디렉토리 설정
            file_dir = os.path.dirname(file_path)
            base_name, ext = os.path.splitext(file_name)
            save_dir = os.path.join(file_dir, f"{base_name}_split")
            os.makedirs(save_dir, exist_ok=True)
            
            created_files = []
            
            if split_mode:  # 작업자 수에 맞게 균등 분할
                self.log(f"총 {total_lines}줄을 {parts_count}개로 균등하게 분할합니다.")
                
                # 균등 분할을 위한 계산
                base_lines_per_part = total_lines // parts_count
                remainder = total_lines % parts_count
                
                # 파일 분할
                start_idx = 0
                
                for i in range(parts_count):
                    # 나머지 분배 (앞쪽 파트들에 1줄씩 추가)
                    extra = 1 if i < remainder else 0
                    lines_in_this_part = base_lines_per_part + extra
                    
                    end_idx = start_idx + lines_in_this_part
                    
                    # 현재 파트에 라인 할당
                    file_lines = lines[start_idx:end_idx]
                    line_count = len(file_lines)
                    
                    # 파일명에 범위 정보 추가
                    output_file = os.path.join(
                        save_dir, 
                        f"{base_name}_part{i+1}_{start_idx+1}-{end_idx}{ext}"
                    )
                    
                    # 파일 저장
                    with open(output_file, 'w', encoding=encoding) as f:
                        f.writelines(file_lines)
                    
                    created_files.append(output_file)
                    self.log(f"- 파트 {i+1}: {line_count}줄 ({start_idx+1}~{end_idx}줄)")
                    start_idx = end_idx
                    
                self.log(f"\n분할 완료: {parts_count}개의 파일이 생성되었습니다.")
                
            else:  # 줄 수 단위로 분할
                # 분할 파일 개수 계산
                split_count = (total_lines + lines_per_file - 1) // lines_per_file  # 올림 나눗셈
                
                self.log(f"총 {total_lines}줄을 {lines_per_file}줄 단위로 분할합니다.")
                self.log(f"총 {split_count}개의 파일이 생성될 예정입니다.")
                
                # 파일 분할
                for i in range(split_count):
                    start_idx = i * lines_per_file
                    end_idx = min(start_idx + lines_per_file, total_lines)
                    
                    # 현재 파일에 라인 할당
                    file_lines = lines[start_idx:end_idx]
                    line_count = len(file_lines)
                    
                    # 파일명에 범위 정보 추가
                    output_file = os.path.join(
                        save_dir, 
                        f"{base_name}_part{i+1}_{start_idx+1}-{end_idx}{ext}"
                    )
                    
                    # 파일 저장
                    with open(output_file, 'w', encoding=encoding) as f:
                        f.writelines(file_lines)
                    
                    created_files.append(output_file)
                    self.log(f"- 파일 {i+1}: {line_count}줄 ({start_idx+1}~{end_idx}줄)")
                
                self.log(f"\n분할 완료: {split_count}개의 파일이 생성되었습니다.")
            
            self.log(f"저장 위치: {save_dir}")
            
            # 생성된 파일을 입력 목록에 추가할지 물어보기
            response = messagebox.askyesno("파일 추가", "생성된 파일을 입력 목록에 추가하시겠습니까?")
            if response:
                for file in created_files:
                    if file not in self.input_files:
                        self.input_files.append(file)
                        self.file_listbox.insert(tk.END, file)
                self.log("생성된 파일들을 입력 목록에 추가했습니다.")
            
            messagebox.showinfo("완료", f"파일 분할이 완료되었습니다!\n저장 위치: {save_dir}")
            
        except Exception as e:
            self.log(f"파일 분할 중 오류 발생: {str(e)}")
            messagebox.showerror("오류", f"파일 분할 중 오류 발생: {str(e)}")

    def start_distribution(self):
        # 버튼 비활성화
        for widget in self.root.winfo_children():
            if isinstance(widget, tk.Button):
                widget.config(state=tk.DISABLED)
        
        # 로그 초기화
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
        
        # 별도 스레드에서 분배 작업 실행
        thread = threading.Thread(target=self.run_distribution)
        thread.daemon = True
        thread.start()
    
    def run_distribution(self):
        try:
            self.distribute_data()
        finally:
            # 작업 완료 후 버튼 다시 활성화
            self.root.after(0, self.enable_buttons)
    
    def enable_buttons(self):
        for widget in self.root.winfo_children():
            if isinstance(widget, tk.Button):
                widget.config(state=tk.NORMAL)

def main():
    root = tk.Tk()
    app = DataDistributorApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()