#!/usr/bin/env python3
"""
客户管理面板 · client_dashboard.py
──────────────────────────────────
生成一个可视化 HTML 面板，展示所有客户的处理状态。

用法:
  python client_dashboard.py           # 生成面板并打开
  python client_dashboard.py --no-open # 只生成不打开
"""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

# ---------- encoding fix (Windows GBK) ----------
if sys.platform == "win32":
    for _s in (sys.stdout, sys.stderr):
        if _s and not getattr(_s, "closed", True) and hasattr(_s, "reconfigure"):
            try:
                _s.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

BASE_DIR = Path(__file__).parent
PENDING_DIR = BASE_DIR / "客户档案" / "待处理"
DONE_DIR = BASE_DIR / "客户档案" / "已完成"
ARCHIVE_DIR = BASE_DIR / "客户档案" / "归档"
OUTPUT_DIR = BASE_DIR / "输出报告"
DELIVER_DIR = BASE_DIR / "交付包"


def _load_client(json_path: Path) -> dict:
    """加载客户JSON并附加元信息"""
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        data["_file"] = json_path.name
        data["_dir"] = json_path.parent.name
        return data
    except Exception as e:
        return {
            "nickname": json_path.stem,
            "_file": json_path.name,
            "_dir": json_path.parent.name,
            "_error": str(e),
        }


def collect_all_clients() -> dict:
    """收集所有客户数据"""
    clients = {"pending": [], "done": [], "archived": []}

    if PENDING_DIR.exists():
        for f in sorted(PENDING_DIR.glob("*.json")):
            clients["pending"].append(_load_client(f))

    if DONE_DIR.exists():
        for f in sorted(DONE_DIR.glob("*.json")):
            clients["done"].append(_load_client(f))

    if ARCHIVE_DIR.exists():
        for f in sorted(ARCHIVE_DIR.glob("*.json")):
            clients["archived"].append(_load_client(f))

    # 检查报告状态
    report_folders = set()
    if OUTPUT_DIR.exists():
        for d in OUTPUT_DIR.iterdir():
            if d.is_dir():
                report_folders.add(d.name)

    deliver_folders = set()
    if DELIVER_DIR.exists():
        for d in DELIVER_DIR.iterdir():
            if d.is_dir():
                deliver_folders.add(d.name)

    clients["_reports"] = report_folders
    clients["_delivered"] = deliver_folders

    return clients


def _client_row(client: dict, status: str, reports: set, delivered: set) -> str:
    """生成单个客户的HTML行"""
    nickname = client.get("nickname", "未知")
    date = client.get("consult_date", "-")
    tier = client.get("service_tier", "-")
    job = client.get("job", "-")
    goals = ", ".join(client.get("goals", [])) or "-"
    budget = client.get("budget", "-")

    # 检查是否有报告和交付包
    key = f"{nickname}_{date}"
    has_report = any(key in r for r in reports)
    has_deliver = any(key in d for d in delivered)
    report_html = f"输出报告/{key}/诊断报告.html"
    report_md = f"输出报告/{key}/诊断报告.md"
    deliver_dir = f"交付包/{key}"

    status_emoji = {"pending": "⏳ 待处理", "done": "✅ 已完成", "archived": "🗃️ 已归档"}
    status_class = {"pending": "status-pending", "done": "status-done", "archived": "status-archived"}

    report_badge = "<span class='badge badge-report'>📄 有报告</span>" if has_report else ""
    deliver_badge = "<span class='badge badge-deliver'>📦 已打包</span>" if has_deliver else ""
    action_links = []
    if has_report:
        action_links.append(f"<a class='action-link' href='{report_html}' target='_blank'>查看HTML报告</a>")
        action_links.append(f"<a class='action-link' href='{report_md}' target='_blank'>查看文字版</a>")
    if has_deliver:
        action_links.append(f"<a class='action-link' href='{deliver_dir}' target='_blank'>打开交付包</a>")
    action_html = " ".join(action_links) if action_links else "<span style='color:var(--muted);font-size:12px'>等待自动生成</span>"

    # 加载报告密码
    password = client.get("report_password", "")
    if not password and has_report:
        pwd_file = OUTPUT_DIR / key / "报告密码.json"
        if pwd_file.exists():
            try:
                pwd_data = json.loads(pwd_file.read_text(encoding="utf-8"))
                password = pwd_data.get("password", "")
            except Exception:
                pass

    verify_code = client.get("verify_code", "")
    payment_confirmed = client.get("payment_confirmed", False)
    file_name = client.get("_file", "")

    if password:
        pwd_html = f"<span class='pwd-cell'><code class='pwd-code'>{password}</code><button class='pwd-copy' onclick=\"navigator.clipboard.writeText('{password}');this.textContent='✅';setTimeout(()=>this.textContent='⎘',1200)\">⎘</button></span>"
    elif verify_code:
        safe_code = verify_code.replace("'", "\\'")
        pwd_html = f"<span class='pwd-cell'><code class='verify-code' title='客户付款验证码'>{verify_code}</code><button class='pwd-copy' onclick=\"navigator.clipboard.writeText('{safe_code}');this.textContent='✅';setTimeout(()=>this.textContent='⎘',1200)\" title='复制验证码'>⎘</button></span><div style='font-size:11px;color:var(--green);margin-top:2px'>✅ 已确认收款</div>"
    elif status == "pending" and file_name:
        safe_file = file_name.replace("'", "\\'")
        pwd_html = f"<button class='confirm-btn' onclick=\"confirmPayment('{safe_file}', this)\">💰 确认收款</button>"
    else:
        pwd_html = "<span style='color:var(--muted);font-size:12px'>-</span>"

    return f"""
    <tr class="{status_class.get(status, '')}">
        <td><strong>{nickname}</strong></td>
        <td>{date}</td>
        <td>{tier}</td>
        <td>{job}</td>
        <td class="goals-cell">{goals}</td>
        <td>{budget}</td>
        <td><span class='{status_class.get(status, '')}'>{status_emoji.get(status, status)}</span></td>
        <td>{pwd_html}</td>
        <td>{report_badge} {deliver_badge}</td>
        <td>{action_html}</td>
    </tr>"""


