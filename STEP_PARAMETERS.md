# SOP 재독해 — 2-Step 구조와 Step별 파라미터 정리

SOP 원문을 재독해한 결과. 검사는 크게 **① Image Acquisition**과 **② Inspection** 두 step이며,
**각 step이 별도의 촬영 파라미터 세트를 갖는다.** 그 사이의 CAD 작업은 촬영이 아니라
"무엇을 어떻게 판정할지"를 정의하는 셋업 단계다.

## 0. 전체 흐름 (SOP 슬라이드 순서 그대로)

```
[Initialization]  장비 상태 확인 (GEM, INS/WFC/FI/IO/WH Running)          — 슬라이드 2~3
      ↓
[STEP ① Image Acquisition]  ※ 레시피 셋업 시 실행
  1. WS Recipe 작성 (파라미터 입력)                                        — 슬라이드 4~5
  2. Jobs > Manual Process > Image Acquisition 실행                        — 슬라이드 6
  3. 웨이퍼 전체 스캔 (~30분), 완료 시 "Recipe명_Base" 이미지 생성          — 슬라이드 7
      ↓
[레시피 구축 (촬영 아님 — Acquisition 이미지 위에서 오프라인 작업)]
  4. Load: Recipe명_Base 불러오기                                          — 슬라이드 8
  5. Wafer CAD: 3개 Step(정렬 위치) 이미지 로드                            — 슬라이드 9
  6. Wafer CAD: Set Initial Die → Pitch X/Y·Rotation → Create Grid        — 슬라이드 10
  7. Wafer CAD: 검사 Die 선택 (십자 5개)                                   — 슬라이드 11
  8. Die CAD: Analysis Settings (② Inspection의 촬영 파라미터 입력)         — 슬라이드 12
  9. Die CAD: Set Area of Interest + Void Threshold 설정                   — 슬라이드 13
 10. Recipe Save                                                           — 슬라이드 14
      ↓
[STEP ② Inspection]  ※ 양산에서 반복 실행되는 것은 이것뿐
 11. Jobs > Inspection > 저장한 Recipe 선택 > Start                        — 슬라이드 15
     → 선택된 die의 AOI만 Analysis Settings 조건으로 재촬영 + void 정량
      ↓
[Results]  결과 확인                                                       — 슬라이드 16
```

---

## 1. STEP ① Image Acquisition 파라미터 (WS Recipe 화면, 슬라이드 4)

목적: **웨이퍼 전체를 스캔해 CAD 구축용 기준 이미지(Recipe_Base)를 만든다.**
소요: **~30분/웨이퍼** (슬라이드 7). 셋업 시 실행.

| 파라미터 | SOP 예시값 | 역할 |
|----------|-----------|------|
| WaferId / Description | Bump_BaseTest1 | 레시피 이름 (WaferId+"_WS"로 생성됨) |
| Die Size Width / Height (mm) | 20.0 / 20.0 | die 검출 기대값 (형상 입력) |
| Bump Diameter (µm) | 26.0 | 범프 검출 기대값 (도면값 입력) |
| Bump Pitch (µm) | 100.0 | 범프 배열 기대값 |
| **X-ray source voltage (kV)** | **60** | 촬영 투과력 |
| **X-ray source power (W)** | **3.9** | 촬영 선속 ※슬라이드5에 4W vs 5W 검출력 차이 예시 있음 |
| **Number of frames to average** | **64** | 촬영 노이즈 평균 (시간 정비례) |
| **Resolution (µm/pixel)** | **0.80** | 스캔 해상도 (시간 ∝ 1/R²) |
| Location 1/2/3 X/Y offset (mm) | ±80 | **정렬용 3점 촬영 위치** → Wafer CAD의 "3개 Step"이 이것 |
| Align Timeout (sec) | 120 | 정렬 제한시간 |
| Substrate Id Angle (deg) | – | 기판 ID 각도 |

## 2. 레시피 구축 단계 (촬영 파라미터 아님 — 정의 작업)

| 화면 | 설정 항목 | 의미 |
|------|-----------|------|
| Wafer CAD – Set Initial Die | Pitch X/Y (mm), Rotation, Bump Size | Acquisition 이미지 위에 die 격자 정의 |
| Wafer CAD – Select Die | 검사 die 선택 (십자 5개) | **② Inspection이 촬영할 die 결정 (검사량)** |
| Die CAD – BumpGroupAnalysis | Selected bumps, Bump size µm, **촬영영역(빨간 박스)** | **② Inspection이 촬영할 AOI 결정 (검사량)** |
| Die CAD – Void Thresholds | VOID_AREA/DIAMETER, Threshold 1~4 | 합불 판정 기준 |

