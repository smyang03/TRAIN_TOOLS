"""
analyze_deps.py
C++ Visual Studio 프로젝트 종속성 분석 도구

기능:
  1. ProjectReference 기반 빌드 순서 (위상 정렬 + 순환 참조 감지)
  2. #include 헤더 의존성 (프로젝트 간 외부 참조)
  3. 둘 다
"""

import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict, deque
from pathlib import Path

# ──────────────────────────────────────────────
# 색상 출력
# ──────────────────────────────────────────────
def _c(text, code): return f"\033[{code}m{text}\033[0m"
def red(t):     return _c(t, "91")
def green(t):   return _c(t, "92")
def yellow(t):  return _c(t, "93")
def cyan(t):    return _c(t, "96")
def magenta(t): return _c(t, "95")
def bold(t):    return _c(t, "1")
def dim(t):     return _c(t, "2")

def header(title):
    w = 60
    print()
    print(bold(cyan("─" * w)))
    print(bold(cyan(f"  {title}")))
    print(bold(cyan("─" * w)))

def pause():
    input(dim("\n  [Enter] 계속..."))

# ──────────────────────────────────────────────
# .sln 파싱
# ──────────────────────────────────────────────
def parse_sln(sln_path: Path) -> dict:
    """{ 프로젝트명: vcxproj절대경로 }"""
    projects = {}
    pattern = re.compile(
        r'^Project\("\{[0-9A-Fa-f\-]+\}"\)\s*=\s*"([^"]+)"\s*,\s*"([^"]+\.vcxproj)"',
        re.IGNORECASE,
    )
    sln_dir = sln_path.parent
    with open(sln_path, encoding="utf-8-sig", errors="replace") as f:
        for line in f:
            m = pattern.match(line.strip())
            if m:
                name, rel = m.group(1), m.group(2)
                vcxproj = (sln_dir / rel.replace("\\", "/")).resolve()
                projects[name] = vcxproj
    return projects

# ──────────────────────────────────────────────
# .vcxproj 파싱
# ──────────────────────────────────────────────
def strip_ns(tag):
    return tag.split("}")[-1] if "}" in tag else tag

def parse_vcxproj_refs(vcxproj_path: Path, guid_to_name: dict) -> list:
    """ProjectReference 로 참조하는 프로젝트명 목록 반환"""
    refs = []
    try:
        tree = ET.parse(vcxproj_path)
        root = tree.getroot()
        for elem in root.iter():
            if strip_ns(elem.tag) == "ProjectReference":
                include = elem.get("Include", "")
                ref_path = (vcxproj_path.parent / include.replace("\\", "/")).resolve()
                # GUID로도 매칭, 경로로도 매칭
                ref_name = None
                for child in elem:
                    if strip_ns(child.tag) == "Project":
                        guid = (child.text or "").strip().upper()
                        ref_name = guid_to_name.get(guid)
                        break
                if ref_name is None:
                    # GUID 없으면 경로로 매칭
                    for name, vpath in guid_to_name.items():
                        if isinstance(vpath, Path) and vpath == ref_path:
                            ref_name = name
                            break
                if ref_name is None:
                    ref_name = ref_path.stem
                refs.append(ref_name)
    except Exception:
        pass
    return refs

def parse_vcxproj_sources(vcxproj_path: Path) -> list:
    """ClCompile / ClInclude 등록 소스 파일 절대경로 목록"""
    sources = []
    _ITEM_TAGS = {"ClCompile", "ClInclude", "CudaCompile"}
    try:
        tree = ET.parse(vcxproj_path)
        root = tree.getroot()
        proj_dir = vcxproj_path.parent
        for elem in root.iter():
            if strip_ns(elem.tag) in _ITEM_TAGS:
                inc = elem.get("Include", "")
                if inc:
                    sources.append((proj_dir / inc.replace("\\", "/")).resolve())
    except Exception:
        pass
    return sources

