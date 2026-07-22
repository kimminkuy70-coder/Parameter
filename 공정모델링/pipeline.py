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
    # F/W 실측 증거(설명 시트에서 인용) — 최다 반복 셀(D26, R=0.5, kV=정점)에서 수준별 평균 Q_dia
    kv0 = round(d26["kv_star"])
    base = [r for r in runs if r["anchor"] == "D26" and r["R"] == 0.5 and round(r["kv"]) == kv0]
    def level_q(key):
        levels = sorted(set(r[key] for r in base))
        return {L: round(float(np.mean([r["q"] for r in base if r[key] == L])), 4) for L in levels}
    f_ev = level_q("F"); w_ev = level_q("W")
    f_spread = round((max(f_ev.values()) - min(f_ev.values())) * 100, 2)
    w_spread = round((max(w_ev.values()) - min(w_ev.values())) * 100, 2)
    f_lv = list(f_ev.keys()); w_lv = list(w_ev.keys())

    w("A1", "X-ray 레시피 계산기", b=True)
    w("A2", "사용법: 노란칸(D, 검사 범프수)만 입력 → 아래 파란칸이 자동 계산됩니다. "
            "각 값이 '왜 그렇게 나오는지'는 옆의 '추천값_설명' 시트에 처음 보는 사람 기준으로 풀어 놨습니다.", wr=True)
    ws.merge_cells("A2:E2"); ws.row_dimensions[2].height = 30

    w("A4", "■ 입력 (노란칸)", GRY, b=True)
    w("A5", "PD 직경 D (µm)"); w("B5", 86, YEL); w("C5", "µm"); w("D5", "제품 도면상 범프 지름(참값). 이거 하나로 kV·R이 정해짐", wr=True)
    w("A6", "검사할 범프 수(목표)"); w("B6", 300, YEL); w("C6", "개"); w("D6", "예상 검사시간(tact) 계산에만 쓰임", wr=True)

    w("A8", "■ 추천값 (자동)", GRY, b=True)
    # kV*
    w("A9", "kV (전압)")
    ws["B9"] = f"=ROUND({line['intercept']}+{line['slope']}*B5,1)"; ws["B9"].fill = BLU
    w("C9", "kV"); w("D9", "측정직경이 실제 PD와 같아지는 '정점'(≈60, B3 실측 정점 59.9). ⚠ 창이 매우 좁음: B3에서 ±0.5kV(59.5·60.5)는 둘 다 게이트 탈락 → 실질 트림 ±0.3kV. 비대칭(높은 쪽 낙폭 2.6배) → 오차 시 살짝 낮게(kV↓) 치우치는 게 안전", wr=True)
    w("A10", "└ 예측 정확도 Q_dia")
    ws["B10"] = f"=ROUND({d26['q_at_star']}+({d86['q_at_star']}-{d26['q_at_star']})/(86-26)*(B5-26),3)"
    ws["B10"].fill = BLU; w("C10", "측정/PD"); w("D10", "위 kV에서 얻는 (측정직경÷PD). 1.00이 완벽, 0.97~1.03이면 합격. 26µm은 ~0.98이 한계", wr=True)
    # R (단일 추천 = N8 상한)
    w("A11", "R (해상도용 픽셀크기)")
    ws["B11"] = f"=ROUND(B5*{round(SQRT_P,4)}/{N8_MIN},2)"; ws["B11"].fill = BLU
    w("C11", "µm/px"); w("D11", f"8% void를 겨우 볼 수 있는 '가장 큰(=가장 안전한) 픽셀'. 큰 R일수록 픽셀당 광자↑ → 측정 안정. "
             f"공식 R=D·√0.08/{N8_MIN}", wr=True)
    w("A12", "└ 사용 가능 범위")
    ws["B12"] = f"=\"0.2 ~ \"&TEXT(B11,\"0.00\")"; ws["B12"].fill = BLU
    w("C12", "µm/px"); w("D12", "이보다 크면 void를 못 봄(해상도 부족). 이보다 작으면(→0.2) 픽셀이 광자를 굶어 측정 실패(26µm R0.2~0.25 실측 실패). "
             "8%보다 작은 void를 잡을 때만 R을 낮추고, 그땐 F·W로 광자 보충 필요", wr=True)
    # F
    w("A13", "F (프레임 수)"); w("B13", 32, BLU); w("C13", "장(최소)")
    w("D13", "여러 장 평균 → 랜덤 노이즈 저감용. 그런데 지금 노이즈가 이미 극히 작아(σ≈0.15%) 더 평균낼 필요가 없어서 최소값. 직경엔 영향 없음(실측 편차 " + f"{f_spread}%p)", wr=True)
    # W
    w("A14", "W (선속=밝기)"); w("B14", 4, BLU); w("C14", "(최소)")
    w("D14", "범프 내부가 어두울 때 밝혀주는 값. 현재 자재(26·86µm)는 얇아서 내부가 안 어두워 효과 없음(실측 W4=W6) → 최소값. 두꺼운 자재 오면 재검토", wr=True)
    # tact
    tc = tact["coef"]
    w("A15", "예상 Tact (검사시간)")
    ws["B15"] = f"=ROUND({tc['b0']}+({tc['per_bump']}+{tc['per_bump_F']}*B13/64)*B6,0)"
    ws["B15"].fill = BLU; w("C15", "초"); w("D15", "대략치. 범프 수·F로 추정(예비 모델이라 오차 큼)", wr=True)
    for rr in (2, 9, 11, 12, 13, 14): ws.row_dimensions[rr].height = 30

    w("A17", "■ 한 줄 요약", ORG, b=True)
    w("A18", "kV=직경 정확도(정점에 정밀 고정) · R=void 해상도+광자 안전(상한이 최적) · "
             "F=노이즈용인데 이미 충분해 최소 · W=밝기용인데 자재가 얇아 불필요해 최소. "
             "→ 지금 자재·스펙에선 kV만 신경 쓰면 되고 R은 공식으로, F·W는 최소로 확정. 자세한 이유는 '추천값_설명' 시트.", wr=True)
    ws.merge_cells("A18:E21")
    for col, wd in {"A": 20, "B": 14, "C": 10, "D": 60, "E": 6}.items():
        ws.column_dimensions[col].width = wd

    # ── 시트: 추천값_설명 (처음 보는 사람용, 파라미터별 상세) ─────────────
    ex = wb.create_sheet("추천값_설명")
    ex["A1"] = "각 추천값을 어떻게 정했나 — 처음 보는 사람용 설명"; ex["A1"].font = Font(bold=True, size=12)
    ex.merge_cells("A1:F1")
    ex["A2"] = ("이 모델은 '자재 직경(D)을 넣으면 범프 직경을 정확히 재는 레시피'를 뽑아줍니다. "
                "네 파라미터(kV·R·F·W)는 서로 다른 일을 담당하고, 아래처럼 각자 다른 방식으로 정해집니다.")
    ex.merge_cells("A2:F2"); ex["A2"].alignment = WR; ex.row_dimensions[2].height = 30
    hdr = ["파라미터", "이게 뭔가", "무엇을 좋게 하나(담당)", "추천값을 어떻게 정하나", "실측 근거 / 주의"]
    ex.append([]); ex.append(hdr)
    for c in range(1, 6): ex.cell(4, c).font = B; ex.cell(4, c).fill = GRY
    rows = [
        ("kV\n(전압)", "X선 전압. 높을수록 투과가 세짐 → 범프 경계를 잡는 위치가 달라져 '측정 직경'이 바뀜.",
         "직경 정확도 — 측정직경이 실제 PD와 맞는가. (네 파라미터 중 직경을 바꾸는 건 kV뿐)",
         "kV를 올리면 측정직경이 커졌다 작아지는 '포물선'. 그 꼭지점(측정직경=PD)이 추천값. 두 자재 다 ≈60이라 D와 거의 무관.",
         "⚠ 가장 중요: 봉우리가 날카로움. PhaseB 실측상 kV+1이면 벌써 ~20% 작게 측정됨. 그래서 트림 ±0.5kV, 정점 정밀 세팅이 핵심. kV 드리프트가 최대 리스크."),
        ("R\n(픽셀 크기)", "이미지 한 픽셀이 실제 몇 µm인가(µm/px). 작을수록 이미지가 곱다(고해상도).",
         "① void 해상도 — 8% void를 몇 픽셀로 그리나(N8). ② 광자 신뢰도 — 픽셀이 클수록 광자를 많이 모아 측정이 안정.",
         "8% void를 겨우 볼 최소 해상도(N8=14)에 해당하는 '가장 큰 R'을 추천. 공식 R=D·√0.08/14. 큰 R=광자 많음=가장 안전한데 void도 볼 수 있는 지점.",
         "왜 더 작게(0.2) 안 쓰나: 픽셀이 잘면 광자를 굶어 측정이 깨짐(26µm R0.2~0.25 실측 실패, R0.35부터 성공). 8%보다 작은 void를 잡을 때만 R을 낮추고, 그땐 F·W로 광자 보충 필요."),
        ("F\n(프레임 수)", "같은 자리를 여러 장 찍어 평균냄. 많을수록 랜덤 노이즈가 줄어듦(∝1/√F). 대신 시간↑.",
         "재현성 — 측정값의 랜덤 흔들림(노이즈 σ)을 줄임. 직경 평균값·해상도(N8)는 안 바꿈.",
         "최소값(32). 이유: 지금 노이즈가 이미 극히 작아(운영점 σ≈0.15%, 허용 예산 14%의 1/100) 더 평균낼 실익이 없음 → 비용(시간)만 늘어 최소.",
         f"F32/64/128 실측 → 직경 편차 {f_spread}%p(무영향). 다만 σ(F) 곡선을 직접 잰 건 아님 → 'F=32면 충분'을 못박으려면 σ 반복실험이 남음(값은 안 바뀔 전망)."),
        ("W\n(선속=밝기)", "X선 파워(밝기). 높이면 어두운 영역이 밝아짐. 시간은 안 늘어남.",
         "밝기 — 범프 내부가 어두워(광자부족) 잘 안 보일 때 SNR을 살림.",
         "최소값(4). 이유: 현재 자재(26·86µm)는 얇아서 내부가 안 어두움 → W를 올려도 효과가 없음. 그래서 최소.",
         "W4 vs W6 실측 → 직경 편차 " + f"{w_spread}%p(무영향). 86µm(제일 두꺼움)에서도 효과 없음 → 이 자재들엔 4가 확정 최적. 더 두껍거나 치밀한 자재가 오면 그때만 재검토."),
    ]
    r = 5
    for row in rows:
        ex.append(list(row))
        for c in range(1, 6): ex.cell(r, c).alignment = WR
        ex.row_dimensions[r].height = 78; r += 1
    ex.append([])
    ex.append(["요약", "kV=정확도 / R=해상도+광자안전 / F=재현성(이미 충분) / W=밝기(자재 얇아 불필요). "
               "직경 정확도는 kV 하나가 지배하고, R은 공식으로, F·W는 '필요 없어서 최소'로 정해집니다."])
    ex.cell(r+1, 1).font = B; ex.merge_cells(f"B{r+1}:E{r+1}"); ex.cell(r+1, 2).alignment = WR
    for c, wd in {"A": 12, "B": 34, "C": 30, "D": 40, "E": 46}.items(): ex.column_dimensions[c].width = wd

    # ── 시트: 오차기준 근거 ─────────────────────────────
    we = wb.create_sheet("오차기준_근거")
    we["A1"] = f"오차 기준 ε = {int(EPS*100)}% 은 어디서 왔나"; we["A1"].font = B
    lines = [
        ("한 줄 요약", f"'측정 오차를 판정 기준의 {int(EPS*100)}% 안으로 넣자'는 목표. 이 목표가 R의 상한(N8≥{N8_MIN})을 정함."),
        ("근거 이론", "게이지 R&R(측정시스템분석, AIAG MSA / ISO 14253): 측정오차 ≤ 판정공차의 10%=우수, 10~30%=허용, >30%=불가."),
        ("왜 20%", f"10%(우수)로 잡으면 86µm만 통과하고 작은 자재(26µm)는 구조적으로 탈락. "
                   f"그래서 같은 이론의 '허용' 등급(10~30%) 안에서 자재 무관 통일값 {int(EPS*100)}%를 채택."),
        ("총오차 구성", "총오차 = √(픽셀화오차² + 노이즈오차²). 픽셀화=2/N8(R이 결정, 계통오차), 노이즈=2σ(F·W가 결정, 랜덤오차)."),
        ("N8 상한 유도", f"두 오차를 반반씩 나누면 각 ≤ ε/√2 = {round(EPS/2**0.5*100,1)}%. "
                        f"픽셀화 2/N8 ≤ {round(EPS/2**0.5*100,1)}% → N8 ≥ 2√2/ε = {N8_MIN}. 이게 R 상한 공식의 뿌리."),
        ("남은 한계", "10µm 같은 더 작은 자재는 실측 없이 외삽. void 검출 정확도(진짜 void를 놓치는가)는 void 샘플이 있어야만 검증 가능 → 미검증."),
    ]
    r = 2
    for k, v in lines:
        we.cell(r, 1, k).font = B; we.cell(r, 2, v).alignment = WR; r += 1
    we.column_dimensions["A"].width = 14; we.column_dimensions["B"].width = 86
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
