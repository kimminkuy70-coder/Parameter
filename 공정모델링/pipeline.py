# -*- coding: utf-8 -*-
"""
공정 모델링 파이프라인 (하이브리드 엔진)
==========================================
입력 : ../실험데이터/공정모델링_DOE_2anchor_3anchor_Fmin32_측정직경모델/
        - 채워진 DOE 엑셀 (조건 + 측정직경 + Tact)
        - 각 런의 XRA_VOID_*.csv (bump 단위 원본)
출력 : 공정모델링/outputs/
        - run_level_summary.csv   런별 요약(Q_dia·N8·게이트·tact)
        - bump_level_merged.csv   bump별 결과 + DOE 조건
        - model_coefficients.json 직경(kV²)·kV*(D)·N8·tact 계수
        - views/*.png             직경Gate·N8·tact·DOE effect
        - ../레시피_계산기.xlsx   계수 반영 오퍼레이터 front-end

실행 : python3 pipeline.py   (repo 루트 또는 이 폴더에서)
"""
import os, csv, glob, re, json, math
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DOE_DIR = os.path.join(HERE, "..", "실험데이터",
                       "공정모델링_DOE_2anchor_3anchor_Fmin32_측정직경모델")
XLSX = os.path.join(DOE_DIR, "공정모델링_DOE_2anchor_3anchor_Fmin32_측정직경모델.xlsx")
OUT = os.path.join(HERE, "outputs")
VIEWS = os.path.join(OUT, "views")
os.makedirs(VIEWS, exist_ok=True)
SQRT_P = math.sqrt(0.08)   # 8% void 등가직경 계수
# 허용 총오차(정확도 목표) ε. 게이지 R&R 규칙: 오차 ≤ 공차의 10%=우수, 10~30%=허용.
# 자재 무관 통일값으로 20%(허용 등급) 채택 → 26·10µm도 구조적으로 달성 가능.
EPS = 0.20
# 픽셀화·노이즈를 균등 분할(RSS)하면 픽셀화 몫 ≤ ε/√2 → N8 = 2√2/ε
N8_MIN = round(2 * math.sqrt(2) / EPS)   # ε=20% → 14 (ε=10%였다면 29)

# ---------------------------------------------------------------- 1. 데이터 로드
def load_runs():
    """채워진 DOE 엑셀에서 런별 조건+측정치 로드, Q·N8 계산, bump수 추가."""
    import openpyxl
    wb = openpyxl.load_workbook(XLSX)
    ws = wb["DOE_2Anchor_Now_38런"]
    hdr = {ws.cell(1, c).value: c for c in range(1, ws.max_column + 1)}
    def col(name, r): return ws.cell(r, hdr[name]).value
    runs = []
    for r in range(2, ws.max_row + 1):
        md = col("Measured_Diameter_um", r)
        if md in (None, ""):
            continue
        pd = float(col("PD_Diameter_um", r)); R = float(col("R_um_per_px", r))
        rec = dict(
            gid=col("Global_Run_ID", r), anchor=col("Anchor_ID", r),
            pd=pd, kv=float(col("kV", r)), R=R, F=float(col("F", r)),
            W=float(col("W", r)), md=float(md),
            tact=float(col("Tact_sec", r)) if col("Tact_sec", r) not in (None, "") else None,
            runid=str(col("RunID", r)), gold=col("Gold_Flag_YN", r),
            lv=float(col("Measured_LargestVoid_pct", r) or 0),
        )
        rec["q"] = rec["md"] / rec["pd"]
        rec["lnq"] = math.log(rec["q"])
        rec["n8"] = rec["md"] * SQRT_P / R
        rec["bumps"] = count_bumps(rec["runid"])
        rec["diam_gate"] = 0.97 <= rec["q"] <= 1.03
        rec["n8_gate"] = rec["n8"] >= N8_MIN
        runs.append(rec)
    return runs

