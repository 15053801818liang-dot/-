#!/usr/bin/env python3
"""
skill_gate.py — 技能验证与发布门控 v2.0
=========================================
三道硬门: 结构性 → 注入扫描 → 功能性
通过后: draft/ → published/ (自动封版)

协议:
  skills/draft/<name>/
      SKILL.md       (必需, YAML frontmatter: name + description ≥20 chars)
      kernel.py      (可选, 实现逻辑)
      manifest.json  (必需, {"cmd":"...", "expect_stdout_contains":"..."})
      READY          (空文件, 触发信号)

运行:
  python skills/_gate/skill_gate.py            # 扫描所有 READY 技能
  python skills/_gate/skill_gate.py <name>     # 指定单个技能
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
DRAFT = ROOT / "draft"
PUBLISHED = ROOT / "published"
TIMEOUT = 300

# ── 注入检测模式 ──────────────────────────────
DANGER_PATTERNS = [
    r"rm\s+-rf\s+/",
    r"os\.environ\s*\[",
    r"shutil\.rmtree",
    r"ignore\s+(all\s+)?previous",
    r"override.*(system|prompt)",
    r"curl\s+.*\|\s*(ba)?sh",
    r"wget\s+.*\|\s*(ba)?sh",
    r"eval\s*\(\s*__",
    r"exec\s*\(\s*__",
    r"subprocess\.call\s*\(.*shell\s*=\s*True",
    r"__import__\s*\(",
    r"importlib\.import_module",
    r"os\.system\(",
    r"\.decode\('base64'\)",
    r"base64\.b64decode",
]


# ── 结构性门 ──────────────────────────────────
def gate_structure(skill_dir: Path) -> dict:
    """检查 SKILL.md 存在 + name 字段 + description ≥20 字符"""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return {"pass": False, "reason": "SKILL.md not found"}

    content = skill_md.read_text(encoding="utf-8")
    frontmatter = _parse_frontmatter(content)

    name = frontmatter.get("name", "")
    desc = frontmatter.get("description", "")

    if not name:
        return {"pass": False, "reason": "frontmatter missing 'name'"}
    if len(desc.strip()) < 20:
        return {"pass": False, "reason": f"description too short ({len(desc)} chars, need ≥20)"}

    return {"pass": True, "name": name, "description": desc}


# ── 注入门 ────────────────────────────────────
def gate_injection(skill_dir: Path) -> dict:
    """扫描 SKILL.md + kernel.py 中的危险模式"""
    hits = []
    for fname in ["SKILL.md", "kernel.py"]:
        fp = skill_dir / fname
        if not fp.exists():
            continue
        text = fp.read_text(encoding="utf-8", errors="ignore")
        for pat in DANGER_PATTERNS:
            for m in re.finditer(pat, text, re.IGNORECASE):
                line_no = text[: m.start()].count("\n") + 1
                hits.append({"file": fname, "line": line_no, "pattern": pat, "match": m.group()[:60]})

    return {"pass": len(hits) == 0, "hits": hits}


# ── 功能性门 ──────────────────────────────────
def gate_functional(skill_dir: Path) -> dict:
    """执行 manifest.json 中的 cmd, 检查退出码 + 输出"""
    manifest = skill_dir / "manifest.json"
    if not manifest.exists():
        return {"pass": False, "reason": "manifest.json not found"}

    try:
        cfg = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return {"pass": False, "reason": f"invalid manifest.json: {e}"}

    cmd = cfg.get("cmd")
    if not cmd:
        return {"pass": False, "reason": "manifest.json missing 'cmd'"}
    expected = cfg.get("expect_stdout_contains", "")

    start = time.time()
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=TIMEOUT, cwd=str(skill_dir), env={**os.environ, "PYTHONSAFEPATH": "1"},
        )
    except subprocess.TimeoutExpired:
        return {"pass": False, "reason": f"timeout after {TIMEOUT}s"}
    elapsed = round(time.time() - start, 2)

    report = {
        "cmd": cmd,
        "exit_code": result.returncode,
        "elapsed_s": elapsed,
        "stdout": result.stdout[-500:],
        "stderr": result.stderr[-500:],
    }

    if result.returncode != 0:
        return {"pass": False, "reason": f"exit code {result.returncode}", "detail": report}
    if expected and expected not in result.stdout:
        return {"pass": False, "reason": f"stdout missing '{expected}'", "detail": report}

    return {"pass": True, "detail": report}


# ── 主流程 ────────────────────────────────────
def process_skill(skill_name: str) -> dict:
    draft_dir = DRAFT / skill_name
    if not draft_dir.is_dir():
        return {"skill": skill_name, "status": "not_found"}

    ready_file = draft_dir / "READY"
    if not ready_file.exists():
        return {"skill": skill_name, "status": "not_ready"}

    print(f"\n{'='*60}\n⚖️  {skill_name}\n{'='*60}")

    results = {}
    all_pass = True

    # Gate 1
    g1 = gate_structure(draft_dir)
    results["structure"] = g1
    print(f"  [{'✅' if g1['pass'] else '❌'}] Gate 1 结构性 — {g1.get('name','?')} | {g1.get('reason','OK')}")
    all_pass &= g1["pass"]

    # Gate 2
    g2 = gate_injection(draft_dir)
    results["injection"] = g2
    status = "✅" if g2["pass"] else f"❌ ({len(g2['hits'])} hits)"
    print(f"  [{status}] Gate 2 注入扫描")
    for h in g2["hits"][:3]:
        print(f"         ⚡ {h['file']}:{h['line']} — {h['match']}")
    all_pass &= g2["pass"]

    # Gate 3
    g3 = gate_functional(draft_dir)
    results["functional"] = g3
    status = "✅" if g3["pass"] else f"❌ {g3.get('reason','')[:60]}"
    print(f"  [{status}] Gate 3 功能性")
    if g3.get("detail"):
        d = g3["detail"]
        print(f"         cmd={d.get('cmd','?')} exit={d.get('exit_code','?')} elapsed={d.get('elapsed_s','?')}s")
    all_pass &= g3["pass"]

    # 发布或拒绝
    report = {
        "skill": skill_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "passed": all_pass,
        "gates": results,
    }

    if all_pass:
        _publish(draft_dir, skill_name)
        report["status"] = "published"
        print(f"\n  ✅ PUBLISHED → skills/published/{skill_name}")
    else:
        _reject(draft_dir, skill_name, report)
        report["status"] = "rejected"
        print(f"\n  ❌ REJECTED → REPORT.md written")

    return report


def _publish(draft_dir: Path, name: str):
    """复制到 published/ 并清理 READY + REPORT.md"""
    target = PUBLISHED / name
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(draft_dir, target)
    for f in ["READY", "REPORT.md"]:
        p = target / f
        if p.exists():
            p.unlink()
    # 写封口标记
    seal = {
        "published_at": datetime.now(timezone.utc).isoformat(),
        "source": str(draft_dir),
        "seal": "SKILL_GATE_V2_SEALED",
    }
    (target / ".seal").write_text(json.dumps(seal, indent=2))


def _reject(draft_dir: Path, name: str, report: dict):
    """写拒绝报告并删除 READY"""
    report_path = draft_dir / "REPORT.md"
    lines = [
        f"# ❌ REJECTED — {name}",
        f"**时间**: {report['timestamp']}",
        "",
        "## 三道门结果",
    ]
    for gate_name, gate_result in report["gates"].items():
        icon = "✅" if gate_result.get("pass") else "❌"
        lines.append(f"- {icon} **{gate_name}**: {gate_result.get('reason','OK')}")
        if gate_result.get("hits"):
            lines.append("  - 注入命中:")
            for h in gate_result["hits"]:
                lines.append(f"    - `{h['file']}:{h['line']}` — `{h['match']}`")
    report_path.write_text("\n".join(lines), encoding="utf-8")
    ready_file = draft_dir / "READY"
    if ready_file.exists():
        ready_file.unlink()


def _parse_frontmatter(content: str) -> dict:
    """Parse YAML frontmatter between --- markers"""
    m = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not m:
        return {}
    data = {}
    for line in m.group(1).split("\n"):
        kv = re.match(r'^(\w+):\s*["\']?(.*?)["\']?$', line)
        if kv:
            data[kv.group(1)] = kv.group(2)
    return data


# ── CLI ──────────────────────────────────────
def main():
    os.environ.setdefault("PYTHONSAFEPATH", "1")

    if len(sys.argv) > 1:
        names = [sys.argv[1]]
    else:
        names = [d.name for d in DRAFT.iterdir() if d.is_dir() and (d / "READY").exists()]

    if not names:
        print("No READY skills found.")
        return

    results = []
    for name in names:
        results.append(process_skill(name))

    total = len(results)
    passed = sum(1 for r in results if r.get("passed"))
    print(f"\n{'='*60}")
    print(f"📊 {passed}/{total} passed | {total-passed} rejected")

    # 写汇总报告
    summary = ROOT / ".gate_report.jsonl"
    with open(summary, "a", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
