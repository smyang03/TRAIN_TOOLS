import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import numpy as np
from pathlib import Path
import time
import glob
import re
import random
from PIL import Image, ImageTk
import cv2

class LabelModifier:
    def __init__(self, root):
        self.root = root
        self.root.title("YOLO 라벨 수정 프로그램")
        self.root.geometry("900x700")
        
        # 변수 초기화
        self.input_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.class_mapping = {}
        self.shift_start = tk.IntVar(value=0)
        self.shift_value = tk.IntVar(value=0)
        self.shift_max_class = tk.IntVar(value=80)
        self.apply_shift = tk.BooleanVar(value=False)
        self.delete_classes = tk.StringVar()
        self.classes_to_delete = set()
        self.input_mode = tk.StringVar(value="file")  # "file" 또는 "folder"
        self.source_class = tk.StringVar()
        self.target_class = tk.StringVar()
        self.enable_duplication = tk.BooleanVar(value=False)
        self.duplication_mappings = {}  # source_class -> [target_class1, target_class2, ...]
        self.image_paths_cache = []
        
        # 탭 컨트롤 생성
        self.tab_control = ttk.Notebook(root)
        self.tab_control.pack(fill="both", expand=True, padx=10, pady=5)
        
        # 탭 1: 파일 설정
        file_tab = ttk.Frame(self.tab_control)
        self.tab_control.add(file_tab, text="파일 설정")
        
        # 탭 2: 클래스 매핑/복제
        mapping_tab = ttk.Frame(self.tab_control)
        self.tab_control.add(mapping_tab, text="클래스 매핑/복제")
        
        # 탭 3: 클래스 변환/삭제
        transform_tab = ttk.Frame(self.tab_control)
        self.tab_control.add(transform_tab, text="클래스 변환/삭제")
        
        # 탭 4: 실행 및 결과
        result_tab = ttk.Frame(self.tab_control)
        self.tab_control.add(result_tab, text="실행 및 결과")
        
        # ===== 탭 1: 파일 설정 =====
        file_frame = ttk.LabelFrame(file_tab, text="입력 및 출력 설정")
        file_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 입력 모드 선택
        mode_frame = ttk.Frame(file_frame)
        mode_frame.pack(fill="x", padx=5, pady=5)
        
        ttk.Label(mode_frame, text="입력 모드:").pack(side="left", padx=5)
        ttk.Radiobutton(mode_frame, text="이미지 목록 파일", variable=self.input_mode, value="file").pack(side="left", padx=10)
        ttk.Radiobutton(mode_frame, text="이미지 폴더", variable=self.input_mode, value="folder").pack(side="left", padx=10)
        
        # 입력 경로
        input_frame = ttk.Frame(file_frame)
        input_frame.pack(fill="x", padx=5, pady=5)
        
        ttk.Label(input_frame, text="입력 경로:").pack(side="left", padx=5)
        ttk.Entry(input_frame, textvariable=self.input_path, width=50).pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(input_frame, text="찾아보기...", command=self.browse_input).pack(side="left", padx=5)
        
        # 출력 경로
        output_frame = ttk.Frame(file_frame)
        output_frame.pack(fill="x", padx=5, pady=5)
        
        ttk.Label(output_frame, text="저장 경로:").pack(side="left", padx=5)
        ttk.Entry(output_frame, textvariable=self.output_path, width=50).pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(output_frame, text="찾아보기...", command=self.browse_output_dir).pack(side="left", padx=5)
        
        # 데이터 확인 버튼
        check_frame = ttk.Frame(file_frame)
        check_frame.pack(fill="x", padx=5, pady=10)
        
        ttk.Button(check_frame, text="어노테이션 체크", command=self.check_annotations, width=20).pack(side="left", padx=10)
        ttk.Button(check_frame, text="클래스별 예시 이미지", command=self.show_class_examples, width=20).pack(side="left", padx=10)
        
        # ===== 탭 2: 클래스 매핑/복제 =====
        # 매핑 프레임
        mapping_frame = ttk.LabelFrame(mapping_tab, text="클래스 매핑 설정")
        mapping_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        ttk.Label(mapping_frame, text="개별 클래스 매핑 (원본 클래스 ID → 새 클래스 ID)").pack(anchor="w", padx=5, pady=5)
        
        # 매핑 테이블 프레임
        table_frame = ttk.Frame(mapping_frame)
        table_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.mapping_table = ttk.Treeview(table_frame, columns=("original", "new"), show="headings", height=8)
        self.mapping_table.heading("original", text="원본 클래스 ID")
        self.mapping_table.heading("new", text="새 클래스 ID")
        self.mapping_table.column("original", width=100)
        self.mapping_table.column("new", width=100)
        self.mapping_table.pack(side="left", fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.mapping_table.yview)
        scrollbar.pack(side="right", fill="y")
        self.mapping_table.configure(yscrollcommand=scrollbar.set)
        
        # 매핑 컨트롤 프레임
        control_frame = ttk.Frame(mapping_frame)
        control_frame.pack(fill="x", padx=5, pady=5)
        
        self.orig_class = tk.StringVar()
        self.new_class = tk.StringVar()
        
        ttk.Label(control_frame, text="원본 클래스:").grid(row=0, column=0, padx=5, pady=5)
        ttk.Entry(control_frame, textvariable=self.orig_class, width=10).grid(row=0, column=1, padx=5, pady=5)
        ttk.Label(control_frame, text="새 클래스:").grid(row=0, column=2, padx=5, pady=5)
        ttk.Entry(control_frame, textvariable=self.new_class, width=10).grid(row=0, column=3, padx=5, pady=5)
        
        ttk.Button(control_frame, text="추가", command=self.add_mapping).grid(row=0, column=4, padx=10, pady=5)
        ttk.Button(control_frame, text="제거", command=self.remove_mapping).grid(row=0, column=5, padx=10, pady=5)
        
        # 복제 프레임
        duplication_frame = ttk.LabelFrame(mapping_tab, text="라벨 복제 설정")
        duplication_frame.pack(fill="x", padx=10, pady=10)
        self.create_duplication_ui(duplication_frame)
        
        # ===== 탭 3: 클래스 변환/삭제 =====
        # Shift 설정 프레임
        shift_frame = ttk.LabelFrame(transform_tab, text="클래스 Shift 설정")
        shift_frame.pack(fill="x", padx=10, pady=10)
        
        shift_check_frame = ttk.Frame(shift_frame)
        shift_check_frame.pack(fill="x", padx=5, pady=5)
        ttk.Checkbutton(shift_check_frame, text="클래스 Shift 적용", variable=self.apply_shift).pack(anchor="w", padx=5)
        
        shift_params_frame = ttk.Frame(shift_frame)
        shift_params_frame.pack(fill="x", padx=5, pady=5)
        
        ttk.Label(shift_params_frame, text="시작 클래스 ID:").grid(row=0, column=0, padx=5, pady=5)
        ttk.Entry(shift_params_frame, textvariable=self.shift_start, width=10).grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(shift_params_frame, text="Shift 값 (+/-):").grid(row=0, column=2, padx=5, pady=5)
        ttk.Entry(shift_params_frame, textvariable=self.shift_value, width=10).grid(row=0, column=3, padx=5, pady=5)
        
        ttk.Label(shift_params_frame, text="최대 클래스 ID:").grid(row=0, column=4, padx=5, pady=5)
        ttk.Entry(shift_params_frame, textvariable=self.shift_max_class, width=10).grid(row=0, column=5, padx=5, pady=5)
        
        # 클래스 삭제 프레임
        delete_frame = ttk.LabelFrame(transform_tab, text="특정 클래스 삭제")
        delete_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        delete_input_frame = ttk.Frame(delete_frame)
        delete_input_frame.pack(fill="x", padx=5, pady=5)
        
        ttk.Label(delete_input_frame, text="삭제할 클래스 ID (콤마로 구분):").pack(side="left", padx=5)
        ttk.Entry(delete_input_frame, textvariable=self.delete_classes, width=40).pack(side="left", padx=5, fill="x", expand=True)
        ttk.Button(delete_input_frame, text="적용", command=self.update_delete_classes).pack(side="left", padx=10)
        
        delete_list_frame = ttk.Frame(delete_frame)
        delete_list_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.delete_list = tk.Listbox(delete_list_frame, height=6)
        self.delete_list.pack(side="left", fill="both", expand=True, padx=5)
        ttk.Button(delete_list_frame, text="제거", command=self.remove_delete_class).pack(side="left", padx=10, anchor="n")
        
        # ===== 탭 4: 실행 및 결과 =====
        # 진행 상태 프레임
        progress_frame = ttk.LabelFrame(result_tab, text="진행 상태")
        progress_frame.pack(fill="x", padx=10, pady=10)
        
        self.progress = ttk.Progressbar(progress_frame, orient="horizontal", length=100, mode="determinate")
        self.progress.pack(fill="x", padx=10, pady=10)
        
        self.status_label = ttk.Label(progress_frame, text="준비됨")
        self.status_label.pack(padx=10, pady=5, anchor="w")
        
        # 실행 버튼 프레임
        button_frame = ttk.Frame(result_tab)
        button_frame.pack(fill="x", padx=10, pady=10)
        
        ttk.Button(button_frame, text="실행", command=self.run_modification, width=15).pack(side="right", padx=10)
        ttk.Button(button_frame, text="취소", command=root.quit, width=15).pack(side="right", padx=10)
        
        # 결과 프레임
        result_frame = ttk.LabelFrame(result_tab, text="처리 결과")
        result_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 결과 텍스트 창에 스크롤바 추가
        result_text_frame = ttk.Frame(result_frame)
        result_text_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.result_text = tk.Text(result_text_frame, height=15)
        self.result_text.pack(side="left", fill="both", expand=True)
        
        result_scrollbar = ttk.Scrollbar(result_text_frame, orient="vertical", command=self.result_text.yview)
        result_scrollbar.pack(side="right", fill="y")
        self.result_text.configure(yscrollcommand=result_scrollbar.set)
        
        # 이미지 예시를 위한 참조 저장
        self.example_window = None
        self.photo_references = []
    def create_duplication_ui(self, duplication_frame):
        ttk.Checkbutton(duplication_frame, text="라벨 복제 활성화", variable=self.enable_duplication).grid(row=0, column=0, padx=5, pady=5)
        
        # 복제 테이블 프레임
        dup_table_frame = ttk.Frame(duplication_frame)
        dup_table_frame.grid(row=1, column=0, columnspan=6, padx=5, pady=5, sticky="ew")
        
        self.duplication_table = ttk.Treeview(dup_table_frame, columns=("source", "target"), show="headings", height=5)
        self.duplication_table.heading("source", text="원본 클래스 ID")
        self.duplication_table.heading("target", text="대상 클래스 ID")
        self.duplication_table.column("source", width=100)
        self.duplication_table.column("target", width=100)
        self.duplication_table.pack(side="left", fill="both", expand=True)
        
        dup_scrollbar = ttk.Scrollbar(dup_table_frame, orient="vertical", command=self.duplication_table.yview)
        dup_scrollbar.pack(side="right", fill="y")
        self.duplication_table.configure(yscrollcommand=dup_scrollbar.set)
        
        # 복제 추가/제거 컨트롤
        dup_control_frame = ttk.Frame(duplication_frame)
        dup_control_frame.grid(row=2, column=0, columnspan=6, padx=5, pady=5, sticky="ew")
        
        ttk.Label(dup_control_frame, text="원본 클래스:").grid(row=0, column=0, padx=5, pady=5)
        ttk.Entry(dup_control_frame, textvariable=self.source_class, width=10).grid(row=0, column=1, padx=5, pady=5)
        ttk.Label(dup_control_frame, text="대상 클래스:").grid(row=0, column=2, padx=5, pady=5)
        ttk.Entry(dup_control_frame, textvariable=self.target_class, width=10).grid(row=0, column=3, padx=5, pady=5)
        
        ttk.Button(dup_control_frame, text="추가", command=self.add_duplication).grid(row=0, column=4, padx=5, pady=5)
        ttk.Button(dup_control_frame, text="제거", command=self.remove_duplication).grid(row=0, column=5, padx=5, pady=5)
    def add_duplication(self):
        source = self.source_class.get().strip()
        target = self.target_class.get().strip()
        
        if not source or not target:
            messagebox.showwarning("입력 오류", "원본 클래스와 대상 클래스를 모두 입력하세요.")
            return
        
        try:
            int(source)
            int(target)
        except ValueError:
            messagebox.showwarning("입력 오류", "클래스 ID는 정수여야 합니다.")
            return
        
        # 기존 항목 확인 및 업데이트
        for item in self.duplication_table.get_children():
            if self.duplication_table.item(item, "values")[0] == source and self.duplication_table.item(item, "values")[1] == target:
                messagebox.showinfo("정보", "이미 존재하는 복제 매핑입니다.")
                self.source_class.set("")
                self.target_class.set("")
                return
        
        # 새 항목 추가
        self.duplication_table.insert("", "end", values=(source, target))
        
        # 복제 매핑에 추가
        if source not in self.duplication_mappings:
            self.duplication_mappings[source] = []
        self.duplication_mappings[source].append(target)
        
        self.source_class.set("")
        self.target_class.set("")

