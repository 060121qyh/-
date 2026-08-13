# -*- coding: utf-8 -*-
"""CDP 验证静态版 platform（http://127.0.0.1:8900/index.html）
验证：STATIC_DATA 注入、静态模式渲染、知识宝库、练题、manifest/SW、console 错误。"""
import asyncio
import json
import sys
import urllib.request

import websockets

TARGET = "http://127.0.0.1:8900/index.html"
errors = []


async def main():
    # 1) 拿页面 WebSocket
    tabs = json.loads(urllib.request.urlopen("http://127.0.0.1:9222/json").read())
    page = next((t for t in tabs if t.get("type") == "page"), None)
    if not page:
        print("FAIL: no page target"); sys.exit(1)
    ws_url = page["webSocketDebuggerUrl"]

    async with websockets.connect(ws_url, max_size=50 * 1024 * 1024) as ws:
        msg_id = 0

        async def send(method, params=None):
            nonlocal msg_id
            msg_id += 1
            await ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
            while True:
                m = json.loads(await ws.recv())
                if m.get("id") == msg_id:
                    return m
                if m.get("method") == "Runtime.consoleAPICalled":
                    for a in m["params"].get("args", []):
                        if a.get("type") in ("error", "warning"):
                            errors.append("[console.%s] %s" % (a["type"], a.get("value", a.get("description", ""))[:200]))
                elif m.get("method") == "Runtime.exceptionThrown":
                    errors.append("[exception] " + str(m["params"]["exceptionDetails"].get("exception", {}).get("description", ""))[:200])
                elif m.get("method") == "Log.entryAdded":
                    e = m["params"]["entry"]
                    if e.get("level") in ("error", "warning"):
                        errors.append("[log.%s] %s" % (e["level"], e.get("text", "")[:200]))
                elif m.get("method") == "Network.loadingFailed":
                    errors.append("[net] " + str(m["params"].get("errorText", ""))[:200])

        async def evaluate(expr, await_promise=False):
            r = await send("Runtime.evaluate", {
                "expression": expr,
                "returnByValue": True,
                "awaitPromise": await_promise,
            })
            if "exceptionDetails" in r.get("result", {}):
                return "EXC: " + r["result"]["exceptionDetails"].get("exception", {}).get("description", "?")
            return r["result"].get("result", {}).get("value")

        await send("Page.enable")
        await send("Runtime.enable")
        await send("Log.enable")
        await send("Network.enable")

        await send("Page.navigate", {"url": TARGET})
        await asyncio.sleep(3.5)  # 等 p5/marked 加载 + init 渲染

        print("=== 静态版渲染验证 (8900) ===")
        print("title:", await evaluate("document.title"))
        print("STATIC_DATA:", await evaluate("typeof window.STATIC_DATA"))
        print("subtitle:", await evaluate("document.getElementById('header-subtitle').textContent"))
        print("badge(知识卡数):", await evaluate("document.getElementById('card-count-badge').textContent"))
        print("stat-cards:", await evaluate("Array.from(document.querySelectorAll('.stat-card .value')).map(e=>e.textContent).join(' | ')"))

        # 切到知识宝库
        await evaluate("document.querySelector('[data-tab=\"knowledge\"]').click()")
        await asyncio.sleep(2)
        print("knowledge cards:", await evaluate("document.querySelectorAll('.card-item').length"))
        print("kb first card:", await evaluate("(document.querySelector('.card-item .card-title')||{}).textContent || 'NONE'"))
        # 点开第一张卡详情
        await evaluate("document.querySelector('.card-item').click()")
        await asyncio.sleep(1.5)
        print("card detail rendered len:", await evaluate("(document.querySelector('.rendered-content')||{}).innerText ? document.querySelector('.rendered-content').innerText.length : -1"))
        await evaluate("document.querySelector('.back-btn') ? document.querySelector('.back-btn').click() : null")

        # 切到练题工坊
        await evaluate("document.querySelector('[data-tab=\"quiz\"]').click()")
        await asyncio.sleep(2)
        print("quiz start text:", await evaluate("(document.querySelector('.quiz-start-screen h3')||{}).textContent || 'NONE'"))
        # 开始练题 → 答第一题 → 判分
        await evaluate("document.getElementById('quiz-start-btn') ? document.getElementById('quiz-start-btn').click() : null")
        await asyncio.sleep(1.5)
        print("quiz question:", await evaluate("(document.querySelector('.quiz-q-num')||{}).textContent || 'NONE'"))
        print("quiz options:", await evaluate("document.querySelectorAll('.quiz-option').length"))
        await evaluate("document.querySelector('.quiz-option') ? document.querySelector('.quiz-option').click() : null")
        await asyncio.sleep(1.2)
        print("explanation visible:", await evaluate("document.querySelector('.quiz-explanation') ? document.querySelector('.quiz-explanation').classList.contains('visible') : false"))
        print("explanation text len:", await evaluate("(document.querySelector('.quiz-explanation')||{}).innerText ? document.querySelector('.quiz-explanation').innerText.length : -1"))

        # 考点汇总
        await evaluate("document.querySelector('[data-tab=\"knowledge\"]').click()")
        await asyncio.sleep(1.5)
        await evaluate("Array.from(document.querySelectorAll('button')).find(b=>b.textContent.includes('考点汇总')) ? Array.from(document.querySelectorAll('button')).find(b=>b.textContent.includes('考点汇总')).click() : null")
        await asyncio.sleep(2)
        print("summary cards:", await evaluate("document.querySelectorAll('.stat-card').length"))

        # manifest / SW 状态
        print("manifest link:", await evaluate("document.querySelector('link[rel=manifest]') ? document.querySelector('link[rel=manifest]').getAttribute('href') : 'NONE'"))
        print("SW support:", await evaluate("'serviceWorker' in navigator"))
        print("SW controller:", await evaluate("navigator.serviceWorker ? navigator.serviceWorker.getRegistration().then(r=>r?r.active?r.active.scriptURL:'installing':'none') : 'no-sw'"))

        # 资源 404 检查
        bad = await evaluate("performance.getEntriesByType('resource').filter(r=>r.responseStatus>=400).map(r=>r.name)")
        print("resource>=400:", bad)

        print("\n=== console/网络错误 ===")
        if errors:
            for e in errors[:15]:
                print(" ", e)
        else:
            print("  (无)")

        await send("Page.captureScreenshot", {"format": "png"})
        # 截图省略（文本证据已充分）

asyncio.run(main())
