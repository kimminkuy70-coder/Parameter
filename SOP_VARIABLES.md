# SOP 변수 정리 (Nordson XM8000) — 화면별 + 역할별 분류

SOP PPTX의 각 레시피 화면 캡처에서 추출. 글로 안 적힌 UI 변수 포함.
역할: **[시간]**=검사시간 지배 / **[품질]**=합불·검출 / **[형상]**=자재 고정값 / **[정렬]**=좌표.

## 1. WS Recipe (초기 Wafer Scan) — 슬라이드 4
| 변수 | 예시값 | 역할 |
|------|--------|------|
| WaferId / Description | Bump_BaseTest1 | ID |
| Die Size Width / Height (mm) | 20.0 / 20.0 | [형상] (입력 nominal) |
| **Bump Diameter (µm)** | **26.0** | [형상] 도면과 일치 |
| Bump Pitch (µm) | 100.0 | [형상] *(도면 실제 46.7 — WS는 nominal/예시값일 수 있음)* |
| **X-ray source voltage (kV)** | **60** | [품질] |
| X-ray source power (W) | 3.9 | [품질/시간] |
| **Number of frames to average** | **64** | ★[시간] 1순위 |
| **Resolution (µm/pixel)** | **0.80** | ★[시간]+[품질] |
| Location 1/2/3 X/Y offset (mm) | ±80 | [정렬] |
| Align Timeout (sec) / Substrate Id Angle | 120 / – | [정렬] |

## 2. Wafer CAD — Set Initial Die / Create Grid — 슬라이드 9·10
| 변수 | 예시값 | 역할 |
|------|--------|------|
| Bump Size (µm) | (입력) | [품질] 검출 기준 |
| Die Width / Height (mm) | 12.670 / 15.634 (측정) | [형상] |
| **Pitch X (mm)** | **12.877** | [정렬] die 그리드 |
| **Pitch Y (mm)** | **16.057** | [정렬] |
| Rotation degree | 0.000 | [정렬] |
| 3점 정렬 | TopRight / BottomLeft / BottomRight | [정렬] |
| **검사 Die 선택 (Wafer Map)** | 5~6개 | ★[시간] 샘플링 |

## 3. Die CAD — BumpGroupAnalysis / Set Area of Interest — 슬라이드 12·13
| 변수 | 예시값 | 역할 |
|------|--------|------|
| **Selected bumps** | **455** | ★[시간] 분석 범프 수 |
| Bump size µm | 27 | [품질] |
| **Area of Interest 그룹 수** | 2 | ★[시간] |

## 4. Die CAD — Analysis Settings 탭 — 슬라이드 12
| 변수 | 예시값 | 역할 |
|------|--------|------|
| **Resolution (µm/px)** | **0.50** | ★[시간]+[품질] |
| X-ray voltage (kV) | 60.0 | [품질] |
| X-ray power (W) | 3.00 | [품질/시간] |
| **Number of frames to average** | **64** | ★[시간] 1순위 |

## 5. Die CAD — Void Percent Thresholds 탭 — 슬라이드 13
| 변수 | 값 | 역할 |
|------|----|------|
| Export Void Type | VOID_AREA (또는 VOID_DIAMETER) | [품질] 판정기준 |
| Threshold 1~4 | 2.0 / 5.5 / 8.5 / 10.5 % | [품질] 합/불 등급 |

## 6. 미확인 탭 (SOP에 화면 없음)
- **Bump Parameters** 탭 — 존재하나 SOP에 캡처 없음. ⚠️ bump 관련 추가 변수가 여기 있을 가능성.
- X-Ray Dosage, Ocr Settings 탭 — 화면 없음.

---

## ★ 핵심: 검사시간은 두 단계 모두에서 결정됨
취득이 **2단계**(WS 초기스캔 + Analysis 본촬영)이고, **각 단계마다 Frame Average·Resolution·kV·W가 따로** 있습니다.
- WS 스캔: frames **64**, resolution **0.80** µm/px
- Analysis: frames **64**, resolution **0.50** µm/px

### 시간 지배 변수 (줄여야 할 대상, 우선순위)
1. **Number of frames to average** (두 단계 각 64) — 노출시간 직접 비례, **1순위**
2. **Resolution** (0.80 / 0.50 µm/px) — 작을수록 타일·픽셀↑ → 시간↑
3. **샘플링**: 검사 Die 수 × Selected bumps(455) × AOI 그룹 수
4. **Power** — 밝기↑ 시 frame average를 줄일 여지

### 고정/제약
- **kV = 60 고정** (품질이 강제, 실험으로 확인됨 — 시간 변수 아님)
- Bump Diameter 26µm / Pitch = 자재 형상값 (변경 대상 아님, 식의 입력)
- Void Threshold = 합/불 기준 (품질 정의)
