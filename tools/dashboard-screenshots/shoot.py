"""Log in to the local render instance and screenshot dashboards via Chrome DevTools."""
import asyncio, base64, json, os, subprocess, sys, time
import aiohttp

BASE = os.environ.get("HA_URL", "http://127.0.0.1:18123")
UI_LANGUAGE = os.environ.get("UI_LANGUAGE", "en")
CLIENT = BASE + "/"


async def get_tokens(session):
    async with session.post(BASE + "/auth/login_flow", json={
        "client_id": CLIENT, "handler": ["homeassistant", None],
        "redirect_uri": CLIENT + "?auth_callback=1"}) as r:
        flow = await r.json()
    async with session.post(BASE + "/auth/login_flow/" + flow["flow_id"], json={
        "client_id": CLIENT, "username": "demo", "password": "demo-render-only"}) as r:
        result = await r.json()
    async with session.post(BASE + "/auth/token", data={
        "grant_type": "authorization_code", "code": result["result"], "client_id": CLIENT}) as r:
        return await r.json()


class CDP:
    def __init__(self, ws):
        self.ws, self.n = ws, 0

    async def call(self, method, **params):
        self.n += 1
        await self.ws.send_json({"id": self.n, "method": method, "params": params})
        while True:
            msg = await self.ws.receive_json()
            if msg.get("id") == self.n:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})


async def main(shots):
    chrome = subprocess.Popen([
        "google-chrome", "--headless=new", "--disable-gpu", "--no-first-run",
        "--user-data-dir=" + sys.argv[1], "--remote-debugging-port=9333",
        "--force-dark-mode", "--hide-scrollbars", "--lang=" + UI_LANGUAGE, "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        async with aiohttp.ClientSession() as session:
            tokens = await get_tokens(session)
            for _ in range(50):
                try:
                    async with session.get("http://127.0.0.1:9333/json") as r:
                        targets = await r.json()
                    break
                except aiohttp.ClientError:
                    await asyncio.sleep(0.2)
            # Confirm the render instance's own HTTP port once (Home Assistant
            # asks for it after HTTP settings changed).
            async with session.ws_connect(BASE + "/api/websocket") as hws:
                await hws.receive_json()
                await hws.send_json({"type": "auth", "access_token": tokens["access_token"]})
                await hws.receive_json()
                await hws.send_json({"id": 1, "type": "http/config/promote"})
                print("promote:", (await hws.receive_json()).get("success"))
            page = next(t for t in targets if t["type"] == "page")
            async with session.ws_connect(page["webSocketDebuggerUrl"], max_msg_size=0) as ws:
                cdp = CDP(ws)
                await cdp.call("Page.enable")
                await cdp.call("Page.navigate", url=BASE + "/auth/authorize")
                await asyncio.sleep(2)
                stored = {**tokens, "hassUrl": BASE, "clientId": CLIENT,
                          "expires": int(time.time() * 1000) + tokens["expires_in"] * 1000}
                await cdp.call("Runtime.evaluate", expression=
                    f"localStorage.setItem('hassTokens', {json.dumps(json.dumps(stored))});"
                    f"localStorage.setItem('selectedLanguage', '\"{UI_LANGUAGE}\"');"
                    "localStorage.setItem('selectedTheme', JSON.stringify({theme:'default', dark:true}));"
                    "localStorage.setItem('dockedSidebar', '\"always_hidden\"');")
                for path, out, width, height in shots:
                    await cdp.call("Emulation.setDeviceMetricsOverride", width=width,
                                   height=height, deviceScaleFactor=1, mobile=False)
                    await cdp.call("Page.navigate", url=BASE + path)
                    await asyncio.sleep(9)
                    shot = await cdp.call("Page.captureScreenshot", format="png")
                    open(out, "wb").write(base64.b64decode(shot["data"]))
                    print("saved", out)
    finally:
        chrome.terminate()


if __name__ == "__main__":
    shots = json.loads(sys.argv[2])
    asyncio.run(main(shots))
