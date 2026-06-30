# auto_upload.py — 로컬 실험 폴더 → GitHub 자동 업로드

VS Code에서 실행하면, 지정한 로컬 폴더(X-ray 검사 결과 등)를 GitHub 저장소로
자동 commit + push 합니다. 압축해서 채팅에 올릴 필요 없이 폴더째 올라갑니다.

## 1. 최초 1회 준비
- git 설치 + GitHub 로그인 (VS Code로 GitHub 쓰고 있으면 보통 이미 됨)
- Python 3.8+ 설치
- (watch 모드 쓸 때만) 터미널에서: `pip install watchdog`

## 2. 설정
`auto_upload.py` 상단 `CONFIG` 에서 **SOURCE_DIR** 만 본인 폴더로 바꾸면 됩니다.
```python
"SOURCE_DIR": r"C:\Users\본인\Desktop\Xray_Results",   # 업로드할 폴더
```
나머지(REPO_URL, BRANCH)는 기본값 그대로 두면 됩니다.

## 3. 실행 (VS Code 터미널)
```bash
# (A) 지금 폴더 상태를 1회 업로드
python tools/auto_upload.py

# (B) 폴더를 직접 지정해서 1회 업로드
python tools/auto_upload.py --source "D:\Xray\TEST7"

# (C) 폴더를 계속 감시 → 새 결과가 생기면 자동 업로드
python tools/auto_upload.py --watch
```

## 동작 방식
1. 저장소가 로컬에 없으면 자동 `clone`, 있으면 해당 브랜치로 맞춤
2. SOURCE_DIR 내용을 저장소로 복사 (구조 그대로)
3. `git add` → `commit`(시각 자동기록) → `push` (실패 시 최대 4회 재시도)

## 주의
- **GitHub는 파일 1개 100MB 제한.** 이를 넘는 파일은 자동으로 건너뛰고 경고합니다.
  대용량(예: 270MP 웨이퍼 맵 원본)을 꼭 올려야 하면 Git LFS가 필요합니다 — 요청 주세요.
- 바이너리(이미지) 데이터가 누적되면 저장소 용량이 계속 커집니다. 양이 많아지면
  데이터 전용 브랜치/저장소 분리를 권장합니다.
- push 인증은 PC의 git 자격증명을 사용합니다(스크립트에 토큰을 넣지 마세요).
