import json
import sys
from pathlib import Path

graph = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
graph["snapshot"] = sys.argv[3]
graph["checked"] = sys.argv[7] if len(sys.argv) > 7 else sys.argv[3]
graph["changelog"] = json.loads(Path(sys.argv[8]).read_text(encoding="utf-8")) if len(sys.argv) > 8 else []
tpl = Path(sys.argv[2]).read_text(encoding="utf-8")
payload = json.dumps(graph, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
def dump(x):
    return json.dumps(x, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


topics = json.loads(Path(sys.argv[5]).read_text(encoding="utf-8"))
vers = json.loads(Path(sys.argv[6]).read_text(encoding="utf-8"))
out = tpl.replace("__DATA__", payload, 1).replace("__TOPICS__", dump(topics), 1).replace("__VERS__", dump(vers), 1)
Path(sys.argv[4]).write_text(out, encoding="utf-8")
print("written", sys.argv[4], len(out.encode("utf-8")), "bytes")
