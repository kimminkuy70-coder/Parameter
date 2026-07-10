# 공정 모델링 (하이브리드: Python 엔진 + Excel 계산기)

DOE 38런(`../실험데이터/`) 실측을 회귀해 **PD 직경 → 추천 kV/R/F/W** 모델을 만듭니다.

## 구조
```
공정모델링/
├── pipeline.py            ← 엔진(Python): CSV 취합 → 회귀 → 계수·뷰·계산기 생성
├── 레시피_계산기.xlsx      ← 산출물(Excel): 오퍼레이터 front-end (PD 입력→추천)
├── outputs/
│   ├── run_level_summary.csv    런별 요약(Q_dia·N8·게이트·tact·bump수)
│   ├── bump_level_merged.csv    bump별 결과 + DOE 조건(회귀/분석 원천)
│   ├── model_coefficients.json  직경(kV²)·kV*(D)·tact 계수
│   └── views/                   직경Gate·N8·tact·DOE주효과 그림(PNG)
└── README.md
```

## 실행
```bash
cd 공정모델링 && python3 pipeline.py
```
`../실험데이터/`의 DOE 엑셀(채워진 측정치)과 XRA_VOID CSV를 읽어 위 산출물을 다시 생성합니다.
새 런이 추가되면(예: 3-anchor 57런) 엑셀만 채우고 **재실행 한 번**이면 계수·계산기가 갱신됩니다.

## 역할 분담 (하이브리드)
- **Python(pipeline.py)** = 엔진: CSV 취합(0 제외 평균)·kV² 회귀·게이트·tact·뷰. 재현 가능.
- **Excel(레시피_계산기.xlsx)** = front-end: Python이 뽑은 계수를 넣어, 장비 PC에서 Python 없이 PD 직경만 입력하면 추천이 나옴.

## 모델 요약 (현재 38런 기준)
| 모델 | 형태 | 결과 |
|------|------|------|
| 직경 | ln_Q = b0 + b_kV·kV + b_kV2·kV² + b_R·R + b_F·F + b_W·W (anchor별) | **kV–직경은 포물선**, kV*≈60(D 거의 무관), R²=0.93(26µm)/0.96(86µm) |
| kV*(D) | 2 anchor 직선 | kV*(D) ≈ 60 (26·86µm 모두 ~60) |
| N8 게이트 | N8 = 측정직경·√0.08 / R ≥ 29 | **26µm 전 조건 미달**(해상도 한계), 86µm은 R≤0.8 통과 |
| Tact | tact = b0 + a·bump + b·bump·(F/64) | R²≈0.33 (예비 — bump·F만으론 부족, 예측변수 보강 필요) |

## 한계·주의 (실측 기반)
- **kV는 정점(≈60)에 고정** — ±2kV에 직경이 ~8%/kV 급변. 직경 Gate(0.97~1.03) 통과는 중심 kV뿐.
- **26µm 8% void 정량 불가** — N8<29(측정가능 R에서). 직경/tact 모델만 유효.
- **void 판정 정확도(False OK/NG) 미검증** — 실측 void≈0%. 8% 근처 void 샘플 확보 후 진행.
- **R/F/W는 직경에 거의 무영향**(kV가 지배) — DOE 주효과 그림 참조.
- Tact 모델은 예비 수준(R²낮음) — 타일수/셋업시간 등 예측변수 보강 시 개선.
