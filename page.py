"""빌드된 페이지(본문 조각)에 문서 뼈대와 링크 미리보기 태그를 붙여 공개용 index.html 을 만든다.

사용법: python3 page.py BUILT.html OUT_index.html [BASE_URL]

BASE_URL 은 공개 주소(예: https://아이디.github.io/tech-law-map/).
주면 카카오톡·메신저 링크 미리보기에 쓰는 og:url, og:image 를 넣는다.
"""
import html
import sys
from pathlib import Path

src = Path(sys.argv[1]).read_text(encoding="utf-8")
out = Path(sys.argv[2])
base = sys.argv[3].strip() if len(sys.argv) > 3 else ""
if base and not base.endswith("/"):
    base += "/"

if src.lstrip().lower().startswith("<!doctype"):
    sys.exit("이미 완성된 문서예요. build.py 결과(본문 조각)를 넣어 주세요.")

# 첫 번째 스타일 블록까지가 머리말, 그 뒤가 본문
marker = "\n</style>\n"
cut = src.index(marker) + len(marker)
head, body = src[:cut], src[cut:]
head = head.replace('<meta name="claude:viewport-fit-sides" content="cover">\n', "")

TITLE = "기술보호법 인용 지도"
DESC = ("산업기술보호법·부정경쟁방지법 등 기술보호 17개 법률과 시행령의 조문 인용 관계, "
        "유출의 정의와 형량, 기술 개념의 포함관계를 원문과 함께 봅니다. 매주 최신 법령으로 갱신.")
ICON = ("data:image/svg+xml,"
        "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E"
        "%3Crect width='64' height='64' rx='14' fill='%2322417c'/%3E"
        "%3Ccircle cx='32' cy='32' r='9' fill='%23f9e27a'/%3E"
        "%3Ccircle cx='32' cy='32' r='20' fill='none' stroke='%23fff' stroke-width='3' opacity='.85'/%3E"
        "%3Ccircle cx='50' cy='22' r='4.5' fill='%23fff'/%3E%3Ccircle cx='16' cy='42' r='4.5' fill='%23fff'/%3E"
        "%3C/svg%3E")

meta = [
    '<meta property="og:type" content="website">',
    '<meta property="og:locale" content="ko_KR">',
    f'<meta property="og:title" content="{html.escape(TITLE)}">',
    f'<meta property="og:description" content="{html.escape(DESC)}">',
    f'<link rel="icon" href="{ICON}">',
]
if base:
    meta += [
        f'<meta property="og:url" content="{html.escape(base)}">',
        f'<meta property="og:image" content="{html.escape(base)}og.png">',
        '<meta property="og:image:width" content="1200">',
        '<meta property="og:image:height" content="630">',
        '<meta name="twitter:card" content="summary_large_image">',
    ]

doc = (
    "<!doctype html>\n<html lang=\"ko\">\n<head>\n<meta charset=\"utf-8\">\n"
    "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n"
    "<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}"
    "body{margin:0;font:14px system-ui,sans-serif}img{max-width:100%}[hidden]{display:none!important}</style>\n"
    + "\n".join(meta) + "\n"
    + head
    + "</head>\n<body>\n"
    + body
    + "\n</body>\n</html>\n"
)
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(doc, encoding="utf-8")
print("written", out, len(doc.encode("utf-8")), "bytes")
