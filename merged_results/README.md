# merged_results — 검사 결과 취합본 (CSV → xlsx)

제품 **NXP-SAF85443B1** 검사 결과. 검사 1건당 결과 CSV들을 이미지 제외하고
하나의 `*_merged_all.xlsx`로 취합한 파일 모음입니다.
(이미지는 제외했지만 `Images` 시트에 파일명이 남아 있어 Composite / Fail / 이미지없음 구분 가능)

## 3개 상위 레시피로 분류 (파일명 접두사 = 레시피명)

| 레시피 폴더 | 검사 건수(xlsx) |
|-------------|-----------------|
| `NXP-SAF85443B1-0R001BK508573860A/` | 135 |
| `QORVOTest/` | 115 |
| `ST-TEST-RECIPE/` | 112 |
| **합계** | **362** |

- 분류 기준: 파일명 `<레시피>__<LotId>__<n>_merged_all.xlsx` 의 첫 `__` 앞부분(= 레시피명).
  각 xlsx 내부 `_VoidReport1` 시트의 Recipe 필드와도 일치함(VoidReport가 있는 건 기준).
- 일부 파일은 VoidReport 없이 Dose/Images 시트만 있음(검사 미완/이미지없음 케이스) — 파일명 기준으로 분류함.

## 각 xlsx 시트 구성 (예)
- `_VoidReport1_*`, `_VoidReport2_*` : Void 판정 요약 (Recipe/Lot/Wafer/Void%)
- `_XRA_VOID_*` : 범프별 상세 (Diameter, Area, % Overall Void 등)
- `BumpLevel_*`, `DieLevel_*` : 범프/다이 레벨 결과
- `Dose_*` : 방사선량 맵
- `Images` : 이미지 파일명 목록(실제 이미지는 제외)
