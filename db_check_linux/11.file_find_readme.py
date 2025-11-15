# 기본 사용법
./copy_files.py --source /경로/소스폴더 --dest /경로/목적지폴더 --list /경로/파일리스트.txt

# 'backup', 'temp' 단어가 포함된 파일 제외
./copy_files.py -s /경로/소스폴더 -d /경로/목적지폴더 -l /경로/파일리스트.txt -e backup temp

# 축약형 옵션 사용
./copy_files.py -s /경로/소스폴더 -d /경로/목적지폴더 -l /경로/파일리스트.txt -e test draft old