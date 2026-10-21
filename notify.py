"""주간 점검이 멈췄을 때 Issues에 올릴 글을 만든다.

사용법: python3 notify.py REPORT_JSON STATUS TODAY RUN_URL OUT_MD
"""
import json
import sys
from pathlib import Path

report_path, status, today, run_url, out = sys.argv[1:6]
p = Path(report_path)
r = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

lines = [f"**{today} 주간 점검이 멈췄어요.** 공개 페이지는 지난 판 그대로예요.", ""]
if status == "needs_review":
    lines += [
        "개념·유출 비교에 쓴 조문 문구가 원문과 맞지 않아요. 보통 개정이 시행돼 문구가 바뀐 경우예요.",
        "아래 목록을 보고 `topics.py`의 해당 구절을 새 문구에 맞게 고치면 다음 점검부터 다시 게시돼요.",
        "",
    ]
else:
    lines += ["법령 저장소 접근 실패 같은 오류예요. 다음 주에 저절로 풀리기도 해요.", ""]

errs = r.get("errors") or ["(자세한 내용은 실행 기록을 보세요)"]
lines += ["### 맞지 않는 항목", "```", *errs[:40], "```"]
if r.get("changes"):
    lines += ["", "### 지난 점검 이후 바뀐 법령", *[f"- {c.strip()}" for c in r["changes"][:20]]]
lines += ["", f"실행 기록: {run_url}"]
Path(out).write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))
