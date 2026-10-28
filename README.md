# TRAIN_TOOLS

학습 DB 작업용 도구 모음. 번호는 배포 폴더(`F:\goptool`)의 exe 번호와 같다.

## 구성

| 번호 | 도구 | Windows (GUI) | Linux (CLI) |
|---|---|---|---|
| 01 | 학습 리스트 생성 / train·valid 분할 | `linux/01.make_label_list.py` (spec: `01.make_label_list.spec`) | `linux/01.make_label_list.py` |
| 02 | 리스트 분할 / 작업자 분배 | `02.data_slice.py` | `linux/02.list_slice.py` |
| 04 | 라벨링 툴 (GTGEN) | `04.GTGEN_Tool_svms_v2.py` | - |
| 05 | 라벨 클래스 변경 / 삭제 / 복제 | `05.label_change.py` | `linux/05.label_change.py` |
| 06 | 라벨 검수 | `label_check/main.py` (spec: `06.label_check.spec`) | - |
| 08 | 리스트 병합 / 경로 단어 교체 | `08.list_merge.py` | `linux/08.list_merge.py` |
| 10 | 이미지 육안 검수 / 분류 | `10.ImageCheck.py` | `linux/10.image_check.py` (썸네일 시트 + 번호로 분류) |

```
.
├─ 0X.*.py / 0X.*.spec   Windows 도구와 빌드 spec
├─ label_check/          06 라벨 검수 (main.py + 모듈, 예전 labelscheck 저장소에서 이전)
├─ config.ini, help.txt, RemoveDefaultdll.exe, *.json   GTGEN 실행 시 함께 있어야 하는 파일
├─ linux/                서버용 CLI 도구
├─ etc/                  위 목록 외 도구 (영상 추출/병합/크롭, 마스킹, RTSP 스캔 등)
│   └─ linux/            기타 서버 스크립트 (file_find, file_move, json2yolo 등)
└─ docs/                 사용 가이드
```

## Linux 도구 사용 예

```bash
# 02 리스트 분할: 3개로 균등 분할 / 작업자 3명에게 분배
python3 linux/02.list_slice.py split list.txt --parts 3
python3 linux/02.list_slice.py distribute list.txt --workers 3 --strategy auto

# 05 라벨 변경: 1->2 매핑, 0번 라벨을 5번으로 복제
python3 linux/05.label_change.py --input-path list.txt --input-mode file --in-place --backup \
    --class-mapping 1:2 --duplicate 0:5

# 08 리스트 병합 + Windows 경로를 Linux 경로로 교체
python3 linux/08.list_merge.py a.txt b.txt -o merged.txt --replace 'V:\=/mnt/v/' --replace '\=/'

# 10 이미지 검수: 번호 붙은 썸네일 시트 생성 -> 시트 보고 번호로 분류 -> 진행 현황
python3 linux/10.image_check.py sheet list.txt --boxes
python3 linux/10.image_check.py apply list.txt_imagecheck --category 주간 --ids 1-40,45
python3 linux/10.image_check.py stats list.txt_imagecheck --unprocessed
```

각 도구의 전체 옵션은 `-h`로 확인한다.

## 빌드 (Windows)

```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pyinstaller --noconfirm 04.GTGEN_Tool_svms_v2.spec
```

conda Python으로 venv를 만들었다면 빌드 전에 `<conda env>\Library\bin`을 PATH 앞에 넣어야 libssl/libcrypto DLL이 exe에 포함된다.

결과는 `dist/`에 생긴다. 자세한 내용은 `docs/BUILD_GUIDE.md`.
