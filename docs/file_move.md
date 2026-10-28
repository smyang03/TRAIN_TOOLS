# 파일 분류 프로그램 사용 가이드 (CLI 버전)

이 프로그램은 JPG 이미지 파일과 관련된 TXT 파일을 처리하는 명령줄 도구입니다. 원본 GUI 애플리케이션의 기능을 리눅스 서버 환경에서 실행할 수 있도록 CLI 형태로 변환한 버전입니다.

## 설치 및 실행 권한 설정

```bash
# 파일을 실행 가능하게 설정
chmod +x file_organizer_cli.py

# 또는 다음과 같이 실행할 수 있습니다
python3 file_organizer_cli.py [옵션]
```

## 기본 사용법

```bash
./file_organizer_cli.py --source /원본/폴더/경로 --dest /대상/폴더/경로
```

## 주요 옵션

| 옵션                      | 설명                                           | 기본값 |
|---------------------------|------------------------------------------------|--------|
| `--source`, `-s`          | 원본 폴더 경로 (필수)                          | -      |
| `--dest`, `-d`            | 대상 폴더 경로                                 | -      |
| `--operation`, `-o`       | 작업 선택: copy(복사) 또는 move(이동)          | copy   |
| `--include-subfolders`, `-r` | 하위 폴더 포함                               | False  |
| `--encoding`, `-e`        | 텍스트 인코딩 (auto/utf-8/euc-kr/cp949/ascii)  | auto   |
| `--file-list`, `-f`       | 처리할 파일 목록이 포함된 텍스트 파일(들)      | -      |
| `--copy-to-parent`, `-p`  | 각 파일 목록의 부모 폴더로 복사/이동           | False  |
| `--log-level`, `-l`       | 로그 레벨 (DEBUG/INFO/WARNING/ERROR)           | INFO   |

## 사용 예시

### 1. 기본 복사 작업

```bash
./file_organizer_cli.py --source /data/images --dest /data/processed
```

### 2. 하위 폴더 포함, 이동 작업

```bash
./file_organizer_cli.py --source /data/raw_images --dest /data/organized --operation move --include-subfolders
```

### 3. 특정 파일 목록만 처리

```bash
./file_organizer_cli.py --source /data/images --dest /data/selected --file-list /path/to/file_list1.txt /path/to/file_list2.txt
```

### 4. 파일 목록의 부모 폴더로 복사

```bash
./file_organizer_cli.py --source /data/images --copy-to-parent --file-list /projects/project1/filelist.txt
```

### 5. 디버그 로그 출력

```bash
./file_organizer_cli.py --source /data/images --dest /data/output --log-level DEBUG
```

## 주요 기능

1. **파일 처리 옵션**:
   - 복사 또는 이동 작업 선택
   - 하위 폴더 포함 여부 선택
   - 특정 파일 목록만 처리하는 옵션

2. **특수 기능**:
   - "부모 폴더로 복사/이동" 옵션
   - JPEGImages/labels 폴더 구조 자동 생성
   - 다양한 인코딩 지원 (UTF-8, EUC-KR, CP949, ASCII)
   - 중복 파일명 자동 처리

## 파일 목록 형식

파일 목록은 텍스트 파일(.txt)로, 각 줄에 하나의 파일 경로가 포함되어 있어야 합니다:

```
/절대/경로/이미지1.jpg
/절대/경로/이미지2.jpg
상대/경로/이미지3.jpg
```

## 주의사항

1. 대용량 파일 처리 시 충분한 디스크 공간이 있는지 확인하세요.
2. 이동 작업 시 원본 파일이 삭제되므로 주의하세요.
3. 실행 전 항상 중요한 데이터는 백업하세요.