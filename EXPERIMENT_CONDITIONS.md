# X-ray Void Inspection — Experiment Conditions

장비: **Nordson XM8000** / Wafer LotID: **126173086**, Slot **17**, Bump Size **26µm**
Void 판정 임계값: **8.0 ~ 100.0%** / 검사 Die 5개 (십자형: 59, 218, 242, 253, 445)

| 실험 | 전압 (kV) | 파워 (W) | RunID | 조건 출처 | 폴더명 |
|------|-----------|----------|-------|-----------|--------|
| TEST1 | 60 | 4.0 | 3567 | 폴더명 + CSV | TEST_60_4 |
| TEST2 | — | — | (예정) | 미업로드 | — |
| TEST3 | 60 | 4.5 | 3569 | 폴더명 | TEST_60_4.5 |
| TEST4 | 60 | 5.5 | 3570 | 사용자 확인 | TEST4 |
| TEST5 | 58 | 5.0 | 3571 | 사용자 확인 (폴더명과 불일치) | TEST_60_5.5 |
| TEST6 | 59 | 5.0 | 3572 | 사용자 확인 | TEST_59_5 |

> ⚠️ **폴더명은 신뢰할 수 없음.** TEST5 폴더명은 `TEST_60_5.5`이지만 실제 조건은 **58kV / 5.0W**이고,
> TEST4는 폴더명·CSV에 조건이 없음(`TEST4`). 위 표의 전압/파워 값이 사용자 확인 기준 정답.

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
| TEST3 | 60kV / 4.5W | 0 | 0.00% | 4/5 |
| TEST4 | 60kV / 5.5W | 0 | 0.00% | 2/5 |
| TEST5 | **58kV / 5.0W** | **10** | **5.97%** | 3/5 |
| TEST6 | 59kV / 5.0W | 0 | 0.00% | 2/5 |

- Void는 **TEST5(58kV / 5.0W)에서만** 검출됨. 동일 5W인 TEST6(59kV)는 0개 →
  같은 파워에서도 전압(58 vs 59kV)·정렬 상태에 따라 검출 결과가 갈림.
- 측정 범프 직경: TEST1(60/4.0) ~9.4µm < TEST5(58/5.0) ~12.6µm
- CAD 매칭 성공률: TEST3(60/4.5)가 4/5로 최고
- ⚠️ TEST4(60/5.5)와 TEST5(58/5.0)는 더 이상 동일 조건 아님 (조건 수정으로 변경됨)
