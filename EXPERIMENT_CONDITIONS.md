# X-ray Void Inspection — Experiment Conditions

장비: **Nordson XM8000** / Wafer LotID: **126173086**, Slot **17**, Bump Size **26µm**
Void 판정 임계값: **8.0 ~ 100.0%** / 검사 Die 5개 (십자형: 59, 218, 242, 253, 445)

| 실험 | 전압 (kV) | 파워 (W) | RunID | 폴더명 (조건과 일치하도록 수정됨) |
|------|-----------|----------|-------|-----------------------------------|
| TEST1 | 60 | 4.0 | 3567 | TEST_60_4 |
| TEST2 | 63.5 | 4.0 | 3568 | TEST_63.5_4 |
| TEST3 | 60 | 4.5 | 3569 | TEST_60_4.5 |
| TEST4 | 60 | 5.5 | 3570 | TEST_60_5.5 *(원래 `TEST4`)* |
| TEST5 | 58 | 5.0 | 3571 | TEST_58_5 *(원래 `TEST_60_5.5`)* |
| TEST6 | 59 | 5.0 | 3572 | TEST_59_5 |

> 파라미터 폴더명을 `TEST_(전압)_(파워)` 형식으로 실제 조건과 일치시킴.
> TEST4(원래 `TEST4`)와 TEST5(원래 `TEST_60_5.5`, 실제 58kV/5W)를 사용자 확인값으로 수정함.

## 폴더 구조 (각 TEST 공통)
```
TEST_(V)_(P)/17/
├─ Images/        Composite(정상) / FailedToMatchCAD(매칭실패) PNG
├─ BumpLevel/     WBA_BumpResult_*.csv
├─ DieLevel/      WBA_DieResult_*.csv
├─ WaferLevel/    직경 Avg/Max/Min/Stdev, Void%, Roundness 등
├─ WaferMaps/     AR_* (Void/매칭 맵)
├─ Dose/          SubstrateDoseMap (방사선량)
├─ XRA_VOID_*.csv 범프별 상세 결과
└─ VoidReport1/2, *_DIEMap, *.jpg
```

## 주요 결과 요약 (조건 수정 반영)
| 실험 | 조건 | Void 검출 범프 | 최대 Void% | CAD 매칭(5 Die 중) |
|------|------|----------------|-----------|--------------------|
| TEST1 | 60kV / 4.0W | 0 | 0.00% | 2/5 |
| TEST2 | 63.5kV / 4.0W | 0 (분석불가) | — | **0/5 (전부 실패)** |
| TEST3 | 60kV / 4.5W | 0 | 0.00% | 4/5 |
| TEST4 | 60kV / 5.5W | 0 | 0.00% | 2/5 |
| TEST5 | **58kV / 5.0W** | **10** | **5.97%** | 3/5 |
| TEST6 | 59kV / 5.0W | 0 | 0.00% | 2/5 |

- Void는 **TEST5(58kV / 5.0W)에서만** 검출됨. 동일 5W인 TEST6(59kV)는 0개 →
  같은 파워에서도 전압(58 vs 59kV)·정렬 상태에 따라 검출 결과가 갈림.
- 측정 범프 직경: TEST1(60/4.0) ~9.4µm < TEST5(58/5.0) ~12.6µm
- CAD 매칭 성공률: TEST3(60/4.5)가 4/5로 최고
- ⚠️ TEST4(60/5.5)와 TEST5(58/5.0)는 더 이상 동일 조건 아님 (조건 수정으로 변경됨)
- ⚠️ **TEST2(63.5kV / 4.0W)**: 5개 Die 전부 CAD 매칭 실패 → 범프 분석 결과 없음(XRA_VOID 0행),
  WaferLevel·WaferMaps 폴더 미생성. 최고 전압·저파워(63.5kV/4W) 조합에서 매칭이 완전히 실패함.
