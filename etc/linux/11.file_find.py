#!/usr/bin/env python3
import os
import shutil
import sys
import argparse
import time

def find_file_in_dir(source_dir, filename, exclude_words=None):
    """
    소스 폴더와 그 하위 폴더에서 지정된 .TXT 파일명을 찾습니다.
    """
    if exclude_words is None:
        exclude_words = []
    
    print(f"'{filename}' 파일 검색 중...")
    
    for root, dirs, files in os.walk(source_dir):
        if filename in files:
            file_path = os.path.join(root, filename)
            # 파일 경로에 제외 단어가 포함되어 있는지 확인
            if any(word in file_path for word in exclude_words):
                continue
            print(f"  파일 발견: {file_path}")
            return file_path
    
    print(f"  '{filename}' 파일을 찾을 수 없습니다.")
    return None

def restore_original_files(source_dir, file_list_path, dest_dir, exclude_words=None):
    """
    파일 리스트에 있는 JPG 파일명을 TXT로 변환하여 
    소스 폴더와 하위 폴더에서 찾아 목적지 폴더로 복사하여 원본 파일을 복원합니다.
    제외 단어가 포함된 파일은 복사하지 않습니다.
    진행 상태를 표시합니다.
    """
    # 파일 리스트와 폴더 확인
    if not os.path.isdir(source_dir):
        print(f"오류: 원본 폴더가 존재하지 않습니다: {source_dir}")
        return False
    
    if not os.path.isfile(file_list_path):
        print(f"오류: 파일 리스트가 존재하지 않습니다: {file_list_path}")
        return False
    
    if not os.path.isdir(dest_dir):
        print(f"오류: 목적지 폴더가 존재하지 않습니다: {dest_dir}")
        return False
    
    # 제외할 단어 목록 확인
    if exclude_words is None:
        exclude_words = []
    
    # 전체 파일 수 확인
    total_files = sum(1 for line in open(file_list_path) if line.strip())
    print(f"총 {total_files}개 파일을 처리할 예정입니다.")
    
    copied_count = 0
    not_found_count = 0
    
    start_time = time.time()
    
    # 파일 리스트 읽기
    with open(file_list_path, 'r') as f:
        for current_num, line in enumerate(f, 1):
            jpg_path = line.strip()
            if not jpg_path:  # 빈 줄 무시
                continue
            
            # 진행 상황 표시
            percent = (current_num / total_files) * 100
            elapsed_time = time.time() - start_time
            files_per_sec = current_num / elapsed_time if elapsed_time > 0 else 0
            
            print(f"\n[{current_num}/{total_files} - {percent:.1f}%] 처리 중... (속도: {files_per_sec:.1f}파일/초)")
            
            # JPG 파일명을 TXT 파일명으로 변환
            txt_path = jpg_path.replace("/JPEGImages/", "/labels/").replace(".jpg", ".txt")
            
            # 파일명만 추출
            txt_filename = os.path.basename(txt_path)
            
            # 확장자가 .txt가 아니면 변경
            if not txt_filename.lower().endswith('.txt'):
                txt_filename = os.path.splitext(txt_filename)[0] + '.txt'
                print(f"파일명을 TXT로 변환: {txt_filename}")
            
            # 소스 폴더와 하위 폴더에서 해당 TXT 파일 찾기
            source_file = find_file_in_dir(source_dir, txt_filename, exclude_words)
            
            # 파일을 찾지 못한 경우
            if source_file is None:
                print(f"경고: 원본 파일을 찾을 수 없음: {txt_filename}")
                not_found_count += 1
                continue
            
            # 파일 복사
            dest_file = os.path.join(dest_dir, txt_filename)
            print(f"복사 중: {source_file} -> {dest_file}")
            
            try:
                shutil.copy2(source_file, dest_file)
                copied_count += 1
                print(f"복사 완료: {copied_count}번째 파일")
            except Exception as e:
                print(f"오류: 파일 복사 실패: {source_file} -> {e}")
    
    total_time = time.time() - start_time
    
    print(f"\n==== 작업 완료! ====")
    print(f"- 총 처리 파일: {total_files}개")
    print(f"- 복사된 파일: {copied_count}개")
    print(f"- 찾지 못한 파일: {not_found_count}개")
    print(f"- 소요 시간: {total_time:.1f}초 (평균 {copied_count/total_time:.1f}파일/초)")
    
    return True

if __name__ == "__main__":
    # 명령줄 인자 파싱
    parser = argparse.ArgumentParser(description='파일 리스트를 기준으로 원본 파일 복원 도구')
    parser.add_argument('--source', '-s', required=True, help='원본 파일이 있는 소스 폴더 경로')
    parser.add_argument('--list', '-l', required=True, help='복원할 파일명 리스트 (JPG 파일명)')
    parser.add_argument('--dest', '-d', required=True, help='복원된 파일을 저장할 목적지 폴더 경로')
    parser.add_argument('--exclude-words', '-e', nargs='+', help='파일 경로에서 제외할 단어들', default=[])
    
    args = parser.parse_args()
    
    restore_original_files(args.source, args.list, args.dest, args.exclude_words)