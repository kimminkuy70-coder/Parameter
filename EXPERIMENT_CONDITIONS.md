# X-ray Void Inspection — Experiment Conditions

장비: **Nordson XM8000** / Wafer LotID: **126173086**, Slot **17**, Bump Size **26µm**
Void 판정 임계값: **8.0 ~ 100.0%** / 검사 Die 5개 (십자형: 59, 218, 242, 253, 445)

| 실험 | 전압 (kV) | 파워 (W) | RunID | 조건 출처 |
|------|-----------|----------|-------|-----------|
| TEST1 | 60 | 4.0 | 3567 | 폴더명 + CSV |
| TEST2 | — | — | (예정) | 미업로드 |
| TEST3 | 60 | 4.5 | 3569 | 폴더명 |
| TEST4 | 60 | 5.5 | 3570 | 사용자 확인 (파일에 미기록) |
| TEST5 | 60 | 5.5 | 3571 | 폴더명 |
| TEST6 | 59 | 5.0 | 3572 | 폴더명 |

> TEST4와 TEST5는 동일 조건(60kV / 5.5W) — 반복 측정 비교용.
> TEST4는 폴더명·CSV에 파라미터가 기록되지 않아 사용자 확인으로 보완함.

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

## 주요 결과 요약
- Void 검출: **TEST5(5.5W)에서만** 실제 Void 검출 (10개 범프, 최대 5.97%)
- 측정 범프 직경: 4W ~9.4µm → 5.5W ~12.6µm (파워↑ → 투과↑)
- CAD 매칭 성공(촬영 5 Die 중): TEST3(4.5W) 4/5로 최고
- 5.5W에서 검출력 우수하나 일부 이미지에 세로 줄무늬 아티팩트 관찰됨