## 3. STEP ② Inspection 파라미터 (Die CAD > Analysis Settings, 슬라이드 12)

목적: **선택된 die의 AOI만 재촬영하여 void 정량.** 양산에서 반복 실행되는 유일한 촬영.
소요: 실측 die당 ~90~100초 (RUN 세트 타임스탬프).

| 파라미터 | SOP 예시값 | 역할 |
|----------|-----------|------|
| **Resolution (µm/px)** | 0.50 | **촬영구역(빨간 박스) 크기를 결정** — SOP 원문: "Resolution ∝ 촬영 영역 사이즈" |
| **X-ray source voltage (kV)** | 60.0 | 검사 촬영 투과력 |
| **X-ray source power (W)** | 3.00~3.9 | 검사 촬영 선속 |
| **Number of frames to average** | 64 | 검사 촬영 노이즈 평균 |
| + 검사량 (§2에서 정의됨) | die 5~6개 × AOI × Selected bumps | Inspection 시간 = 검사량 × 조건 |

---

## 4. 재독해에서 확인된 핵심 사실 (이전 문서 정정 포함)

**(1) 두 step 모두 "촬영"이며, 각자 독립된 kV/W/Frame/R을 가진다.**
- Acquisition = 웨이퍼 전체를 거칠게 (R 0.8), Inspection = 선택 AOI만 정밀하게 (R 0.5~1.0).

**(2) SOP 관행: Inspection의 kV/W/Frame은 "4page(WS Recipe)에서 설정된 값" 그대로 복사.**
- 슬라이드 12 원문에 명시. 즉 **두 step 파라미터는 원래 독립인데 SOP는 같은 값을 쓰는 관행**.
- → 실험에서 두 step 값을 따로 최적화할 수 있는 여지가 있다는 뜻 (예: Acquisition만 Frame 32).

**(3) Resolution(Analysis)의 1차 의미는 "촬영구역 크기"다.**
- SOP 원문: "빨간 박스=촬영 영역", "Resolution ∝ 촬영 영역 사이즈".
- 픽셀 정밀도는 그 결과로 따라오는 것. (기존 문서는 픽셀 관점만 강조 — 보완)

**(4) ★ Image Acquisition은 레시피 셋업 때 실행하는 단계다. 양산 반복분은 Inspection뿐.**
- SOP 흐름상 Acquisition(슬라이드 6~7) → CAD 구축 → Save → Inspection(슬라이드 15).
- 운영 실태와 일치: 제조 현장은 Acquisition 없이 기존 레시피 3종을 재사용 중.
- **[정정]** 기존 OPTIMIZATION_PLAN의 "전체 tact 40분 → 17분" 프레임은 부정확:
  - **양산 tact = Inspection(~10분)만.** Acquisition 30분은 **레시피 개발 리드타임** 비용.
  - 따라서 시간 전략도 둘로 나뉜다:
    - **양산 tact 단축** = Inspection 쪽 (검사량: die 수·AOI·Selected bumps / R로 촬영구역·타일 / Frame)
    - **셋업 리드타임 단축** = Acquisition 쪽 (Frame 64→32, R 0.8→1.2 등 — 새 자재 셋업이 잦을수록 중요)
  - 사용자 통찰("Acquisition이 길고 검사는 짧다 → 검사 Frame은 높게 가져가 품질 확보")은
    이 구조에서 정확히 성립: **Inspection Frame은 품질 투자처, Acquisition Frame은 절감처.**

**(5) 슬라이드 5: Power 4W vs 5W "검출력 변화" 예시가 SOP에 존재.**
- SOP 작성 근거로는 power가 검출력에 영향. 단, 통제실험(60kV, 3.5/4.0/4.5W)에서는 무차이.
- 두 결과의 간극(측정 범위·조건 차이)은 확인 필요 항목으로 유지.

## 5. Step별 시간·품질 지렛대 요약

| | STEP ① Acquisition (셋업 1회) | STEP ② Inspection (양산 반복) |
|---|---|---|
| 시간 비용 | ~30분/웨이퍼 (리드타임) | die당 ~1.5분 (tact) |
| 품질 요건 | **검출·정렬만 되면 됨** | **void 정량 정확 (Q_dia≈1)** |
| 시간 지렛대 | Frame 64→32, R 0.8→↑ | 검사량(die·AOI·bumps), R(촬영구역), Frame |
| 품질 지렛대 | kV (검출 성립 한도) | kV(정확도), R(void 픽셀), Frame(재현성) |
| 형상 입력 | Bump Diameter/Pitch, Die Size (도면값) | Bump size, AOI (CAD에서) |
