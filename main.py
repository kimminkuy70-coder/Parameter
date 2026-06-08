"""
AOI 장비(AOI-17~25호기) 레시피 파라미터 엑셀 정리 도구
실행: python main.py
"""

import sys
from pathlib import Path
from src.ini_parser import parse_ini_file
from src.excel_handler import ExcelHandler

MACHINE_RANGE = range(17, 26)


def input_path(prompt):
    """경로 입력 (드래그&드롭 시 따옴표 자동 제거)"""
    return input(prompt).strip().strip('"').strip("'")


def main():
    print("=" * 62)
    print("  AOI 장비 레시피 파라미터 엑셀 정리 도구")
    print("  대상: AOI-17호기 ~ AOI-25호기")
    print("=" * 62)

    # ── 1. 엑셀 파일 경로 ──────────────────────────────────────
    excel_path = input_path("\n엑셀 파일 경로: ")
    if not Path(excel_path).exists():
        print(f"\n오류: 파일을 찾을 수 없습니다\n  → {excel_path}")
        sys.exit(1)

    # ── 2. 호기 선택 ───────────────────────────────────────────
    while True:
        try:
            num = int(input("\n호기 번호 (17~25): ").strip())
            if num in MACHINE_RANGE:
                break
            print("  17~25 사이의 숫자를 입력하세요.")
        except ValueError:
            print("  숫자를 입력하세요.")

    print(f"  → AOI-{num}호기 선택")

    # ── 3. INI 파일 경로 입력 ──────────────────────────────────
    print("\nINI 파일 경로를 입력하세요 (빈 줄 입력 시 종료):")
    ini_paths = []
    while True:
        p = input_path("  경로: ")
        if not p:
            if ini_paths:
                break
            print("  INI 파일을 하나 이상 입력하세요.")
            continue
        path = Path(p)
        if not path.exists():
            print(f"  경고: 파일 없음 → {p}")
            continue
        if not path.suffix.lower() == '.ini':
            print(f"  경고: .ini 파일이 아닙니다 → {p}")
        ini_paths.append(path)
        print(f"  추가됨: {path.name}")

    # ── 4. INI 파일 파싱 ───────────────────────────────────────
    print("\n파싱 중...")
    parsed_files = {}
    for path in ini_paths:
        try:
            parsed_files[path.name] = parse_ini_file(path)
            sections = len(parsed_files[path.name]['sections_order'])
            params = sum(len(v) for v in parsed_files[path.name]['data'].values())
            print(f"  {path.name}: 섹션 {sections}개, 파라미터 {params}개")
        except Exception as e:
            print(f"  오류 ({path.name}): {e}")

    if not parsed_files:
        print("\n파싱된 파일이 없습니다.")
        sys.exit(1)

    # ── 5. 변경 사항 비교 ──────────────────────────────────────
    handler = ExcelHandler(excel_path, num)
    changes = handler.preview_changes(parsed_files)

    actionable = [c for c in changes if c['type'] != 'NO_SHEET']
    if not actionable:
        print("\n변경 사항이 없습니다. (이미 최신 상태)")
        sys.exit(0)

    print("\n" + "=" * 62)
    print(f"  변경 사항 미리보기  —  AOI-{num}호기")
    print("=" * 62)
    handler.print_changes(changes)

    # ── 6. 컨펌 ───────────────────────────────────────────────
    answer = input("\n위 변경 사항을 엑셀에 적용하시겠습니까? (y / n): ").strip().lower()
    if answer != 'y':
        print("취소되었습니다.")
        sys.exit(0)

    # ── 7. 적용 및 저장 ────────────────────────────────────────
    out_path = handler.apply_changes(changes)
    print(f"\n완료! 저장 위치:\n  {out_path}")


if __name__ == "__main__":
    main()
