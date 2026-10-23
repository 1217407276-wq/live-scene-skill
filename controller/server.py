"""Minimal local web UI. Feedback controls are rendered by this program."""
from __future__ import annotations

import html
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    from .brand_assets import inspect_brand_assets
except ImportError:  # allows `python controller/server.py`
    from brand_assets import inspect_brand_assets

try:
    from .workflow import ImageProvider, Workflow, WorkflowError, sha256_file
except ImportError:  # allows `python controller/server.py`
    from workflow import ImageProvider, Workflow, WorkflowError, sha256_file


class UnconfiguredProvider(ImageProvider):
    def generate_three(self, project, round_number, destination):
        raise RuntimeError("No image-generation provider is configured. Add an adapter; no images were generated.")

    def edit_three(self, source_image, project, round_number, changes, destination):
        raise RuntimeError("No image-edit provider is configured. The selected file was not edited.")


ROOT = Path(os.environ.get("LIVE_SCENE_DATA", "./live-scene-data")).resolve()
WORKFLOW = Workflow(ROOT / "workflow.sqlite3", ROOT / "assets", UnconfiguredProvider())
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def esc(x):
    return html.escape(str(x or ""))


def render(p):
    brand = inspect_brand_assets(REPOSITORY_ROOT)
    brand_lines = "".join(f'<li>{esc(v["path"])}：{"可读取，格式标记通过" if v["readable"] and v["valid_format"] else "缺失或无法验证"}</li>'
                          for v in brand.values() if isinstance(v, dict))
    cards = "".join(
        f'<label class="card"><img src="/asset/{esc(a["id"])}?project={esc(p["id"])}" alt="{a["variant"]}">'
        f'<strong>{a["variant"]}</strong><small>{esc(a["id"])}</small>'
        f'<input type="radio" name="asset_id" value="{esc(a["id"])}" required></label>'
        for a in p["assets"] if Path(a["path"]).is_file()
    )
    saved = p.get("last_changes", {})
    saved_allow = saved.get("allow", [])
    options = "".join(f'<label><input type="checkbox" name="allow" value="{esc(x)}"{" checked" if x in saved_allow else ""}>{esc(x)}</label>' for x in
                      ["镜头/主体尺寸", "空间纵深", "扩图", "光线", "品牌配色", "Logo位置/比例", "棉花", "家具/装置", "大促点缀", "画面简化"])
    state = f'<p>项目 {esc(p["id"])} · 第 {p["round_number"]} 轮 · 阶段 {esc(p["phase"])}</p>'
    err = f'<p class="error">{esc(p["last_error"])}</p>' if p["last_error"] else ""
    panel = ""
    if p["phase"] == "feedback":
        panel = f'''<section><h2>第 {p["round_number"]} 轮反馈</h2><p>选择并锁定一个真实原图。下方修改项可多选，也可自由输入。</p>
          <form method="post" action="/lock?project={esc(p['id'])}"><div class="cards">{cards}</div>
          <fieldset><legend>允许修改（多选）</legend>{options}</fieldset>
          <textarea name="free_text" placeholder="自由补充，例如：棉花减少30%"></textarea>
          <input name="preserve" placeholder="必须保持不变（必填）"><input name="forbid" placeholder="禁止改动（必填）">
          <button>锁定所选原图并保存修改边界</button></form></section>'''
    elif p["phase"] == "planning":
        panel = f'''<form method="post" action="/confirm?project={esc(p['id'])}"><label>已确认方案<textarea name="direction" required></textarea></label><button>确认方向</button></form>'''
    elif p["phase"] == "confirmed":
        panel = f'<form method="post" action="/generate?project={esc(p["id"])}"><button>生成本轮 A/B/C</button></form>'
    elif p["phase"] == "locked":
        locked_options = "".join(f'<label><input type="checkbox" name="allow" value="{esc(x)}"{" checked" if x in saved_allow else ""}>{esc(x)}</label>' for x in
                                  ["镜头/主体尺寸", "空间纵深", "扩图", "光线", "品牌配色", "Logo位置/比例", "棉花", "家具/装置", "大促点缀", "画面简化"])
        panel = f'''<form method="post" action="/refine?project={esc(p['id'])}"><p>锁定原图ID：{esc(p['locked_asset_id'])}</p>
          <fieldset><legend>本轮允许修改（多选）</legend>{locked_options}</fieldset>
          <input name="allow_text" placeholder="其他允许修改项（逗号分隔）"><input name="preserve" value="{esc(', '.join(saved.get('preserve', [])))}" placeholder="必须保持不变（必填）"><input name="forbid" value="{esc(', '.join(saved.get('forbid', [])))}" placeholder="禁止改动（必填）">
          <textarea name="free_text" placeholder="自由输入本轮修改">{esc(saved.get('free_text', ''))}</textarea><button>按锁定原图生成下一轮 A/B/C</button></form>'''
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>直播间场景工作台</title><style>body{{font:16px system-ui;max-width:1000px;margin:2rem auto;padding:0 1rem;background:#f6f5f1;color:#222}}section,form{{background:white;padding:1rem;border-radius:12px;margin:1rem 0}}.cards{{display:flex;gap:1rem;flex-wrap:wrap}}.card{{width:28%;min-width:180px}}img{{width:100%;aspect-ratio:3/4;object-fit:contain;background:#eee}}small{{display:block;overflow-wrap:anywhere}}fieldset label{{display:inline-block;margin:.5rem}}textarea,input{{display:block;margin:.5rem 0;padding:.7rem;width:min(95%,600px)}}button{{padding:.8rem 1.2rem;background:#00AC97;color:white;border:0;border-radius:8px;cursor:pointer}}.error{{color:#a00}}</style>
    <h1>AI直播间场景工作台</h1>{state}<details><summary>品牌素材状态</summary><ul>{brand_lines}</ul><p>标准绿：#00AC97 / RGB(0,172,151)；生成色彩仍需后期校验。</p></details>{err}{panel}</html>'''


class Handler(BaseHTTPRequestHandler):
    def respond(self, body, code=200, content_type="text/html; charset=utf-8"):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

    def form(self):
        n = int(self.headers.get("Content-Length", "0")); return parse_qs(self.rfile.read(n).decode())

    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        if u.path == "/":
            return self.respond('<h1>项目</h1><form method="post" action="/new"><textarea name="brief" placeholder="项目需求" required></textarea><button>新建项目</button></form>')
        if u.path == "/project":
            return self.respond(render(WORKFLOW.recover(q["id"][0])))
        if u.path == "/asset/" + u.path.rsplit("/", 1)[-1] and u.path.startswith("/asset/"):
            asset_id = u.path.split("/")[-1]; p_id = q.get("project", [""])[0]
            try:
                a = WORKFLOW.asset(p_id, asset_id); path = Path(a["path"])
                if not path.is_file() or sha256_file(path) != a["sha256"]: return self.respond("asset integrity check failed", 404, "text/plain")
                return self.respond(path.read_bytes(), 200, "image/png")
            except WorkflowError as e: return self.respond(str(e), 404, "text/plain")
        return self.respond("not found", 404)

    def do_POST(self):
        u = urlparse(self.path); q = parse_qs(u.query); f = self.form()
        try:
            if u.path == "/new":
                p = WORKFLOW.create_project(json.loads(f.get("brief", ["{}"])[0])); return self.respond(f'<a href="/project?id={p["id"]}">打开项目 {p["id"]}</a>')
            p_id = q["project"][0]
            if u.path == "/confirm": WORKFLOW.confirm_direction(p_id, f.get("direction", [""])[0])
            elif u.path == "/generate": WORKFLOW.generate(p_id)
            elif u.path == "/lock":
                changes = {"allow": f.get("allow", []), "preserve": f.get("preserve", [""]), "forbid": f.get("forbid", [""]), "free_text": f.get("free_text", [""])[0]}
                WORKFLOW.lock_asset(p_id, f.get("asset_id", [""])[0], changes)
            elif u.path == "/refine":
                allow = f.get("allow_text", [""])[0].strip()
                selected = f.get("allow", [])
                WORKFLOW.refine(p_id, {"allow": selected + [x.strip() for x in allow.split(",") if x.strip()], "preserve": [f.get("preserve", [""])[0]], "forbid": [f.get("forbid", [""])[0]], "free_text": f.get("free_text", [""])[0]})
            else: return self.respond("not found", 404)
            return self.respond(render(WORKFLOW.recover(p_id)))
        except (WorkflowError, KeyError, ValueError, json.JSONDecodeError) as e:
            p_id = q.get("project", [""])[0]
            try: return self.respond(render(WORKFLOW.recover(p_id)) + f'<p class="error">{esc(e)}</p>')
            except Exception: return self.respond(f'<p class="error">{esc(e)}</p>', 400)


if __name__ == "__main__":
    host = os.environ.get("LIVE_SCENE_HOST", "127.0.0.1"); port = int(os.environ.get("LIVE_SCENE_PORT", "8765"))
    print(f"Live Scene workbench: http://{host}:{port}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
