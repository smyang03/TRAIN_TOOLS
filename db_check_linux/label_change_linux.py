#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import argparse
import numpy as np
from pathlib import Path
import time
import glob
import re
import shutil
from collections import defaultdict, Counter

class YOLOLabelModifier:
    def __init__(self, args):
        """
        YOLO 라벨 수정 도구 초기화
        
        Args:
            args: 명령줄 인자
        """
        self.input_path = args.input_path
        self.input_mode = args.input_mode
        self.in_place = args.in_place
        self.backup = args.backup
        self.verbose = args.verbose
        
        # 출력 경로 설정 (in-place가 아닌 경우)
        if not self.in_place:
            self.output_path = args.output_path
            # 출력 디렉토리 생성
            os.makedirs(self.output_path, exist_ok=True)
        else:
            self.output_path = None
        
        # 클래스 매핑 설정
        self.class_mapping = {}
        if args.class_mapping:
            for mapping in args.class_mapping.split(','):
                orig, new = mapping.split(':')
                self.class_mapping[orig.strip()] = new.strip()
        
        # 클래스 시프트 설정
        self.apply_shift = False
        if args.shift_value is not None:
            self.apply_shift = True
            self.shift_start = args.shift_start
            self.shift_value = args.shift_value
            self.shift_max_class = args.shift_max
        
        # 클래스 삭제 설정
        self.classes_to_delete = set()
        if args.delete_classes:
            self.classes_to_delete = set(args.delete_classes.split(','))
        
        # 클래스 선택 설정
        self.selected_classes = set()
        if args.select_classes:
            self.selected_classes = set(args.select_classes.split(','))
        
        # 통계 변수 초기화
        self.class_stats = {}
        self.annotated_classes = Counter()
        
        # 결과 요약을 위한 변수
        self.processed_files = 0
        self.error_files = 0
        self.missing_label_files = 0
        self.total_annotations = 0
        self.missing_label_images = []
        self.duplicate_label_paths = set()
        self.backup_count = 0
    
    def get_image_paths(self):
        """입력 모드에 따라 이미지 경로 목록 반환"""
        if self.input_mode == "file":
            # 파일 모드: 텍스트 파일에서 이미지 경로 읽기
            with open(self.input_path, 'r', encoding='utf-8') as f:
                return [line.strip() for line in f if line.strip()]
        else:
            # 폴더 모드: 폴더 내 모든 jpg 파일 경로 찾기
            folder_path = self.input_path
            jpg_files = []
            
            # 한글 경로 처리를 위해 Path 객체 사용
            try:
                folder = Path(folder_path)
                
                # 재귀적으로 모든 jpg 파일 검색 (대소문자 구분 없이)
                for pattern in ['*.jpg', '*.JPG', '*.jpeg', '*.JPEG']:
                    jpg_files.extend([str(p) for p in folder.glob(f'**/{pattern}')])
                
                # 중복 제거 및 정렬
                jpg_files = list(set(jpg_files))
                jpg_files.sort()
                
            except Exception as e:
                if self.verbose:
                    print(f"경로 탐색 중 오류 발생: {e}")
                # 기존 방식으로 폴백
                for ext in ['*.jpg', '*.JPG', '*.jpeg', '*.JPEG']:
                    try:
                        jpg_files.extend(glob.glob(os.path.join(folder_path, '**', ext), recursive=True))
                    except Exception:
                        pass
                        
                # 중복 제거 및 정렬
                jpg_files = list(set(jpg_files))
                jpg_files.sort()
            
            return jpg_files
    
    def process_labels(self, original_labels):
        """라벨 처리 로직"""
        new_labels = []
        
        for line in original_labels:
            parts = line.split()
            if len(parts) < 5:  # YOLO 포맷은 최소 5개 값이 필요
                continue
            
            class_id = parts[0]
            
            # 소수점 클래스 ID를 정수로 변환 (예: '0.0' -> '0')
            if '.' in class_id:
                try:
                    # 소수점 값을 정수로 변환 (소수점 이하 버림)
                    class_id = str(int(float(class_id)))
                    parts[0] = class_id  # 원본 parts 배열도 업데이트
                except ValueError:
                    # 변환 실패 시 원래 값 유지
                    pass
            
            # 클래스 선택 모드에서는 선택된 클래스만 처리
            if self.selected_classes and class_id not in self.selected_classes:
                continue
            
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
            elif self.apply_shift:
                try:
                    orig_id = int(float(class_id))  # 소수점 값도 처리
                    if orig_id >= self.shift_start:
                        new_id = orig_id + self.shift_value
                        
                        # 최대 클래스 ID 확인
                        if new_id > self.shift_max_class:
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
            
            # 클래스 어노테이션 통계 업데이트
            self.annotated_classes[new_class_id] += 1
            self.total_annotations += 1
            
            # 새 라벨 라인 생성
            parts[0] = new_class_id
            new_line = " ".join(parts)
            new_labels.append(new_line)
        
        return new_labels
    
    def sort_stats_by_class(self):
        """클래스 통계를 클래스 ID 순서로 정렬"""
        # 클래스 매핑 항목 처리
        mapping_stats = {}
        shift_stats = {}
        delete_stats = {}
        
        for key, count in self.class_stats.items():
            if "→" in key and not key.startswith("Shift"):
                # 클래스 매핑 항목
                orig = key.split(" → ")[0]
                try:
                    # 소수점 값도 처리
                    mapping_stats[key] = (float(orig), count)
                except ValueError:
                    # 변환 실패 시 0으로 취급 (정렬 시 앞에 배치)
                    mapping_stats[key] = (0, count)
            elif key.startswith("Shift"):
                # Shift 항목: "Shift: 21 → 22"
                match = re.search(r"Shift: (\d+\.?\d*) → (\d+\.?\d*)", key)
                if match:
                    try:
                        # 소수점 값도 처리
                        orig = float(match.group(1))
                        shift_stats[key] = (orig, count)
                    except ValueError:
                        # 변환 실패 시 0으로 취급
                        shift_stats[key] = (0, count)
            elif key.startswith("삭제됨"):
                # 삭제 항목
                match = re.search(r"삭제됨 \([^)]+\): (\d+\.?\d*)", key)
                if match:
                    try:
                        # 소수점 값도 처리
                        orig = float(match.group(1))
                        delete_stats[key] = (orig, count)
                    except ValueError:
                        # 변환 실패 시 0으로 취급
                        delete_stats[key] = (0, count)
        
        # 각 카테고리별로 정렬
        sorted_mapping = sorted(mapping_stats.items(), key=lambda x: x[1][0])
        sorted_shift = sorted(shift_stats.items(), key=lambda x: x[1][0])
        sorted_delete = sorted(delete_stats.items(), key=lambda x: x[1][0])
        
        # 모든 항목 합치기
        sorted_stats = {}
        
        # 먼저 매핑 항목
        for key, (_, count) in sorted_mapping:
            sorted_stats[key] = count
            
        # 다음 Shift 항목
        for key, (_, count) in sorted_shift:
            sorted_stats[key] = count
            
        # 마지막으로 삭제 항목
        for key, (_, count) in sorted_delete:
            sorted_stats[key] = count
            
        return sorted_stats
    
    def get_class_stats_summary(self):
        """클래스 변경 통계로부터 전체 요약 정보 생성"""
        # 원본 클래스 수집
        original_classes = set()
        new_classes = set()
        deleted_classes = set()
        deleted_count = 0
        
        # 각 변경 유형 분석
        for key, count in self.class_stats.items():
            if key.startswith("삭제됨"):
                # 삭제된 클래스: "삭제됨 (지정 클래스): 3" 또는 "삭제됨 (최대 클래스 초과): 80"
                match = re.search(r"삭제됨 \([^)]+\): (\d+\.?\d*)", key)
                if match:
                    class_id = match.group(1)
                    try:
                        # 소수점 값도 처리
                        original_classes.add(float(class_id))
                        deleted_classes.add(float(class_id))
                    except ValueError:
                        pass
                    deleted_count += count
            elif "→" in key:
                if key.startswith("Shift"):
                    # Shift된 클래스: "Shift: 21 → 22"
                    match = re.search(r"Shift: (\d+\.?\d*) → (\d+\.?\d*)", key)
                    if match:
                        try:
                            # 소수점 값도 처리
                            orig_id = float(match.group(1))
                            new_id = float(match.group(2))
                            original_classes.add(orig_id)
                            new_classes.add(new_id)
                        except ValueError:
                            pass
                else:
                    # 매핑된 클래스: "0 → 1"
                    parts = key.split(" → ")
                    if len(parts) == 2:
                        try:
                            # 소수점 값도 처리
                            orig_id = float(parts[0])
                            new_id = float(parts[1])
                            original_classes.add(orig_id)
                            new_classes.add(new_id)
                        except ValueError:
                            pass
        
        # 클래스 선택 모드에서 선택된 클래스 정보
        selected_classes_info = ""
        if self.selected_classes:
            selected_classes_info = f"선택된 클래스: {', '.join(sorted(self.selected_classes, key=lambda x: float(x) if '.' in x else int(x)))}\n"
        
        # 요약 정보 생성
        original_class_count = len(original_classes)
        new_class_count = len(new_classes)
        original_min_class = min(original_classes) if original_classes else 0
        original_max_class = max(original_classes) if original_classes else 0
        new_min_class = min(new_classes) if new_classes else 0
        new_max_class = max(new_classes) if new_classes else 0
        
        summary = {
            "total_annotations": self.total_annotations,
            "deleted_annotations": deleted_count,
            "original_class_count": original_class_count,
            "new_class_count": new_class_count,
            "original_min_class": original_min_class,
            "original_max_class": original_max_class,
            "new_min_class": new_min_class,
            "new_max_class": new_max_class,
            "selected_classes_info": selected_classes_info
        }
        
        return summary
    
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
        
    def get_annotation_info(self):
        """어노테이션 정보를 문자열로 반환"""
        info = "=== 어노테이션 통계 ===\n"
        info += f"총 어노테이션 개수: {self.total_annotations}개\n\n"
        
        info += "클래스별 어노테이션 개수:\n"
        # 클래스 ID를 정수로 변환하여 정렬 (소수점 처리)
        try:
            # 소수점 값이 있는 경우에 대비하여 float 변환 후 정렬
            sorted_classes = sorted(self.annotated_classes.items(), key=lambda x: float(x[0]))
        except ValueError:
            # 변환 실패 시 문자열 그대로 정렬
            sorted_classes = sorted(self.annotated_classes.items())
        
        for class_id, count in sorted_classes:
            info += f"클래스 {class_id}: {count}개\n"
        
        return info
    
    def run(self):
        """라벨 수정 메인 실행 함수"""
        start_time = time.time()
        
        # 이미지 경로 목록 가져오기
        image_paths = self.get_image_paths()
        unique_image_count = self.count_unique_image_source(image_paths)
        
        total_files = len(image_paths)
        processed_label_paths = set()
        
        print(f"처리 시작: 총 {total_files}개 이미지 파일")
        print(f"입력 모드: {self.input_mode}")
        
        if self.in_place:
            print("저장 모드: 원본 파일 직접 수정")
            if self.backup:
                print("백업 모드: 활성화 (.bak 파일 생성)")
        else:
            print(f"출력 경로: {self.output_path}")
        
        if self.class_mapping:
            print("클래스 매핑:", ", ".join([f"{k}→{v}" for k, v in self.class_mapping.items()]))
        
        if self.apply_shift:
            print(f"클래스 Shift: 시작={self.shift_start}, 값={self.shift_value}, 최대={self.shift_max_class}")
        
        if self.classes_to_delete:
            print("삭제할 클래스:", ", ".join(sorted(self.classes_to_delete, key=int)))
        
        if self.selected_classes:
            print("선택한 클래스:", ", ".join(sorted(self.selected_classes, key=int)))
        
        for idx, image_path in enumerate(image_paths):
            try:
                # 진행 상황 표시
                if idx % 100 == 0 or idx == len(image_paths) - 1:
                    percent = (idx + 1) / total_files * 100
                    print(f"처리 중... {idx+1}/{total_files} ({percent:.1f}%)", end='\r')
                
                # 이미지 경로를 라벨 경로로 변환 (한글 경로 지원)
                try:
                    # Path 객체를 사용하여 안전하게 경로 처리
                    img_path = Path(image_path)
                    
                    # 이미지 확장자를 제외한 베이스명 가져오기
                    base_name = img_path.stem
                    
                    # 라벨 디렉토리를 찾기 위해 이미지 경로에서 'JPEGImages'를 'labels'로 변경
                    parent_path = str(img_path.parent)
                    label_dir = parent_path.replace('JPEGImages', 'labels')
                    
                    # 라벨 파일 경로 생성
                    label_path = os.path.join(label_dir, f"{base_name}.txt")
                    
                    # 라벨 파일이 없는 경우를 대비한 대안 경로 생성
                    if not os.path.exists(label_path):
                        # 확장자 제외한 이미지 경로
                        img_path_no_ext = os.path.splitext(image_path)[0]
                        # 일반적인 라벨 경로 변환 시도
                        label_path = img_path_no_ext.replace('JPEGImages', 'labels') + '.txt'
                except Exception as e:
                    # Path 객체 사용 실패 시 기존 문자열 방식으로 폴백
                    if self.verbose:
                        print(f"\n경로 변환 중 오류 발생: {e}")
                    label_path = image_path.replace('JPEGImages', 'labels').replace('.jpg', '.txt').replace('.JPG', '.txt').replace('.jpeg', '.txt').replace('.JPEG', '.txt')
                
                if not os.path.exists(label_path):
                    if self.verbose:
                        print(f"\n경고: 라벨 파일을 찾을 수 없음: {label_path}")
                    self.missing_label_images.append(image_path)
                    self.missing_label_files += 1
                    continue
                
                # 중복 라벨 확인
                if label_path in processed_label_paths:
                    self.duplicate_label_paths.add(label_path)
                    continue
                
                processed_label_paths.add(label_path)
                
                # 라벨 파일 읽기 (한글 경로 지원)
                try:
                    with open(label_path, 'r', encoding='utf-8') as file:
                        lines = file.readlines()
                except UnicodeDecodeError:
                    # UTF-8 디코딩 실패 시 다른 인코딩 시도
                    encodings = ['cp949', 'euc-kr', 'latin1']
                    for encoding in encodings:
                        try:
                            with open(label_path, 'r', encoding=encoding) as file:
                                lines = file.readlines()
                            break
                        except UnicodeDecodeError:
                            continue
                    else:  # 모든 인코딩 시도 실패
                        if self.verbose:
                            print(f"\n오류: {label_path} 파일 인코딩을 결정할 수 없습니다.")
                        self.error_files += 1
                        continue
                
                # 원본 라벨 저장
                original_labels = []
                for line in lines:
                    line = line.strip()
                    if line:  # 빈 줄이 아닌 경우만 추가
                        original_labels.append(line)
                
                # 라벨 처리
                new_labels = self.process_labels(original_labels)
                
                # 라벨 파일 저장 (in-place 또는 새 경로)
                if self.in_place:
                    # 원본 파일 백업 (옵션이 활성화된 경우)
                    if self.backup:
                        backup_path = label_path + '.bak'
                        try:
                            shutil.copy2(label_path, backup_path)
                            self.backup_count += 1
                        except Exception as e:
                            if self.verbose:
                                print(f"\n백업 파일 생성 오류: {e}")
                    
                    # 원본 파일 직접 수정
                    try:
                        with open(label_path, 'w', encoding='utf-8') as file:
                            file.write("\n".join(new_labels))
                    except Exception as e:
                        if self.verbose:
                            print(f"\n라벨 파일 저장 오류: {e}")
                        self.error_files += 1
                        continue
                    
                    save_path = label_path  # 결과 요약용
                else:
                    try:
                        # 파일명만 추출하여 새 경로에 저장
                        filename = os.path.basename(label_path)
                        save_path = os.path.join(self.output_path, filename)
                        
                        # 디렉토리 구조 유지하려면 아래 코드 활성화
                        # rel_path = os.path.relpath(os.path.dirname(label_path), os.path.dirname(self.input_path))
                        # save_dir = os.path.join(self.output_path, rel_path)
                        # os.makedirs(save_dir, exist_ok=True)
                        # save_path = os.path.join(save_dir, filename)
                        
                        # 새 라벨 파일 저장
                        with open(save_path, 'w', encoding='utf-8') as file:
                            file.write("\n".join(new_labels))
                    except Exception as e:
                        if self.verbose:
                            print(f"\n라벨 파일 저장 오류: {e}")
                        self.error_files += 1
                        continue
                
                self.processed_files += 1
                
            except Exception as e:
                if self.verbose:
                    print(f"\n오류: {label_path} 처리 중 에러 발생: {e}")
                self.error_files += 1
        
        # 처리 완료 후 결과 표시
        elapsed_time = time.time() - start_time
        
        # 클래스 ID 기준으로 정렬된 통계
        sorted_stats = self.sort_stats_by_class()
        
        # 전체 요약 정보 생성
        class_summary = self.get_class_stats_summary()
        
        # 어노테이션 정보 가져오기
        annotation_info = self.get_annotation_info()
        
        print("\n\n=== 처리 결과 요약 ===")
        print(f"고유 이미지 수: {unique_image_count}")
        print(f"총 이미지 파일 수: {total_files}")
        print(f"처리 완료: {self.processed_files}")
        print(f"오류: {self.error_files}")
        print(f"라벨 파일 없음: {self.missing_label_files}")
        
        if self.duplicate_label_paths:
            print(f"중복 처리된 라벨 파일: {len(self.duplicate_label_paths)}개")
            
        if self.in_place:
            print(f"직접 수정된 라벨 파일: {self.processed_files}개")
            if self.backup:
                print(f"백업 파일 생성: {self.backup_count}개")
        
        print(f"소요 시간: {elapsed_time:.2f}초")
        
        print("\n=== 어노테이션 및 클래스 변경 요약 ===")
        print(f"전체 어노테이션 개수: {class_summary['total_annotations']}개")
        
        if class_summary['deleted_annotations'] > 0:
            print(f"삭제된 어노테이션: {class_summary['deleted_annotations']}개")
        
        if class_summary['selected_classes_info']:
            print(class_summary['selected_classes_info'], end='')
        
        print(f"원본 클래스 범위: {class_summary['original_min_class']} ~ {class_summary['original_max_class']} ({class_summary['original_class_count']}개 클래스)")
        print(f"변경 후 클래스 범위: {class_summary['new_min_class']} ~ {class_summary['new_max_class']} ({class_summary['new_class_count']}개 클래스)")
        
        print("\n=== 클래스 변경 통계 (클래스 ID 순) ===")
        for key, count in sorted_stats.items():
            print(f"{key}: {count}개")
        
        print("\n" + annotation_info)
        
        # 결과 요약 파일 저장 경로 결정
        if self.in_place:
            # in-place 모드에서는 현재 디렉토리에 저장
            summary_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "result_summary.txt")
        else:
            # 일반 모드에서는 출력 디렉토리에 저장
            summary_path = os.path.join(self.output_path, "result_summary.txt")
            
        try:
            with open(summary_path, 'w', encoding='utf-8') as f:
                f.write("=== 처리 결과 요약 ===\n")
                f.write(f"고유 이미지 수: {unique_image_count}\n")
                f.write(f"총 이미지 파일 수: {total_files}\n")
                f.write(f"처리 완료: {self.processed_files}\n")
                f.write(f"오류: {self.error_files}\n")
                f.write(f"라벨 파일 없음: {self.missing_label_files}\n")
                
                if self.duplicate_label_paths:
                    f.write(f"중복 처리된 라벨 파일: {len(self.duplicate_label_paths)}개\n")
                
                f.write(f"소요 시간: {elapsed_time:.2f}초\n\n")
                
                f.write("=== 어노테이션 및 클래스 변경 요약 ===\n")
                f.write(f"전체 어노테이션 개수: {class_summary['total_annotations']}개\n")
                
                if class_summary['deleted_annotations'] > 0:
                    f.write(f"삭제된 어노테이션: {class_summary['deleted_annotations']}개\n")
                
                if class_summary['selected_classes_info']:
                    f.write(class_summary['selected_classes_info'])
                
                f.write(f"원본 클래스 범위: {class_summary['original_min_class']} ~ {class_summary['original_max_class']} ({class_summary['original_class_count']}개 클래스)\n")
                f.write(f"변경 후 클래스 범위: {class_summary['new_min_class']} ~ {class_summary['new_max_class']} ({class_summary['new_class_count']}개 클래스)\n\n")
                
                f.write("=== 클래스 변경 통계 (클래스 ID 순) ===\n")
                for key, count in sorted_stats.items():
                    f.write(f"{key}: {count}개\n")
                
                f.write("\n" + annotation_info)
                
            print(f"\n요약 파일이 저장되었습니다: {summary_path}")
        except Exception as e:
            print(f"\n요약 파일 저장 중 오류 발생: {e}")
        
        print(f"\n처리 완료: 총 {total_files}개 이미지 중 {self.processed_files}개 라벨 처리 완료 ({self.error_files}개 오류)")

