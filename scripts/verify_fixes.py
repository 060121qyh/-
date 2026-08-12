"""
验证脚本：测试 TA-001 修复后的所有5条验收标准
针对: BLK-001, BLK-002, BLK-003, T-005, T-006, T-010, T-012
"""
import json
import urllib.request
import urllib.error

BASE = "http://localhost:8899"
passed = 0
failed = 0

def test(name, method, path, body=None, checks=None):
    global passed, failed
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            status = resp.status
    except urllib.error.HTTPError as e:
        result = json.loads(e.read())
        status = e.code

    ok = True
    msgs = []
    for label, fn in (checks or []):
        r = fn(status, result)
        if not r:
            ok = False
            msgs.append(f"  FAIL: {label}")
    if ok:
        passed += 1
        print(f"PASS {name}")
    else:
        failed += 1
        print(f"FAIL {name} (HTTP {status})")
        for m in msgs:
            print(m)
    return result

# ── AC1: /api/knowledge/card?path=时政热点/xxx.md → 200 ──
test("AC1: knowledge/card path resolution",
     "GET",
     "/api/knowledge/card?path=%E6%97%B6%E6%94%BF%E7%83%AD%E7%82%B9/2025%E5%B9%B4%E5%9B%BD%E5%8A%A1%E9%99%A2%E6%94%BF%E5%BA%9C%E5%B7%A5%E4%BD%9C%E6%8A%A5%E5%91%8A%EF%BC%88%E6%9D%8E%E5%BC%BA%E6%80%BB%E7%90%86%C2%B7%E5%8D%81%E5%9B%9B%E5%B1%8A%E5%85%A8%E5%9B%BD%E4%BA%BA%E5%A4%A7%E4%B8%89%E6%AC%A1%E4%BC%9A%E8%AE%AE%EF%BC%89%E6%A0%B8%E5%BF%83%E8%80%83%E7%82%B9.md",
     checks=[
         ("HTTP 200", lambda s, r: s == 200),
         ("has content", lambda s, r: bool(r.get("content"))),
         ("has quality score", lambda s, r: "quality" in r and r["quality"]["score"] >= 0),
     ])

# ── AC2: /api/quality?path=时政热点/xxx.md → 10维度 ──
r2 = test("AC2: quality 10-dimension scoring",
     "GET",
     "/api/quality?path=%E6%97%B6%E6%94%BF%E7%83%AD%E7%82%B9/2025%E5%B9%B4%E5%9B%BD%E5%8A%A1%E9%99%A2%E6%94%BF%E5%BA%9C%E5%B7%A5%E4%BD%9C%E6%8A%A5%E5%91%8A%EF%BC%88%E6%9D%8E%E5%BC%BA%E6%80%BB%E7%90%86%C2%B7%E5%8D%81%E5%9B%9B%E5%B1%8A%E5%85%A8%E5%9B%BD%E4%BA%BA%E5%A4%A7%E4%B8%89%E6%AC%A1%E4%BC%9A%E8%AE%AE%EF%BC%89%E6%A0%B8%E5%BF%83%E8%80%83%E7%82%B9.md",
     checks=[
         ("HTTP 200", lambda s, r: s == 200),
         ("10 dimensions", lambda s, r: len(r.get("dimensions", {})) == 10),
         ("score is 100", lambda s, r: r.get("score") == 100),
     ])

# ── AC3: POST /api/quiz/submit → 判分+五段式解析 ──
r3 = test("AC3: quiz submit with answer field",
     "POST",
     "/api/quiz/submit",
     body={"question_id": "2026-08-12-001-5", "answer": "C"},
     checks=[
         ("HTTP 200", lambda s, r: s == 200),
         ("has is_correct", lambda s, r: "is_correct" in r),
         ("5-segment explanation",
          lambda s, r: len(r.get("explanation", {}).get("structured", {})) == 5),
     ])

# ── AC4: mastery.json correct_rate updated ──
test("AC4: mastery correct_rate updated",
     "GET",
     "/api/mastery",
     checks=[
         ("HTTP 200", lambda s, r: s == 200),
         ("时政热点 has correct_rate > 0",
          lambda s, r: r.get("modules", {}).get("时政热点", {}).get("correct_rate", 0) > 0),
         ("时政热点 total > 7 (was updated)",
          lambda s, r: r.get("modules", {}).get("时政热点", {}).get("total", 0) > 7),
     ])

# ── AC5: wrong-questions/ directory ──
import os
wrong_dir = "D:/乔一禾/项目工作区/多Agent学习导师/data/wrong-questions"
wrong_files = os.listdir(wrong_dir) if os.path.isdir(wrong_dir) else []
has_files = len(wrong_files) > 0
if has_files:
    passed += 1
    print(f"PASS AC5: wrong-questions/ directory ({len(wrong_files)} files)")
else:
    failed += 1
    print(f"FAIL AC5: wrong-questions/ directory empty or missing")

# ── Summary ──
print(f"\n{'='*50}")
print(f"RESULTS: {passed} passed, {failed} failed out of 5")
print(f"{'ALL PASSED' if failed == 0 else 'SOME FAILED'}")
print(f"{'='*50}")