# 4. 복제 매핑 제거 함수
    def remove_duplication(self):
        selected = self.duplication_table.selection()
        if not selected:
            messagebox.showwarning("선택 오류", "제거할 복제 매핑을 선택하세요.")
            return
        
        for item in selected:
            values = self.duplication_table.item(item, "values")
            source = values[0]
            target = values[1]
            
            # 복제 매핑에서 제거
            if source in self.duplication_mappings and target in self.duplication_mappings[source]:
                self.duplication_mappings[source].remove(target)
                if not self.duplication_mappings[source]:  # 비어있으면 키 제거
                    del self.duplication_mappings[source]
            
            self.duplication_table.delete(item)
    def process_labels_with_duplication(self, original_labels):
        new_labels = []
        duplicate_labels = []  # 복제할 라벨 저장 리스트
        
        # 먼저 모든 라인을 처리하고, 복제가 필요한 경우 별도로 저장
        for line in original_labels:
            parts = line.split()
            if len(parts) < 5:  # YOLO 포맷은 최소 5개 값이 필요
                continue
            
            class_id = parts[0]
            
            # 복제 설정에 따라 복제 대상 라벨 저장
            if self.enable_duplication.get() and class_id in self.duplication_mappings:
                for target_class in self.duplication_mappings[class_id]:
                    # 원본 라인을 복제하고 대상 클래스로 변경
                    duplicate_parts = parts.copy()
                    duplicate_parts[0] = target_class  # 대상 클래스로 변경
                    duplicate_labels.append(" ".join(duplicate_parts))
                    
                    # 통계 업데이트
                    key = f"복제: {class_id} → {target_class}"
                    self.class_stats[key] = self.class_stats.get(key, 0) + 1
            
            # 여기서 클래스 매핑, 삭제 등 다른 처리를 계속합니다...
            # (기존 코드 유지)
            
            # 특정 클래스 삭제 확인
            if class_id in self.classes_to_delete:
                # 통계 업데이트
                key = f"삭제됨 (지정 클래스): {class_id}"
                self.class_stats[key] = self.class_stats.get(key, 0) + 1
                continue
            
            # 클래스 변경 적용
            new_class_id = class_id
            
            # 개별 매핑 적용
            if class_id in self.class_mapping:
                new_class_id = self.class_mapping[class_id]
                
                # 통계 업데이트
                key = f"{class_id} → {new_class_id}"
                self.class_stats[key] = self.class_stats.get(key, 0) + 1
            
            # Shift 적용
            elif self.apply_shift.get():
                try:
                    orig_id = int(class_id)
                    if orig_id >= self.shift_start.get():
                        new_id = orig_id + self.shift_value.get()
                        
                        # 최대 클래스 ID 확인
                        if new_id > self.shift_max_class.get():
                            # 최대 클래스 ID를 초과하는 경우 해당 객체 삭제 (건너뛰기)
                            key = f"삭제됨 (최대 클래스 초과): {class_id}"
                            self.class_stats[key] = self.class_stats.get(key, 0) + 1
                            continue
                        
                        new_class_id = str(new_id)
                        
                        # 통계 업데이트
                        key = f"Shift: {class_id} → {new_class_id}"
                        self.class_stats[key] = self.class_stats.get(key, 0) + 1
                except ValueError:
                    pass
            
            # 새 라벨 라인 생성
            parts[0] = new_class_id
            new_line = " ".join(parts)
            new_labels.append(new_line)
        
        # 복제 라벨 추가
        new_labels.extend(duplicate_labels)
        
        return new_labels

    # 6. 통계 처리시 복제 항목도 포함되도록 수정 (sort_stats_by_class 함수)
    def sort_stats_by_class(self, class_stats):
        """클래스 통계를 클래스 ID 순서로 정렬"""
        # 클래스 매핑 항목 처리
        mapping_stats = {}
        shift_stats = {}
        delete_stats = {}
        duplication_stats = {}
        
        for key, count in class_stats.items():
            if "→" in key and not key.startswith("Shift") and not key.startswith("복제"):
                # 클래스 매핑 항목
                orig = key.split(" → ")[0]
                mapping_stats[key] = (int(orig), count)
            elif key.startswith("Shift"):
                # Shift 항목: "Shift: 21 → 22"
                match = re.search(r"Shift: (\d+) → (\d+)", key)
                if match:
                    orig = int(match.group(1))
                    shift_stats[key] = (orig, count)
            elif key.startswith("삭제됨"):
                # 삭제 항목
                match = re.search(r"삭제됨 \([^)]+\): (\d+)", key)
                if match:
                    orig = int(match.group(1))
                    delete_stats[key] = (orig, count)
            elif key.startswith("복제"):
                # 복제 항목: "복제: 0 → 1"
                match = re.search(r"복제: (\d+) → (\d+)", key)
                if match:
                    orig = int(match.group(1))
                    duplication_stats[key] = (orig, count)
        
        # 각 카테고리별로 정렬
        sorted_mapping = sorted(mapping_stats.items(), key=lambda x: x[1][0])
        sorted_shift = sorted(shift_stats.items(), key=lambda x: x[1][0])
        sorted_delete = sorted(delete_stats.items(), key=lambda x: x[1][0])
        sorted_duplication = sorted(duplication_stats.items(), key=lambda x: x[1][0])
        
        # 모든 항목 합치기
        sorted_stats = {}
        
        # 먼저 매핑 항목
        for key, (_, count) in sorted_mapping:
            sorted_stats[key] = count
            
        # 다음 복제 항목
        for key, (_, count) in sorted_duplication:
            sorted_stats[key] = count
            
        # 다음 Shift 항목
        for key, (_, count) in sorted_shift:
            sorted_stats[key] = count
            
        # 마지막으로 삭제 항목
        for key, (_, count) in sorted_delete:
            sorted_stats[key] = count
            
        return sorted_stats
    def browse_input(self):
        """입력 경로 선택 (파일 또는 폴더)"""
        if self.input_mode.get() == "file":
            file_path = filedialog.askopenfilename(
                title="이미지 목록 파일 선택",
                filetypes=[("텍스트 파일", "*.txt"), ("모든 파일", "*.*")]
            )
            if file_path:
                self.input_path.set(file_path)
        else:  # folder mode
            dir_path = filedialog.askdirectory(title="이미지 폴더 선택")
            if dir_path:
                self.input_path.set(dir_path)
    
    def browse_output_dir(self):
        dir_path = filedialog.askdirectory(title="저장 경로 선택")
        if dir_path:
            self.output_path.set(dir_path)
    
    def add_mapping(self):
        orig = self.orig_class.get().strip()
        new = self.new_class.get().strip()
        
        if not orig or not new:
            messagebox.showwarning("입력 오류", "원본 클래스와 새 클래스를 모두 입력하세요.")
            return
        
        try:
            int(orig)
            int(new)
        except ValueError:
            messagebox.showwarning("입력 오류", "클래스 ID는 정수여야 합니다.")
            return
        
        # 기존 항목 확인 및 업데이트
        for item in self.mapping_table.get_children():
            if self.mapping_table.item(item, "values")[0] == orig:
                self.mapping_table.item(item, values=(orig, new))
                self.class_mapping[orig] = new
                self.orig_class.set("")
                self.new_class.set("")
                return
        
        # 새 항목 추가
        self.mapping_table.insert("", "end", values=(orig, new))
        self.class_mapping[orig] = new
        self.orig_class.set("")
        self.new_class.set("")
    
    def remove_mapping(self):
        selected = self.mapping_table.selection()
        if not selected:
            messagebox.showwarning("선택 오류", "제거할 매핑을 선택하세요.")
            return
        
        for item in selected:
            orig = self.mapping_table.item(item, "values")[0]
            if orig in self.class_mapping:
                del self.class_mapping[orig]
            self.mapping_table.delete(item)
            
    def update_delete_classes(self):
        """삭제할 클래스 목록 업데이트"""
        classes_str = self.delete_classes.get().strip()
        if not classes_str:
            return
            
        # 콤마로 구분된 클래스 ID를 분리하고 공백 제거
        classes = [cls.strip() for cls in classes_str.split(",")]
        valid_classes = []
        
        for cls in classes:
            try:
                # 숫자 형식인지 확인
                int(cls)
                valid_classes.append(cls)
                self.classes_to_delete.add(cls)
            except ValueError:
                messagebox.showwarning("입력 오류", f"'{cls}'는 유효한 클래스 ID가 아닙니다. 숫자만 입력하세요.")
        
        # 리스트박스 업데이트
        self.delete_list.delete(0, tk.END)
        for cls in sorted(self.classes_to_delete, key=int):
            self.delete_list.insert(tk.END, cls)
            
        # 입력 필드 초기화
        self.delete_classes.set("")
    
    def remove_delete_class(self):
        """선택한 삭제 클래스 제거"""
        selected = self.delete_list.curselection()
        if not selected:
            messagebox.showwarning("선택 오류", "제거할 클래스를 선택하세요.")
            return
            
        for index in selected[::-1]:  # 역순으로 처리하여 인덱스 문제 방지
            cls = self.delete_list.get(index)
            self.classes_to_delete.remove(cls)
            self.delete_list.delete(index)
    
    def get_image_paths(self):
        """입력 모드에 따라 이미지 경로 목록 반환"""
        if self.input_mode.get() == "file":
            # 파일 모드: 텍스트 파일에서 이미지 경로 읽기
            with open(self.input_path.get(), 'r', encoding='utf-8') as f:
                return [line.strip() for line in f if line.strip()]
        else:
            # 폴더 모드: 폴더 내 모든 jpg 파일 경로 찾기
            folder_path = self.input_path.get()
            jpg_files = []
            
            # 모든 jpg 파일 검색 (대소문자 구분 없이)
            for ext in ['*.jpg', '*.JPG', '*.jpeg', '*.JPEG']:
                jpg_files.extend(glob.glob(os.path.join(folder_path, '**', ext), recursive=True))
            
            # 중복 제거 및 정렬
            jpg_files = list(set(jpg_files))
            jpg_files.sort()
            
            return jpg_files

    def show_class_examples(self):
        """각 클래스별로 2개의 예시 이미지를 보여주는 새 창을 생성"""
        if not self.input_path.get():
            messagebox.showwarning("경로 오류", "입력 경로를 선택하세요.")
            return
            
        try:
            self.status_label.config(text="예시 이미지 준비 중...")
            self.root.update()
            
            # 이미지 경로 목록 가져오기
            image_paths = self.get_image_paths()
            
            # 라벨 파일별 이미지와 클래스 ID 정보 수집
            class_examples = {}  # 클래스 ID -> [(이미지경로, 바운딩박스), ...]
            
            for image_path in image_paths:
                # 이미지 경로를 라벨 경로로 변환
                label_path = image_path.replace('JPEGImages', 'labels').replace('.jpg', '.txt').replace('.JPG', '.txt').replace('.jpeg', '.txt').replace('.JPEG', '.txt')
                
                if os.path.exists(label_path):
                    # 라벨 파일 읽기
                    with open(label_path, 'r') as file:
                        lines = file.readlines()
                    
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                            
                        parts = line.split()
                        if len(parts) < 5:  # YOLO 포맷은 최소 5개 값이 필요
                            continue
                        
                        class_id = parts[0]
                        # YOLO 포맷 바운딩 박스: center_x, center_y, width, height (정규화된 값)
                        bbox = [float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])]
                        
                        if class_id not in class_examples:
                            class_examples[class_id] = []
                        
                        # 각 클래스당 최대 10개까지만 수집 (나중에 랜덤하게 2개 선택)
                        if len(class_examples[class_id]) < 10:
                            class_examples[class_id].append((image_path, bbox))
            
            # 클래스가 없는 경우 처리
            if not class_examples:
                messagebox.showinfo("정보", "라벨 파일에서 클래스 정보를 찾을 수 없습니다.")
                self.status_label.config(text="준비됨")
                return
            
            # 기존 예시 창이 있으면 닫기
            if self.example_window and self.example_window.winfo_exists():
                self.example_window.destroy()
            
            # 새 창 생성
            self.example_window = tk.Toplevel(self.root)
            self.example_window.title("클래스별 예시 이미지")
            self.example_window.geometry("800x600")
            
            # 스크롤 가능한 프레임 생성
            main_frame = ttk.Frame(self.example_window)
            main_frame.pack(fill="both", expand=True)
            
            canvas = tk.Canvas(main_frame)
            scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
            scrollable_frame = ttk.Frame(canvas)
            
            scrollable_frame.bind(
                "<Configure>",
                lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
            )
            
            canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
            canvas.configure(yscrollcommand=scrollbar.set)
            
            canvas.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")
            
            # 각 클래스별로 2개의 예시 이미지 표시
            self.photo_references = []  # 이미지 참조 저장 (가비지 컬렉션 방지)
            
            # 클래스 ID를 정수로 변환하여 정렬
            sorted_classes = sorted([int(cls) for cls in class_examples.keys()])
            
            for class_id in sorted_classes:
                class_id_str = str(class_id)
                
                # 클래스별 프레임
                class_frame = ttk.LabelFrame(scrollable_frame, text=f"클래스 ID: {class_id_str}")
                class_frame.pack(fill="x", padx=10, pady=5, ipadx=5, ipady=5)
                
                # 이미지 예시 개수 선택 (최대 2개, 더 적으면 가능한 만큼)
                examples = class_examples[class_id_str]
                if len(examples) > 2:
                    examples = random.sample(examples, 2)
                
                # 이미지 레이블 생성
                for i, (img_path, bbox) in enumerate(examples):
                    try:
                        # 이미지 로드 및 바운딩 박스 그리기
                        img_bytes = np.fromfile(img_path, np.uint8)
                        img = cv2.imdecode(img_bytes, cv2.IMREAD_COLOR)
                        if img is None:
                            continue
                            
                        h, w, _ = img.shape
                        
                        # YOLO 형식 바운딩 박스를 픽셀 좌표로 변환
                        x_center, y_center, width, height = bbox
                        x1 = int((x_center - width/2) * w)
                        y1 = int((y_center - height/2) * h)
                        x2 = int((x_center + width/2) * w)
                        y2 = int((y_center + height/2) * h)
                        
                        # 바운딩 박스 그리기
                        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
                        
                        # 이미지 리사이즈 (너무 크면 작게, 너무 작으면 크게)
                        max_dim = 300
                        scale = min(max_dim / w, max_dim / h)
                        if scale < 1 or scale > 3:  # 크기 조정이 필요한 경우에만
                            new_w = int(w * scale)
                            new_h = int(h * scale)
                            img = cv2.resize(img, (new_w, new_h))
                        
                        # OpenCV BGR -> RGB 변환
                        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                        
                        # PIL 이미지로 변환 후 Tkinter와 호환되는 형식으로 변환
                        pil_img = Image.fromarray(img)
                        photo = ImageTk.PhotoImage(image=pil_img)
                        self.photo_references.append(photo)  # 참조 유지
                        
                        # 이미지 라벨 생성
                        img_label = ttk.Label(class_frame, image=photo)
                        img_label.grid(row=0, column=i, padx=5, pady=5)
                        
                        # 이미지 파일명 라벨 추가
                        filename = os.path.basename(img_path)
                        if len(filename) > 30:  # 파일명이 너무 길면 자르기
                            filename = filename[:27] + "..."
                        name_label = ttk.Label(class_frame, text=filename)
                        name_label.grid(row=1, column=i, padx=5)
                        
                    except Exception as e:
                        print(f"이미지 로드 오류 ({img_path}): {e}")
            
            self.status_label.config(text="준비됨")
            
        except Exception as e:
            self.status_label.config(text="오류 발생")
            messagebox.showerror("오류", f"예시 이미지 표시 중 오류가 발생했습니다: {e}")
    
    def check_annotations(self):
        """라벨 파일의 어노테이션 개수 확인"""
        if not self.input_path.get():
            messagebox.showwarning("경로 오류", "입력 경로를 선택하세요.")
            return
            
        try:
            self.result_text.delete(1.0, tk.END)
            self.status_label.config(text="어노테이션 체크 중...")
            self.root.update()
            
            start_time = time.time()
            
            # 이미지 경로 목록 가져오기
            image_paths = self.get_image_paths()
            unique_image_count = self.count_unique_image_source(image_paths)
            
            total_files = len(image_paths)
            found_label_files = 0
            missing_label_files = 0
            total_annotations = 0
            class_counts = {}  # 클래스별 어노테이션 개수
            error_files = 0
            missing_label_images = []
            
            # 중복 라벨 파일 확인
            processed_label_paths = set()
            duplicate_label_paths = set()
            
            self.progress["maximum"] = total_files
            self.progress["value"] = 0
            
            for idx, image_path in enumerate(image_paths):
                # 이미지 경로를 라벨 경로로 변환
                label_path = image_path.replace('JPEGImages', 'labels').replace('.jpg', '.txt').replace('.JPG', '.txt').replace('.jpeg', '.txt').replace('.JPEG', '.txt')
                
                # 중복 라벨 확인
                if label_path in processed_label_paths:
                    duplicate_label_paths.add(label_path)
                    self.progress["value"] = idx + 1
                    continue
                
                if os.path.exists(label_path):
                    processed_label_paths.add(label_path)
                    found_label_files += 1
                    
                    # 라벨 파일 읽기
                    with open(label_path, 'r') as file:
                        lines = file.readlines()
                    
                    file_annotation_count = 0
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                            
                        parts = line.split()
                        if len(parts) < 5:  # YOLO 포맷은 최소 5개 값이 필요
                            continue
                        
                        class_id = parts[0]
                        
                        # 클래스별 카운트 업데이트
                        if class_id in class_counts:
                            class_counts[class_id] += 1
                        else:
                            class_counts[class_id] = 1
                            
                        file_annotation_count += 1
                    
                    total_annotations += file_annotation_count
                else:
                    missing_label_files += 1
                
                # 진행률 업데이트 (50개마다 한 번씩 업데이트하여 성능 향상)
                if idx % 50 == 0 or idx == total_files - 1:
                    self.progress["value"] = idx + 1
                    self.status_label.config(text=f"어노테이션 체크 중... ({idx+1}/{total_files})")
                    self.root.update()
            
            # 처리 완료 후 결과 표시
            elapsed_time = time.time() - start_time
            
            # 클래스 ID 순으로 정렬
            sorted_class_counts = {k: v for k, v in sorted(class_counts.items(), key=lambda x: int(x[0]))}
            
            # 요약 작성
            summary = f"=== 어노테이션 체크 결과 ===\n"
            summary += f"고유 이미지 수: {unique_image_count}개\n"
            summary += f"총 이미지 파일 수: {total_files}개\n"
            summary += f"라벨 파일 발견: {found_label_files}개\n"
            summary += f"라벨 파일 없음: {missing_label_files}개\n"
            if duplicate_label_paths:
                summary += f"중복 라벨 파일: {len(duplicate_label_paths)}개\n"
            summary += f"총 어노테이션 수: {total_annotations}개\n"
            summary += f"클래스 수: {len(class_counts)}개\n"
            summary += f"소요 시간: {elapsed_time:.2f}초\n\n"
            
            summary += "=== 클래스별 어노테이션 개수 ===\n"
            for class_id, count in sorted_class_counts.items():
                summary += f"클래스 {class_id}: {count}개\n"
            
            # 결과 표시
            self.result_text.insert(tk.END, summary)
            self.status_label.config(text="어노테이션 체크 완료")
            self.progress["value"] = total_files
            
        except Exception as e:
            self.status_label.config(text="오류 발생")
            messagebox.showerror("오류", f"어노테이션 체크 중 오류가 발생했습니다: {e}")
    def run_modification(self):
        if not self.input_path.get():
            messagebox.showwarning("경로 오류", "입력 경로를 선택하세요.")
            return
        
        if not self.output_path.get():
            messagebox.showwarning("경로 오류", "저장 경로를 선택하세요.")
            return
        
        if not os.path.exists(self.output_path.get()):
            try:
                os.makedirs(self.output_path.get())
            except Exception as e:
                messagebox.showerror("저장 경로 오류", f"저장 경로를 생성할 수 없습니다: {e}")
                return
        
        # 라벨 복제 기능을 위한 유효성 검사
        if self.enable_duplication.get() and not self.duplication_mappings:
            messagebox.showwarning("복제 설정 오류", "라벨 복제를 활성화했지만 복제 매핑이 설정되지 않았습니다.")
            return
        
        try:
            self.result_text.delete(1.0, tk.END)
            self.status_label.config(text="처리 중...")
            self.root.update()
            
            start_time = time.time()
            
            # 이미지 경로 목록 가져오기
            image_paths = self.get_image_paths()
            unique_image_count = self.count_unique_image_source(image_paths)
            
            total_files = len(image_paths)
            processed_files = 0
            error_files = 0
            self.class_stats = {}  # 클래스별 변경 통계
            
            # 없는 라벨 파일과 매칭되는 이미지 저장
            missing_label_images = []
            duplicate_label_paths = set()
            processed_label_paths = set()
            
            self.progress["maximum"] = total_files
            self.progress["value"] = 0
            
            for idx, image_path in enumerate(image_paths):
                try:
                    # 이미지 경로를 라벨 경로로 변환
                    label_path = image_path.replace('JPEGImages', 'labels').replace('.jpg', '.txt').replace('.JPG', '.txt').replace('.jpeg', '.txt').replace('.JPEG', '.txt')
                    
                    if not os.path.exists(label_path):
                        self.result_text.insert(tk.END, f"경고: 라벨 파일을 찾을 수 없음: {label_path}\n")
                        missing_label_images.append(image_path)
                        error_files += 1
                        continue
                    
                    # 중복 라벨 확인
                    if label_path in processed_label_paths:
                        duplicate_label_paths.add(label_path)
                        continue
                    
                    processed_label_paths.add(label_path)
                    
                    # 라벨 파일 읽기
                    with open(label_path, 'r') as file:
                        lines = file.readlines()
                    
                    # 원본 라벨 저장
                    original_labels = []
                    for line in lines:
                        line = line.strip()
                        if line:  # 빈 줄이 아닌 경우만 추가
                            original_labels.append(line)
                    
                    # process_labels_with_duplication 함수 사용 - 여러 클래스 복제 처리
                    if self.enable_duplication.get():
                        new_labels = self.process_labels_with_duplication(original_labels)
                    else:
                        # 복제 기능을 사용하지 않는 경우 기존 처리 방식 사용
                        new_labels = []
                        for line in original_labels:
                            parts = line.split()
                            if len(parts) < 5:  # YOLO 포맷은 최소 5개 값이 필요
                                continue
                            
                            class_id = parts[0]
                            
                            # 특정 클래스 삭제 확인
                            if class_id in self.classes_to_delete:
                                # 통계 업데이트
                                key = f"삭제됨 (지정 클래스): {class_id}"
                                self.class_stats[key] = self.class_stats.get(key, 0) + 1
                                continue
                            
                            # 클래스 변경 적용
                            new_class_id = class_id
                            
                            # 개별 매핑 적용
                            if class_id in self.class_mapping:
                                new_class_id = self.class_mapping[class_id]
                                
                                # 통계 업데이트
                                key = f"{class_id} → {new_class_id}"
                                self.class_stats[key] = self.class_stats.get(key, 0) + 1
                            
                            # Shift 적용
                            elif self.apply_shift.get():
                                try:
                                    orig_id = int(class_id)
                                    if orig_id >= self.shift_start.get():
                                        new_id = orig_id + self.shift_value.get()
                                        
                                        # 최대 클래스 ID 확인
                                        if new_id > self.shift_max_class.get():
                                            # 최대 클래스 ID를 초과하는 경우 해당 객체 삭제 (건너뛰기)
                                            key = f"삭제됨 (최대 클래스 초과): {class_id}"
                                            self.class_stats[key] = self.class_stats.get(key, 0) + 1
                                            continue
                                        
                                        new_class_id = str(new_id)
                                        
                                        # 통계 업데이트
                                        key = f"Shift: {class_id} → {new_class_id}"
                                        self.class_stats[key] = self.class_stats.get(key, 0) + 1
                                except ValueError:
                                    pass
                            
                            # 새 라벨 라인 생성
                            parts[0] = new_class_id
                            new_line = " ".join(parts)
                            new_labels.append(new_line)
                    
                    # 파일명만 추출하여 저장 경로 생성
                    filename = os.path.basename(label_path)
                    save_path = os.path.join(self.output_path.get(), filename)
                    
                    # 새 라벨 파일 저장
                    with open(save_path, 'w') as file:
                        file.write("\n".join(new_labels))
                    
                    processed_files += 1
                    
                except Exception as e:
                    self.result_text.insert(tk.END, f"오류: {label_path} 처리 중 에러 발생: {e}\n")
                    error_files += 1
                
                # 진행률 업데이트
                self.progress["value"] = idx + 1
                if (idx + 1) % 10 == 0 or idx == len(image_paths) - 1:  # 10개마다 또는 마지막 항목에서 업데이트
                    self.status_label.config(text=f"처리 중... ({idx+1}/{total_files})")
                    self.root.update()
            
            # 처리 완료 후 결과 표시
            elapsed_time = time.time() - start_time
            
            # 클래스 ID 기준으로 정렬된 통계
            sorted_stats = self.sort_stats_by_class(self.class_stats)
            
            # 전체 요약 정보 생성
            class_summary = self.get_class_stats_summary(self.class_stats)
            
            summary = f"=== 처리 결과 요약 ===\n"
            summary += f"고유 이미지 수: {unique_image_count}\n"
            summary += f"총 이미지 파일 수: {total_files}\n"
            summary += f"처리 완료: {processed_files}\n"
            summary += f"오류: {error_files}\n"
            if duplicate_label_paths:
                summary += f"중복 처리된 라벨 파일: {len(duplicate_label_paths)}개\n"
            summary += f"소요 시간: {elapsed_time:.2f}초\n\n"
            
            summary += f"=== 어노테이션 및 클래스 변경 요약 ===\n"
            summary += f"전체 어노테이션 개수: {class_summary['total_annotations']}개\n"
            if class_summary['deleted_annotations'] > 0:
                summary += f"삭제된 어노테이션: {class_summary['deleted_annotations']}개\n"
            if class_summary['duplicated_annotations'] > 0:
                summary += f"복제된 어노테이션: {class_summary['duplicated_annotations']}개\n"
            summary += f"원본 클래스 범위: {class_summary['original_min_class']} ~ {class_summary['original_max_class']} ({class_summary['original_class_count']}개 클래스)\n"
            summary += f"변경 후 클래스 범위: {class_summary['new_min_class']} ~ {class_summary['new_max_class']} ({class_summary['new_class_count']}개 클래스)\n\n"
            
            summary += "=== 클래스 변경 통계 (클래스 ID 순) ===\n"
            for key, count in sorted_stats.items():
                summary += f"{key}: {count}개\n"
            
            # 결과 요약 파일 저장
            summary_path = os.path.join(self.output_path.get(), "result_summary.txt")
            try:
                with open(summary_path, 'w', encoding='utf-8') as f:
                    f.write(summary)
                self.result_text.delete(1.0, tk.END)
                self.result_text.insert(tk.END, summary)
                self.result_text.insert(tk.END, f"\n요약 파일이 저장되었습니다: {summary_path}\n")
            except Exception as e:
                self.result_text.delete(1.0, tk.END)
                self.result_text.insert(tk.END, summary)
                self.result_text.insert(tk.END, f"\n요약 파일 저장 중 오류 발생: {e}\n")
            
            self.status_label.config(text="처리 완료")
            
            # 완료 메시지
            messagebox.showinfo("처리 완료", f"총 {total_files}개 이미지 중 {processed_files}개 라벨 처리 완료 ({error_files}개 오류)")
            
        except Exception as e:
            self.status_label.config(text="오류 발생")
            messagebox.showerror("오류", f"처리 중 오류가 발생했습니다: {e}")
    
    def sort_stats_by_class(self, class_stats):
        """클래스 통계를 클래스 ID 순서로 정렬"""
        # 클래스 매핑 항목 처리
        mapping_stats = {}
        shift_stats = {}
        delete_stats = {}
        duplication_stats = {}
        
        for key, count in class_stats.items():
            if "→" in key and not key.startswith("Shift") and not key.startswith("복제"):
                # 클래스 매핑 항목
                orig = key.split(" → ")[0]
                mapping_stats[key] = (int(orig), count)
            elif key.startswith("Shift"):
                # Shift 항목: "Shift: 21 → 22"
                match = re.search(r"Shift: (\d+) → (\d+)", key)
                if match:
                    orig = int(match.group(1))
                    shift_stats[key] = (orig, count)
            elif key.startswith("삭제됨"):
                # 삭제 항목
                match = re.search(r"삭제됨 \([^)]+\): (\d+)", key)
                if match:
                    orig = int(match.group(1))
                    delete_stats[key] = (orig, count)
            elif key.startswith("복제"):
                # 복제 항목: "복제: 0 → 1"
                match = re.search(r"복제: (\d+) → (\d+)", key)
                if match:
                    orig = int(match.group(1))
                    duplication_stats[key] = (orig, count)
        
        # 각 카테고리별로 정렬
        sorted_mapping = sorted(mapping_stats.items(), key=lambda x: x[1][0])
        sorted_shift = sorted(shift_stats.items(), key=lambda x: x[1][0])
        sorted_delete = sorted(delete_stats.items(), key=lambda x: x[1][0])
        sorted_duplication = sorted(duplication_stats.items(), key=lambda x: x[1][0])
        
        # 모든 항목 합치기
        sorted_stats = {}
        
        # 먼저 매핑 항목
        for key, (_, count) in sorted_mapping:
            sorted_stats[key] = count
            
        # 다음 복제 항목
        for key, (_, count) in sorted_duplication:
            sorted_stats[key] = count
            
        # 다음 Shift 항목
        for key, (_, count) in sorted_shift:
            sorted_stats[key] = count
            
        # 마지막으로 삭제 항목
        for key, (_, count) in sorted_delete:
            sorted_stats[key] = count
            
        return sorted_stats
    
    def count_unique_image_source(self, image_paths):
        """이미지 파일의 고유 소스 이미지 수 계산"""
        if not image_paths:
            return 0
            
        # 파일 경로에서 이미지 이름만 추출 (확장자 제외)
        image_base_names = []
        for path in image_paths:
            base_name = os.path.basename(path)
            name_without_ext = os.path.splitext(base_name)[0]
            image_base_names.append(name_without_ext)
            
        # 고유 이미지 수 반환
        return len(set(image_base_names))
    
    def get_class_stats_summary(self, class_stats):
        """클래스 변경 통계로부터 전체 요약 정보 생성"""
        # 원본 클래스 수집
        original_classes = set()
        new_classes = set()
        deleted_classes = set()
        deleted_count = 0
        duplicated_count = 0
        total_annotations = 0
        
        # 각 변경 유형 분석
        for key, count in class_stats.items():
            total_annotations += count
            
            if key.startswith("삭제됨"):
                # 삭제된 클래스: "삭제됨 (지정 클래스): 3" 또는 "삭제됨 (최대 클래스 초과): 80"
                match = re.search(r"삭제됨 \([^)]+\): (\d+)", key)
                if match:
                    class_id = match.group(1)
                    original_classes.add(int(class_id))
                    deleted_classes.add(int(class_id))
                    deleted_count += count
            elif key.startswith("복제"):
                # 복제된 클래스: "복제: 0 → 1"
                match = re.search(r"복제: (\d+) → (\d+)", key)
                if match:
                    orig_id = int(match.group(1))
                    new_id = int(match.group(2))
                    original_classes.add(orig_id)
                    new_classes.add(new_id)
                    duplicated_count += count
            elif "→" in key:
                if key.startswith("Shift"):
                    # Shift된 클래스: "Shift: 21 → 22"
                    match = re.search(r"Shift: (\d+) → (\d+)", key)
                    if match:
                        orig_id = int(match.group(1))
                        new_id = int(match.group(2))
                        original_classes.add(orig_id)
                        new_classes.add(new_id)
                else:
                    # 매핑된 클래스: "0 → 1"
                    parts = key.split(" → ")
                    if len(parts) == 2:
                        orig_id = int(parts[0])
                        new_id = int(parts[1])
                        original_classes.add(orig_id)
                        new_classes.add(new_id)
        
        # 요약 정보 생성
        original_class_count = len(original_classes)
        new_class_count = len(new_classes)
        original_min_class = min(original_classes) if original_classes else 0
        original_max_class = max(original_classes) if original_classes else 0
        new_min_class = min(new_classes) if new_classes else 0
        new_max_class = max(new_classes) if new_classes else 0
        
        summary = {
            "total_annotations": total_annotations,
            "deleted_annotations": deleted_count,
            "duplicated_annotations": duplicated_count,
            "original_class_count": original_class_count,
            "new_class_count": new_class_count,
            "original_min_class": original_min_class,
            "original_max_class": original_max_class,
            "new_min_class": new_min_class,
            "new_max_class": new_max_class
        }
        
        return summary

def main():
    root = tk.Tk()
    app = LabelModifier(root)
    root.mainloop()

if __name__ == "__main__":
    main()
            
    
    