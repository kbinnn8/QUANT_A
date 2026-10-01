"""QUANT_A 上傳小程式（在你的 Windows 電腦上執行）

監看 MT5 共用資料夾，發現 EA 輸出的回測結果（.json）就上傳到 GitHub 的 runs/ 資料夾，
Streamlit 上的 app 一兩分鐘內就會出現這筆回測。

- 只用 Python 標準函式庫，不需要安裝任何套件
- GitHub token 只存在這台電腦（%APPDATA%\\QuantA\\uploader.ini），不會上傳到任何地方
- 用法：雙擊「啟動上傳程式.bat」；第一次會請你貼上 token
  參數：--setup 重新設定 token、--once 處理完現有檔案就結束、--check 只檢查連線
"""
from __future__ import annotations

import argparse
import base64
import configparser
import datetime as dt
import getpass
import hashlib
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_DEFAULT = "kbinnn8/QUANT_A"
BRANCH_DEFAULT = "main"
API = os.environ.get("QUANTA_API", "https://api.github.com")      # 測試時可以改成假的伺服器
APPDATA = Path(os.environ.get("APPDATA", Path.home()))
CONFIG_FILE = APPDATA / "QuantA" / "uploader.ini"
WATCH_DEFAULT = APPDATA / "MetaQuotes" / "Terminal" / "Common" / "Files" / "QuantA"
POLL_SECONDS = 5

try:                                       # Windows 主控台顯示中文
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def now() -> str:
    return dt.datetime.now().strftime("%H:%M:%S")


def log(msg: str):
    print(f"[{now()}] {msg}", flush=True)


# ───────────────────────── 設定 ─────────────────────────
def load_config() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg["github"] = {"token": "", "repo": REPO_DEFAULT, "branch": BRANCH_DEFAULT}
    cfg["paths"] = {"watch_dir": str(WATCH_DEFAULT)}
    if CONFIG_FILE.exists():
        cfg.read(CONFIG_FILE, encoding="utf-8")
    return cfg


def save_config(cfg: configparser.ConfigParser):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        cfg.write(f)