# ──────────────────────────────────────────────
# GUID 맵 구성
# ──────────────────────────────────────────────
def build_guid_map(projects: dict) -> dict:
    """{ '{GUID}': 프로젝트명 }"""
    guid_map = {}
    pattern = re.compile(r'<ProjectGuid>\s*(\{[^}]+\})\s*</ProjectGuid>', re.IGNORECASE)
    for name, vpath in projects.items():
        if not vpath.exists():
            continue
        try:
            content = vpath.read_text(encoding="utf-8-sig", errors="replace")
            m = pattern.search(content)
            if m:
                guid_map[m.group(1).upper()] = name
        except Exception:
            pass
    return guid_map

# ──────────────────────────────────────────────
# 1. ProjectReference 빌드 순서 (위상 정렬)
# ──────────────────────────────────────────────
def analyze_build_order(projects: dict):
    header("ProjectReference 빌드 순서 분석")

    guid_map = build_guid_map(projects)
    # guid_map 에 경로도 추가 (경로 매칭용)
    path_map = {v: k for k, v in projects.items()}
    guid_map_with_path = dict(guid_map)
    for vpath, name in path_map.items():
        guid_map_with_path[vpath] = name

    # 의존 그래프 구성
    graph = {name: [] for name in projects}          # name → [depends_on, ...]
    in_degree = {name: 0 for name in projects}

    for name, vpath in projects.items():
        if not vpath.exists():
            continue
        refs = parse_vcxproj_refs(vpath, guid_map_with_path)
        for ref in refs:
            if ref in graph:
                graph[name].append(ref)   # name 은 ref 에 의존
            else:
                print(yellow(f"  [WARN] '{name}' → '{ref}' 참조 (sln 외부)"))

    # in_degree 계산 (위상 정렬용: ref 가 먼저 빌드되어야 함)
    # name → ref 이므로 ref 의 in_degree 는 영향 없음
    # 빌드 순서: ref 먼저 → name 나중
    rev_graph = defaultdict(list)   # ref → [name, ...]
    for name, deps in graph.items():
        for dep in deps:
            rev_graph[dep].append(name)
            in_degree[name] = in_degree.get(name, 0)  # 이미 있음

    # 실제 in_degree: 내가 의존하는 게 많을수록 나중에 빌드
    real_in_degree = {name: 0 for name in projects}
    for name, deps in graph.items():
        real_in_degree[name] = len(set(deps) & set(projects))

    # Kahn 알고리즘 위상 정렬 (레이어별)
    dep_count = {name: len([d for d in deps if d in projects])
                 for name, deps in graph.items()}
    queue = deque(sorted([n for n, c in dep_count.items() if c == 0]))
    visited = set()
    layers = []

    # 역방향 그래프: dep → [누가 dep에 의존하는지]
    rdep = defaultdict(list)
    for name, deps in graph.items():
        for d in deps:
            if d in projects:
                rdep[d].append(name)

    temp_count = dict(dep_count)
    while queue:
        layer = []
        next_queue = deque()
        for _ in range(len(queue)):
            node = queue.popleft()
            if node in visited:
                continue
            visited.add(node)
            layer.append(node)
        layers.append(layer)
        for node in layer:
            for dependent in rdep[node]:
                temp_count[dependent] -= 1
                if temp_count[dependent] == 0 and dependent not in visited:
                    next_queue.append(dependent)
        queue = deque(sorted(next_queue))

    # 순환 참조 감지
    cycle_nodes = set(projects) - visited
    if cycle_nodes:
        print(red(f"\n  ⚠ 순환 참조 감지: {', '.join(sorted(cycle_nodes))}"))

    # 출력
    has_refs = any(deps for deps in graph.values())
    if not has_refs:
        print(yellow("\n  ProjectReference 가 없습니다. (독립 프로젝트들)"))
        print(f"\n  전체 프로젝트 {len(projects)}개:")
        for name in sorted(projects):
            print(f"    • {name}")
        return

    print(f"\n  총 {len(projects)}개 프로젝트, {len(layers)}개 빌드 레이어\n")
    for i, layer in enumerate(layers, 1):
        label = f"  Layer {i}"
        if i == 1:
            label += "  (의존성 없음 — 가장 먼저 빌드)"
        elif i == len(layers):
            label += "  (최종 빌드)"
        print(bold(label))
        for name in layer:
            deps = graph[name]
            if deps:
                dep_str = dim(f" ← {', '.join(deps)}")
            else:
                dep_str = ""
            print(f"    {'├' if name != layer[-1] else '└'}─ {name}{dep_str}")
        print()

    # 의존 관계 상세
    print(bold("  의존 관계 상세:"))
    any_dep = False
    for name in sorted(projects):
        deps = graph.get(name, [])
        if deps:
            any_dep = True
            print(f"    {cyan(name)}")
            for d in deps:
                print(f"      └─ requires: {d}")
    if not any_dep:
        print(dim("    (없음)"))

