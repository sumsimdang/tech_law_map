"""기술보호법 인용 지도 주간 점검.

사용법: python3 run_update.py KIT_DIR WORK_DIR TODAY(YYYY-MM-DD)

KIT_DIR  : parse.py, versions.py, topics.py, build.py, template.html, diagA.json, diagB.json,
           state.json(지난 점검 상태), changelog.json(점검 기록)이 있는 폴더
WORK_DIR : 빈 작업 폴더 (법령 저장소를 여기에 받는다)

종료 코드
  0 : 새 페이지를 만들었음 → WORK_DIR/out/tech-law-map.html 을 같은 링크에 게시하면 됨
  2 : 근거 구절 검증이 멈춤 → 게시하지 말고 report.json 의 errors 를 사람이 확인
  1 : 그 밖의 오류 (저장소 접근 실패 등)
결과 요약은 WORK_DIR/out/report.json 과 표준 출력에 남긴다.
"""
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

KIT = Path(sys.argv[1]).resolve()
WORK = Path(sys.argv[2]).resolve()
TODAY = sys.argv[3]
OUT = WORK / "out"
OUT.mkdir(parents=True, exist_ok=True)
REPO = WORK / "src" / "lk"
PY = sys.executable


def run(cmd, cwd=None, check=True):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(map(str, cmd))}\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    return r


def law_dirs():
    src = (KIT / "parse.py").read_text(encoding="utf-8")
    src = src.replace("SRC = Path(sys.argv[1])", "SRC = None").replace("OUT = Path(sys.argv[2])", "OUT = None")
    ns = {}
    exec(compile(src.split("if __name__")[0], "parse", "exec"), ns)
    return ns["LAWS"]


