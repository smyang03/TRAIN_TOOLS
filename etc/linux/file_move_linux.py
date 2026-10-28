#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import shutil
import argparse
import logging
from pathlib import Path

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class FileOrganizerCLI:
    def __init__(self):
        self.args = None
        self.files_processed = {"jpg": 0, "txt": 0, "skipped": 0}
        
    def parse_arguments(self):
        """명령줄 인수 파싱"""
        parser = argparse.ArgumentParser(description='파일 분류 프로그램 (CLI 버전)')
        
        parser.add_argument('--source', '-s', required=True, help='원본 폴더 경로')
        parser.add_argument('--dest', '-d', help='대상 폴더 경로')
        parser.add_argument('--operation', '-o', choices=['copy', 'move'], default='copy', 
                            help='작업 선택: copy(복사) 또는 move(이동) (기본값: copy)')
        parser.add_argument('--include-subfolders', '-r', action='store_true', 
                            help='하위 폴더 포함 (기본값: False)')
        parser.add_argument('--encoding', '-e', choices=['auto', 'utf-8', 'euc-kr', 'cp949', 'ascii'], 
                            default='auto', help='텍스트 인코딩 (기본값: auto)')
        parser.add_argument('--file-list', '-f', nargs='+', 
                            help='처리할 파일 목록이 포함된 텍스트 파일 경로 (여러 개 지정 가능)')
        parser.add_argument('--copy-to-parent', '-p', action='store_true', 
                            help='각 파일의 부모 폴더로 복사/이동 (기본값: False)')
        parser.add_argument('--log-level', '-l', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], 
                            default='INFO', help='로그 레벨 설정 (기본값: INFO)')
        
        self.args = parser.parse_args()
        
        # 로그 레벨 설정
        logger.setLevel(getattr(logging, self.args.log_level))
        
        # 인수 검증
        if not self.args.copy_to_parent and not self.args.dest:
            parser.error("--copy-to-parent가 설정되지 않은 경우 --dest 인수가 필요합니다.")
            
        return self.args
    
    def get_unique_path(self, base_path):
        """중복 파일명 처리를 위한 유니크 경로 생성 함수"""
        if not os.path.exists(base_path):
            return base_path
        
        directory, filename = os.path.split(base_path)
        name, ext = os.path.splitext(filename)
        
        counter = 1
        while os.path.exists(base_path):
            new_filename = f"{name}_{counter}{ext}"
            base_path = os.path.join(directory, new_filename)
            counter += 1
        
        return base_path
    
    def find_matching_txt_file(self, jpg_path, base_name):
        """JPG 파일 경로로부터 매칭되는 TXT 파일 찾기"""
        possible_txt_paths = []
        
        # 1. 같은 폴더 내 같은 이름의 TXT 파일
        jpg_dir = os.path.dirname(jpg_path)
        basic_txt_path = os.path.join(jpg_dir, f"{base_name}.txt")
        possible_txt_paths.append(basic_txt_path)
        
        # 2. JPEGImages 폴더 내 파일이라면 대응하는 labels 폴더 확인
        if 'JPEGImages' in jpg_path:
            alt_txt_path = jpg_path.replace('JPEGImages', 'labels')
            alt_txt_path = os.path.splitext(alt_txt_path)[0] + '.txt'
            possible_txt_paths.append(alt_txt_path)
        
        # 가능한 경로 중 존재하는 파일 확인
        for path in possible_txt_paths:
            if os.path.exists(path):
                return path
        
        return None
    
    def process_txt_file(self, txt_path, dest_txt_path, operation, encoding, file_name=None):
        """텍스트 파일 복사/이동 처리"""
        if not file_name:
            file_name = os.path.basename(txt_path)
            
        try:
            # 인코딩 자동 감지 또는 지정된 인코딩 사용
            if encoding == "auto":
                encodings_to_try = ["utf-8", "euc-kr", "cp949", "ascii"]
                content = None
                
                for enc in encodings_to_try:
                    try:
                        with open(txt_path, 'r', encoding=enc) as f:
                            content = f.read()
                        break  # 성공적으로 읽었으면 루프 종료
                    except UnicodeDecodeError:
                        continue
                
                if content is not None:
                    # 성공적으로 읽은 후 새 위치에 쓰기
                    if operation == "copy":
                        with open(dest_txt_path, 'w', encoding='utf-8') as f:
                            f.write(content)
                        action = "복사됨"
                    else:  # move
                        with open(dest_txt_path, 'w', encoding='utf-8') as f:
                            f.write(content)
                        try:
                            os.remove(txt_path)
                        except PermissionError:
                            logger.warning(f"경고: 원본 파일 삭제 권한 없음: {file_name}")
                        action = "이동됨"
                else:
                    # 인코딩 감지 실패 시 바이너리 모드로 복사 시도
                    if operation == "copy":
                        shutil.copy2(txt_path, dest_txt_path)
                        action = "바이너리 모드로 복사됨"
                    else:  # move
                        shutil.move(txt_path, dest_txt_path)
                        action = "바이너리 모드로 이동됨"
            else:
                # 특정 인코딩 사용
                try:
                    with open(txt_path, 'r', encoding=encoding) as f_in:
                        content = f_in.read()
                    with open(dest_txt_path, 'w', encoding='utf-8') as f_out:
                        f_out.write(content)
                    
                    if operation == "move":
                        try:
                            os.remove(txt_path)
                        except PermissionError:
                            logger.warning(f"경고: 원본 파일 삭제 권한 없음: {file_name}")
                    
                    action = "복사됨" if operation == "copy" else "이동됨"
                except UnicodeDecodeError:
                    # 인코딩 오류 시 바이너리 모드로 복사 시도
                    if operation == "copy":
                        shutil.copy2(txt_path, dest_txt_path)
                        action = "바이너리 모드로 복사됨"
                    else:  # move
                        shutil.move(txt_path, dest_txt_path)
                        action = "바이너리 모드로 이동됨"
            
            logger.info(f"{file_name} - 텍스트 파일이 {action}")
            return True
        except Exception as e:
            logger.error(f"오류: {file_name} - {str(e)}")
            return False
    
    def process_files(self):
        """파일 처리 실행"""
        source = self.args.source
        dest = self.args.dest
        operation = self.args.operation
        encoding = self.args.encoding
        include_subfolders = self.args.include_subfolders
        use_file_list = self.args.file_list is not None
        copy_to_parent = self.args.copy_to_parent
        
        if not os.path.isdir(source):
            logger.error(f"오류: 원본 폴더가 존재하지 않습니다: {source}")
            return False
        
        if not copy_to_parent and not os.path.isdir(dest):
            logger.error(f"오류: 대상 폴더가 존재하지 않습니다: {dest}")
            return False
        
        if use_file_list and not self.args.file_list:
            logger.error("오류: 파일 목록이 지정되지 않았습니다.")
            return False
        
        # JPEGImages와 labels 폴더 생성 (대상 폴더 내에)
        jpeg_folder = None
        labels_folder = None
        
        if not copy_to_parent:
            jpeg_folder = os.path.join(dest, "JPEGImages")
            labels_folder = os.path.join(dest, "labels")
            
            # 폴더가 없으면 생성
            os.makedirs(jpeg_folder, exist_ok=True)
            os.makedirs(labels_folder, exist_ok=True)
            
            logger.info(f"이미지 파일 저장 경로: {jpeg_folder}")
            logger.info(f"텍스트 파일 저장 경로: {labels_folder}")
        else:
            logger.info("각 파일 목록의 부모 폴더로 복사/이동합니다.")
        
        # 파일 처리 카운터 초기화
        self.files_processed = {"jpg": 0, "txt": 0, "skipped": 0}
        files = []
        
        # 파일 목록 가져오기
        if use_file_list:
            # 파일 목록 텍스트 파일 사용
            logger.info("파일 목록 읽는 중...")
            
            for file_list_path in self.args.file_list:
                try:
                    logger.info(f"파일 목록 처리 중: {file_list_path}")
                    
                    # 파일 목록 읽기 (여러 인코딩 시도)
                    content = None
                    for enc in ["utf-8", "euc-kr", "cp949", "ascii"]:
                        try:
                            with open(file_list_path, 'r', encoding=enc) as f:
                                content = f.read()
                            break
                        except UnicodeDecodeError:
                            continue
                    
                    if content is None:
                        logger.warning(f"경고: 파일 목록 '{os.path.basename(file_list_path)}'을 읽을 수 없습니다. 건너뜁니다.")
                        continue
                    
                    # 각 줄을 파일 경로로 처리
                    paths = [line.strip() for line in content.splitlines() if line.strip()]
                    
                    for file_path in paths:
                        # 절대 경로인지 상대 경로인지 확인
                        if os.path.isabs(file_path):
                            # 절대 경로인 경우
                            if os.path.isfile(file_path):
                                # 상대 경로도 계산 (로깅용)
                                try:
                                    rel_path = os.path.relpath(file_path, source)
                                except ValueError:
                                    # 다른 드라이브에 있는 경우 등 상대 경로 계산 불가능할 때
                                    rel_path = os.path.basename(file_path)
                                files.append((file_path, rel_path, file_list_path))  # 세 번째 요소로 파일 목록 경로 추가
                        else:
                            # 상대 경로인 경우 (소스 폴더 기준)
                            abs_path = os.path.join(source, file_path)
                            if os.path.isfile(abs_path):
                                files.append((abs_path, file_path, file_list_path))
                    
                    logger.info(f"파일 목록 '{os.path.basename(file_list_path)}'에서 {len(paths)}개 경로 읽음")
                    
                except Exception as e:
                    logger.error(f"파일 목록 '{os.path.basename(file_list_path)}' 처리 중 오류 발생: {str(e)}")
        else:
            # 일반 폴더 스캔 모드
            if include_subfolders:
                logger.info("모든 하위 폴더 스캔 중...")
                
                for root_path, _, filenames in os.walk(source):
                    for filename in filenames:
                        file_path = os.path.join(root_path, filename)
                        # 상대 경로 계산 (원본 폴더 기준)
                        rel_path = os.path.relpath(file_path, source)
                        files.append((file_path, rel_path, None))
            else:
                # 현재 폴더의 파일만 처리
                logger.info("현재 폴더 스캔 중...")
                for filename in os.listdir(source):
                    file_path = os.path.join(source, filename)
                    if os.path.isfile(file_path):
                        files.append((file_path, filename, None))
        
        # 파일 쌍 처리를 위한 딕셔너리
        paired_files = {}
        
        # 파일 분석 단계: JPG 파일을 키로, 연결된 TXT 파일을 값으로 저장
        logger.info("파일 분석 중...")
        
        for item in files:
            if len(item) == 3:  # 파일 목록에서 가져온 경우
                source_path, rel_path, list_path = item
            else:  # 일반 폴더 스캔에서 가져온 경우
                source_path, rel_path = item
                list_path = None
                
            file_name = os.path.basename(rel_path)
            base_name, ext = os.path.splitext(file_name)
            
            if ext.lower() in ['.jpg', '.jpeg']:
                # JPG 파일일 경우
                # 대응하는 TXT 파일 경로 확인
                txt_path = self.find_matching_txt_file(source_path, base_name)
                
                # 파일 쌍 정보 저장
                paired_files[base_name] = {
                    'jpg_path': source_path,
                    'jpg_name': file_name,
                    'txt_path': txt_path,
                    'txt_name': f"{base_name}.txt" if txt_path else None,
                    'list_path': list_path  # 파일 목록 경로 저장
                }
        
        # 파일 처리 시작
        total_files = len(paired_files)
        if total_files == 0:
            logger.warning("처리할 JPG 파일이 없습니다.")
            return False
            
        logger.info(f"총 {total_files}개의 파일 쌍 처리 시작...")
        processed_count = 0
        
        for base_name, file_info in paired_files.items():
            jpg_path = file_info['jpg_path']
            jpg_name = file_info['jpg_name']
            txt_path = file_info['txt_path']
            txt_name = file_info['txt_name']
            
            # 진행 상황 업데이트
            processed_count += 1
            progress_percentage = int(processed_count / total_files * 100)
            if processed_count % 10 == 0 or processed_count == total_files:  # 10개 처리마다 또는 마지막에 로그 출력
                logger.info(f"처리 중... {processed_count}/{total_files} ({progress_percentage}%)")
            
            logger.debug(f"처리 중: {jpg_name}")
            
            # JPG 파일 처리
            if copy_to_parent:
                # 파일 목록의 부모 폴더 찾기
                list_path = file_info.get('list_path')
                if list_path:
                    file_list_parent = os.path.dirname(list_path)
                else:
                    # 파일 목록 정보가 없는 경우 처리
                    logger.warning(f"경고: {jpg_name} - 파일 목록 정보를 찾을 수 없습니다.")
                    self.files_processed["skipped"] += 1
                    continue
                
                jpeg_folder = os.path.join(file_list_parent, "JPEGImages")
                labels_folder = os.path.join(file_list_parent, "labels")
                
                # 폴더가 없으면 생성
                os.makedirs(jpeg_folder, exist_ok=True)
                os.makedirs(labels_folder, exist_ok=True)
            
            # JPG 파일 복사/이동
            dest_jpg_path = os.path.join(jpeg_folder, jpg_name)
            dest_jpg_path = self.get_unique_path(dest_jpg_path)
            
            try:
                if operation == "copy":
                    shutil.copy2(jpg_path, dest_jpg_path)
                    action_jpg = "복사됨"
                    if copy_to_parent:
                        action_jpg += " (파일 목록 부모 폴더로)"
                else:  # move
                    shutil.move(jpg_path, dest_jpg_path)
                    action_jpg = "이동됨"
                    if copy_to_parent:
                        action_jpg += " (파일 목록 부모 폴더로)"
                
                self.files_processed["jpg"] += 1
                logger.info(f"{jpg_name} - 이미지 파일이 {action_jpg}")
            except Exception as e:
                logger.error(f"오류: {jpg_name} - {str(e)}")
                self.files_processed["skipped"] += 1
            
            # TXT 파일 처리
            if txt_path:
                # TXT 파일이 존재하는 경우
                dest_txt_path = os.path.join(labels_folder, txt_name)
                dest_txt_path = self.get_unique_path(dest_txt_path)
                
                if self.process_txt_file(txt_path, dest_txt_path, operation, encoding, txt_name):
                    self.files_processed["txt"] += 1
                else:
                    self.files_processed["skipped"] += 1
        
        # 완료 메시지
        logger.info("처리 완료!")
        logger.info(f"이미지 파일: {self.files_processed['jpg']}개")
        logger.info(f"텍스트 파일: {self.files_processed['txt']}개")
        if self.files_processed["skipped"] > 0:
            logger.info(f"건너뛴 파일: {self.files_processed['skipped']}개")
        
        return True

def main():
    try:
        app = FileOrganizerCLI()
        app.parse_arguments()
        success = app.process_files()
        
        if success:
            logger.info("프로그램이 성공적으로 완료되었습니다.")
            return 0
        else:
            logger.error("프로그램이 오류와 함께 종료되었습니다.")
            return 1
            
    except KeyboardInterrupt:
        logger.warning("사용자에 의해 프로그램이 중단되었습니다.")
        return 130
    except Exception as e:
        logger.error(f"예상치 못한 오류가 발생했습니다: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())