# ──────────────────────────────────────────────
# 2. #include 헤더 의존성
# ──────────────────────────────────────────────
_INCLUDE_RE = re.compile(r'^\s*#\s*include\s*["<]([^">]+)[">]', re.MULTILINE)
_SKIP_DIRS  = {"x64", "x86", "Debug", "Release", "ipch", ".vs", "__pycache__"}

def collect_headers(proj_dir: Path) -> dict:
    """{ 헤더파일명(소문자): 절대경로 }"""
    result = {}
    for root, dirs, files in os.walk(proj_dir):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".")]
        for fname in files:
            if Path(fname).suffix.lower() in {".h", ".hpp", ".inl"}:
                result[fname.lower()] = Path(root, fname).resolve()
    return result

def analyze_include_deps(projects: dict):
    header("#include 헤더 의존성 분석")

    # 각 프로젝트별 헤더 파일 맵 구성
    proj_headers: dict[str, dict] = {}
    for name, vpath in projects.items():
        if vpath.exists():
            proj_headers[name] = collect_headers(vpath.parent)

    # 각 프로젝트의 소스에서 include 추출 → 어느 프로젝트 헤더인지 매핑
    # { 프로젝트명: { 참조하는 외부 프로젝트명: [헤더들] } }
    dep_map: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    unresolved_map: dict[str, set] = defaultdict(set)

    print(f"\n  {len(projects)}개 프로젝트 분석 중", end="", flush=True)

    for name, vpath in projects.items():
        if not vpath.exists():
            continue
        sources = parse_vcxproj_sources(vpath)
        includes_seen = set()

        for src in sources:
            if not src.exists():
                continue
            try:
                content = src.read_text(encoding="utf-8-sig", errors="replace")
            except Exception:
                continue
            for m in _INCLUDE_RE.finditer(content):
                inc = m.group(1)
                fname = Path(inc).name.lower()
                if fname in includes_seen:
                    continue
                includes_seen.add(fname)

                # 같은 프로젝트 헤더인지 확인
                own_headers = proj_headers.get(name, {})
                if fname in own_headers:
                    continue  # 자기 프로젝트 내부 참조는 제외

                # 다른 프로젝트 헤더인지 확인
                found = False
                for other_name, other_headers in proj_headers.items():
                    if other_name == name:
                        continue
                    if fname in other_headers:
                        dep_map[name][other_name].append(Path(inc).name)
                        found = True
                        break
                if not found and not inc.startswith(("windows", "std", "cuda")):
                    unresolved_map[name].add(Path(inc).name)

        print(".", end="", flush=True)

    print()

    # 출력
    any_dep = False
    for name in sorted(projects):
        ext_deps = dep_map.get(name, {})
        if not ext_deps:
            continue
        any_dep = True
        total_headers = sum(len(v) for v in ext_deps.values())
        print(f"\n  {bold(cyan(name))}  {dim(f'(외부 참조 {len(ext_deps)}개 프로젝트, 헤더 {total_headers}개)')}")
        for other in sorted(ext_deps):
            headers = sorted(set(ext_deps[other]))
            print(f"    └─ {other}")
            for h in headers[:10]:
                print(f"         {dim(h)}")
            if len(headers) > 10:
                print(f"         {dim(f'... 외 {len(headers)-10}개')}")

    if not any_dep:
        print(yellow("\n  프로젝트 간 헤더 의존성이 감지되지 않았습니다."))
        print(dim("  (소스가 vcxproj 에 등록되어 있지 않거나 상대경로 include 미사용)"))

    # 요약 테이블
    print()
    print(bold("  의존성 요약 (행→열 방향으로 참조):"))
    names = sorted(projects)
    col_w = max(len(n) for n in names) + 2

    # 의존이 있는 프로젝트만 행으로
    dep_names = sorted(dep_map.keys())
    ref_names = sorted({r for deps in dep_map.values() for r in deps})

    if dep_names and ref_names:
        print(f"\n  {'':>{col_w}}", end="")
        for r in ref_names:
            print(f"  {r[:12]:>12}", end="")
        print()
        for d in dep_names:
            print(f"  {d:>{col_w}}", end="")
            for r in ref_names:
                mark = "  ●" if r in dep_map[d] else "   "
                print(f"  {mark:>12}", end="")
            print()

