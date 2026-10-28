# PyInstaller 빌드 가이드

## 문제: RecursionError 발생 시

PyInstaller로 빌드할 때 다음과 같은 에러가 발생할 수 있습니다:
```
RecursionError: maximum recursion depth exceeded
```

## 해결 방법

### 1. .spec 파일 사용 (권장)

이미 최적화된 .spec 파일이 포함되어 있습니다:

```cmd
# 라벨 체크 툴 빌드
pyinstaller 06.label_check.spec

# 라벨 툴 빌드
pyinstaller 04.GTGEN_Tool_svms_v2.spec
```

### 2. 직접 명령어로 빌드

```cmd
# 라벨 체크 툴
pyinstaller --onefile ^
    --exclude-module tensorflow ^
    --exclude-module torch ^
    --exclude-module scipy ^
    --exclude-module matplotlib ^
    --exclude-module pandas ^
    --recursion-limit 5000 ^
    06.label_check.py

# 라벨 툴
pyinstaller --onefile ^
    --exclude-module tensorflow ^
    --exclude-module torch ^
    --exclude-module scipy ^
    --exclude-module matplotlib ^
    --exclude-module pandas ^
    --recursion-limit 5000 ^
    04.GTGEN_Tool_svms_v2.py
```

## .spec 파일의 주요 기능

1. **재귀 깊이 제한 증가**: `sys.setrecursionlimit(5000)`
2. **불필요한 패키지 제외**: tensorflow, torch, scipy 등 대용량 라이브러리 제외
3. **빌드 속도 향상**: 필요한 패키지만 포함

## 필요한 패키지만 포함

실제 사용하는 패키지:
- tkinter (GUI)
- PIL/Pillow (이미지 처리)
- numpy (수치 계산)
- tqdm (진행률 표시)

제외되는 패키지 (불필요):
- tensorflow, torch (딥러닝 - 미사용)
- scipy, pandas (과학 계산 - 미사용)
- matplotlib (시각화 - 미사용)
- jupyter, notebook (개발 도구 - 미사용)

## 빌드 결과

```
dist/
├── 06.label_check.exe      # 라벨 체크 툴
└── 04.GTGEN_Tool_svms_v2.exe  # 라벨 툴
```

## 클린 빌드

이전 빌드 결과를 제거하고 새로 빌드:

```cmd
pyinstaller --clean 06.label_check.spec
pyinstaller --clean 04.GTGEN_Tool_svms_v2.spec
```

## 문제 해결

### Q: "ModuleNotFoundError: No module named 'XXX'" 발생
A: hiddenimports에 모듈 추가:
```python
hiddenimports=['XXX'],
```

### Q: 실행 파일이 너무 큼
A: UPX 압축 활성화 (이미 활성화됨):
```python
upx=True,
```

### Q: 콘솔 창을 숨기고 싶음
A: console 옵션 변경:
```python
console=False,
```