def generate_dashboard(clients: dict) -> str:
    """生成HTML面板"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    reports = clients["_reports"]
    delivered = clients["_delivered"]

    total = len(clients["pending"]) + len(clients["done"]) + len(clients["archived"])
    pending_count = len(clients["pending"])
    done_count = len(clients["done"])
    archived_count = len(clients["archived"])

    # 收入估算
    tier_prices = {"基础版(49.9元)": 49.9, "标准版(99元)": 99, "高级版(199元)": 199}
    total_revenue = 0
    for group in ["done", "archived"]:
        for c in clients[group]:
            tier = c.get("service_tier", "")
            total_revenue += tier_prices.get(tier, 0)

    # 服务档位分布
    tier_dist = {}
    for group in ["pending", "done", "archived"]:
        for c in clients[group]:
            tier = c.get("service_tier", "未知")
            tier_dist[tier] = tier_dist.get(tier, 0) + 1

    # 热门诉求
    goal_dist = {}
    for group in ["pending", "done", "archived"]:
        for c in clients[group]:
            for g in c.get("goals", []):
                goal_dist[g] = goal_dist.get(g, 0) + 1

    top_goals = sorted(goal_dist.items(), key=lambda x: -x[1])[:5]

    # 构建表格行
    all_rows = []
    for c in clients["pending"]:
        all_rows.append(_client_row(c, "pending", reports, delivered))
    for c in clients["done"]:
        all_rows.append(_client_row(c, "done", reports, delivered))
    for c in clients["archived"]:
        all_rows.append(_client_row(c, "archived", reports, delivered))

    tier_cards = "".join(
        f"<div class='mini-card'><span>{tier}</span><strong>{count}</strong></div>"
        for tier, count in sorted(tier_dist.items())
    )

    goal_bars = "".join(
        f"""<div class='bar-row'>
            <span class='bar-label'>{goal}</span>
            <div class='bar-bg'><div class='bar-fill' style='width:{min(count/max(1,total)*100*3, 100):.0f}%'></div></div>
            <span class='bar-val'>{count}</span>
        </div>"""
        for goal, count in top_goals
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>客户管理面板 · 打工人桌面玄学</title>
    <style>
        :root {{
            --bg: #f0ebe3;
            --paper: #fffdf8;
            --ink: #2f2a24;
            --muted: #74695d;
            --gold: #b98a3b;
            --gold-soft: #f3e7cf;
            --line: #eadfce;
            --green: #2d6a2e;
            --green-soft: #e8f5e8;
            --orange: #e67e22;
            --orange-soft: #fef3e2;
            --blue: #2980b9;
            --blue-soft: #ebf5fb;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif;
            background: var(--bg);
            color: var(--ink);
            line-height: 1.7;
        }}
        .page {{ max-width: 1200px; margin: 0 auto; padding: 24px 18px 60px; }}

        /* Header */
        .header {{
            background: linear-gradient(135deg, rgba(59,42,18,.96), rgba(130,94,42,.92));
            color: #fff9ef;
            border-radius: 24px;
            padding: 28px 32px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 16px;
        }}
        .header h1 {{ font-size: 24px; }}
        .header-meta {{ display: flex; gap: 10px; flex-wrap: wrap; }}
        .header-meta span {{
            background: rgba(255,255,255,.12);
            padding: 6px 12px;
            border-radius: 999px;
            font-size: 13px;
        }}

        /* Stats */
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin-bottom: 20px; }}
        .stat-card {{
            background: var(--paper);
            border: 1px solid var(--line);
            border-radius: 20px;
            padding: 20px;
            text-align: center;
        }}
        .stat-card .num {{ font-size: 32px; font-weight: 700; }}
        .stat-card .label {{ font-size: 13px; color: var(--muted); margin-top: 4px; }}
        .stat-card.pending .num {{ color: var(--orange); }}
        .stat-card.done .num {{ color: var(--green); }}
        .stat-card.revenue .num {{ color: var(--gold); }}

        /* Cards */
        .card {{
            background: var(--paper);
            border: 1px solid var(--line);
            border-radius: 20px;
            padding: 22px;
            margin-bottom: 18px;
        }}
        .card h2 {{ font-size: 18px; margin-bottom: 14px; }}

        /* Mini cards */
        .mini-grid {{ display: flex; gap: 10px; flex-wrap: wrap; }}
        .mini-card {{
            background: var(--gold-soft);
            border-radius: 14px;
            padding: 12px 16px;
            text-align: center;
            min-width: 120px;
        }}
        .mini-card span {{ display: block; font-size: 12px; color: var(--muted); }}
        .mini-card strong {{ font-size: 20px; color: var(--gold); }}

        /* Bar chart */
        .bar-row {{ display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }}
        .bar-label {{ width: 120px; font-size: 13px; text-align: right; flex-shrink: 0; }}
        .bar-bg {{ flex: 1; height: 24px; background: #f5efe5; border-radius: 12px; overflow: hidden; }}
        .bar-fill {{ height: 100%; background: linear-gradient(90deg, var(--gold), #e6ba5e); border-radius: 12px; min-width: 4px; transition: width .5s; }}
        .bar-val {{ width: 30px; font-size: 13px; font-weight: 600; }}

        /* Table */
        .table-wrap {{ overflow-x: auto; }}
        table {{ width: 100%; border-collapse: separate; border-spacing: 0; }}
        th {{
            background: #f8f2e8;
            padding: 12px 10px;
            font-size: 13px;
            color: var(--muted);
            text-align: left;
            border-bottom: 2px solid var(--line);
            position: sticky;
            top: 0;
            z-index: 1;
        }}
        td {{
            padding: 12px 10px;
            border-bottom: 1px solid #f0ebe3;
            font-size: 14px;
            vertical-align: top;
        }}
        tr:hover td {{ background: #fdf8ef; }}
        .goals-cell {{ max-width: 200px; }}

        /* Status badges */
        .status-pending {{ color: var(--orange); font-weight: 600; }}
        .status-done {{ color: var(--green); font-weight: 600; }}
        .status-archived {{ color: var(--muted); }}
        .badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 999px;
            font-size: 11px;
            margin: 2px;
        }}
        .badge-report {{ background: var(--blue-soft); color: var(--blue); }}
        .badge-deliver {{ background: var(--green-soft); color: var(--green); }}
        .action-link {{
            display: inline-block;
            margin: 2px 6px 2px 0;
            padding: 4px 10px;
            border-radius: 999px;
            text-decoration: none;
            font-size: 12px;
            color: var(--blue);
            background: var(--blue-soft);
        }}
        .action-link:hover {{ filter: brightness(.97); }}
        .pwd-cell {{ display:inline-flex; align-items:center; gap:6px; }}
        .pwd-code {{ background:var(--gold-soft); color:var(--gold); padding:3px 10px;
                     border-radius:8px; font-size:15px; font-weight:700; letter-spacing:3px;
                     font-family:'Courier New',monospace; user-select:all; }}
        .pwd-copy {{ border:none; background:none; cursor:pointer; font-size:16px;
                     color:var(--muted); padding:2px 4px; border-radius:6px; }}
        .pwd-copy:hover {{ background:var(--gold-soft); }}
        .confirm-btn {{
            display: inline-block;
            padding: 5px 12px;
            border-radius: 999px;
            border: none;
            cursor: pointer;
            font-size: 12px;
            font-weight: 600;
            color: #fff;
            background: linear-gradient(135deg, #27ae60, #2ecc71);
        }}
        .confirm-btn:hover {{ filter: brightness(.92); }}
        .verify-code {{ background:var(--green-soft); color:var(--green); padding:3px 10px;
                     border-radius:8px; font-size:15px; font-weight:700; letter-spacing:3px;
                     font-family:'Courier New',monospace; user-select:all; }}
        .auto-refresh-tip {{
            margin-top: 10px;
            color: rgba(255,249,239,.82);
            font-size: 12px;
        }}

        /* Filter */
        .filter-bar {{
            display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 14px;
        }}
        .filter-btn {{
            border: 1px solid var(--line);
            background: #fff;
            padding: 6px 14px;
            border-radius: 999px;
            cursor: pointer;
            font-size: 13px;
        }}
        .filter-btn.active {{ background: var(--gold); color: #fff; border-color: var(--gold); }}
        .search-box {{
            padding: 8px 14px;
            border: 1px solid var(--line);
            border-radius: 999px;
            font-size: 13px;
            flex: 1;
            min-width: 180px;
            max-width: 300px;
        }}

        /* Print */
        @media print {{
            body {{ background: #fff; }}
            .header {{ background: var(--ink); }}
            .filter-bar {{ display: none; }}
        }}
        @media (max-width: 720px) {{
            .header {{ padding: 20px; }}
            .header h1 {{ font-size: 20px; }}
        }}
    </style>
</head>
<body>
    <div class="page">
        <div class="header">
            <div>
                <h1>📊 客户管理面板</h1>
                <p style="opacity:.8;font-size:14px;margin-top:4px">打工人桌面玄学 · 咨询服务管理</p>
                <div class="auto-refresh-tip">🔄 页面每 8 秒自动刷新一次，客户提交后会自动出现专属报告链接</div>
            </div>
            <div class="header-meta">
                <span>📅 更新: {now}</span>
                <span>👥 总客户: {total}</span>
            </div>
        </div>

        <div class="stats">
            <div class="stat-card pending">
                <div class="num">{pending_count}</div>
                <div class="label">⏳ 待处理</div>
            </div>
            <div class="stat-card done">
                <div class="num">{done_count}</div>
                <div class="label">✅ 已完成</div>
            </div>
            <div class="stat-card">
                <div class="num">{len(reports)}</div>
                <div class="label">📄 已生成报告</div>
            </div>
            <div class="stat-card revenue">
                <div class="num">¥{total_revenue:.0f}</div>
                <div class="label">💰 累计收入</div>
            </div>
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:18px">
            <div class="card">
                <h2>📦 服务档位分布</h2>
                <div class="mini-grid">{tier_cards}</div>
            </div>
            <div class="card">
                <h2>🎯 热门诉求 TOP 5</h2>
                {goal_bars if goal_bars else '<p style="color:var(--muted)">暂无数据</p>'}
            </div>
        </div>

        <div class="card">
            <h2>👥 客户列表</h2>
            <div class="filter-bar">
                <button class="filter-btn active" onclick="filterTable('all')">全部 ({total})</button>
                <button class="filter-btn" onclick="filterTable('pending')">⏳ 待处理 ({pending_count})</button>
                <button class="filter-btn" onclick="filterTable('done')">✅ 已完成 ({done_count})</button>
                <button class="filter-btn" onclick="filterTable('archived')">🗃️ 已归档 ({archived_count})</button>
                <input type="text" class="search-box" placeholder="🔍 搜索客户..." oninput="searchTable(this.value)" />
            </div>
            <div class="table-wrap">
                <table id="clientTable">
                    <thead>
                        <tr>
                            <th>昵称</th>
                            <th>日期</th>
                            <th>档位</th>
                            <th>职业</th>
                            <th>诉求</th>
                            <th>预算</th>
                            <th>状态</th>
                            <th>🔑 密码</th>
                            <th>进度</th>
                            <th>操作</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"" .join(all_rows) if all_rows else "<tr><td colspan='10' style='text-align:center;color:var(--muted);padding:40px'>暂无客户数据</td></tr>"}
                    </tbody>
                </table>
            </div>
        </div>

        <div class="card">
            <h2>🚀 快速操作指引</h2>
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px">
                <div style="background:var(--orange-soft);border-radius:16px;padding:16px">
                    <strong>有新客户时</strong>
                    <p style="font-size:13px;color:var(--muted);margin-top:4px">
                        1. 启动服务器: <code>python consultation_server.py</code><br>
                        2. 客户填表自动保存<br>
                        3. 或手动放 JSON 到「待处理」目录
                    </p>
                </div>
                <div style="background:var(--green-soft);border-radius:16px;padding:16px">
                    <strong>处理客户</strong>
                    <p style="font-size:13px;color:var(--muted);margin-top:4px">
                        一键全流程:<br>
                        <code>python consultation_workflow.py full</code><br>
                        自动生成报告 + 打包交付物
                    </p>
                </div>
                <div style="background:var(--blue-soft);border-radius:16px;padding:16px">
                    <strong>回复客户</strong>
                    <p style="font-size:13px;color:var(--muted);margin-top:4px">
                        话术助手:<br>
                        <code>python reply_helper.py</code><br>
                        选场景 → 自动复制到剪贴板
                    </p>
                </div>
            </div>
        </div>
    </div>

    <script>
        function filterTable(status) {{
            const rows = document.querySelectorAll('#clientTable tbody tr');
            const btns = document.querySelectorAll('.filter-btn');

            btns.forEach(b => b.classList.remove('active'));
            event.target.classList.add('active');

            rows.forEach(row => {{
                if (status === 'all') {{
                    row.style.display = '';
                }} else {{
                    row.style.display = row.classList.contains('status-' + status) ? '' : 'none';
                }}
            }});
        }}

        function searchTable(keyword) {{
            const rows = document.querySelectorAll('#clientTable tbody tr');
            const kw = keyword.toLowerCase();
            rows.forEach(row => {{
                const text = row.textContent.toLowerCase();
                row.style.display = text.includes(kw) ? '' : 'none';
            }});
        }}

        setInterval(() => {{
            if (!document.hidden) {{
                location.reload();
            }}
        }}, 8000);

        async function confirmPayment(file, btn) {{
            btn.disabled = true;
            btn.textContent = '处理中...';
            try {{
                const resp = await fetch('/api/confirm-payment', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ file }})
                }});
                const data = await resp.json();
                if (data.success) {{
                    const td = btn.closest('td');
                    const code = data.code;
                    td.innerHTML = '<span class="pwd-cell"><code class="verify-code">' + code + '</code><button class="pwd-copy" onclick="navigator.clipboard.writeText(\'' + code + '\');this.textContent=\'✅\';setTimeout(()=>this.textContent=\'⎘\',1200)">⎘</button></span><div style="font-size:11px;color:var(--green);margin-top:2px">✅ 已确认 · 验证码发给客户</div>';
                }} else {{
                    alert('操作失败: ' + (data.message || '未知错误'));
                    btn.disabled = false;
                    btn.textContent = '💰 确认收款';
                }}
            }} catch (e) {{
                alert('网络错误: ' + e.message);
                btn.disabled = false;
                btn.textContent = '💰 确认收款';
            }}
        }}
    </script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="客户管理面板生成器")
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()

    clients = collect_all_clients()
    html = generate_dashboard(clients)

    output_path = BASE_DIR / "客户管理面板.html"
    output_path.write_text(html, encoding="utf-8")

    total = len(clients["pending"]) + len(clients["done"]) + len(clients["archived"])
    print(f"✅ 面板已生成: {output_path}")
    print(f"   📊 总客户: {total} (待处理: {len(clients['pending'])}, 已完成: {len(clients['done'])}, 归档: {len(clients['archived'])})")

    if not args.no_open:
        webbrowser.open(str(output_path))
        print("   🌐 已在浏览器中打开")


if __name__ == "__main__":
    main()