# ───────────────────────── GitHub API ─────────────────────────
def gh(method: str, path: str, token: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "QuantA-Uploader",
        **({"Content-Type": "application/json"} if data else {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode("utf-8") or "{}")
        except Exception:
            payload = {}
        return e.code, payload


def check(cfg) -> bool:
    token, repo = cfg["github"]["token"], cfg["github"]["repo"]
    if not token:
        log("還沒有設定 GitHub token。")
        return False
    try:
        code, info = gh("GET", f"/repos/{repo}", token)
    except urllib.error.URLError as e:
        log(f"連不上 GitHub：{e.reason}（檢查網路）")
        return False
    if code == 200:
        can_push = info.get("permissions", {}).get("push", True)
        log(f"連線成功：{info.get('full_name', repo)}" + ("" if can_push else "（但 token 沒有寫入權限！）"))
        return bool(can_push)
    if code in (401, 403):
        log("token 無效或沒有權限。請用 --setup 重新設定，並確認 token 有 QUANT_A 的 Contents 讀寫權限。")
    elif code == 404:
        log(f"找不到 {repo}：token 可能沒有開放這個 repository 的存取權。")
    else:
        log(f"GitHub 回應 {code}：{info.get('message', '')}")
    return False


def setup(cfg):
    print()
    print("=== 設定 GitHub token ===")
    print("在 GitHub：Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token")
    print("  Repository access：Only select repositories → 選 QUANT_A")
    print("  Permissions → Repository permissions → Contents：Read and write")
    print("產生後複製，貼到下面（輸入時畫面不會顯示，這是正常的），按 Enter。")
    token = getpass.getpass("token：").strip()
    if not token:
        print("沒有輸入，取消。")
        return False
    cfg["github"]["token"] = token
    if check(cfg):
        save_config(cfg)
        log(f"已儲存設定：{CONFIG_FILE}")
        return True
    log("沒有儲存，請確認 token 後再試一次。")
    return False


# ───────────────────────── 處理檔案 ─────────────────────────
def prepare(raw: bytes) -> dict:
    """讀取 EA 輸出的 JSON，補上 id 與建立時間。"""
    text = None
    for enc in ("utf-8-sig", "utf-16"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError("無法辨識檔案編碼")
    d = json.loads(text)
    for k in ("equity", "trades", "symbol"):
        if k not in d:
            raise ValueError(f"缺少欄位 {k}")
    stamp = dt.datetime.now()
    if not d.get("created"):
        d["created"] = stamp.isoformat(timespec="seconds")
    if not d.get("id"):
        h = hashlib.md5(raw).hexdigest()[:6]
        d["id"] = f"{stamp:%Y%m%d-%H%M%S}-{h}"
    d.setdefault("source", "mt5")
    return d


def upload(cfg, d: dict) -> tuple[bool, str]:
    token, repo, branch = cfg["github"]["token"], cfg["github"]["repo"], cfg["github"]["branch"]
    content = json.dumps(d, ensure_ascii=False).encode("utf-8")
    path = f"runs/{d['id']}.json"
    body = {"message": f"MT5 回測：{d.get('name', d['id'])}", "branch": branch,
            "content": base64.b64encode(content).decode("ascii")}
    code, info = gh("PUT", f"/repos/{repo}/contents/{path}", token, body)
    if code in (200, 201):
        return True, path
    if code == 422:                    # 同名檔案已存在：換一個 id 再試
        d["id"] += "b"
        return upload(cfg, d)
    return False, f"GitHub 回應 {code}：{info.get('message', '')}"


def process(cfg, watch: Path) -> int:
    done = watch / "uploaded"
    failed = watch / "failed"
    n = 0
    for f in sorted(watch.glob("*.json")):
        try:
            raw = f.read_bytes()
            d = prepare(raw)
        except Exception as e:
            failed.mkdir(exist_ok=True)
            shutil.move(str(f), str(failed / f.name))
            log(f"✗ {f.name} 格式不正確，已移到 failed\\：{e}")
            continue
        try:
            ok, msg = upload(cfg, d)
        except urllib.error.URLError as e:
            log(f"… 暫時連不上 GitHub（{e.reason}），稍後重試 {f.name}")
            return n
        if ok:
            done.mkdir(exist_ok=True)
            shutil.move(str(f), str(done / f.name))
            log(f"✓ 已上傳：{d.get('name', f.name)}（{len(d.get('trades', []))} 筆交易）→ {msg}")
            log("  約 1–2 分鐘後會出現在 app 的「研究紀錄」。")
            n += 1
        else:
            log(f"✗ 上傳失敗 {f.name}：{msg}（稍後重試）")
    return n


def main():
    ap = argparse.ArgumentParser(description="QUANT_A 上傳小程式")
    ap.add_argument("--setup", action="store_true", help="重新設定 GitHub token")
    ap.add_argument("--once", action="store_true", help="處理完現有檔案就結束")
    ap.add_argument("--check", action="store_true", help="只檢查連線")
    ap.add_argument("--watch", help="改用其他監看資料夾")
    args = ap.parse_args()

    cfg = load_config()
    if args.watch:
        cfg["paths"]["watch_dir"] = args.watch
    watch = Path(cfg["paths"]["watch_dir"])
    watch.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print(" QUANT_A 上傳小程式")
    print(f" 監看資料夾：{watch}")
    print(f" 上傳到：{cfg['github']['repo']}（{cfg['github']['branch']}）/runs/")
    print("=" * 60)

    if args.setup or not cfg["github"]["token"]:
        if not setup(cfg):
            return 1
    elif not check(cfg):
        return 1
    if args.check:
        return 0

    process(cfg, watch)
    if args.once:
        return 0
    log("開始監看。在 MT5 跑完回測，結果會自動上傳。按 Ctrl+C 結束。")
    try:
        while True:
            time.sleep(POLL_SECONDS)
            process(cfg, watch)
    except KeyboardInterrupt:
        log("已結束。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
