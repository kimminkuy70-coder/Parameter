#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auto_upload.py
로컬 실험 결과 폴더(X-ray 검사 결과 등)를 GitHub 저장소로 자동 업로드합니다.

준비물
  - git 설치 + GitHub 인증 설정 (VS Code로 GitHub 쓰고 있으면 보통 이미 됨)
  - Python 3.8+
  - (watch 모드만) pip install watchdog

사용법 (VS Code 터미널에서)
  python auto_upload.py                 # 폴더를 1회 업로드(commit+push)
  python auto_upload.py --watch         # 폴더를 계속 감시하다 변경되면 자동 업로드
  python auto_upload.py --source "D:\\Xray\\results"   # 소스 폴더 직접 지정

설정은 아래 CONFIG 또는 --source / 환경변수 XRAY_SOURCE_DIR 로 지정.
"""

import os
import sys
import time
import shutil
import argparse
import subprocess
from datetime import datetime

# ===================== CONFIG (여기만 본인 환경에 맞게 수정) =====================
CONFIG = {
    # 1) 업로드할 로컬 실험 결과 폴더 (예: r"C:\Users\me\Desktop\Xray_Results")
    "SOURCE_DIR": r"",

    # 2) GitHub 저장소를 로컬 어디에 둘지 (없으면 자동 clone 됨)
    "REPO_DIR": os.path.join(os.path.expanduser("~"), "Parameter_repo"),

    # 3) 저장소 주소 / 브랜치
    "REPO_URL": "https://github.com/kimminkuy70-coder/Parameter.git",
    "BRANCH": "claude/compressed-file-size-limits-jt8o41",

    # 4) 저장소 안에서 데이터를 넣을 하위 폴더 ("" = 루트, 기존 TEST1.. 와 동일하게)
    "DEST_SUBDIR": "",

    # 5) GitHub 파일 1개 100MB 제한. 이보다 크면 건너뛰고 경고 (LFS 미사용 가정)
    "MAX_FILE_MB": 95,

    # 6) watch 모드: 마지막 변경 후 이 시간(초) 동안 조용하면 업로드 (쓰기 중 중복방지)
    "DEBOUNCE_SEC": 15,
}
# ==============================================================================


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def run(args, cwd=None, check=True):
    """git 등 외부 명령 실행."""
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if r.stdout.strip():
        print(r.stdout.strip())
    if check and r.returncode != 0:
        print(r.stderr.strip())
        raise RuntimeError(f"명령 실패: {' '.join(args)}")
    return r


def ensure_repo(cfg):
    """저장소가 없으면 clone, 있으면 해당 브랜치로 맞춤."""
    repo, url, branch = cfg["REPO_DIR"], cfg["REPO_URL"], cfg["BRANCH"]
    if not os.path.isdir(os.path.join(repo, ".git")):
        log(f"저장소 clone: {url} -> {repo}")
        run(["git", "clone", url, repo])
    # 최신화 + 브랜치 보장
    run(["git", "fetch", "origin"], cwd=repo, check=False)
    # 원격에 브랜치가 있으면 추적, 없으면 새로 생성
    has_remote = run(["git", "ls-remote", "--heads", "origin", branch],
                     cwd=repo, check=False).stdout.strip()
    if has_remote:
        run(["git", "checkout", "-B", branch, f"origin/{branch}"], cwd=repo, check=False)
        run(["git", "pull", "origin", branch], cwd=repo, check=False)
    else:
        run(["git", "checkout", "-B", branch], cwd=repo, check=False)
    log(f"브랜치 준비 완료: {branch}")


def check_big_files(root, max_mb):
    """100MB 초과 파일 탐지."""
    big = []
    limit = max_mb * 1024 * 1024
    for dp, _, files in os.walk(root):
        if ".git" in dp.split(os.sep):
            continue
        for f in files:
            p = os.path.join(dp, f)
            try:
                if os.path.getsize(p) > limit:
                    big.append((p, os.path.getsize(p) / 1024 / 1024))
            except OSError:
                pass
    return big


def sync_source_into_repo(cfg):
    """소스 폴더 내용을 저장소(하위폴더)로 복사. 소스가 곧 저장소면 복사 생략."""
    src = os.path.abspath(cfg["SOURCE_DIR"])
    repo = os.path.abspath(cfg["REPO_DIR"])
    if not src or not os.path.isdir(src):
        raise SystemExit(f"SOURCE_DIR 가 올바르지 않습니다: {src!r}\n"
                         f"--source 인자나 CONFIG['SOURCE_DIR'] 를 설정하세요.")
    dest = repo if not cfg["DEST_SUBDIR"] else os.path.join(repo, cfg["DEST_SUBDIR"])

    # 소스가 저장소 내부면 복사 불필요 (다른 드라이브면 commonpath가 에러 → 내부 아님)
    try:
        inside = os.path.commonpath([src, repo]) == repo
    except ValueError:
        inside = False  # Windows에서 서로 다른 드라이브(C: vs E:)인 경우
    if inside:
        log("소스가 저장소 내부 → 복사 생략, 그대로 커밋합니다.")
        return
    os.makedirs(dest, exist_ok=True)
    log(f"복사: {src}  ->  {dest}")
    # 큰 파일은 건너뛰며 복사
    limit = cfg["MAX_FILE_MB"] * 1024 * 1024
    skipped = []
    for dp, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d != ".git"]
        rel = os.path.relpath(dp, src)
        outdir = dest if rel == "." else os.path.join(dest, rel)
        os.makedirs(outdir, exist_ok=True)
        for f in files:
            sp = os.path.join(dp, f)
            try:
                if os.path.getsize(sp) > limit:
                    skipped.append(sp)
                    continue
                shutil.copy2(sp, os.path.join(outdir, f))
            except OSError as e:
                log(f"  복사 실패 무시: {sp} ({e})")
    if skipped:
        log(f"⚠ {cfg['MAX_FILE_MB']}MB 초과로 건너뛴 파일 {len(skipped)}개 (GitHub 제한). "
            f"필요하면 Git LFS 사용을 권장합니다.")
        for s in skipped[:10]:
            log(f"    - {s}")


def commit_and_push(cfg, message=None):
    repo, branch = cfg["REPO_DIR"], cfg["BRANCH"]
    run(["git", "add", "-A"], cwd=repo)
    # 변경 없으면 종료
    status = run(["git", "status", "--porcelain"], cwd=repo, check=False).stdout.strip()
    if not status:
        log("변경 사항 없음 → 업로드 건너뜀")
        return False
    # 안전: 혹시 큰 파일이 스테이징됐는지 최종 확인
    big = check_big_files(repo, cfg["MAX_FILE_MB"])
    if big:
        log("⚠ 100MB 근처 대용량 파일 감지 — push가 거부될 수 있습니다:")
        for p, mb in big[:10]:
            log(f"    {mb:.1f}MB  {p}")
    msg = message or f"Auto-upload experiment data {datetime.now():%Y-%m-%d %H:%M:%S}"
    run(["git", "commit", "-m", msg], cwd=repo)
    # push (네트워크 오류 시 백오프 재시도)
    delay = 2
    for attempt in range(1, 5):
        r = run(["git", "push", "-u", "origin", branch], cwd=repo, check=False)
        if r.returncode == 0:
            log("✅ 업로드 완료")
            return True
        log(f"push 실패(시도 {attempt}/4). {delay}s 후 재시도...\n{r.stderr.strip()}")
        time.sleep(delay)
        delay *= 2
    raise RuntimeError("push 4회 실패 — 네트워크/인증 확인 필요")


def do_once(cfg, message=None):
    ensure_repo(cfg)
    sync_source_into_repo(cfg)
    return commit_and_push(cfg, message)


def do_watch(cfg):
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        raise SystemExit("watch 모드는 watchdog 필요: pip install watchdog")

    src = os.path.abspath(cfg["SOURCE_DIR"])
    if not os.path.isdir(src):
        raise SystemExit(f"SOURCE_DIR 가 올바르지 않습니다: {src!r}")

    ensure_repo(cfg)
    state = {"pending": False, "last": 0.0}

    class H(FileSystemEventHandler):
        def on_any_event(self, e):
            if e.is_directory:
                return
            state["pending"] = True
            state["last"] = time.time()

    obs = Observer()
    obs.schedule(H(), src, recursive=True)
    obs.start()
    log(f"👀 감시 시작: {src}  (변경 후 {cfg['DEBOUNCE_SEC']}s 안정되면 자동 업로드, Ctrl+C 종료)")
    try:
        while True:
            time.sleep(2)
            if state["pending"] and (time.time() - state["last"]) >= cfg["DEBOUNCE_SEC"]:
                state["pending"] = False
                try:
                    sync_source_into_repo(cfg)
                    commit_and_push(cfg)
                except Exception as ex:
                    log(f"업로드 중 오류(계속 감시): {ex}")
    except KeyboardInterrupt:
        log("종료합니다.")
    finally:
        obs.stop()
        obs.join()


def main():
    ap = argparse.ArgumentParser(description="로컬 실험 폴더를 GitHub로 자동 업로드")
    ap.add_argument("--source", help="업로드할 로컬 폴더 경로")
    ap.add_argument("--repo", help="로컬 저장소 경로 (없으면 자동 clone)")
    ap.add_argument("--branch", help="대상 브랜치")
    ap.add_argument("--subdir", help="저장소 내 하위 폴더")
    ap.add_argument("--message", "-m", help="커밋 메시지")
    ap.add_argument("--watch", action="store_true", help="폴더 감시 자동 업로드 모드")
    a = ap.parse_args()

    cfg = dict(CONFIG)
    if a.source:  cfg["SOURCE_DIR"] = a.source
    if a.repo:    cfg["REPO_DIR"] = a.repo
    if a.branch:  cfg["BRANCH"] = a.branch
    if a.subdir is not None: cfg["DEST_SUBDIR"] = a.subdir
    if os.environ.get("XRAY_SOURCE_DIR"):
        cfg["SOURCE_DIR"] = cfg["SOURCE_DIR"] or os.environ["XRAY_SOURCE_DIR"]

    if a.watch:
        do_watch(cfg)
    else:
        do_once(cfg, a.message)


if __name__ == "__main__":
    main()
