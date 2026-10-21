"""각 법률의 '오늘 시행 중인 판본'을 git 이력에서 찾아, 현재 파일(최신 공포본)과 조문별로 비교한다.

출력: versions.json
  {law_key: {"inforce": {"commit", "promulgated", "effective"} | null,
             "pending": {"promulgated", "effective"} | null,
             "changed": {article_key: in_force_text or ""(시행 중 판본에 없던 조문)}}}
"""
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(sys.argv[1])
TODAY = sys.argv[2]  # YYYY-MM-DD
OUT = Path(sys.argv[3])

src = (Path(__file__).parent / "parse.py").read_text(encoding="utf-8")
src = src.replace("SRC = Path(sys.argv[1])", "SRC = None").replace("OUT = Path(sys.argv[2])", "OUT = None")
ns = {}
exec(compile(src.split("if __name__")[0], "parse", "exec"), ns)
split_articles, parse_meta, LAWS = ns["split_articles"], ns["parse_meta"], ns["LAWS"]


def git(*args):
    return subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=REPO, capture_output=True, text=True, check=True).stdout


result = {}
for d, key, short, group in LAWS:
    path = f"kr/{d}/법률.md"
    head_text = (REPO / path).read_text(encoding="utf-8")
    head_meta = parse_meta(head_text)
    entry = {"inforce": None, "pending": None, "changed": {}}
    if head_meta.get("시행일자", "") <= TODAY:
        result[key] = entry
        continue
    entry["pending"] = {"promulgated": head_meta.get("공포일자"), "effective": head_meta.get("시행일자")}
    commits = git("log", "HEAD", "--format=%H", "--", path).split()
    chosen = None
    for c in commits:
        try:
            txt = git("show", f"{c}:{path}")
        except subprocess.CalledProcessError:
            continue
        meta = parse_meta(txt)
        if meta.get("시행일자", "9999") <= TODAY:
            chosen = (c, txt, meta)
            break
    if not chosen:
        print(f"[{short}] 시행 중 판본을 이력에서 찾지 못함", file=sys.stderr)
        result[key] = entry
        continue
    c, txt, meta = chosen
    entry["inforce"] = {"commit": c[:10], "promulgated": meta.get("공포일자"), "effective": meta.get("시행일자")}
    old = {a["key"]: a for a in split_articles(txt)}
    new = {a["key"]: a for a in split_articles(head_text)}
    for k, a in new.items():
        o = old.get(k)
        if o is None:
            entry["changed"][k] = ""
        elif o["text"] != a["text"]:
            entry["changed"][k] = o["text"]
    result[key] = entry
    print(f"[{short}] 시행 중 {meta.get('공포일자')} 판(시행 {meta.get('시행일자')}) · 시행 예정 {head_meta.get('시행일자')} · 바뀌는 조문 {len(entry['changed'])}개: {sorted(entry['changed'])[:12]}")

OUT.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