# ──────────────────────────────────────────────
# 입력 헬퍼
# ──────────────────────────────────────────────
def ask(prompt, default=None):
    suffix = f" [{default}]" if default else ""
    try:
        val = input(f"  {prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    return val if val else default

def ask_path(prompt, must_exist, is_dir=False):
    while True:
        raw = ask(prompt)
        if not raw:
            print(red("    입력이 필요합니다."))
            continue
        p = Path(raw.strip('"').strip("'")).resolve()
        if must_exist:
            if is_dir and not p.is_dir():
                print(red(f"    폴더를 찾을 수 없습니다: {p}"))
                continue
            if not is_dir and not p.exists():
                print(red(f"    파일을 찾을 수 없습니다: {p}"))
                continue
        return p

# ──────────────────────────────────────────────
# 메인 루프
# ──────────────────────────────────────────────
def main():
    print(bold(cyan("\n======================================")))
    print(bold(cyan("  C++ 프로젝트 종속성 분석기")))
    print(bold(cyan("======================================")))

    # ── 경로 입력
    print()
    sln_path    = ask_path("sln 파일 경로", must_exist=True,  is_dir=False)
    proj_folder = ask_path("프로젝트 폴더 경로", must_exist=True, is_dir=True)

    # ── sln 파싱
    try:
        all_projects = parse_sln(sln_path)
    except Exception as e:
        print(red(f"  [ERROR] sln 파싱 실패: {e}"))
        pause()
        sys.exit(1)

    # 폴더 하위 vcxproj 와 매칭되는 프로젝트만 필터
    def under(vpath, folder):
        try:
            vpath.relative_to(folder)
            return True
        except ValueError:
            return False

    projects = {k: v for k, v in all_projects.items() if under(v, proj_folder)}

    if not projects:
        print(yellow(f"\n  '{proj_folder}' 하위에 등록된 프로젝트가 없습니다."))
        print(cyan("  sln 전체 프로젝트로 대신 분석합니다."))
        projects = all_projects

    print(green(f"\n  ✔ {len(projects)}개 프로젝트 로드 완료"))

    # ── 메인 메뉴 루프
    while True:
        print()
        print(bold("  ┌─────────────────────────────────┐"))
        print(bold("  │  분석 메뉴                      │"))
        print(bold("  ├─────────────────────────────────┤"))
        print(bold("  │  1. ProjectReference 빌드 순서  │"))
        print(bold("  │  2. #include 헤더 의존성        │"))
        print(bold("  │  3. 둘 다                       │"))
        print(bold("  │  4. 경로 재입력                 │"))
        print(bold("  │  0. 종료                        │"))
        print(bold("  └─────────────────────────────────┘"))

        choice = ask("선택")

        if choice == "1":
            analyze_build_order(projects)
            pause()
        elif choice == "2":
            analyze_include_deps(projects)
            pause()
        elif choice == "3":
            analyze_build_order(projects)
            analyze_include_deps(projects)
            pause()
        elif choice == "4":
            # 재입력
            print()
            sln_path    = ask_path("sln 파일 경로", must_exist=True,  is_dir=False)
            proj_folder = ask_path("프로젝트 폴더 경로", must_exist=True, is_dir=True)
            try:
                all_projects = parse_sln(sln_path)
            except Exception as e:
                print(red(f"  [ERROR] sln 파싱 실패: {e}"))
                continue
            projects = {k: v for k, v in all_projects.items() if under(v, proj_folder)}
            if not projects:
                projects = all_projects
            print(green(f"\n  ✔ {len(projects)}개 프로젝트 로드 완료"))
        elif choice == "0":
            print(cyan("\n  종료합니다."))
            break
        else:
            print(yellow("  1~4 또는 0을 입력하세요."))

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(cyan("\n\n  종료합니다."))