report = {"date": TODAY, "status": "error", "changes": [], "errors": []}
try:
    laws = law_dirs()
    # 1. 법령 저장소 받기 (필요한 법률만, 18개월 이력 포함)
    if not REPO.exists():
        REPO.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "--filter=blob:none", "--sparse", "--depth", "1",
             "https://github.com/legalize-kr/legalize-kr", str(REPO)])
    run(["git", "-c", "core.quotepath=off", "sparse-checkout", "set", "--no-cone"] + [f"kr/{d}/" for d, *_ in laws], cwd=REPO)
    since = (dt.date.fromisoformat(TODAY) - dt.timedelta(days=540)).isoformat()
    run(["git", "fetch", "--quiet", "--filter=blob:none", f"--shallow-since={since}", "origin", "main"], cwd=REPO)
    run(["git", "checkout", "--quiet", "FETCH_HEAD"], cwd=REPO)
    snapshot = run(["git", "log", "-1", "--format=%cd", "--date=short"], cwd=REPO).stdout.strip()
    report["snapshot"] = snapshot

    # 2. 인용 파싱, 판본 비교
    run([PY, "-I", str(KIT / "parse.py"), str(REPO / "kr"), str(OUT / "graph.json")])
    vr = run([PY, "-I", str(KIT / "versions.py"), str(REPO), TODAY, str(OUT / "versions.json")])
    report["versions_log"] = vr.stdout.strip().splitlines()

    graph = json.loads((OUT / "graph.json").read_text(encoding="utf-8"))
    vers = json.loads((OUT / "versions.json").read_text(encoding="utf-8"))
    short = {l["key"]: l["short"] for l in graph["laws"]}
    cross = [e for e in graph["edges"] if not e["tl"].startswith("ext:") and e["tl"] != e["s"]]
    pairs = {}
    for e in cross:
        k = f'{e["s"]}>{e["tl"]}'
        pairs[k] = pairs.get(k, 0) + 1
    state = {
        "snapshot": snapshot,
        "laws": {l["key"]: {"promulgated": l["promulgated"], "effective": l["effective"]} for l in graph["laws"]},
        "pending": sorted(k for k, v in vers.items() if v.get("pending")),
        "edges": len(graph["edges"]),
        "cross": len(cross),
        "pairs": pairs,
    }

    # 3. 지난 점검과 비교
    prev_path = KIT / "state.json"
    prev = json.loads(prev_path.read_text(encoding="utf-8")) if prev_path.exists() else None
    changes = []
    if prev:
        for k, v in state["laws"].items():
            o = prev["laws"].get(k)
            if o and (o["promulgated"], o["effective"]) != (v["promulgated"], v["effective"]):
                changes.append(f"{short[k]} 새 판본: {o['promulgated']} 공포본 → {v['promulgated']} 공포본(시행 {v['effective']})")
        for k in sorted(set(prev.get("pending", [])) - set(state["pending"])):
            if k in short:
                changes.append(f"{short[k]} 개정이 시행돼 현행 문구가 됐어요")
        for k in sorted(set(state["pending"]) - set(prev.get("pending", []))):
            changes.append(f"{short[k]}에 시행 예정 개정이 새로 생겼어요")
        if prev["cross"] != state["cross"]:
            changes.append(f"법률 간 인용 {prev['cross']}건 → {state['cross']}건")
        moved = [k for k in set(prev["pairs"]) | set(pairs) if prev["pairs"].get(k, 0) != pairs.get(k, 0)]
        for k in sorted(moved)[:12]:
            a, b = k.split(">")
            changes.append(f"  {short[a]} → {short[b]}: {prev['pairs'].get(k, 0)}건 → {pairs.get(k, 0)}건")
    report["changes"] = changes

    # 4. 개념·유출 근거 구절 검증 (문구가 바뀌면 여기서 멈춘다)
    tr = run([PY, str(KIT / "topics.py"), str(OUT / "graph.json"), str(OUT / "versions.json"), str(OUT / "topics.json"), TODAY], check=False)
    report["topics_log"] = (tr.stdout + tr.stderr).strip().splitlines()[-40:]
    if tr.returncode != 0:
        report["status"] = "needs_review"
        report["errors"] = [l.strip() for l in report["topics_log"] if l.strip().startswith("-") or "Error" in l]
        (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=1))
        sys.exit(2)

    # 5. 점검 기록 갱신 후 페이지 빌드
    log_path = KIT / "changelog.json"
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else []
    real = [c for c in changes if not c.startswith("  ")]
    same = next((x for x in log if x.get("date") == TODAY), None)
    if same and not real:
        same["snapshot"] = snapshot  # 같은 날 다시 돌렸고 바뀐 게 없으면 그날 기록을 그대로 둔다
    else:
        log = [x for x in log if x.get("date") != TODAY]
        log.insert(0, {"date": TODAY, "snapshot": snapshot, "changes": real or ["바뀐 법령 없음"]})
    log = log[:30]
    (OUT / "changelog.json").write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    run([PY, "-I", str(KIT / "build.py"), str(OUT / "graph.json"), str(KIT / "template.html"), snapshot,
         str(OUT / "tech-law-map.html"), str(OUT / "topics.json"), str(OUT / "versions.json"), TODAY, str(OUT / "changelog.json")])

    # 6. 법률 간 인용표 CSV
    A = {k: {a["k"]: a for a in v} for k, v in graph["articles"].items()}
    lab = lambda k: "제" + k.split("-")[0] + "조" + ("의" + k.split("-")[1] if "-" in k else "")
    import csv
    with open(OUT / "cross_citations.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["인용하는 법률", "조문", "조문 제목", "항", "인용받는 법률", "인용받는 조문", "인용받는 조문 제목", "인용 표기"])
        for e in cross:
            sa = A[e["s"]][e["sa"]]
            ta = A[e["tl"]][e["ta"]] if e["ta"] else None
            w.writerow([short[e["s"]], lab(e["sa"]), sa["t"], "".join(e["ps"]), short[e["tl"]],
                        lab(e["ta"]) if e["ta"] else "법률 전체", ta["t"] if ta else "", ", ".join(e["lb"])])
    report["status"] = "built"
    report["changed"] = bool(changes) or not prev
except Exception as ex:  # noqa
    report["status"] = "error"
    report["errors"] = [str(ex)[-3000:]]
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    sys.exit(1)

(OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=1))
sys.exit(0)
