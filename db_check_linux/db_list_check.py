#!/usr/bin/env python3
import os
import argparse
import shutil

def get_file_list(directory):
    """지정된 디렉토리의 모든 파일 목록을 반환합니다."""
    file_list = []
    for root, _, files in os.walk(directory):
        for file in files:
            # 전체 경로에서 기본 디렉토리를 제외한 상대 경로를 저장
            rel_path = os.path.join(root, file).replace(directory, '').lstrip('/')
            file_list.append(rel_path)
    return file_list

def compare_directories(base_dir, second_dir, action, output_dir=None):
    """두 디렉토리를 비교하고 지정된 작업을 수행합니다."""
    base_files = set(get_file_list(base_dir))
    second_files = set(get_file_list(second_dir))
    
    if action == "list-duplicates":
        # 두 디렉토리에 모두 존재하는 파일 목록
        duplicates = base_files.intersection(second_files)
        print(f"중복 파일 수: {len(duplicates)}")
        for file in sorted(duplicates):
            print(file)
            
    elif action == "list-unique":
        # 두 번째 디렉토리에만 있는 파일 목록
        unique_files = second_files - base_files
        print(f"고유 파일 수: {len(unique_files)}")
        for file in sorted(unique_files):
            print(file)
            
    elif action == "copy-unique" and output_dir:
        # 두 번째 디렉토리에만 있는 파일을 출력 디렉토리로 복사
        unique_files = second_files - base_files
        print(f"고유 파일 {len(unique_files)}개를 {output_dir}로 복사합니다...")
        for file in unique_files:
            src_path = os.path.join(second_dir, file)
            dst_path = os.path.join(output_dir, file)
            # 대상 디렉토리가 없으면 생성
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            shutil.copy2(src_path, dst_path)
        print("복사 완료!")
        
    elif action == "merge" and output_dir:
        # 기본 디렉토리의 모든 파일 + 두 번째 디렉토리의 고유 파일을 출력 디렉토리로 복사
        unique_files = second_files - base_files
        print(f"기본 디렉토리의 모든 파일과 두 번째 디렉토리의 고유 파일 {len(unique_files)}개를 {output_dir}로 병합합니다...")
        
        # 먼저 기본 디렉토리의 모든 파일 복사
        for file in base_files:
            src_path = os.path.join(base_dir, file)
            dst_path = os.path.join(output_dir, file)
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            shutil.copy2(src_path, dst_path)
        
        # 두 번째 디렉토리의 고유 파일 복사
        for file in unique_files:
            src_path = os.path.join(second_dir, file)
            dst_path = os.path.join(output_dir, file)
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            shutil.copy2(src_path, dst_path)
        print("병합 완료!")

def main():
    parser = argparse.ArgumentParser(description='YOLO 학습 데이터베이스 디렉토리 비교 및 관리 도구')
    parser.add_argument('base_dir', help='기준이 되는 기본 디렉토리 경로')
    parser.add_argument('second_dir', help='비교할 두 번째 디렉토리 경로')
    parser.add_argument('--action', choices=['list-duplicates', 'list-unique', 'copy-unique', 'merge'], 
                        required=True, help='수행할 작업')
    parser.add_argument('--output', help='출력 디렉토리 (copy-unique 또는 merge 작업에 필요)')
    
    args = parser.parse_args()
    
    if (args.action in ['copy-unique', 'merge']) and not args.output:
        parser.error(f"'{args.action}' 작업에는 --output 인수가 필요합니다")
    
    compare_directories(args.base_dir, args.second_dir, args.action, args.output)

if __name__ == "__main__":
    main()