def count_bumps(runid_field):
    """RunID(다중이면 첫 값)의 XRA_VOID bump 행수."""
    rid = runid_field.split("/")[0]
    fs = glob.glob(os.path.join(DOE_DIR, "**", f"XRA_VOID_{rid}.csv"), recursive=True)
    if not fs:
        return 0
    with open(fs[0]) as f:
        return sum(1 for _ in f) - 1

# ---------------------------------------------------------------- 2. 요약/병합 CSV
def write_run_summary(runs):
    cols = ["gid", "runid", "anchor", "pd", "kv", "R", "F", "W", "md", "q", "lnq",
            "n8", "tact", "bumps", "lv", "gold", "diam_gate", "n8_gate"]
    with open(os.path.join(OUT, "run_level_summary.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(cols)
        for r in runs:
            w.writerow([round(r[c], 4) if isinstance(r[c], float) else r[c] for c in cols])

def write_bump_merged(runs):
    cond = {r["runid"].split("/")[0]: r for r in runs}
    out = os.path.join(OUT, "bump_level_merged.csv")
    with open(out, "w", newline="") as fo:
        w = csv.writer(fo)
        w.writerow(["RunID", "Global_Run_ID", "PD", "kV", "R", "F", "W",
                    "DieID", "BumpID", "Diameter_um", "LargestVoid_pct", "Result"])
        for xf in sorted(glob.glob(os.path.join(DOE_DIR, "**", "XRA_VOID_*.csv"), recursive=True)):
            rid = re.search(r"_(\d+)\.csv", xf).group(1)
            c = cond.get(rid)
            if not c:
                continue
            with open(xf) as fi:
                for row in csv.DictReader(fi):
                    w.writerow([rid, c["gid"], c["pd"], c["kv"], c["R"], c["F"], c["W"],
                                row["DieID"], row["ID"], row["Diameter (um)"],
                                row["% Largest Void"], row["Result"]])

# ---------------------------------------------------------------- 3. 직경 모델 (kV²)
def fit_diameter(runs):
    """anchor별 ln_Q ~ 1 + kV + kV² + R + F + W 회귀 → 계수·kV*(정점)·R²."""
    res = {}
    for anchor in sorted(set(r["anchor"] for r in runs)):
        rr = [r for r in runs if r["anchor"] == anchor]
        X = np.array([[1, r["kv"], r["kv"]**2, r["R"], r["F"], r["W"]] for r in rr])
        y = np.array([r["lnq"] for r in rr])
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        yhat = X @ beta
        ss_res = np.sum((y - yhat)**2); ss_tot = np.sum((y - y.mean())**2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        b0, b_kv, b_kv2, b_R, b_F, b_W = beta
        kv_star = -b_kv / (2 * b_kv2) if b_kv2 != 0 else None   # 정점(=Q 최대 kV)
        pd = rr[0]["pd"]
        res[anchor] = dict(
            pd=pd, coef=dict(b0=b0, kV=b_kv, kV2=b_kv2, R=b_R, F=b_F, W=b_W),
            kv_star=round(kv_star, 2), r2=round(r2, 4),
            q_at_star=round(math.exp(b0 + b_kv*kv_star + b_kv2*kv_star**2
                            + b_R*rr[0]["R"] + b_F*64 + b_W*4), 4),
        )
    # kV*(D) 2점 직선
    anchors = sorted(res, key=lambda a: res[a]["pd"])
    (d1, k1), (d2, k2) = [(res[a]["pd"], res[a]["kv_star"]) for a in anchors]
    slope = (k2 - k1) / (d2 - d1)
    res["_kv_star_line"] = dict(slope=round(slope, 5), intercept=round(k1 - slope*d1, 4),
                                note=f"kV*(D) = {round(k1-slope*d1,3)} + {round(slope,5)}·D  (2 anchor 직선)")
    return res

# ---------------------------------------------------------------- 4. Tact 모델
def fit_tact(runs):
    """tact ~ 1 + bumps + bumps·(F/64) 회귀 (검사시간 ∝ 검사량×프레임)."""
    rr = [r for r in runs if r["tact"]]
    X = np.array([[1, r["bumps"], r["bumps"]*r["F"]/64.0] for r in rr])
    y = np.array([r["tact"] for r in rr])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    yhat = X @ beta
    r2 = 1 - np.sum((y-yhat)**2)/np.sum((y-y.mean())**2)
    return dict(coef=dict(b0=round(beta[0],3), per_bump=round(beta[1],5),
                          per_bump_F=round(beta[2],5)), r2=round(r2,4))

# ---------------------------------------------------------------- 5. 뷰(PNG)
def make_views(runs, diam, tact):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager as fm
    fp = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
    if os.path.exists(fp):
        fm.fontManager.addfont(fp)
        matplotlib.rcParams["font.family"] = fm.FontProperties(fname=fp).get_name()
    matplotlib.rcParams["axes.unicode_minus"] = False
    C = {"D26": "#2E86C1", "D86": "#E67E22"}

    # (1) 직경 Gate: Q vs kV + 포물선 + kV*
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for anchor in ("D26", "D86"):
        rr = [r for r in runs if r["anchor"] == anchor]
        ax.scatter([r["kv"] for r in rr], [r["q"] for r in rr], s=28, color=C[anchor],
                   alpha=.55, label=f"{anchor} 실측")
        c = diam[anchor]["coef"]; ks = np.linspace(min(r["kv"] for r in rr)-0.5,
                                                    max(r["kv"] for r in rr)+0.5, 60)
        Rr, Ff, Ww = rr[0]["R"], 64, 4
        q = np.exp(c["b0"]+c["kV"]*ks+c["kV2"]*ks**2+c["R"]*Rr+c["F"]*Ff+c["W"]*Ww)
        ax.plot(ks, q, color=C[anchor], lw=2)
        ax.axvline(diam[anchor]["kv_star"], color=C[anchor], ls="--", lw=1)
    ax.axhspan(0.97, 1.03, color="green", alpha=.08, label="직경 Gate 0.97~1.03")
    ax.set_xlabel("kV"); ax.set_ylabel("Q_dia (측정/PD)")
    ax.set_title("직경 Gate: kV–직경은 2차(포물선), kV*=정점")
    ax.legend(fontsize=8); fig.tight_layout(); fig.savefig(f"{VIEWS}/1_직경Gate_QvsKV.png", dpi=110); plt.close(fig)

    # (2) N8 Gate: N8 vs R
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for anchor in ("D26", "D86"):
        rr = [r for r in runs if r["anchor"] == anchor]
        ax.scatter([r["R"] for r in rr], [r["n8"] for r in rr], s=28, color=C[anchor], alpha=.6, label=anchor)
    ax.axhline(N8_MIN, color="red", ls="--", label=f"N8 Gate = {N8_MIN}")
    ax.set_xlabel("R (µm/px)"); ax.set_ylabel("N8 = 측정직경·√0.08 / R")
    ax.set_title(f"N8 해상도 Gate(N8≥{N8_MIN}): 26µm은 R≤0.5, 86µm은 R≤1.5(정점kV 기준) 통과")
    ax.legend(fontsize=8); fig.tight_layout(); fig.savefig(f"{VIEWS}/2_N8Gate_N8vsR.png", dpi=110); plt.close(fig)

    # (3) Tact: 실측 vs 예측
    fig, ax = plt.subplots(figsize=(6, 5))
    rr = [r for r in runs if r["tact"]]
    c = tact["coef"]
    pred = [c["b0"]+c["per_bump"]*r["bumps"]+c["per_bump_F"]*r["bumps"]*r["F"]/64 for r in rr]
    ax.scatter([r["tact"] for r in rr], pred, s=28, color="#8E44AD", alpha=.6)
    lim = [0, max(max(r["tact"] for r in rr), max(pred))*1.05]
    ax.plot(lim, lim, "k--", lw=1)
    ax.set_xlabel("실측 Tact (s)"); ax.set_ylabel("모델 예측 Tact (s)")
    ax.set_title(f"Tact 모델 (bump수·F)  R²={tact['r2']}")
    fig.tight_layout(); fig.savefig(f"{VIEWS}/3_Tact_실측vs예측.png", dpi=110); plt.close(fig)

    # (4) DOE 주효과 (Q_dia) — 교락 제거판
    #   kV : 전체 데이터(정점 포물선이 목적)
    #   R/F/W : kV를 각 자재의 정점 레벨에 고정한 뒤 수준별 평균 → 교락 제거
    #   같은 y축 + 각 패널에 peak-to-peak(Δ%p) 표기 → kV만 크고 R/F/W는 평탄함이 한눈에 보이게.
    vtx = {a: min(sorted(set(r["kv"] for r in runs if r["anchor"] == a)),
                  key=lambda L: abs(L - diam[a]["kv_star"])) for a in ("D26", "D86")}
    fig, axes = plt.subplots(1, 4, figsize=(13.5, 3.8), sharey=True)
    facs = [("kv", None), ("R", "kv"), ("F", "kv"), ("W", "kv")]
    for ax, (fac, fixkey) in zip(axes, facs):
        deltas = []
        for anchor in ("D26", "D86"):
            rr = [r for r in runs if r["anchor"] == anchor]
            if fixkey == "kv":                      # 정점 kV로 고정 → 교락 제거
                rr = [r for r in rr if r["kv"] == vtx[anchor]]
            levels = sorted(set(r[fac] for r in rr))
            means = [float(np.mean([r["q"] for r in rr if r[fac] == L])) for L in levels]
            deltas.append((max(means) - min(means)) * 100)
            ax.plot(levels, means, "o-", color=C[anchor], lw=1.8, ms=6,
                    label=f"{anchor}" + (f" (Δ{(max(means)-min(means))*100:.1f}%p)"))
        ax.axhspan(0.97, 1.03, color="green", alpha=.06)   # 직경 Gate = '무영향' 기준띠
        dtag = "포물선(정점≈60)" if fac == "kv" else f"평탄 Δ≤{max(deltas):.1f}%p"
        cond = "" if fac == "kv" else f"\n(kV=정점 고정: 26µm={vtx['D26']:.0f}, 86µm={vtx['D86']:.0f})"
        ax.set_title(f"{fac} 주효과 — {dtag}{cond}", fontsize=9)
        ax.set_xlabel(fac); ax.grid(alpha=.3); ax.legend(fontsize=7.5)
    axes[0].set_ylabel("평균 Q_dia (측정/PD)")
    fig.suptitle("DOE 주효과 (Q_dia) — kV는 20%p 급변(포물선), R/F/W는 kV 고정 시 초록띠 안 평탄 = 직경 무영향",
                 fontsize=11)
    fig.tight_layout(); fig.savefig(f"{VIEWS}/4_DOE주효과_Qdia.png", dpi=110); plt.close(fig)

# ---------------------------------------------------------------- 6. 레시피 계산기(Excel)
def build_calculator(diam, tact, runs):
    import openpyxl
    from openpyxl.styles import PatternFill, Font, Alignment
    YEL = PatternFill("solid", fgColor="FFF2CC"); BLU = PatternFill("solid", fgColor="DDEBF7")
    GRY = PatternFill("solid", fgColor="E2EFDA"); ORG = PatternFill("solid", fgColor="FCE4D6")
    B = Font(bold=True); WR = Alignment(wrap_text=True, vertical="top")
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "레시피_계산기"
    line = diam["_kv_star_line"]; d26 = diam["D26"]; d86 = diam["D86"]
    def w(a, v, f=None, b=False, wr=False):
        ws[a] = v
        if f: ws[a].fill = f
        if b: ws[a].font = B
        if wr: ws[a].alignment = WR
    w("A1", "X-ray 레시피 계산기 (DOE 38런 회귀 기반)", b=True)
    w("A2", "노란칸=입력. PD 직경만 넣으면 kV/R/F/W 추천이 나옵니다. 계수는 pipeline.py가 산출.", wr=True); ws.merge_cells("A2:E2")
    w("A4", "■ 입력", GRY, b=True)
    w("A5", "PD 직경 D (µm)"); w("B5", 86, YEL); w("C5", "µm")
    w("A6", "검사할 범프 수(목표)"); w("B6", 300, YEL); w("C6", "개")
    w("A8", "■ 추천 (자동)", GRY, b=True)
    # kV*(D) = intercept + slope·D
    w("A9", "kV* (추천 시작 전압)")
    ws["B9"] = f"=ROUND({line['intercept']}+{line['slope']}*B5,1)"; ws["B9"].fill = BLU
    w("C9", "kV"); w("D9", "kV–직경 정점(2 anchor 직선 보간). ⚠ 창이 좁음: PhaseB 실측상 kV+1이면 이미 ~20% 언더사이즈 → 트림은 ±0.5kV 이내로만, 정점 정밀 맞춤 필수", wr=True)
    # 예측 Q at kV* : anchor 보간(26↔86)
    w("A10", "예측 Q_dia @ kV*")
    ws["B10"] = f"=ROUND({d26['q_at_star']}+({d86['q_at_star']}-{d26['q_at_star']})/(86-26)*(B5-26),3)"
    ws["B10"].fill = BLU; w("C10", "-"); w("D10", "정점에서 얻는 최대 Q(≈1). 26µm은 ~0.98가 한계", wr=True)
    # ── R : 이론 상한(N8 게이트 공식) vs 실측 확인값(F32·정점kV, 두 게이트 통과) ──
    # 실측확인 R: D26=0.5(D26-08), D86=0.8(D86-08) — 둘 다 F=32·정점kV에서 유일하게 확인된 값.
    # N8 공식은 R×F 상호작용이 없다고 가정(회귀가 additive)한 이론치라 실측확인보다 낙관적일 수 있음.
    R_CONF_26, R_CONF_86 = 0.5, 0.8
    w("A11", f"R 상한 (이론, N8≥{N8_MIN} 공식)")
    ws["B11"] = f"=ROUND(B5*{round(SQRT_P,4)}/{N8_MIN},2)"; ws["B11"].fill = BLU
    w("C11", "µm/px"); w("D11", "N8 게이트 공식값. F가 N8에 영향 없다는 가정(additive 회귀) 하의 이론 상한", wr=True)
    w("A12", "R 실측 확인 상한 (F=32·정점kV)")
    ws["B12"] = f"=ROUND({R_CONF_26}+({R_CONF_86}-{R_CONF_26})/(86-26)*(B5-26),2)"; ws["B12"].fill = BLU
    w("C12", "µm/px"); w("D12", "F=32·정점kV 조합에서 실제로 두 게이트를 통과한 값(26µm=0.5, 86µm=0.8, 2anchor 보간). "
             "이 값을 넘는 R은 F=32에서 미검증(Phase B1 대상)", wr=True)
    w("A13", "R 권장 범위 (하한~상한)")
    ws["B13"] = "=\"0.2(장비 하한) ~ \"&TEXT(MIN(B11,B12),\"0.00\")&\" µm/px\""; ws["B13"].fill = BLU
    w("C13", ""); w("D13", "권장 상한 = 이론·실측확인 중 더 보수적인 값(=MIN). 하한 0.2는 장비 물리 하한(광자부족 위험 구간)", wr=True)
    # 각 anchor에서 '실측 확인된 가장 고운(낮은) R' — 26µm=0.35(RF1), 86µm=0.5(D86-06). 이보다 낮은 R은 미검증.
    R_FINE_26, R_FINE_86 = 0.35, 0.5
    w("A14", "R 추천 ① 기본 (속도 우선)")
    ws["B14"] = "=MIN(B11,B12)"; ws["B14"].fill = BLU
    w("C14", "µm/px"); w("D14", "N8 게이트(≥14)를 통과하는 가장 거친(빠른) R. 해상도 여유를 최소로 씀 = 기본값. 26µm→0.5(N8≈14.5), 86µm→0.8(N8≈30)", wr=True)
    w("A15", "R 추천 ② 대안 (void 해상도 우선)")
    ws["B15"] = f"=MIN(B14,ROUND({R_FINE_26}+({R_FINE_86}-{R_FINE_26})/(86-26)*(B5-26),2))"; ws["B15"].fill = ORG
    w("C15", "µm/px"); w("D15", "각 자재에서 실측 확인된 가장 고운(낮은) R → void 해상도(N8) 여유 최대. "
             "26µm→0.35(RF1: Q0.9945·N8 20.9·거짓NG0%), 86µm→0.5(D86-06: Q0.998·N8 48.5). 더 낮추면 미검증. 그만큼 느려짐", wr=True)

    # ── F/W 고정 근거: 최다 반복 셀(D26, R=0.5, kV=정점)에서 F·W 수준별 평균 Q_dia 비교 ──
    kv0 = round(d26["kv_star"])
    base = [r for r in runs if r["anchor"] == "D26" and r["R"] == 0.5 and round(r["kv"]) == kv0]
    def level_q(key):
        levels = sorted(set(r[key] for r in base))
        return {L: round(float(np.mean([r["q"] for r in base if r[key] == L])), 4) for L in levels}
    f_ev = level_q("F"); w_ev = level_q("W")
    f_spread = round((max(f_ev.values()) - min(f_ev.values())) * 100, 2)
    w_spread = round((max(w_ev.values()) - min(w_ev.values())) * 100, 2)
    f_lv = list(f_ev.keys()); w_lv = list(w_ev.keys())
    w("A16", "F 범위 (테스트 확인)")
    w("B16", f"{int(min(f_lv))} ~ {int(max(f_lv))}", BLU); w("C16", "장비 배율")
    w("D16", f"실측 테스트 구간(kV{kv0}·R0.5): F{f_lv} → 평균 Q_dia={list(f_ev.values())}(편차 {f_spread}%p) → 전 구간 직경 무영향", wr=True)
    w("A17", "F 추천"); w("B17", 32, BLU); w("C17", "장비 최소")
    w("D17", "직경 무영향 확인 구간의 최소값 사용 → tact만 아끼는 선택. void σ 예산(2차 모델링)이 정해지면 상향될 수 있음", wr=True)
    w("A18", "W 범위 (테스트 확인)")
    w("B18", f"{min(w_lv):g} ~ {max(w_lv):g}", BLU); w("C18", "")
    w("D18", f"실측 테스트 구간(동일 조건): W{w_lv} → 평균 Q_dia={list(w_ev.values())}(편차 {w_spread}%p) → 전 구간 직경 무영향", wr=True)
    w("A19", "W 추천"); w("B19", 4, BLU)
    w("D19", "직경 무영향 확인 구간의 기본값(최소) 사용. 두꺼운 자재 도입 시(SNR 부족) 재검토 필요", wr=True)

    # 예상 tact
    tc = tact["coef"]
    w("A20", "예상 Tact (s, 근사)")
    ws["B20"] = f"=ROUND({tc['b0']}+({tc['per_bump']}+{tc['per_bump_F']}*B17/64)*B6,0)"
    ws["B20"].fill = BLU; w("C20", "초"); w("D20", "tact≈b0+(계수)·bump수. 검사 범프수·F로 추정", wr=True)
    for rr in (11, 12, 15, 16, 18): ws.row_dimensions[rr].height = 30

    w("A22", "■ 주의 (실측 기반)", ORG, b=True)
    w("A23", f"① kV–직경은 포물선 → kV는 정점(≈60)에 고정, 트림은 ±0.5kV 이내(kV+1이면 이미 ~20% 언더 — PhaseB). "
             f"② 오차기준 ε={int(EPS*100)}%(N8≥{N8_MIN})로 통일 → 26µm도 R≤0.5에서 통과(자세한 근거는 '오차기준_근거' 시트). "
             f"③ R 추천은 두 값: ①기본(속도, N8 게이트 턱걸이) ②대안(void 해상도 여유, 더 고움). 둘 다 게이트 통과 — 목적에 따라 선택. "
             f"④ void 판정 정확도(False OK/NG)는 8% 근처 void 샘플 확보 후 검증(2차 모델링). "
             f"⑤ F/W는 직경 무영향 확인 구간 내 최소값을 권장(비용 최소화) — R처럼 상/하한이 있는 게 아니라 '무관하니 최소'가 근거.", wr=True)
    ws.merge_cells("A23:E27")
    for col, wd in {"A": 26, "B": 20, "C": 10, "D": 52, "E": 6}.items():
        ws.column_dimensions[col].width = wd

    # ── 시트: 파라미터 메커니즘 ─────────────────────────────
    wm = wb.create_sheet("파라미터_메커니즘")
    wm["A1"] = "파라미터 메커니즘 — 자재 직경 D가 주어지면 각 값을 어떻게 정하나"; wm["A1"].font = B
    wm.append(["파라미터", "무엇을 조절하나(물리)", "D가 주어지면 어떻게 정하나", "D 의존성"])
    for c in "ABCD": wm[f"{c}2"].font = B; wm[f"{c}2"].fill = GRY
    mech = [
        ("kV", "X-ray 투과/대비 → threshold가 범프 경계를 잡는 위치 → 측정직경",
         "측정직경=PD가 되는 정점(≈60)에 고정 후 1kV씩 트림. 직경의 '정확도'를 담당", "거의 무관(26·86µm 둘다 ~60)"),
        ("R", "픽셀 크기 → 8% void가 몇 픽셀(N8)로 표현되나 → 픽셀화 오차(2/N8)",
         "N8≥게이트 되는 가장 거친(빠른) R = D·√0.08/N8. void의 '해상도'를 담당", "D에 비례(클수록 R↑ 가능)"),
        ("F", "여러 장 평균 → 랜덤 광자노이즈 저감(∝1/√F). 측정직경·N8은 안 바뀜",
         "노이즈 σ가 예산 안에 들도록 최소 F(≥32). 측정 '재현성'을 담당", "무관(조건별 σ로 결정)"),
        ("W", "X-ray 선속(밝기) → 광자부족 영역의 SNR. 시간은 안 늘어남",
         "얇은 범프는 4 고정(효과 미검출). 두꺼운 범프 내부가 어두울 때만 ↑", "두께 의존(현재 자재는 4)"),
    ]
    for row in mech: wm.append(list(row))
    wm.append([])
    wm.append(["핵심", "kV=정확도, R=해상도, F=재현성, W=밝기 — 서로 다른 오차원을 담당해 독립적으로 목표에 맞춘다."])
    for c, wd in {"A": 8, "B": 40, "C": 44, "D": 22}.items(): wm.column_dimensions[c].width = wd

    # ── 시트: 오차기준 근거 ─────────────────────────────
    we = wb.create_sheet("오차기준_근거")
    we["A1"] = f"오차 기준 ε = {int(EPS*100)}% (자재 무관 통일)"; we["A1"].font = B
    lines = [
        ("근거 이론", "게이지 R&R(측정시스템분석, AIAG MSA / ISO 14253): 측정오차 ≤ 판정공차의 10%=우수, 10~30%=허용, >30%=불가."),
        ("왜 20%", f"8% void 판정선에 적용. 10%(우수)는 86µm만 통과하고 26·10µm은 구조적 탈락. "
                   f"같은 이론의 '허용' 등급 범위(10~30%) 안에서 통일값 {int(EPS*100)}%를 채택 → 자재 무관 동일 원칙."),
        ("총오차 구성", "총오차 = √(픽셀화² + 노이즈²). 픽셀화=2/N8(R로 결정, 계통), 노이즈=2σ(F/W로 결정, 랜덤)."),
        ("N8 게이트 유도", f"픽셀화·노이즈 균등분할 → 각 ≤ ε/√2 = {round(EPS/2**0.5*100,1)}%. "
                        f"픽셀화 2/N8 ≤ {round(EPS/2**0.5*100,1)}% → N8 ≥ 2√2/ε = {N8_MIN}."),
        ("자재별 달성", f"N8≥{N8_MIN} 충족: 86µm(여유)·26µm(R≤0.5, N8≈14.7)·10µm(R≈0.2에서 N8≈14, 측정성공 시)."),
        ("주의", "10µm은 실측 없음(외삽). 26µm의 R=0.35는 F=128에서만 확인됨 — F=32×R=0.35 조합은 데이터에 아예 없음(미검증, "
                 "R하한 0.5는 F=32 기준 실측확인값). F를 올리면 R을 더 낮출 여지가 있는지가 Phase B1의 핵심 질문."),
        ("F/W 고정 근거", f"kV{kv0}·R0.5(38런 중 최다 반복 조건)에서 F 수준별 평균 Q_dia 편차 {f_spread}%p, "
                       f"W 수준별 편차 {w_spread}%p — 둘 다 노이즈 수준. kV 정점 고정 + 극단 R을 피하면 F/W는 직경에 관측 가능한 영향이 없어 "
                       f"F=32(장비 최소, tact 절약)·W=4(기본값)로 고정. 근거는 '레시피_계산기' 시트 F/W 범위·추천 행 참조."),
    ]
    r = 2
    for k, v in lines:
        we.cell(r, 1, k).font = B; we.cell(r, 2, v).alignment = WR; r += 1
    we.column_dimensions["A"].width = 16; we.column_dimensions["B"].width = 80
    # 계수 시트
    ws2 = wb.create_sheet("모델계수")
    ws2["A1"] = "직경 모델 계수 (anchor별 ln_Q = b0 + b_kV·kV + b_kV2·kV² + b_R·R + b_F·F + b_W·W)"; ws2["A1"].font = B
    ws2.append(["anchor", "PD", "b0", "b_kV", "b_kV2", "b_R", "b_F", "b_W", "kV*", "Q@kV*", "R²"])
    for a in ("D26", "D86"):
        c = diam[a]["coef"]
        ws2.append([a, diam[a]["pd"], round(c["b0"],5), round(c["kV"],5), round(c["kV2"],6),
                    round(c["R"],5), round(c["F"],6), round(c["W"],5),
                    diam[a]["kv_star"], diam[a]["q_at_star"], diam[a]["r2"]])
    ws2.append([]); ws2.append(["kV*(D) 직선", line["note"]])
    ws2.append(["Tact 모델", f"tact = {tc['b0']} + {tc['per_bump']}·bump + {tc['per_bump_F']}·bump·(F/64), R²={tact['r2']}"])
    for col in "ABCDEFGHIJK": ws2.column_dimensions[col].width = 12
    wb.save(os.path.join(HERE, "레시피_계산기.xlsx"))

# ---------------------------------------------------------------- main
def main():
    runs = load_runs()
    write_run_summary(runs); write_bump_merged(runs)
    diam = fit_diameter(runs); tact = fit_tact(runs)
    with open(os.path.join(OUT, "model_coefficients.json"), "w") as f:
        json.dump({"diameter": diam, "tact": tact,
                   "gates": {"N8_min": N8_MIN, "diam_gate": [0.97, 1.03]}},
                  f, ensure_ascii=False, indent=2)
    make_views(runs, diam, tact)
    build_calculator(diam, tact, runs)
    # 콘솔 요약
    print("=== 직경 모델 (kV²) ===")
    for a in ("D26", "D86"):
        print(f"  {a}: kV*={diam[a]['kv_star']}  Q@kV*={diam[a]['q_at_star']}  R²={diam[a]['r2']}")
    print("  " + diam["_kv_star_line"]["note"])
    print(f"=== Tact 모델 R²={tact['r2']} ===")
    print(f"게이트 통과: 직경 {sum(r['diam_gate'] for r in runs)}/{len(runs)}, "
          f"N8 {sum(r['n8_gate'] for r in runs)}/{len(runs)}, "
          f"둘다 {sum(r['diam_gate'] and r['n8_gate'] for r in runs)}/{len(runs)}")
    print("산출물:", OUT, "+ 레시피_계산기.xlsx")

if __name__ == "__main__":
    main()
