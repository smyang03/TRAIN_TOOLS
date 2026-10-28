# 스크립트를 다운로드하고 실행 권한 부여
chmod +x yolo_db_compare.py

# 중복 파일 목록 표시
./yolo_db_compare.py /path/to/base_db /path/to/second_db --action list-duplicates

# 고유 파일 목록 표시
./yolo_db_compare.py /path/to/base_db /path/to/second_db --action list-unique

# 고유 파일만 복사
./yolo_db_compare.py /path/to/base_db /path/to/second_db --action copy-unique --output /path/to/output_dir

# 두 디렉토리 병합 (중복 없이)
./yolo_db_compare.py /path/to/base_db /path/to/second_db --action merge --output /path/to/merged_dir