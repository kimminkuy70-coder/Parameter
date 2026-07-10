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
N8_MIN = 29                # 해상도 게이트

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
    ax.set_title("N8 해상도 Gate: 26µm은 전 조건 미달, 86µm은 R≤0.8 통과")
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

    # (4) DOE 주효과 (Q_dia): 각 인자 수준별 평균 Q
    fig, axes = plt.subplots(1, 4, figsize=(13, 3.4), sharey=True)
    for ax, fac in zip(axes, ["kv", "R", "F", "W"]):
        for anchor in ("D26", "D86"):
            rr = [r for r in runs if r["anchor"] == anchor]
            levels = sorted(set(r[fac] for r in rr))
            means = [np.mean([r["q"] for r in rr if r[fac] == L]) for L in levels]
            ax.plot(levels, means, "o-", color=C[anchor], label=anchor)
        ax.set_title(f"{fac} 주효과"); ax.set_xlabel(fac); ax.grid(alpha=.3)
    axes[0].set_ylabel("평균 Q_dia"); axes[0].legend(fontsize=8)
    fig.suptitle("DOE 주효과 (Q_dia) — kV가 지배적, R/F/W는 미미")
    fig.tight_layout(); fig.savefig(f"{VIEWS}/4_DOE주효과_Qdia.png", dpi=110); plt.close(fig)

# ---------------------------------------------------------------- 6. 레시피 계산기(Excel)
def build_calculator(diam, tact):
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
    w("C9", "kV"); w("D9", "kV–직경 포물선의 정점(2 anchor 직선 보간). 실검사서 ±1kV 트림", wr=True)
    # 예측 Q at kV* : anchor 보간(26↔86)
    w("A10", "예측 Q_dia @ kV*")
    ws["B10"] = f"=ROUND({d26['q_at_star']}+({d86['q_at_star']}-{d26['q_at_star']})/(86-26)*(B5-26),3)"
    ws["B10"].fill = BLU; w("C10", "-"); w("D10", "정점에서 얻는 최대 Q(≈1). 26µm은 ~0.98가 한계", wr=True)
    # R : N8 게이트 상한 = D·√0.08 / 29
    w("A11", "R 상한 (N8≥29)")
    ws["B11"] = f"=ROUND(B5*{round(SQRT_P,4)}/{N8_MIN},2)"; ws["B11"].fill = BLU
    w("C11", "µm/px"); w("D11", "이 값 이하라야 8% void 해상도 확보. 26µm은 측정가능 R보다 작아 달성 불가", wr=True)
    w("A12", "R 추천")
    ws["B12"] = "=IF(B11>=0.35,MIN(B11,0.8),\"측정불가(광자부족)→직경만\")"; ws["B12"].fill = BLU
    w("C12", "µm/px"); w("D12", "N8 상한과 측정하한(0.35) 사이. 없으면 8% void 정량 불가", wr=True)
    w("A13", "F 추천"); w("B13", 32, BLU); w("C13", "장비 최소"); w("D13", "직경엔 F 영향 미미 → 최소 32. void σ는 별도", wr=True)
    w("A14", "W 추천"); w("B14", 4, BLU); w("D14", "W 효과 미검출 → 4 고정", wr=True)
    # 예상 tact
    tc = tact["coef"]
    w("A15", "예상 Tact (s, 근사)")
    ws["B15"] = f"=ROUND({tc['b0']}+({tc['per_bump']}+{tc['per_bump_F']}*B13/64)*B6,0)"
    ws["B15"].fill = BLU; w("C15", "초"); w("D15", "tact≈b0+(계수)·bump수. 검사 범프수·F로 추정", wr=True)
    w("A17", "■ 주의 (실측 기반)", ORG, b=True)
    w("A18", "① kV–직경은 포물선 → kV는 정점(중심)에 고정, ±2kV에 직경 8%/kV 급변. "
             "② 26µm은 N8<29(해상도 한계)라 8% void 정량 불가·직경만. "
             "③ void 판정 정확도(False OK/NG)는 8% 근처 void 샘플 확보 후 검증. "
             "④ R/F/W는 직경에 거의 무영향(kV가 지배).", wr=True); ws.merge_cells("A18:E21")
    for col, wd in {"A": 20, "B": 16, "C": 10, "D": 46, "E": 6}.items():
        ws.column_dimensions[col].width = wd
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
    build_calculator(diam, tact)
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
