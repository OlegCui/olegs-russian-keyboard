# -*- coding: utf-8 -*-
import json
import sys
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
UA = {"User-Agent": "ru-ime-p0/0.1 (diag)"}


def api(p):
    p = dict(p, format="json")
    u = "https://ru.wikipedia.org/w/api.php?" + urllib.parse.urlencode(p)
    r = urllib.request.Request(u, headers=UA)
    return json.loads(urllib.request.urlopen(r, timeout=30).read().decode("utf-8"))


a = api({"action": "query", "list": "random", "rnlimit": 5, "rnnamespace": 0})
titles = [x["title"] for x in a["query"]["random"]]
print("A) list=random ->", len(titles), "titles")
print("   ", titles)

print("\nB) prop=extracts, exlimit=20, titles=5")
b = api({"action": "query", "titles": "|".join(titles),
         "prop": "extracts", "explaintext": 1, "exlimit": 20})
for pid, pg in b["query"]["pages"].items():
    print(f"   {pg.get('title')!r:40} extract_len={len(pg.get('extract',''))}")

print("\nC) prop=extracts, exlimit=max, titles=5")
c = api({"action": "query", "titles": "|".join(titles),
         "prop": "extracts", "explaintext": 1, "exlimit": "max"})
for pid, pg in c["query"]["pages"].items():
    print(f"   {pg.get('title')!r:40} extract_len={len(pg.get('extract',''))}")

print("\nD) generator=random + extracts, exlimit=max")
d = api({"action": "query", "generator": "random", "grnnamespace": 0, "grnlimit": 10,
         "prop": "extracts", "explaintext": 1, "exlimit": "max"})
pages = d.get("query", {}).get("pages", {})
print(f"   pages={len(pages)}")
ok = sum(1 for p in pages.values() if len(p.get("extract", "")) > 200)
print(f"   with extract>200: {ok}")

print("\nE) revisions wikitext, titles=5")
e = api({"action": "query", "titles": "|".join(titles),
         "prop": "revisions", "rvprop": "content", "rvslots": "main", "rvlimit": 1})
tot = 0
for pid, pg in e["query"]["pages"].items():
    revs = pg.get("revisions", [])
    if revs:
        txt = revs[0].get("slots", {}).get("main", {}).get("*", "")
        tot += len(txt)
        print(f"   {pg.get('title')!r:40} wikitext_len={len(txt)}")
print(f"   total wikitext chars: {tot}")
