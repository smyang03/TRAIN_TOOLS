# 라벨링 툴 수정 보고서

## 1. 요약

이번 수정은 `선택한 박스 1개를 지우려 했는데 txt 내부 전체가 같이 지워지는 것처럼 보이는 문제`를 중심으로, 삭제/마스킹/라벨 변경의 공통 selection 상태와 파일 갱신 로직을 함께 정리한 작업입니다.

핵심 원인은 두 가지였습니다.

1. `class/page/filter/mode` 전환 후에도 이전 selection이 내부에 남아 있었습니다.
2. full-image 선택이 edit 대상 box selection으로 확장되고 있었습니다.

이 두 문제 때문에 사용자는 현재 화면에서 박스 하나만 선택했다고 생각해도, 실제 edit 대상은 다른 페이지/다른 화면 상태의 box까지 포함될 수 있었습니다.

## 2. 수정한 내용

### selection / 화면 전환

- `main.py`
  - `selected_full_image_labels`를 추가해 full-image 선택과 box 선택을 분리했습니다.
  - `_save_label_info_for_widget()`에서 full-image 선택 시 더 이상 파일 내부 box 전체를 edit 대상에 넣지 않도록 수정했습니다.
  - `_clear_selection_for_view_change()`를 추가하고 아래 상황에서 selection을 비우도록 변경했습니다.
    - class 변경
    - overlap class 변경
    - overlap filter 변경
    - Box Images 모드 on/off
    - IoU threshold 변경
    - page 이동 / 직접 page 입력 / page size 변경
  - `handle_left_click()`가 label widget 클릭을 잘못 판별하던 조건을 `img_path` 기준에서 `label_path` 기준으로 수정했습니다.
  - `update_selection_info()`에서 selection button 상태를 실제 selection과 동기화하도록 정리했습니다.

### 삭제 / 클래스 변경 / 마스킹

- `label_operations.py`
  - `_mark_modified()`를 추가해 파일 단위와 line 단위 변경 이력을 함께 기록하도록 정리했습니다.
  - `_safe_destroy_window()`를 추가해 modal window의 `grab_release()`와 `destroy()`가 안전하게 수행되도록 정리했습니다.
  - delete / class change / masking 완료 직후에는 progress/dialog window를 먼저 정리한 다음 refresh를 수행하도록 순서를 바꿨습니다.
  - cache refresh 또는 partial refresh가 실패해도 UI가 modal 상태로 남지 않도록 fallback log와 `viewer.refresh_data()` 경로를 추가했습니다.
  - `change_class_labels()`
    - 지원 범위를 넘는 class id를 차단하도록 수정했습니다.
    - 이미 같은 class인 box는 no-op으로 건너뛰도록 수정했습니다.
    - 실제 변경이 없을 때 별도 메시지를 표시하도록 수정했습니다.
  - `convert_label_to_mask()`
    - 선택 line을 먼저 candidate로 모은 뒤, 실제로 유효한 pixel box에 대해서만 라벨 제거가 일어나도록 수정했습니다.
    - grayscale / 2-channel / RGB / RGBA에 맞는 mask fill value를 동적으로 생성하도록 수정했습니다.
    - image와 label을 temp file로 만든 뒤 `_replace_files_with_rollback()`으로 교체하게 바꿨습니다.
    - image 교체 후 label 교체가 실패하면 이전 상태로 rollback 하도록 수정했습니다.
  - `_create_backup()`는 `copy2()`를 사용하도록 변경했습니다.

### backup 경로 충돌

- `utils.py`
  - `make_path()`를 basename만 쓰는 방식에서 drive/하위 디렉터리를 포함한 안전한 상대 경로 방식으로 바꿨습니다.
  - 같은 파일명(`same_name.txt`)이 여러 폴더에 있어도 backup 경로가 충돌하지 않도록 수정했습니다.

### 자동 검증 스크립트

- `tests/run_review_fixes.py`
  - 외부 dependency 없이 실행 가능한 plain assertion 스크립트를 추가했습니다.
  - 다음 항목을 검증합니다.
    - `make_path()` 충돌 방지
    - full-image selection이 box selection으로 확장되지 않는지
    - view mode 변경 시 selection이 비워지는지
    - multi-file rollback helper가 실패 시 원본 상태를 복구하는지

## 3. 추가로 같이 고친 부분

- selection toggle button이 실제 내부 selection 상태와 어긋날 수 있는 문제를 같이 정리했습니다.
- full-image mode에서도 파일 단위 selection과 box edit selection이 섞이지 않도록 분리했습니다.
- modification indicator가 full-image view에서도 파일 단위로 표시될 수 있도록 변경 이력 기록을 보강했습니다.
- 사용자가 보고한 `첫 작업 후 다음 삭제/변경/마스킹에서 응답없음` 증상에 대응해, edit 후속 refresh가 실패해도 dialog/grab이 남아 UI를 막지 않도록 cleanup 순서를 보강했습니다.

## 4. 검증 결과

### 실행한 검증

다음 명령으로 syntax 검증과 핵심 로직 검증을 수행했습니다.

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
& 'C:\Program Files\NVIDIA Corporation\Nsight Compute 2022.4.0\host\target-windows-x64\python\bin\python.exe' -m py_compile main.py ui_manager.py label_operations.py data_manager.py image_processor.py utils.py tests\run_review_fixes.py
```

결과:

- `py_compile` 통과

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
& 'C:\Program Files\NVIDIA Corporation\Nsight Compute 2022.4.0\host\target-windows-x64\python\bin\python.exe' tests\run_review_fixes.py
```

결과:

- `review_fixes: ok`
- 추가 검증 항목:
  - `_safe_destroy_window()`가 `grab_release -> destroy -> parent.update_idletasks` 순서로 동작하는지 stub 기반으로 확인

### 주의

- 이 sandbox Python에는 `numpy`, `PIL`, `tkinter`, `unittest`가 없어 GUI end-to-end 실행은 못 했습니다.
- 대신 syntax 검증과, selection/rollback/backup 경로 로직은 stub 기반 스크립트로 확인했습니다.
- 실제 앱 동작은 사용 중인 Windows Python 환경에서 아래 수동 체크를 한 번 더 권장합니다.

## 5. 권장 수동 확인

1. Box Images 모드에서 박스 1개만 선택 후 삭제:
   - 해당 txt에서 선택한 line만 지워지는지 확인
2. full-image mode에서 이미지 선택 후 Box Images 모드 전환:
   - 이전 selection이 자동으로 비워지는지 확인
3. class 변경:
   - 같은 class로 바꿀 때 no-op 처리되는지 확인
   - 100 이상 class 입력 시 차단되는지 확인
4. masking:
   - JPG, PNG, RGBA PNG, grayscale 이미지 각각에서 동작 확인
   - masking 중 강제 실패 상황에서 image/label 불일치가 남지 않는지 확인
5. backup:
   - 서로 다른 폴더의 동명 파일에 대해 `original_backup` 경로가 분리되는지 확인

## 6. 수정 파일

- `main.py`
- `ui_manager.py`
- `label_operations.py`
- `utils.py`
- `tests/run_review_fixes.py`
