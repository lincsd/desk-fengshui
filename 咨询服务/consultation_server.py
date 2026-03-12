#!/usr/bin/env python3
"""
本地咨询服务器 · consultation_server.py
──────────────────────────────────────
启动后：
  1. 浏览器打开表单页面（自动打开）
  2. 客户填好表单 → 点击「提交」→ JSON 自动保存到 客户档案/待处理/
  3. 你收到桌面通知 → 不用手动复制粘贴任何东西

用法:
  python consultation_server.py              # 默认端口 8899
  python consultation_server.py --port 9000  # 自定义端口
  python consultation_server.py --no-open    # 不自动打开浏览器
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import random
import string
import sys
import os
import shutil
import webbrowser
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote, urlencode

BASE_DIR = Path(__file__).parent
ROOT_DIR = BASE_DIR.parent.parent
# 云端部署时（如 Railway），utils/ 和 prompts/ 放在脚本的上一级目录
_SEARCH_DIRS = [ROOT_DIR, BASE_DIR.parent]
_UTILS_ROOT = next((d for d in _SEARCH_DIRS if (d / "utils").exists()), ROOT_DIR)
if str(_UTILS_ROOT) not in sys.path:
    sys.path.insert(0, str(_UTILS_ROOT))

from utils import GeminiClient

# ---------- encoding fix (Windows GBK) ----------
if sys.platform == "win32":
    for _s in (sys.stdout, sys.stderr):
        if _s and not getattr(_s, "closed", True) and hasattr(_s, "reconfigure"):
            try:
                _s.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

PENDING_DIR = BASE_DIR / "客户档案" / "待处理"
DONE_DIR = BASE_DIR / "客户档案" / "已完成"
PHOTO_DIR = BASE_DIR / "客户档案" / "照片"
OUTPUT_DIR = BASE_DIR / "输出报告"
DASHBOARD_PATH = BASE_DIR / "客户管理面板.html"
AI_PROMPT_FILE = next(
    (d / "prompts" / "desk_ai_prompt.txt" for d in _SEARCH_DIRS
     if (d / "prompts" / "desk_ai_prompt.txt").exists()),
    ROOT_DIR / "prompts" / "desk_ai_prompt.txt"  # 默认（本地）
)

# 服务档位对应价格
TIER_PRICES = {
    "基础版(49.9元)": 49.9,
    "标准版(99元)": 99,
    "高级版(199元)": 199,
}

AI_FALLBACK_REPLY = "我先帮你做一个轻一点的判断：如果你现在还不确定该从哪里开始，通常最先调整的是桌面的整洁度、背后支撑感，以及视线正前方的压迫感。这三点往往比买新摆件更快见效。\n\n如果你愿意，也可以再告诉我你的工位是开放式还是靠墙，我可以继续帮你缩小范围。"


def load_ai_system_prompt() -> str:
    if AI_PROMPT_FILE.exists():
        return AI_PROMPT_FILE.read_text(encoding="utf-8").strip()
    return "你是一位温柔、有分寸、偏女性审美的桌面玄学顾问，擅长给用户低调、耐看、实用的轻量建议。"


def build_chat_prompt(history: list[dict]) -> str:
    system_prompt = load_ai_system_prompt()
    recent_history = history[-12:]
    conversation_lines: list[str] = []
    role_map = {"user": "用户", "assistant": "顾问"}
    for item in recent_history:
        role = role_map.get(item.get("role", "user"), "用户")
        content = str(item.get("content", "")).strip()
        if content:
            conversation_lines.append(f"{role}：{content}")

    prompt = (
        f"{system_prompt}\n\n"
        "以下是对话历史，请基于最后一个用户问题继续回答。\n"
        "如果用户的问题已经比较明确，就直接给轻量建议；如果信息不够，再追问 1-2 个关键问题。\n"
        "如果适合引导正式服务，只用一句温柔的话轻轻引导，不要强推。\n\n"
        + "\n".join(conversation_lines)
        + "\n\n请直接输出给用户看的最终回复。"
    )
    return prompt


def generate_password(length: int = 6) -> str:
    """生成随机数字密码，方便老师口述或微信发送。"""
    return "".join(random.choices(string.digits, k=length))


def wrap_report_with_password_gate(html_content: str, password: str, nickname: str, tier: str) -> str:
    """将诊断报告 HTML 用密码锁页面包裹。"""
    # Base64 编码原始报告内容
    encoded = base64.b64encode(html_content.encode("utf-8")).decode("ascii")
    # SHA-256 哈希密码用于前端验证
    pwd_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
    price = TIER_PRICES.get(tier, 99)

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>专属诊断报告 · {nickname}</title>
    <style>
        :root {{ --bg:#f0ebe3; --paper:#fffdf8; --ink:#2f2a24; --gold:#b98a3b; --gold-soft:#f3e7cf; --green:#2d6a2e; }}
        * {{ box-sizing:border-box; margin:0; padding:0; }}
        body {{ font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
                background:var(--bg); color:var(--ink); min-height:100vh;
                display:flex; align-items:center; justify-content:center; }}
        .gate {{ background:var(--paper); border-radius:28px; padding:48px 36px;
                 max-width:440px; width:90%; text-align:center;
                 box-shadow:0 12px 40px rgba(0,0,0,.08); }}
        .gate h1 {{ font-size:28px; margin-bottom:6px; }}
        .gate .sub {{ color:#74695d; font-size:14px; margin-bottom:28px; }}
        .gate .lock-icon {{ font-size:56px; margin-bottom:18px; }}
        .gate .info-box {{ background:var(--gold-soft); border-radius:16px; padding:18px;
                          margin-bottom:24px; text-align:left; line-height:1.8; font-size:14px; }}
        .gate .info-box .price {{ font-size:28px; font-weight:700; color:var(--gold); }}
        .gate input {{ width:100%; padding:14px 18px; font-size:20px; letter-spacing:8px;
                      text-align:center; border:2px solid #eadfce; border-radius:16px;
                      background:#fdfbf7; outline:none; transition:border .2s; }}
        .gate input:focus {{ border-color:var(--gold); }}
        .gate .btn {{ width:100%; padding:14px; margin-top:14px; border:none; border-radius:16px;
                     background:linear-gradient(135deg,#3b2a12,#825e2a); color:#fff;
                     font-size:16px; font-weight:600; cursor:pointer; transition:opacity .2s; }}
        .gate .btn:hover {{ opacity:.92; }}
        .gate .err {{ color:#e74c3c; font-size:13px; margin-top:10px; min-height:20px; }}
        .gate .contact {{ margin-top:20px; padding-top:18px; border-top:1px solid #eadfce;
                         font-size:13px; color:#74695d; line-height:1.7; }}
        .gate .contact strong {{ color:var(--ink); }}
    </style>
</head>
<body>
    <div class="gate" id="gatePage">
        <div class="lock-icon">🔐</div>
        <h1>专属诊断报告</h1>
        <p class="sub">{nickname} 的工位风水诊断</p>
        <div class="info-box">
            <div>📋 服务档位：<strong>{tier}</strong></div>
            <div style="margin-top:8px">💰 咨询费用：<span class="price">¥{price:.0f}</span></div>
            <div style="margin-top:8px;font-size:12px;color:#74695d">支付后老师会发送 6 位查看密码</div>
        </div>
        <input type="text" id="pwdInput" maxlength="6" placeholder="请输入 6 位密码" autocomplete="off" />
        <button class="btn" onclick="verifyPwd()">🔓 解锁查看报告</button>
        <div class="err" id="errMsg"></div>
        <div class="contact">
            还没有密码？<br>
            请添加老师 <strong>小红书：打工人桌面玄学</strong><br>
            支付咨询费后即可获取密码 🙏
        </div>
    </div>
    <div id="reportContainer" style="display:none"></div>
    <script>
    var H="{pwd_hash}";
    var D="{encoded}";
    function sha256(s){{return crypto.subtle.digest("SHA-256",new TextEncoder().encode(s)).then(function(b){{return Array.from(new Uint8Array(b)).map(function(x){{return x.toString(16).padStart(2,"0")}}).join("")}});}}
    function verifyPwd(){{
        var v=document.getElementById("pwdInput").value.trim();
        if(!v){{document.getElementById("errMsg").textContent="请输入密码";return;}}
        sha256(v).then(function(h){{
            if(h===H){{
                document.getElementById("gatePage").style.display="none";
                var decoded=atob(D);
                var bytes=new Uint8Array(decoded.length);
                for(var i=0;i<decoded.length;i++)bytes[i]=decoded.charCodeAt(i);
                var html=new TextDecoder("utf-8").decode(bytes);
                document.open();document.write(html);document.close();
            }}else{{
                document.getElementById("errMsg").textContent="❌ 密码错误，请重新输入";
                document.getElementById("pwdInput").value="";
                document.getElementById("pwdInput").focus();
            }}
        }});
    }}
    document.getElementById("pwdInput").addEventListener("keydown",function(e){{if(e.key==="Enter")verifyPwd();}});
    </script>
</body>
</html>'''


def refresh_dashboard() -> None:
    """刷新客户管理面板 HTML。"""
    try:
        from client_dashboard import collect_all_clients, generate_dashboard

        clients = collect_all_clients()
        DASHBOARD_PATH.write_text(generate_dashboard(clients), encoding="utf-8")
    except Exception as e:
        print(f"⚠️ 刷新客户管理面板失败: {e}")


def process_and_finalize_client(file_path: Path) -> dict:
    """生成报告 → 加密码锁 → 移到已完成目录。"""
    from generate_consultation_report import process_profile

    data = json.loads(file_path.read_text(encoding="utf-8"))
    nickname = data.get("nickname", file_path.stem)
    consult_date = data.get("consult_date") or datetime.now().strftime("%Y-%m-%d")
    tier = data.get("service_tier", "标准版(99元)")
    report_key = f"{nickname}_{consult_date}"

    # 1. 生成原始报告
    process_profile(file_path)

    # 2. 生成密码并包裹报告
    password = generate_password()
    report_dir = OUTPUT_DIR / report_key
    html_path = report_dir / "诊断报告.html"

    if html_path.exists():
        original_html = html_path.read_text(encoding="utf-8")
        protected_html = wrap_report_with_password_gate(original_html, password, nickname, tier)
        html_path.write_text(protected_html, encoding="utf-8")

    # 3. 保存密码信息
    pwd_info = {
        "password": password,
        "nickname": nickname,
        "tier": tier,
        "price": TIER_PRICES.get(tier, 99),
        "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    (report_dir / "报告密码.json").write_text(
        json.dumps(pwd_info, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 4. 把密码也写回客户 JSON
    data["report_password"] = password
    file_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 5. 移到已完成
    DONE_DIR.mkdir(parents=True, exist_ok=True)
    dest = DONE_DIR / file_path.name
    counter = 1
    while dest.exists():
        dest = DONE_DIR / f"{file_path.stem}_{counter}.json"
        counter += 1
    shutil.move(str(file_path), str(dest))

    return {
        "done_file": dest.name,
        "report_key": report_key,
        "report_password": password,
        "report_html_url": f"/咨询服务/输出报告/{report_key}/诊断报告.html",
        "report_md_url": f"/咨询服务/输出报告/{report_key}/诊断报告.md",
        "dashboard_url": "/咨询服务/客户管理面板.html",
    }


class ConsultationHandler(SimpleHTTPRequestHandler):
    """自定义 HTTP 处理器"""

    def __init__(self, *args, **kwargs):
        # 设置静态文件根目录为 知识付费 目录（方便访问电子书和落地页）
        super().__init__(*args, directory=str(BASE_DIR.parent), **kwargs)

    def do_POST(self):
        """处理表单提交"""
        if self.path == "/api/submit":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)

            try:
                data = json.loads(body.decode("utf-8"))
                result = self._save_client(data)

                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))

            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                error = {"success": False, "message": f"保存失败: {str(e)}"}
                self.wfile.write(json.dumps(error, ensure_ascii=False).encode("utf-8"))
            return

        if self.path == "/api/chat":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)

            try:
                payload = json.loads(body.decode("utf-8"))
                result = self._chat_reply(payload)

                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                error = {"success": False, "message": f"AI 回复失败: {str(e)}"}
                self.wfile.write(json.dumps(error, ensure_ascii=False).encode("utf-8"))
            return

        if self.path == "/api/upload-photo":
            self._handle_photo_upload()
            return

        self.send_response(404)
        self.end_headers()

    def do_OPTIONS(self):
        """处理 CORS 预检请求"""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _save_client(self, data: dict) -> dict:
        """保存客户JSON到待处理目录"""
        PENDING_DIR.mkdir(parents=True, exist_ok=True)
        DONE_DIR.mkdir(parents=True, exist_ok=True)

        nickname = data.get("nickname", "匿名客户").strip() or "匿名客户"
        date_str = data.get("consult_date") or datetime.now().strftime("%Y-%m-%d")
        data.setdefault("submission_status", "submitted")
        data.setdefault("payment_status", "unpaid")
        data.setdefault("submitted_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        # 避免文件名冲突
        base_name = f"{nickname}_{date_str}"
        file_path = PENDING_DIR / f"{base_name}.json"
        counter = 1
        while file_path.exists():
            file_path = PENDING_DIR / f"{base_name}_{counter}.json"
            counter += 1

        file_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        refresh_dashboard()

        queue_query = urlencode(
            {
                "nickname": nickname,
                "tier": data.get("service_tier", "标准版(99元)"),
                "file": file_path.name,
            }
        )
        queue_url = f"/咨询服务/购买后须知.html?{queue_query}"
        payment_guide_query = urlencode(
            {
                "nickname": nickname,
                "tier": data.get("service_tier", "标准版(99元)"),
                "file": file_path.name,
                "queue_url": queue_url,
            }
        )
        payment_guide_url = f"/咨询服务/支付引导页.html?{payment_guide_query}"

        print(f"\n{'=' * 50}")
        print(f"📥 新客户提交！")
        print(f"   昵称: {nickname}")
        print(f"   档位: {data.get('service_tier', '未知')}")
        print(f"   职业: {data.get('job', '未填')}")
        print(f"   诉求: {', '.join(data.get('goals', []))}")
        print(f"   保存: {file_path}")
        print(f"   💰 当前状态: 待支付")
        print(f"   🔗 支付引导: {payment_guide_url}")
        print(f"{'=' * 50}\n")

        # Windows 桌面通知
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.user32.MessageBeep(0x00000040)
            except Exception:
                pass

        result = {
            "success": True,
            "message": f"已保存到 {file_path.name}",
            "file": str(file_path.name),
            "auto_generated": False,
            "payment_status": data.get("payment_status", "unpaid"),
            "queue_url": queue_url,
            "payment_guide_url": payment_guide_url,
        }

        return result

    def _handle_photo_upload(self):
        """处理照片上传"""
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self.send_response(400)
            self.end_headers()
            return

        # 简单解析 multipart
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        # 提取 boundary
        boundary = content_type.split("boundary=")[1].encode()
        parts = body.split(b"--" + boundary)

        saved_files = []
        nickname = "客户"

        for part in parts:
            if b"Content-Disposition" not in part:
                continue

            header_end = part.find(b"\r\n\r\n")
            if header_end == -1:
                continue

            header = part[:header_end].decode("utf-8", errors="replace")
            data = part[header_end + 4:]
            if data.endswith(b"\r\n"):
                data = data[:-2]

            if 'name="nickname"' in header:
                nickname = data.decode("utf-8", errors="replace").strip() or "客户"
            elif 'name="photo"' in header:
                # 提取文件名
                fn_start = header.find('filename="')
                if fn_start != -1:
                    fn_start += 10
                    fn_end = header.find('"', fn_start)
                    original_name = header[fn_start:fn_end]

                    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
                    save_name = f"{nickname}_{original_name}"
                    save_path = PHOTO_DIR / save_name
                    save_path.write_bytes(data)
                    saved_files.append(save_name)

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        result = {"success": True, "files": saved_files}
        self.wfile.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))

    def _chat_reply(self, payload: dict) -> dict:
        history = payload.get("history", [])
        if not isinstance(history, list) or not history:
            return {
                "success": True,
                "reply": AI_FALLBACK_REPLY,
                "hint": "如果你想按自己的工位情况更细一点看，可以直接填写表单。",
                "cta_url": "/咨询服务/客户信息收集表_网页版.html",
            }

        prompt = build_chat_prompt(history)
        try:
            client = GeminiClient()
            reply = client.generate_text(prompt).strip()
        except Exception:
            reply = ""

        if not reply:
            reply = AI_FALLBACK_REPLY

        return {
            "success": True,
            "reply": reply,
            "hint": "如果你想按自己的工位情况更细一点看，可以直接填写表单，我会按你的实际情况整理建议。",
            "cta_url": "/咨询服务/客户信息收集表_网页版.html",
        }

    def log_message(self, format, *args):
        """自定义日志格式"""
        message = str(args[0]) if args else ""
        if "POST /api/" in message:
            return  # POST 请求日志已在 _save_client 中打印
        # 只显示非静态资源请求
        if args and not any(ext in message for ext in [".css", ".js", ".ico", ".png", ".jpg"]):
            sys.stderr.write(f"  📡 {message}\n")


def generate_server_form(port: int) -> str:
    """生成带服务端提交功能的增强版表单"""
    # 读取原始表单
    original = (BASE_DIR / "客户信息收集表_网页版.html").read_text(encoding="utf-8")

    inject_script = f'''
    <script>
    // ===== 服务端自动提交 =====
    const SERVER_URL = 'http://localhost:{port}';

    function goToResultPage(path) {{
        if (!path) return;
        if (path.startsWith('http://') || path.startsWith('https://')) {{
            window.location.href = path;
            return;
        }}
        window.location.href = SERVER_URL + path;
    }}

    async function submitToServer() {{
        buildJson();
        const jsonText = document.getElementById('output').textContent;
        if (!jsonText || jsonText.includes('点击上方按钮')) {{
            alert('请先填写表单内容');
            return;
        }}

        try {{
            const resp = await fetch(SERVER_URL + '/api/submit', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: jsonText
            }});
            const result = await resp.json();
            if (result.success) {{
                alert('资料提交成功，接下来进入预约支付页面。');
                goToResultPage(result.payment_guide_url || result.queue_url);
            }} else {{
                alert('提交失败: ' + result.message);
            }}
        }} catch (e) {{
            alert('无法连接到本地服务器，请确认 consultation_server.py 正在运行\n\n错误: ' + e.message);
        }}
    }}

    document.addEventListener('DOMContentLoaded', function() {{
        const btnRow = document.querySelector('.btn-row');
        if (btnRow) {{
            const serverBtn = document.createElement('button');
            serverBtn.className = 'primary';
            serverBtn.style.cssText = 'background:#2d6a2e;font-size:16px;padding:14px 24px';
            serverBtn.textContent = '🚀 一键提交到服务器';
            serverBtn.onclick = submitToServer;
            btnRow.insertBefore(serverBtn, btnRow.firstChild);
        }}

        const indicator = document.createElement('div');
        indicator.id = 'server-status';
        indicator.style.cssText = 'position:fixed;top:12px;right:12px;padding:8px 14px;border-radius:999px;font-size:12px;z-index:9999;background:#e74c3c;color:#fff';
        indicator.textContent = '🔴 检测服务器...';
        document.body.appendChild(indicator);

        fetch(SERVER_URL + '/api/submit', {{ method: 'OPTIONS' }})
            .then(() => {{
                indicator.style.background = '#2d6a2e';
                indicator.textContent = '🟢 服务器已连接';
                setTimeout(() => {{ indicator.style.opacity = '0.5'; }}, 3000);
            }})
            .catch(() => {{
                indicator.textContent = '🔴 服务器未连接';
            }});
    }});
    </script>
    '''

    enhanced = original.replace("</body>", inject_script + "\n</body>")
    return enhanced
def main():
    parser = argparse.ArgumentParser(description="本地咨询服务器")
    parser.add_argument("--port", type=int, default=None, help="端口号 (默认: 8899)")
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()

    # Railway/云平台用 PORT 环境变量，本地用 --port 参数，兜底 8899
    port = args.port or int(os.environ.get("PORT", 8899))

    # 生成增强版表单
    enhanced_form = generate_server_form(port)
    enhanced_path = BASE_DIR / "客户信息收集表_服务器版.html"
    enhanced_path.write_text(enhanced_form, encoding="utf-8")

    # 确保目录存在
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    DONE_DIR.mkdir(parents=True, exist_ok=True)
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    refresh_dashboard()

    server = HTTPServer(("0.0.0.0", port), ConsultationHandler)

    url = f"http://localhost:{port}/咨询服务/客户信息收集表_服务器版.html"
    dashboard_url = f"http://localhost:{port}/咨询服务/客户管理面板.html"

    print(f"""
╔══════════════════════════════════════════════════╗
║         🏯 咨询服务器已启动                       ║
╠══════════════════════════════════════════════════╣
║                                                  ║
║  📋 表单地址:                                     ║
║  {url:<49s}║
║  📊 管理面板:                                     ║
║  {dashboard_url:<49s}║
║                                                  ║
║  📂 档案保存: 客户档案/待处理 → 已完成/             ║
║  📷 照片保存: 客户档案/照片/                        ║
║                                                  ║
║  💡 客户提交后会先进入支付引导页                     ║
║  🛑 按 Ctrl+C 停止服务器                           ║
╚══════════════════════════════════════════════════╝
""")

    if not args.no_open:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 服务器已停止")
        server.server_close()


if __name__ == "__main__":
    main()
