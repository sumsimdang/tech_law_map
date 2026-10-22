"""기술보호 관련 법률의 조문 간 인용 관계를 추출한다.

입력: legalize-kr 저장소의 kr/{법령명}/법률.md, 시행령.md (국가법령정보센터 원문)
출력: graph.json (법률, 시행령, 조문, 인용 엣지, 외부 법령)

시행령은 법률 키에 "_d"를 붙인 키(예: itp_d)로 다룬다. 시행령 본문의 "법 제N조"는 모법 조문,
"이 영"과 번호만 쓴 "제N조"는 같은 시행령 조문, 「X 시행령」·"같은 법 시행령"은 X의 시행령으로 푼다.
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

SRC = Path(sys.argv[1])
OUT = Path(sys.argv[2])

# (디렉토리, 키, 약칭, 분류)
LAWS = [
    ("산업기술의유출방지및보호에관한법률", "itp", "산업기술보호법", "core"),
    ("국가첨단전략산업경쟁력강화및보호에관한특별조치법", "nst", "국가첨단전략산업법", "core"),
    ("방위산업기술보호법", "dtp", "방산기술보호법", "core"),
    ("부정경쟁방지및영업비밀보호에관한법률", "ucp", "부정경쟁방지법", "core"),
    ("중소기업기술보호지원에관한법률", "smt", "중소기업기술보호법", "core"),
    ("대ㆍ중소기업상생협력촉진에관한법률", "wcp", "상생협력법", "trade"),
    ("하도급거래공정화에관한법률", "sub", "하도급법", "trade"),
    ("대외무역법", "fta", "대외무역법", "export"),
    ("외국인투자촉진법", "fdi", "외국인투자법", "export"),
    ("국가연구개발혁신법", "rnd", "국가연구개발혁신법", "rnd"),
    ("산업기술혁신촉진법", "iti", "산업기술혁신법", "rnd"),
    ("기술의이전및사업화촉진에관한법률", "ttc", "기술이전법", "rnd"),
    ("반도체산업경쟁력강화및지원에관한특별법", "semi", "반도체특별법", "rnd"),
    ("발명진흥법", "inv", "발명진흥법", "ip"),
    ("특허법", "pat", "특허법", "ip"),
    ("방위사업법", "dap", "방위사업법", "security"),
    ("국가정보원법", "nis", "국가정보원법", "security"),
]

DEC_SUFFIX = "_d"


def circ(n: int) -> str:
    if 1 <= n <= 20:
        return chr(0x2460 + n - 1)
    if 21 <= n <= 35:
        return chr(0x3251 + n - 21)
    if 36 <= n <= 50:
        return chr(0x32B1 + n - 36)
    return f"({n})"


CIRCLED = "".join(circ(i) for i in range(1, 51))


def norm_name(s: str) -> str:
    s = re.sub(r"\s+", "", s)
    return s.replace("·", "ㆍ").replace("・", "ㆍ").replace("•", "ㆍ")


def art_key(a: str, b: str | None) -> str:
    return f"{int(a)}" + (f"-{int(b)}" if b else "")


def art_label(key: str) -> str:
    a, _, b = key.partition("-")
    return f"제{a}조" + (f"의{b}" if b else "")


def parse_meta(text: str) -> dict:
    fm = text.split("---", 2)[1]
    meta = {}
    for line in fm.splitlines():
        m = re.match(r"^(\S+):\s*(.*)$", line)
        if m:
            meta[m.group(1)] = m.group(2).strip().strip("'")
    dept = re.findall(r"^- (.+)$", fm, re.M)
    meta["소관부처"] = dept
    return meta


def clean_display(body: str) -> str:
    """마크다운 표기를 걷어내 화면에 보일 본문으로 만든다."""
    t = body.replace("\\.", ".")
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    t = re.sub(r"<(\d{1,2})>\s*<\1>", lambda m: circ(int(m.group(1))), t)  # ⑯ 이상 항 번호
    lines = [ln.rstrip() for ln in t.splitlines()]
    out = []
    for ln in lines:
        if ln.strip() == "":
            continue
        out.append(ln)
    return "\n".join(out)


ANNOT = re.compile(r"<(?:[^<>]*\d{4}\.\d{1,2}\.\d{1,2}[^<>]*|단서 생략|생략)>")


def mask_annotations(t: str) -> str:
    """개정 이력 <개정 2020.1.1> 등을 같은 길이의 공백으로 가려 오프셋을 유지한다."""
    return ANNOT.sub(lambda m: " " * len(m.group(0)), t)


def split_articles(text: str):
    body = text.split("---", 2)[2]
    body = re.split(r"^## 부칙", body, flags=re.M)[0]
    chapter = ""
    section = ""
    arts = []
    cur = None
    for line in body.splitlines():
        if line.startswith("##### "):
            if cur:
                arts.append(cur)
            m = re.match(r"^##### 제(\d+)조(?:의(\d+))?\s*(?:\((.*)\))?\s*$", line)
            if not m:
                raise ValueError(f"heading parse fail: {line}")
            cur = {
                "key": art_key(m.group(1), m.group(2)),
                "title": (m.group(3) or "").strip(),
                "chapter": chapter,
                "section": section,
                "lines": [],
            }
        elif line.startswith("### "):
            section = line[4:].strip()
        elif line.startswith("## "):
            chapter = line[3:].strip()
            section = ""
        elif line.startswith("# "):
            continue
        elif cur is not None:
            cur["lines"].append(line)
    if cur:
        arts.append(cur)
    for a in arts:
        a["text"] = clean_display("\n".join(a.pop("lines")))
        a["deleted"] = (not a["title"]) and a["text"].startswith("삭제")
    return arts


TOKEN = re.compile(
    r"「(?P<law>[^」]{2,90})」"
    r"|(?P<same>같은\s?법)(?P<samedec>\s?시행령|\s?시행규칙)?(?!률)"
    r"|(?P<samedeconly>같은\s?영)(?=\s?제\d)"
    r"|(?P<sameother>같은\s?(?:조약|협약|협정|규칙|규정))(?=\s?제\d)"
    r"|(?P<this>이\s?법)(?=[\s에의을과이은도])"
    r"|(?P<thisdec>이\s?영)(?=[\s에의을과이은도])"
    r"|(?P<parent>(?<![가-힣」\w])법)(?=\s?제\d)"
    r"|(?P<art>제(?P<a>\d+)조(?:의(?P<b>\d+))?(?P<sub>(?:제\d+항)?(?:제\d+호)?(?:[가-힣]목)?))"
)
def is_connector(gap: str) -> bool:
    """두 조문 사이 텍스트가 목록 연결어만으로 이뤄졌는지 판단한다.
    예: ' 및 ', '까지의 규정, ', '(제1항은 제외한다) 및 ', '부터 제4항까지 및 '"""
    g = re.sub(r"\([^()]*\)", "", gap)
    g = re.sub(r"제\d+(?:항|호)|[가-힣]목", "", g)
    g = re.sub(r"까지의\s?각\s?규정|까지의\s?규정|의\s?규정|까지|부터|및|또는|ㆍ|·|,|이나|내지|각각|와|과", "", g)
    return g.strip() == ""


ALIAS_GAP = re.compile(r'^\s*\(이하\s*"[^"]{1,30}"\s*(?:이?라|으로)\s*한다\)\s*$')


def tight(gap) -> bool:
    """「법률명」과 조문 번호 사이가 비었거나 약칭 정의만 끼어 있는지."""
    return gap is not None and (gap.strip() == "" or bool(ALIAS_GAP.match(gap)))


QUOTED = re.compile(r'"[^"\n]{0,300}"|“[^”\n]{0,300}”')


def mask_quotes(t: str) -> str:
    """'"제124조부터 제127조까지의 규정"은 …로 본다'처럼 따옴표 안의 조문 번호는
    다른 법률의 문구를 옮긴 것이므로 인용 추출에서 제외한다."""
    return QUOTED.sub(lambda m: (" " * len(m.group(0))) if "조" in m.group(0) else m.group(0), t)


def para_of(text: str, pos: int) -> str | None:
    """pos 위치가 속한 항 번호(①…)를 찾는다."""
    seg = text[:pos]
    best = None
    for m in re.finditer(r"(?m)^\s*([" + CIRCLED + r"])", seg):
        best = m.group(1)
    return best


def main():
    laws = []
    decrees = []
    name_to_key = {}
    articles = {}  # law key -> list of article dicts
    order = {}  # law key -> {art key: index}

    for d, key, short, group in LAWS:
        raw = (SRC / d / "법률.md").read_text(encoding="utf-8")
        meta = parse_meta(raw)
        arts = split_articles(raw)
        articles[key] = arts
        order[key] = {a["key"]: i for i, a in enumerate(arts)}
        name_to_key[norm_name(meta["제목"])] = key
        laws.append(
            {
                "key": key,
                "name": meta["제목"],
                "short": short,
                "group": group,
                "promulgated": meta.get("공포일자"),
                "effective": meta.get("시행일자"),
                "number": meta.get("공포번호"),
                "dept": meta.get("소관부처", []),
                "url": "https://www.law.go.kr/법령/" + d,
            }
        )
        dec_path = SRC / d / "시행령.md"
        if dec_path.exists():
            draw = dec_path.read_text(encoding="utf-8")
            dmeta = parse_meta(draw)
            dkey = key + DEC_SUFFIX
            darts = split_articles(draw)
            articles[dkey] = darts
            order[dkey] = {a["key"]: i for i, a in enumerate(darts)}
            name_to_key[norm_name(dmeta["제목"])] = dkey
            decrees.append(
                {
                    "key": dkey,
                    "parent": key,
                    "name": dmeta["제목"],
                    "short": short + " 시행령",
                    "group": group,
                    "promulgated": dmeta.get("공포일자"),
                    "effective": dmeta.get("시행일자"),
                    "number": dmeta.get("공포번호"),
                    "dept": dmeta.get("소관부처", []),
                    "url": "https://www.law.go.kr/법령/" + d + "시행령",
                }
            )

    edges = []
    external = Counter()
    external_display = {}
    unresolved = []
    decree_refs = Counter()

    def resolve_target(law_key, ext_name, a_key):
        """반환: (target_law, target_art or None, resolved_bool)"""
        if law_key is not None:
            if a_key is None:
                return law_key, None, True
            if a_key in order[law_key]:
                return law_key, a_key, True
            return law_key, a_key, False
        return ("ext:" + ext_name), a_key, True

    parent_of = {dd["key"]: dd["parent"] for dd in decrees}
    for src_law in [l["key"] for l in laws] + [dd["key"] for dd in decrees]:
        is_dec = src_law in parent_of
        for art in articles[src_law]:
            if art["deleted"]:
                continue
            text = art["text"]
            masked = mask_quotes(mask_annotations(text))
            last_law_ctx = None  # 마지막으로 언급된 「법률」 (같은 법 해석용): ("core", key) / ("ext", name) / ("decree", ...)
            prev = None  # 직전 토큰 정보 dict(kind, end, ctx)
            for m in TOKEN.finditer(masked):
                kind = m.lastgroup if m.group("art") is None else "art"
                if m.group("law"):
                    kind = "law"
                elif m.group("same"):
                    kind = "same"
                elif m.group("this"):
                    kind = "this"
                elif m.group("thisdec"):
                    kind = "thisdec"
                elif m.group("parent"):
                    kind = "parent"
                elif m.group("samedeconly"):
                    kind = "samedeconly"
                elif m.group("sameother"):
                    kind = "sameother"
                gap = masked[prev["end"]:m.start()] if prev else None

                # 직전 법률 단위 인용이 조문 없이 끝났다면 법률 전체 인용으로 기록
                if prev and prev["kind"] in ("law", "same") and not (kind == "art" and tight(gap)):
                    ctx = prev["ctx"]
                    if ctx and ctx[0] in ("core", "ext"):
                        tl, ta, ok = resolve_target(ctx[1] if ctx[0] == "core" else None, ctx[1], None)
                        if not (tl == src_law):
                            edges.append(
                                dict(s=src_law, sa=art["key"], tl=tl, ta=None, lbl="", span=[prev["start"], prev["end"]], p=para_of(text, prev["start"]))
                            )

                if kind == "law":
                    raw_name = m.group("law").strip()
                    nm = norm_name(raw_name)
                    dec = re.search(r"(시행령|시행규칙)$", nm)
                    if nm in name_to_key:
                        ctx = ("core", name_to_key[nm])
                    elif dec:
                        parent = nm[: dec.start()]
                        ctx = ("decree", parent, dec.group(1), raw_name)
                        decree_refs[raw_name] += 1
                    else:
                        ctx = ("ext", nm)
                        external_display.setdefault(nm, raw_name)
                    last_law_ctx = ctx
                    prev = dict(kind="law", start=m.start(), end=m.end(), ctx=ctx)
                    continue
                if kind == "same":
                    if m.group("samedec"):
                        sd = m.group("samedec").strip()
                        base = last_law_ctx[1] if last_law_ctx and last_law_ctx[0] == "core" else None
                        if sd == "시행령" and base and (base + DEC_SUFFIX) in order:
                            ctx = ("core", base + DEC_SUFFIX)
                        else:
                            ctx = ("decree",) if last_law_ctx is None else ("decree", last_law_ctx[1], sd, "")
                    else:
                        ctx = last_law_ctx
                    prev = dict(kind="same", start=m.start(), end=m.end(), ctx=ctx)
                    continue
                if kind == "this":
                    prev = dict(kind="this", start=m.start(), end=m.end(), ctx=("core", parent_of.get(src_law, src_law)))
                    continue
                if kind == "thisdec":
                    prev = dict(kind="this", start=m.start(), end=m.end(), ctx=("core", src_law))
                    continue
                if kind == "parent":
                    # 시행령 본문의 "법 제N조" = 모법. 법률 본문에는 쓰이지 않는다.
                    prev = dict(kind="this", start=m.start(), end=m.end(), ctx=("core", parent_of[src_law])) if is_dec else None
                    continue
                if kind == "sameother":
                    ctx = last_law_ctx if last_law_ctx and last_law_ctx[0] == "ext" else ("skip",)
                    prev = dict(kind="same", start=m.start(), end=m.end(), ctx=ctx)
                    continue
                if kind == "samedeconly":
                    ctx = last_law_ctx if last_law_ctx and last_law_ctx[0] == "core" and last_law_ctx[1] in parent_of else None
                    prev = dict(kind="same", start=m.start(), end=m.end(), ctx=ctx) if ctx else None
                    continue

                # 조문 토큰
                a_key = art_key(m.group("a"), m.group("b"))
                ctx = ("core", src_law)
                rng_from = None
                span_start = m.start()
                if prev and prev["kind"] in ("law", "same", "this") and tight(gap):
                    ctx = prev["ctx"] or ("core", src_law)
                    span_start = prev["start"]  # 「법률명」 제N조 전체를 한 덩어리로 표시
                elif prev and prev["kind"] == "art" and is_connector(gap):
                    ctx = prev["ctx"]
                    if gap.strip() == "부터" and masked[m.end():m.end() + 3].lstrip().startswith("까지"):
                        rng_from = prev["akey"]

                if ctx[0] in ("decree", "skip"):
                    decree_refs[(ctx[3] or ctx[1] + ctx[2]) if len(ctx) > 3 else "?"] += 0
                    prev = dict(kind="art", start=m.start(), end=m.end(), ctx=ctx, akey=a_key)
                    continue

                label = m.group("art")
                if rng_from and ctx[0] == "ext":
                    label = f"{art_label(rng_from)}~{label}"
                targets = [a_key]
                if rng_from and ctx[0] == "core":
                    ordm = order[ctx[1]]
                    if rng_from in ordm and a_key in ordm:
                        i0, i1 = ordm[rng_from], ordm[a_key]
                        targets = [articles[ctx[1]][i]["key"] for i in range(i0 + 1, i1 + 1)]
                for tk in targets:
                    if ctx[0] == "core":
                        tl, ta, ok = resolve_target(ctx[1], None, tk)
                    else:
                        tl, ta, ok = resolve_target(None, ctx[1], tk)
                        external[ctx[1]] += 1
                    if tl == src_law and ta == art["key"]:
                        continue  # 같은 조문 안의 자기 참조
                    e = dict(s=src_law, sa=art["key"], tl=tl, ta=ta, lbl=label if tk == a_key else f"{art_label(rng_from)}~{label} 범위", span=[span_start, m.end()], p=para_of(text, m.start()))
                    if not ok:
                        e["unresolved"] = True
                        unresolved.append((src_law, art["key"], tl, ta, label))
                    edges.append(e)
                prev = dict(kind="art", start=m.start(), end=m.end(), ctx=ctx, akey=a_key)

            # 문장 끝에 남은 법률 단위 인용
            if prev and prev["kind"] in ("law", "same"):
                ctx = prev["ctx"]
                if ctx and ctx[0] in ("core", "ext"):
                    tl, ta, ok = resolve_target(ctx[1] if ctx[0] == "core" else None, ctx[1], None)
                    if tl != src_law:
                        edges.append(dict(s=src_law, sa=art["key"], tl=tl, ta=None, lbl="", span=[prev["start"], prev["end"]], p=para_of(text, prev["start"])))

    # 법률 단위 외부 인용 집계
    for e in edges:
        if e["tl"].startswith("ext:") and e["ta"] is None:
            external[e["tl"][4:]] += 1

    # 중복 엣지 정리 (같은 조문→같은 대상, 여러 번 인용) : span 목록으로 합침
    merged = {}
    for e in edges:
        k = (e["s"], e["sa"], e["tl"], e["ta"])
        if k not in merged:
            merged[k] = dict(e, spans=[e["span"]], lbls=[e["lbl"]] if e["lbl"] else [], ps=[e["p"]] if e["p"] else [])
        else:
            mm = merged[k]
            mm["spans"].append(e["span"])
            if e["lbl"] and e["lbl"] not in mm["lbls"]:
                mm["lbls"].append(e["lbl"])
            if e["p"] and e["p"] not in mm["ps"]:
                mm["ps"].append(e["p"])
            if e.get("unresolved"):
                mm["unresolved"] = True
    edges_out = []
    for e in merged.values():
        out = {"s": e["s"], "sa": e["sa"], "tl": e["tl"], "ta": e["ta"], "lb": e["lbls"], "sp": e["spans"], "ps": e["ps"]}
        if e.get("unresolved"):
            out["u"] = 1
        edges_out.append(out)

    ext_list = [
        {"key": "ext:" + k, "name": external_display.get(k, k), "count": c}
        for k, c in external.most_common()
    ]

    data = {
        "laws": laws,
        "decrees": decrees,
        "articles": {
            k: [
                {"k": a["key"], "t": a["title"], "c": a["chapter"], "s": a["section"], "x": a["text"], "d": 1 if a["deleted"] else 0}
                for a in v
            ]
            for k, v in articles.items()
        },
        "edges": edges_out,
        "external": ext_list,
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # 리포트
    n_art = sum(len(v) for v in articles.values())
    fam = lambda k: parent_of.get(k, k)
    cross = [e for e in edges_out if not e["tl"].startswith("ext:") and fam(e["tl"]) != fam(e["s"])]
    deleg = [e for e in edges_out if not e["tl"].startswith("ext:") and fam(e["tl"]) == fam(e["s"]) and e["tl"] != e["s"]]
    intra = [e for e in edges_out if e["tl"] == e["s"]]
    print(f"decrees={len(decrees)} decree_articles={sum(len(articles[dd['key']]) for dd in decrees)} deleg={len(deleg)} cross_from_decree={sum(1 for e in cross if e['s'] in parent_of or e['tl'] in parent_of)}")
    ext_e = [e for e in edges_out if e["tl"].startswith("ext:")]
    print(f"laws={len(laws)} articles={n_art} edges={len(edges_out)} intra={len(intra)} cross={len(cross)} external_edges={len(ext_e)} external_laws={len(ext_list)}")
    print(f"unresolved={len(unresolved)}")
    for u in unresolved[:40]:
        print("  UNRESOLVED", u)
    print("decree refs:", decree_refs.most_common(10))
    pair = Counter((fam(e["s"]), fam(e["tl"])) for e in cross)
    print("cross-law pairs:")
    for (a, b), c in pair.most_common():
        print(f"  {a} -> {b}: {c}")
    print("top external:", [(x["name"], x["count"]) for x in ext_list[:25]])
    print("size bytes:", OUT.stat().st_size)


if __name__ == "__main__":
    main()
