# YOLO 라벨 수정 CLI 도구 사용법

이 도구는 YOLO 형식의 라벨 파일을 수정하기 위한 명령줄 인터페이스(CLI) 도구입니다. 리눅스 서버 환경에서 사용할 수 있으며, 다양한 라벨 수정 기능을 제공합니다.

## 기능

- **두 가지 입력 모드**: 이미지 목록 파일 또는 이미지 폴더
- **클래스 매핑**: 특정 클래스 ID를 다른 ID로 변경
- **클래스 Shift**: 지정 범위의 클래스 ID를 일정값만큼 증가/감소
- **클래스 삭제**: 특정 클래스 ID를 가진 객체 제거
- **클래스 선택**: 특정 클래스 ID만 선택하여 라벨 생성
- **어노테이션 정보 표시**: 처리된 라벨의 클래스별 어노테이션 통계 제공

## 설치 및 요구사항

- Python 3.6 이상
- NumPy 라이브러리

```bash
pip install numpy
```

## 기본 사용법

```bash
python cli_yolo_label_modifier.py --input-path <입력 경로> --input-mode <file|folder> --output-path <출력 경로> [옵션]
```

### 필수 인자

- `--input-path`: 이미지 목록 파일 또는 이미지 폴더 경로
- `--input-mode`: 입력 모드 (`file` 또는 `folder`)

### 출력 관련 인자 (둘 중 하나는 필수)

- `--output-path`: 수정된 라벨 파일을 저장할 경로 (새 위치에 저장)
- `--in-place`: 원본 라벨 파일을 직접 수정 (플래그)
  - `--backup`: 원본 파일 직접 수정 시 백업 파일(.bak) 생성 (플래그)

### 선택적 인자

- `--class-mapping`: 클래스 매핑 (형식: "원본:새클래스,원본:새클래스,...")
- `--shift-start`: 시프트 시작 클래스 ID (기본값: 0)
- `--shift-value`: 시프트 값 (+/-)
- `--shift-max`: 최대 클래스 ID (기본값: 80)
- `--delete-classes`: 삭제할 클래스 ID (콤마로 구분)
- `--select-classes`: 선택할 클래스 ID (콤마로 구분)
- `--verbose`: 상세 로그 출력

## 사용 예시

### 1. 기본 실행 (새 경로에 저장)

이미지 목록 파일 모드:
```bash
python cli_yolo_label_modifier.py --input-path /path/to/images.txt --input-mode file --output-path /path/to/output
```

이미지 폴더 모드:
```bash
python cli_yolo_label_modifier.py --input-path /path/to/images --input-mode folder --output-path /path/to/output
```

### 2. 원본 파일 직접 수정 (in-place)

기본 실행 (백업 없음):
```bash
python cli_yolo_label_modifier.py --input-path /path/to/images.txt --input-mode file --in-place
```

백업 파일 생성:
```bash
python cli_yolo_label_modifier.py --input-path /path/to/images --input-mode folder --in-place --backup
```

### 3. 클래스 매핑 사용

클래스 ID 0을 1로, 2를 3으로 변경 (새 경로에 저장):
```bash
python cli_yolo_label_modifier.py --input-path /path/to/images.txt --input-mode file --output-path /path/to/output --class-mapping "0:1,2:3"
```

클래스 ID 0을 1로, 2를 3으로 변경 (원본 파일 수정):
```bash
python cli_yolo_label_modifier.py --input-path /path/to/images.txt --input-mode file --in-place --class-mapping "0:1,2:3"
```

### 4. 클래스 Shift 사용

클래스 ID 5 이상의 모든 클래스를 2씩 증가:
```bash
python cli_yolo_label_modifier.py --input-path /path/to/images --input-mode folder --output-path /path/to/output --shift-start 5 --shift-value 2 --shift-max 80
```

### 5. 클래스 삭제 사용

클래스 ID 0, 5, 9를 삭제:
```bash
python cli_yolo_label_modifier.py --input-path /path/to/images.txt --input-mode file --output-path /path/to/output --delete-classes "0,5,9"
```

### 6. 특정 클래스만 선택

클래스 ID 1, 3, 5만 포함하는 라벨 생성:
```bash
python cli_yolo_label_modifier.py --input-path /path/to/images --input-mode folder --output-path /path/to/output --select-classes "1,3,5"
```

### 7. 여러 기능 조합

클래스 매핑과 삭제 기능 동시 사용 (원본 파일 수정 + 백업):
```bash
python cli_yolo_label_modifier.py --input-path /path/to/images.txt --input-mode file --in-place --backup --class-mapping "0:1,2:3" --delete-classes "4,5"
```

### 8. 상세 로그 출력

처리 과정에서 상세 정보를 확인하려면 `--verbose` 옵션 사용:
```bash
python cli_yolo_label_modifier.py --input-path /path/to/images --input-mode folder --output-path /path/to/output --verbose
```

## 결과물

프로그램은 다음과 같은 결과물을 생성합니다:

1. 수정된 라벨 파일 (출력 디렉토리에 저장)
2. 결과 요약 파일 (`result_summary.txt`)

결과 요약 파일에는 다음 정보가 포함됩니다:
- 처리된 파일 수 통계
- 어노테이션 및 클래스 변경 요약
- 클래스 변경 통계
- 클래스별 어노테이션 개수

## 주의사항

1. 라벨 파일은 기존 이미지 경로에서 'JPEGImages'를 'labels'로 변경하고, 확장자를 '.txt'로 변경하여 찾습니다.
2. 라벨 파일이 없는 이미지는 처리되지 않고 건너뜁니다.
3. 출력 디렉토리가 존재하지 않으면 자동으로 생성됩니다.
4. 기존 라벨 파일과 이름이 같은 파일이 출력 디렉토리에 있으면 덮어쓰게 됩니다.
5. `--in-place` 옵션을 사용하면 원본 라벨 파일이 직접 수정됩니다. 이 작업은 되돌릴 수 없으므로 주의하세요.
6. 안전을 위해 `--in-place` 옵션 사용 시 `--backup` 옵션을 함께 사용하여 원본 파일을 백업하는 것을 권장합니다.

args)
modifier.run()
```