def parse_args():
    parser = argparse.ArgumentParser(description='YOLO 라벨 수정 CLI 도구')
    
    # 필수 인자
    parser.add_argument('--input-path', required=True, help='이미지 목록 파일 또는 이미지 폴더 경로')
    parser.add_argument('--input-mode', required=True, choices=['file', 'folder'], help='입력 모드 (file: 이미지 목록 파일, folder: 이미지 폴더)')
    
    # 출력 관련 인자 (in-place 모드를 사용할 경우 output-path는 필수가 아님)
    parser.add_argument('--output-path', help='수정된 라벨 파일 저장 경로')
    parser.add_argument('--in-place', action='store_true', help='원본 라벨 파일을 직접 수정 (output-path 지정 불필요)')
    parser.add_argument('--backup', action='store_true', help='원본 파일 수정 시 백업 파일 생성 (.bak 확장자)')
    
    # 클래스 매핑 관련 인자
    parser.add_argument('--class-mapping', help='클래스 매핑 (형식: "원본:새클래스,원본:새클래스,...") 예: "0:1,2:3"')
    
    # 클래스 시프트 관련 인자
    parser.add_argument('--shift-start', type=int, default=0, help='시프트 시작 클래스 ID')
    parser.add_argument('--shift-value', type=int, help='시프트 값 (+/-)')
    parser.add_argument('--shift-max', type=int, default=80, help='최대 클래스 ID')
    
    # 클래스 삭제 관련 인자
    parser.add_argument('--delete-classes', help='삭제할 클래스 ID (콤마로 구분) 예: "0,5,9"')
    
    # 클래스 선택 관련 인자
    parser.add_argument('--select-classes', help='선택할 클래스 ID (콤마로 구분) 예: "1,3,5"')
    
    # 기타 인자
    parser.add_argument('--verbose', action='store_true', help='상세 로그 출력')
    
    args = parser.parse_args()
    
    # 인자 유효성 검사
    if not args.in_place and not args.output_path:
        parser.error("--in-place를 사용하지 않을 경우 --output-path는 필수입니다.")
    
    return args

def main():
    # 명령줄 인자 처리
    args = parse_args()
    
    # YOLO 라벨 수정기 생성
    modifier = YOLOLabelModifier(args)
    
    # 실행
    modifier.run()

if __name__ == "__main__":
    main()