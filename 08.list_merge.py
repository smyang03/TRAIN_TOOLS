
import os
import glob
import tkinter as tk
from tkinter import filedialog, messagebox, ttk



class FilePathCombinerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("파일 경로 결합 및 교체 도구")
        self.root.geometry("650x650")
        self.root.resizable(True, True)
        
        # 변수 초기화
        self.input_files = []  # 입력 파일 리스트
        self.output_file = tk.StringVar()
        self.operation = tk.StringVar(value="combine")  # 기본값은 '결합'
        self.replacements = []  # 교체 단어 쌍 리스트 (old, new)
        
        # GUI 구성
        self.create_widgets()
    
    def create_widgets(self):
        # 프레임 구성
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 노트북(탭) 생성
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # 탭 1: 파일 합치기
        self.combine_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.combine_tab, text="파일 합치기")
        
        # 탭 2: 단어 교체
        self.replace_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.replace_tab, text="단어 교체")
        
        # 탭 1 구성 (파일 합치기)
        self.setup_combine_tab()
        
        # 탭 2 구성 (단어 교체)
        self.setup_replace_tab()
    
    def setup_combine_tab(self):
        # 입력 파일 선택 영역
        input_frame = ttk.LabelFrame(self.combine_tab, text="입력 파일", padding=10)
        input_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 파일 패턴 입력 및 추가 버튼
        input_pattern_frame = ttk.Frame(input_frame)
        input_pattern_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(input_pattern_frame, text="파일 또는 패턴:").pack(side=tk.LEFT, padx=5)
        self.input_pattern_entry = ttk.Entry(input_pattern_frame, width=40)
        self.input_pattern_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        ttk.Button(input_pattern_frame, text="찾아보기", command=self.browse_input_files).pack(side=tk.LEFT, padx=5)
        ttk.Button(input_pattern_frame, text="추가", command=self.add_input_file).pack(side=tk.LEFT, padx=5)
        
        # 입력 파일 목록 프레임
        files_frame = ttk.Frame(input_frame)
        files_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # 입력 파일 목록 (리스트박스 + 스크롤바)
        list_frame = ttk.Frame(files_frame)
        list_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.file_listbox = tk.Listbox(list_frame, height=10)
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        list_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.file_listbox.yview)
        list_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_listbox.configure(yscrollcommand=list_scrollbar.set)
        
        # 파일 목록 버튼 프레임
        list_btn_frame = ttk.Frame(files_frame)
        list_btn_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=5)
        
        ttk.Button(list_btn_frame, text="선택 삭제", command=self.remove_selected_file).pack(side=tk.TOP, fill=tk.X, pady=2)
        ttk.Button(list_btn_frame, text="모두 삭제", command=self.clear_files).pack(side=tk.TOP, fill=tk.X, pady=2)
        
        # 출력 파일 선택 영역
        output_frame = ttk.LabelFrame(self.combine_tab, text="출력 파일", padding=10)
        output_frame.pack(fill=tk.X, padx=5, pady=5)
        
        output_path_frame = ttk.Frame(output_frame)
        output_path_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(output_path_frame, text="출력 파일:").pack(side=tk.LEFT, padx=5)
        ttk.Entry(output_path_frame, textvariable=self.output_file, width=40).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Button(output_path_frame, text="찾아보기", command=self.browse_output_file).pack(side=tk.LEFT, padx=5)
        
        # 단어 교체 영역
        replace_frame = ttk.LabelFrame(self.combine_tab, text="단어 교체 (선택 사항)", padding=10)
        replace_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 교체 단어 입력 영역
        replace_input_frame = ttk.Frame(replace_frame)
        replace_input_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(replace_input_frame, text="원본 단어:").pack(side=tk.LEFT, padx=5)
        self.old_word_entry = ttk.Entry(replace_input_frame, width=15)
        self.old_word_entry.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(replace_input_frame, text="교체 단어:").pack(side=tk.LEFT, padx=5)
        self.new_word_entry = ttk.Entry(replace_input_frame, width=15)
        self.new_word_entry.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(replace_input_frame, text="추가", command=self.add_replacement).pack(side=tk.LEFT, padx=5)
        
        # 교체 단어 목록 프레임
        replace_list_frame = ttk.Frame(replace_frame)
        replace_list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # 교체 단어 목록 (테이블 + 스크롤바)
        self.replace_tree = ttk.Treeview(replace_list_frame, columns=("old", "new"), show="headings", height=6)
        self.replace_tree.heading("old", text="원본 단어")
        self.replace_tree.heading("new", text="교체 단어")
        self.replace_tree.column("old", width=150)
        self.replace_tree.column("new", width=150)
        self.replace_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        replace_scrollbar = ttk.Scrollbar(replace_list_frame, orient=tk.VERTICAL, command=self.replace_tree.yview)
        replace_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.replace_tree.configure(yscrollcommand=replace_scrollbar.set)
        
        # 교체 목록 버튼 프레임
        replace_btn_frame = ttk.Frame(replace_frame)
        replace_btn_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(replace_btn_frame, text="선택 삭제", command=self.remove_selected_replacement).pack(side=tk.LEFT, padx=5)
        ttk.Button(replace_btn_frame, text="모두 삭제", command=self.clear_replacements).pack(side=tk.LEFT, padx=5)
        
        # 실행 버튼 프레임
        btn_frame = ttk.Frame(self.combine_tab)
        btn_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(btn_frame, text="파일 합치기 실행", command=self.execute_combine, width=20).pack(side=tk.LEFT, padx=5)
        
        # 로그 영역
        log_frame = ttk.LabelFrame(self.combine_tab, text="로그", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 로그 텍스트 영역
        self.combine_log = tk.Text(log_frame, height=8, width=60, wrap=tk.WORD)
        log_scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.combine_log.yview)
        self.combine_log.configure(yscrollcommand=log_scrollbar.set)
        
        self.combine_log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    def setup_replace_tab(self):
        # 입력 및 출력 파일 선택 영역
        file_frame = ttk.LabelFrame(self.replace_tab, text="파일 선택", padding=10)
        file_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 입력 파일
        input_file_frame = ttk.Frame(file_frame)
        input_file_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(input_file_frame, text="입력 파일:").pack(side=tk.LEFT, padx=5)
        self.replace_input_entry = ttk.Entry(input_file_frame, width=40)
        self.replace_input_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Button(input_file_frame, text="찾아보기", command=self.browse_replace_input).pack(side=tk.LEFT, padx=5)
        
        # 출력 파일
        output_file_frame = ttk.Frame(file_frame)
        output_file_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(output_file_frame, text="출력 파일:").pack(side=tk.LEFT, padx=5)
        self.replace_output_entry = ttk.Entry(output_file_frame, width=40)
        self.replace_output_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Button(output_file_frame, text="찾아보기", command=self.browse_replace_output).pack(side=tk.LEFT, padx=5)
        
        # 단어 교체 영역
        replace_frame = ttk.LabelFrame(self.replace_tab, text="단어 교체", padding=10)
        replace_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 교체 단어 입력 영역
        replace_input_frame = ttk.Frame(replace_frame)
        replace_input_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(replace_input_frame, text="원본 단어:").pack(side=tk.LEFT, padx=5)
        self.replace_old_word_entry = ttk.Entry(replace_input_frame, width=15)
        self.replace_old_word_entry.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(replace_input_frame, text="교체 단어:").pack(side=tk.LEFT, padx=5)
        self.replace_new_word_entry = ttk.Entry(replace_input_frame, width=15)
        self.replace_new_word_entry.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(replace_input_frame, text="추가", command=self.add_replacement_tab2).pack(side=tk.LEFT, padx=5)
        
        # 교체 단어 목록 프레임
        replace_list_frame = ttk.Frame(replace_frame)
        replace_list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # 교체 단어 목록 (테이블 + 스크롤바)
        self.replace_tree_tab2 = ttk.Treeview(replace_list_frame, columns=("old", "new"), show="headings", height=6)
        self.replace_tree_tab2.heading("old", text="원본 단어")
        self.replace_tree_tab2.heading("new", text="교체 단어")
        self.replace_tree_tab2.column("old", width=150)
        self.replace_tree_tab2.column("new", width=150)
        self.replace_tree_tab2.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        replace_scrollbar = ttk.Scrollbar(replace_list_frame, orient=tk.VERTICAL, command=self.replace_tree_tab2.yview)
        replace_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.replace_tree_tab2.configure(yscrollcommand=replace_scrollbar.set)
        
        # 교체 목록 버튼 프레임
        replace_btn_frame = ttk.Frame(replace_frame)
        replace_btn_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(replace_btn_frame, text="선택 삭제", command=self.remove_selected_replacement_tab2).pack(side=tk.LEFT, padx=5)
        ttk.Button(replace_btn_frame, text="모두 삭제", command=self.clear_replacements_tab2).pack(side=tk.LEFT, padx=5)
        
        # 실행 버튼 프레임
        btn_frame = ttk.Frame(self.replace_tab)
        btn_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(btn_frame, text="단어 교체 실행", command=self.execute_replace, width=20).pack(side=tk.LEFT, padx=5)
        
        # 상태 표시 및 진행 상황
        status_frame = ttk.Frame(self.replace_tab)
        status_frame.pack(fill=tk.X, pady=5)
        
        self.replace_progress = ttk.Progressbar(status_frame, orient=tk.HORIZONTAL, length=100, mode='determinate')
        self.replace_progress.pack(fill=tk.X, padx=5, pady=5)
        
        # 로그 영역
        log_frame = ttk.LabelFrame(self.replace_tab, text="로그", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 로그 텍스트 영역
        self.replace_log = tk.Text(log_frame, height=8, width=60, wrap=tk.WORD)
        log_scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.replace_log.yview)
        self.replace_log.configure(yscrollcommand=log_scrollbar.set)
        
        self.replace_log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    def browse_input_files(self):
        file_paths = filedialog.askopenfilenames(
            title="입력 파일 선택 (여러 개 선택 가능)", 
            filetypes=[("텍스트 파일", "*.txt"), ("모든 파일", "*.*")]
        )
        if file_paths:
            self.input_pattern_entry.delete(0, tk.END)
            self.input_pattern_entry.insert(0, ";".join(file_paths))
    
    def browse_output_file(self):
        file_path = filedialog.asksaveasfilename(
            title="출력 파일 저장 경로", 
            filetypes=[("텍스트 파일", "*.txt"), ("모든 파일", "*.*")]
        )
        if file_path:
            self.output_file.set(file_path)
    
    def browse_replace_input(self):
        file_path = filedialog.askopenfilename(
            title="입력 파일 선택", 
            filetypes=[("텍스트 파일", "*.txt"), ("모든 파일", "*.*")]
        )
        if file_path:
            self.replace_input_entry.delete(0, tk.END)
            self.replace_input_entry.insert(0, file_path)
    
    def browse_replace_output(self):
        file_path = filedialog.asksaveasfilename(
            title="출력 파일 저장 경로", 
            filetypes=[("텍스트 파일", "*.txt"), ("모든 파일", "*.*")]
        )
        if file_path:
            self.replace_output_entry.delete(0, tk.END)
            self.replace_output_entry.insert(0, file_path)
    
    def add_input_file(self):
        pattern = self.input_pattern_entry.get().strip()
        if not pattern:
            messagebox.showwarning("입력 오류", "파일 경로나 패턴을 입력하세요.")
            return
        
        # 세미콜론으로 구분된 다중 파일 처리
        patterns = pattern.split(";")
        for p in patterns:
            p = p.strip()
            if not p:
                continue
            
            # 이미 목록에 있는지 확인
            if p in self.input_files:
                messagebox.showinfo("중복 알림", f"'{p}'는 이미 목록에 있습니다.")
                continue
            
            # 패턴일 경우 매칭 파일 확인
            matched_files = []
            if "*" in p or "?" in p:
                matched_files = glob.glob(p)
                if not matched_files:
                    self.combine_log.insert(tk.END, f"주의: '{p}' 패턴과 일치하는 파일을 찾을 수 없습니다.\n")
                    self.combine_log.see(tk.END)
            
            # 목록에 추가
            self.input_files.append(p)
            self.file_listbox.insert(tk.END, p)
            
            # 매칭 파일 수 로그 출력
            if "*" in p or "?" in p:
                self.combine_log.insert(tk.END, f"패턴 '{p}'에 매칭된 파일: {len(matched_files)}개\n")
                self.combine_log.see(tk.END)
        
        # 입력 필드 비우기
        self.input_pattern_entry.delete(0, tk.END)
    
    def remove_selected_file(self):
        selected_indices = self.file_listbox.curselection()
        if not selected_indices:
            return
        
        # 뒤에서부터 삭제 (앞에서 삭제하면 인덱스가 변경됨)
        for i in sorted(selected_indices, reverse=True):
            del self.input_files[i]
            self.file_listbox.delete(i)
    
    def clear_files(self):
        self.input_files.clear()
        self.file_listbox.delete(0, tk.END)
    
    def add_replacement(self):
        old_word = self.old_word_entry.get().strip()
        new_word = self.new_word_entry.get().strip()
        
        if not old_word:
            messagebox.showwarning("입력 오류", "원본 단어를 입력하세요.")
            return
        
        # 교체 쌍 추가
        for item in self.replace_tree.get_children():
            if self.replace_tree.item(item, "values")[0] == old_word:
                messagebox.showinfo("중복 알림", f"'{old_word}'는 이미 목록에 있습니다.")
                return
        
        self.replace_tree.insert("", tk.END, values=(old_word, new_word))
        
        # 입력 필드 비우기
        self.old_word_entry.delete(0, tk.END)
        self.new_word_entry.delete(0, tk.END)
    
    def add_replacement_tab2(self):
        old_word = self.replace_old_word_entry.get().strip()
        new_word = self.replace_new_word_entry.get().strip()
        
        if not old_word:
            messagebox.showwarning("입력 오류", "원본 단어를 입력하세요.")
            return
        
        # 교체 쌍 추가
        for item in self.replace_tree_tab2.get_children():
            if self.replace_tree_tab2.item(item, "values")[0] == old_word:
                messagebox.showinfo("중복 알림", f"'{old_word}'는 이미 목록에 있습니다.")
                return
        
        self.replace_tree_tab2.insert("", tk.END, values=(old_word, new_word))
        
        # 입력 필드 비우기
        self.replace_old_word_entry.delete(0, tk.END)
        self.replace_new_word_entry.delete(0, tk.END)
    
    def remove_selected_replacement(self):
        selected_items = self.replace_tree.selection()
        for item in selected_items:
            self.replace_tree.delete(item)
    
    def remove_selected_replacement_tab2(self):
        selected_items = self.replace_tree_tab2.selection()
        for item in selected_items:
            self.replace_tree_tab2.delete(item)
    
    def clear_replacements(self):
        for item in self.replace_tree.get_children():
            self.replace_tree.delete(item)
    
    def clear_replacements_tab2(self):
        for item in self.replace_tree_tab2.get_children():
            self.replace_tree_tab2.delete(item)
    
    def execute_combine(self):
        # 입력 파일 확인
        if not self.input_files:
            messagebox.showwarning("입력 오류", "입력 파일을 추가하세요.")
            return
        
        # 출력 파일 확인
        output_file = self.output_file.get().strip()
        if not output_file:
            messagebox.showwarning("입력 오류", "출력 파일을 지정하세요.")
            return
        
        # 교체 사전 생성
        replace_dict = {}
        for item in self.replace_tree.get_children():
            values = self.replace_tree.item(item, "values")
            old_word, new_word = values[0], values[1]
            replace_dict[old_word] = new_word
        
        # 로그 초기화
        self.combine_log.delete(1.0, tk.END)
        self.combine_log.insert(tk.END, "파일 경로 결합 작업 시작...\n")
        
        try:
            # 모든 경로 수집
            all_paths = []
            
            for pattern in self.input_files:
                # 와일드카드 패턴 처리
                matched_files = []
                if "*" in pattern or "?" in pattern:
                    matched_files = glob.glob(pattern)
                else:
                    if os.path.exists(pattern):
                        matched_files = [pattern]
                
                self.combine_log.insert(tk.END, f"패턴 '{pattern}'에 매칭된 파일: {len(matched_files)}개\n")
                
                # 파일 내용 읽기
                for file_path in matched_files:
                    try:
                        # 다양한 인코딩 시도
                        for encoding in ["utf-8", "euc-kr", "cp949"]:
                            try:
                                with open(file_path, 'r', encoding=encoding) as f:
                                    file_content = f.read().strip()
                                    paths = [line.strip() for line in file_content.split('\n') if line.strip()]
                                    all_paths.extend(paths)
                                    self.combine_log.insert(tk.END, f"처리 완료: {file_path} - {len(paths)}개 경로 (인코딩: {encoding})\n")
                                    self.combine_log.see(tk.END)
                                    self.root.update_idletasks()
                                    break
                            except UnicodeDecodeError:
                                continue
                        else:  # 모든 인코딩 시도 실패
                            self.combine_log.insert(tk.END, f"경고: 파일 '{file_path}'의 인코딩을 감지할 수 없습니다. 건너뜁니다.\n")
                            self.combine_log.see(tk.END)
                            
                    except Exception as e:
                        self.combine_log.insert(tk.END, f"오류: {file_path} 파일 읽기 실패 - {str(e)}\n")
                        self.combine_log.see(tk.END)
            
            # 단어 교체
            if replace_dict and all_paths:
                self.combine_log.insert(tk.END, "단어 교체 수행 중...\n")
                modified_paths = []
                for path in all_paths:
                    modified_path = path
                    for old_word, new_word in replace_dict.items():
                        modified_path = modified_path.replace(old_word, new_word)
                    modified_paths.append(modified_path)
                all_paths = modified_paths
                
                for old_word, new_word in replace_dict.items():
                    self.combine_log.insert(tk.END, f"교체: '{old_word}' -> '{new_word}'\n")
                    self.combine_log.see(tk.END)
            
            # 중복 제거
            unique_paths = list(dict.fromkeys(all_paths))
            self.combine_log.insert(tk.END, f"총 경로 수: {len(all_paths)}, 고유 경로 수: {len(unique_paths)}\n")
            
            # 출력 파일에 쓰기
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(unique_paths))
            
            self.combine_log.insert(tk.END, f"완료: 모든 경로가 '{output_file}'에 저장되었습니다.\n")
            self.combine_log.see(tk.END)
            
            messagebox.showinfo("완료", f"파일 합치기가 완료되었습니다.\n{len(unique_paths)}개의 고유 경로가 저장되었습니다.")
            
        except Exception as e:
            error_msg = f"오류 발생: {str(e)}"
            self.combine_log.insert(tk.END, f"{error_msg}\n")
            self.combine_log.see(tk.END)
            messagebox.showerror("오류", error_msg)
    
    def execute_replace(self):
        # 입력 파일 확인
        input_file = self.replace_input_entry.get().strip()
        if not input_file or not os.path.exists(input_file):
            messagebox.showwarning("입력 오류", "유효한 입력 파일을 지정하세요.")
            return
        
        # 출력 파일 확인
        output_file = self.replace_output_entry.get().strip()
        if not output_file:
            messagebox.showwarning("입력 오류", "출력 파일을 지정하세요.")
            return
        
        # 교체 사전 생성
        replace_dict = {}
        for item in self.replace_tree_tab2.get_children():
            values = self.replace_tree_tab2.item(item, "values")
            old_word, new_word = values[0], values[1]
            replace_dict[old_word] = new_word
        
        if not replace_dict:
            messagebox.showwarning("입력 오류", "교체할 단어 쌍을 추가하세요.")
            return
        
        # 로그 초기화
        self.replace_log.delete(1.0, tk.END)
        self.replace_log.insert(tk.END, "단어 교체 작업 시작...\n")
        
        try:
            # 진행바 초기화
            self.replace_progress['value'] = 0
            self.root.update_idletasks()
            
            # 인코딩 감지 및 파일 읽기
            paths = []
            for encoding in ["utf-8", "euc-kr", "cp949"]:
                try:
                    with open(input_file, 'r', encoding=encoding) as f:
                        file_content = f.read().strip()
                        paths = [line.strip() for line in file_content.split('\n') if line.strip()]
                        self.replace_log.insert(tk.END, f"'{input_file}'에서 {len(paths)}개의 경로를 읽었습니다. (인코딩: {encoding})\n")
                        self.replace_log.see(tk.END)
                        break
                except UnicodeDecodeError:
                    continue
            else:
                raise Exception(f"파일 '{input_file}'의 인코딩을 감지할 수 없습니다.")
            
            if not paths:
                self.replace_log.insert(tk.END, "경고: 파일에 유효한 경로가 없습니다.\n")
                self.replace_log.see(tk.END)
                return
            
            # 진행 상황 설정
            self.replace_progress['maximum'] = len(paths)
            
            # 단어 교체
            modified_paths = []
            for i, path in enumerate(paths):
                # 진행 상황 업데이트
                self.replace_progress['value'] = i + 1
                if i % 100 == 0:  # 성능을 위해 매 100개 항목마다 UI 업데이트
                    self.root.update_idletasks()
                
                # 단어 교체 수행
                modified_path = path
                for old_word, new_word in replace_dict.items():
                    modified_path = modified_path.replace(old_word, new_word)
                modified_paths.append(modified_path)
            
            # 교체 내용 로그 출력
            for old_word, new_word in replace_dict.items():
                self.replace_log.insert(tk.END, f"교체: '{old_word}' -> '{new_word}'\n")
            
            # 출력 파일에 쓰기
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(modified_paths))
            
            # 완료 메시지
            self.replace_log.insert(tk.END, f"완료: 수정된 경로가 '{output_file}'에 저장되었습니다.\n")
            self.replace_log.see(tk.END)
            
            messagebox.showinfo("완료", "단어 교체가 완료되었습니다.")
            
        except Exception as e:
            error_msg = f"오류 발생: {str(e)}"
            self.replace_log.insert(tk.END, f"{error_msg}\n")
            self.replace_log.see(tk.END)
            messagebox.showerror("오류", error_msg)

def main():
    root = tk.Tk()
    app = FilePathCombinerApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()