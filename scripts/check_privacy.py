#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
隱私靜態檢查：作答紀錄只能留在使用者手機，App 程式裡不准出現任何能把資料送出去的寫法
------------------------------------------------------------------------------------------
三層保證的第二層（第一層是 index.html 的 CSP；第三層是瀏覽器實測網路請求，部署前跑）。

規則：
    P1 js/、sw.js 裡不得出現：非 GET 的 fetch（method: POST/PUT/PATCH/DELETE）、sendBeacon、WebSocket、
       XMLHttpRequest、EventSource、外部網址字串（http:// 或 https://）
    P2 index.html 必須有 CSP，default-src 與 connect-src 都只能是 'self'
    P3 index.html 必須有 <meta name="robots" content="noindex…">
    P4 index.html 不得載入外部資源（src／href 是 http(s)://）

用法：
    python scripts/check_privacy.py             # 檢查工作區
    python scripts/check_privacy.py --staged    # 檢查暫存區（pre-commit 用；沒有相關檔就略過）
    python scripts/check_privacy.py --selftest  # 假樣本證明每條規則都會紅
結束碼：0 通過；1 擋下；2 程式出錯。
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]

JS_RULES = [
    ("P1", re.compile(r"method\s*:\s*['\"](POST|PUT|PATCH|DELETE)['\"]", re.I), "非 GET 的請求"),
    ("P1", re.compile(r"sendBeacon"), "sendBeacon"),
    ("P1", re.compile(r"\bWebSocket\b"), "WebSocket"),
    ("P1", re.compile(r"\bXMLHttpRequest\b"), "XMLHttpRequest"),
    ("P1", re.compile(r"\bEventSource\b"), "EventSource"),
    ("P1", re.compile(r"https?://"), "外部網址"),
]


def app_files(root: Path):
    files = [root / "index.html", root / "sw.js"] + sorted((root / "js").glob("**/*.js"))
    return [f for f in files if f.exists()]


def check_js(rel, text):
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        # 只把「行首或空白後面的 //」當註解；https:// 的 // 前面是冒號，不能被當成註解吃掉
        code = re.sub(r"(^|\s)//.*$", r"\1", line)
        for rule, pat, why in JS_RULES:
            if pat.search(code):
                out.append((rule, f"{rel}:{i}", why))
    return out


def check_html(rel, text):
    out = []
    # content 的值用哪種引號包，就讀到同一種引號為止（CSP 內容本身含 'self' 的單引號）
    m = re.search(r'<meta[^>]+http-equiv=["\']Content-Security-Policy["\'][^>]+content=(["\'])(.*?)\1', text, re.I | re.S)
    if not m:
        out.append(("P2", rel, "沒有 CSP"))
    else:
        csp = {d.split()[0]: d.split()[1:] for d in (x.strip() for x in m.group(2).split(";")) if d}
        for directive in ("default-src", "connect-src"):
            if csp.get(directive) != ["'self'"]:
                out.append(("P2", rel, f"CSP 的 {directive} 必須只有 'self'（現在是 {csp.get(directive)}）"))
    if not re.search(r'<meta[^>]+name=["\']robots["\'][^>]+content=["\'][^"\']*noindex', text, re.I):
        out.append(("P3", rel, "沒有 robots noindex"))
    for mm in re.finditer(r'(?:src|href)\s*=\s*["\'](https?://[^"\']+)', text, re.I):
        out.append(("P4", rel, f"載入外部資源 {mm.group(1)}"))
    return out


def check_texts(items):
    """items：[(相對路徑, 內容)]"""
    probs = []
    for rel, text in items:
        if rel.endswith(".html"):
            probs += check_html(rel, text)
        else:
            probs += check_js(rel, text)
    return probs


def report(scope, probs):
    if not probs:
        print(f"PRIVACY OK（{scope}）")
        return 0
    print(f"PRIVACY BLOCKED（{scope}）：{len(probs)} 項")
    for rule, where, why in probs:
        print(f"  {rule} {where}：{why}")
    return 1


def staged_items():
    out = subprocess.run(["git", "diff", "--cached", "--name-only", "-z", "--diff-filter=ACMRT"], cwd=ROOT, capture_output=True, check=True)
    names = [n for n in out.stdout.decode("utf-8").split("\0") if n]
    rel_ok = lambda n: n == "index.html" or n == "sw.js" or (n.startswith("js/") and n.endswith(".js"))
    items = []
    for n in filter(rel_ok, names):
        items.append((n, subprocess.run(["git", "show", f":{n}"], cwd=ROOT, capture_output=True, check=True).stdout.decode("utf-8")))
    return items


def selftest():
    good_html = (ROOT / "index.html").read_text(encoding="utf-8")
    ext = "https" + "://example.invalid/x"          # 執行時才組字，這支檔自己不能含外部網址
    cases = [
        ("乾淨的 js", "js/a.js", "fetch('data/manifest.json').then(r => r.json());\n", set()),
        ("註解裡提到 http 不算", "js/a.js", "// 參考 " + ext + "\nconst a = 1;\n", set()),
        ("POST", "js/a.js", "fetch('data/x', { method: 'POST', body });\n", {"P1"}),
        ("sendBeacon", "js/a.js", "navigator.sendBeacon('data/x', d);\n", {"P1"}),
        ("WebSocket", "sw.js", "const s = new WebSocket(u);\n", {"P1"}),
        ("XMLHttpRequest", "js/a.js", "const x = new XMLHttpRequest();\n", {"P1"}),
        ("外部網址", "js/a.js", f"fetch('{ext}');\n", {"P1"}),
        ("合格的 index.html", "index.html", good_html, set()),
        ("CSP 的 connect-src 放寬", "index.html", good_html.replace("connect-src 'self'", "connect-src 'self' " + ext), {"P2"}),
        ("拿掉 CSP", "index.html", re.sub(r'<meta http-equiv="Content-Security-Policy"[^>]+>', "", good_html), {"P2"}),
        ("拿掉 noindex", "index.html", re.sub(r'<meta name="robots"[^>]+>', "", good_html), {"P3"}),
        ("載入外部腳本", "index.html", good_html.replace("</head>", f'<script src="{ext}"></script></head>'), {"P4"}),
    ]
    fails = 0
    for desc, rel, text, expect in cases:
        got = {r for r, _w, _y in check_texts([(rel, text)])}
        ok = got == expect
        print(f"{'✓' if ok else '✗'} {desc}：預期 {sorted(expect) or '通過'}，實際 {sorted(got) or '通過'}")
        fails += 0 if ok else 1
    if fails:
        print(f"PRIVACY SELFTEST FAILED：{fails} 項不符")
        return 1
    print(f"PRIVACY SELFTEST OK：{len(cases)} 項全部符合")
    return 0


def main(argv):
    try:
        if "--selftest" in argv:
            return selftest()
        if "--staged" in argv:
            items = staged_items()
            if not items:
                print("PRIVACY OK（暫存區沒有 App 程式檔，略過）")
                return 0
            return report(f"暫存區：{len(items)} 個檔", check_texts(items))
        files = app_files(ROOT)
        return report(f"工作區：{len(files)} 個檔", check_texts([(f.relative_to(ROOT).as_posix(), f.read_text(encoding="utf-8")) for f in files]))
    except Exception as e:
        print(f"PRIVACY ERROR：{type(e).__name__}: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
