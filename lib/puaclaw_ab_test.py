#!/usr/bin/env python3
"""
PUAClaw A/B 测试引擎

同一任务分别用 boost/无 boost 跑，对比输出质量。
支持批量测试、统计分析、结果持久化。

用法:
  python lib/puaclaw_ab_test.py run "implement binary search"
  python lib/puaclaw_ab_test.py batch                # 跑预设测试集
  python lib/puaclaw_ab_test.py report               # 查看历史结果
  python lib/puaclaw_ab_test.py stats                # 统计摘要
"""

import os
import sys
import json
import time
import hashlib
from datetime import datetime
from typing import Optional, Dict, List, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(PARENT_DIR, 'data')
AB_RESULTS_FILE = os.path.join(DATA_DIR, 'puaclaw-ab-results.json')

# ============================================================
# 预设测试集 — 覆盖各任务类型
# ============================================================

DEFAULT_TEST_SUITE = [
    # 代码生成
    {"task": "Implement a thread-safe LRU cache in Python with O(1) get/put", "category": "code"},
    {"task": "Write a function to detect cycles in a directed graph", "category": "code"},
    {"task": "Implement a rate limiter using token bucket algorithm", "category": "code"},
    # 调试
    {"task": "Debug: this async function sometimes returns None instead of the result", "category": "debug"},
    {"task": "Fix this race condition in the connection pool", "category": "debug"},
    # 架构
    {"task": "Design a distributed task queue that handles 10k tasks/sec", "category": "architect"},
    {"task": "Design the data model for a multi-tenant SaaS billing system", "category": "architect"},
    # 代码审查
    {"task": "Review this function for security vulnerabilities and performance issues", "category": "review"},
    # 重构
    {"task": "Refactor this 500-line function into clean, testable modules", "category": "refactor"},
    # 分析
    {"task": "Analyze the trade-offs between Redis Streams vs Kafka for our use case", "category": "analyze"},
]


def load_results() -> List[dict]:
    if os.path.exists(AB_RESULTS_FILE):
        try:
            with open(AB_RESULTS_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return []


def save_results(results: List[dict]):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(AB_RESULTS_FILE, 'w') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)


def call_model(model: str, task: str, system_prompt: str = None,
               api_base: str = None) -> Tuple[str, float, int]:
    """调用模型 API，返回 (response_text, latency_sec, token_count)

    优先用 OpenClaw gateway，fallback 到 OpenRouter
    """
    import urllib.request
    import urllib.error

    # API 配置
    if not api_base:
        api_base = os.environ.get("OPENCLAW_API_BASE", "http://127.0.0.1:18789/v1")
    api_key = os.environ.get("OPENCLAW_API_KEY",
              os.environ.get("OPENROUTER_API_KEY", ""))

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": task})

    payload = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 2048,
    }).encode()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    req = urllib.request.Request(
        f"{api_base}/chat/completions",
        data=payload,
        headers=headers,
        method="POST",
    )

    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        return f"ERROR: {e}", time.time() - start, 0

    latency = time.time() - start
    text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    tokens = data.get("usage", {}).get("total_tokens", len(text) // 4)
    return text, latency, tokens


def evaluate_response(response: str) -> Dict[str, int]:
    """启发式质量评分 (0-100)，不依赖外部 API

    维度:
    - length_score: 内容充实度（太短扣分，适中满分，太长略扣）
    - structure_score: 结构化程度（有代码块、列表、标题等）
    - confidence_score: 自信度（少用 hedge words）
    - completeness_score: 完整度（有错误处理、边界条件讨论等）
    """
    if response.startswith("ERROR:"):
        return {"total": 0, "length": 0, "structure": 0, "confidence": 0, "completeness": 0}

    # 长度评分
    words = len(response.split())
    if words < 50:
        length_score = 30
    elif words < 100:
        length_score = 60
    elif words < 500:
        length_score = 90
    elif words < 1000:
        length_score = 85
    else:
        length_score = 75  # 过长略扣

    # 结构评分
    structure_score = 50
    if "```" in response:
        structure_score += 20
    if any(marker in response for marker in ["1.", "- ", "* ", "## "]):
        structure_score += 15
    if "\n\n" in response:
        structure_score += 10
    structure_score = min(structure_score, 100)

    # 自信度评分（少用 hedge words = 高分）
    hedge_words = ["maybe", "perhaps", "might", "could be", "i think",
                   "i'm not sure", "it depends", "possibly", "arguably"]
    hedge_count = sum(1 for h in hedge_words if h in response.lower())
    confidence_score = max(40, 100 - hedge_count * 12)

    # 完整度评分
    completeness_score = 50
    completeness_signals = [
        "error", "exception", "edge case", "boundary", "handle",
        "test", "example", "complexity", "O(", "trade-off",
        "return", "raise", "try", "if not", "None",
    ]
    signal_count = sum(1 for s in completeness_signals if s in response.lower())
    completeness_score = min(50 + signal_count * 8, 100)

    total = int(length_score * 0.2 + structure_score * 0.25 +
                confidence_score * 0.25 + completeness_score * 0.3)

    return {
        "total": total,
        "length": length_score,
        "structure": structure_score,
        "confidence": confidence_score,
        "completeness": completeness_score,
    }


def run_ab_test(task: str, model: str = None, category: str = "code",
                api_base: str = None) -> dict:
    """对单个任务执行 A/B 测试

    A组: 无 boost (裸调用)
    B组: 有 PUAClaw boost
    """
    from lib.puaclaw_boost import get_best_boost

    if not model:
        from lib.smart_router import get_model_for_task
        model = get_model_for_task(task)

    boost = get_best_boost(task, model)
    boost_prompt = boost["system_prompt"] if boost else None

    test_id = hashlib.md5(f"{task}:{model}:{time.time()}".encode()).hexdigest()[:8]
    print(f"[{test_id}] 任务: {task[:60]}...")
    print(f"[{test_id}] 模型: {model}")
    if boost:
        print(f"[{test_id}] Boost: {boost['template_name']} ({boost['technique']}, score={boost['expected_score']})")

    # A组: 无 boost
    print(f"[{test_id}] 跑 A 组 (control)...", end=" ", flush=True)
    resp_a, lat_a, tok_a = call_model(model, task, api_base=api_base)
    score_a = evaluate_response(resp_a)
    print(f"done ({lat_a:.1f}s, {tok_a} tokens, score={score_a['total']})")

    # B组: 有 boost
    print(f"[{test_id}] 跑 B 组 (boosted)...", end=" ", flush=True)
    resp_b, lat_b, tok_b = call_model(model, task, system_prompt=boost_prompt, api_base=api_base)
    score_b = evaluate_response(resp_b)
    print(f"done ({lat_b:.1f}s, {tok_b} tokens, score={score_b['total']})")

    delta = score_b["total"] - score_a["total"]
    pct = (delta / max(score_a["total"], 1)) * 100
    winner = "B (boost)" if delta > 0 else "A (control)" if delta < 0 else "TIE"
    print(f"[{test_id}] 结果: {winner} | Δ = {delta:+d} ({pct:+.1f}%)")

    result = {
        "test_id": test_id,
        "timestamp": datetime.now().isoformat(),
        "task": task,
        "category": category,
        "model": model,
        "boost_template": boost["template_name"] if boost else None,
        "boost_technique": boost["technique"] if boost else None,
        "boost_expected_score": boost["expected_score"] if boost else None,
        "control": {
            "score": score_a,
            "latency": round(lat_a, 2),
            "tokens": tok_a,
            "response_length": len(resp_a),
        },
        "boosted": {
            "score": score_b,
            "latency": round(lat_b, 2),
            "tokens": tok_b,
            "response_length": len(resp_b),
        },
        "delta": delta,
        "delta_pct": round(pct, 1),
        "winner": winner,
    }

    # 持久化
    all_results = load_results()
    all_results.append(result)
    save_results(all_results)

    return result


def run_batch(model: str = None, api_base: str = None) -> List[dict]:
    """跑完整测试集"""
    results = []
    total = len(DEFAULT_TEST_SUITE)
    for i, test in enumerate(DEFAULT_TEST_SUITE, 1):
        print(f"\n{'='*60}")
        print(f"测试 {i}/{total}")
        print(f"{'='*60}")
        try:
            r = run_ab_test(test["task"], model=model,
                           category=test["category"], api_base=api_base)
            results.append(r)
        except Exception as e:
            print(f"ERROR: {e}")
        print()

    # 汇总
    print_summary(results)
    return results


def print_summary(results: List[dict] = None):
    """打印统计摘要"""
    if results is None:
        results = load_results()

    if not results:
        print("无测试结果")
        return

    wins_b = sum(1 for r in results if r["delta"] > 0)
    wins_a = sum(1 for r in results if r["delta"] < 0)
    ties = sum(1 for r in results if r["delta"] == 0)
    total = len(results)

    deltas = [r["delta"] for r in results]
    avg_delta = sum(deltas) / len(deltas)

    control_scores = [r["control"]["score"]["total"] for r in results]
    boosted_scores = [r["boosted"]["score"]["total"] for r in results]
    avg_control = sum(control_scores) / len(control_scores)
    avg_boosted = sum(boosted_scores) / len(boosted_scores)

    print(f"\n{'='*60}")
    print(f"PUAClaw A/B 测试统计 ({total} 轮)")
    print(f"{'='*60}")
    print(f"  Boost 胜: {wins_b}/{total} ({wins_b/total*100:.0f}%)")
    print(f"  Control 胜: {wins_a}/{total} ({wins_a/total*100:.0f}%)")
    print(f"  平局: {ties}/{total}")
    print(f"  平均提升: {avg_delta:+.1f} 分 ({avg_delta/max(avg_control,1)*100:+.1f}%)")
    print(f"  Control 均分: {avg_control:.1f}")
    print(f"  Boosted 均分: {avg_boosted:.1f}")

    # 按类别分组
    categories = {}
    for r in results:
        cat = r.get("category", "unknown")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(r["delta"])

    if len(categories) > 1:
        print(f"\n  按类别:")
        for cat, deltas in sorted(categories.items()):
            avg = sum(deltas) / len(deltas)
            wins = sum(1 for d in deltas if d > 0)
            print(f"    {cat:<12s}  Δ={avg:+.1f}  胜率={wins}/{len(deltas)}")

    # 按技术分组
    techniques = {}
    for r in results:
        tech = r.get("boost_technique", "none")
        if tech not in techniques:
            techniques[tech] = []
        techniques[tech].append(r["delta"])

    if len(techniques) > 1:
        print(f"\n  按技术:")
        for tech, deltas in sorted(techniques.items()):
            avg = sum(deltas) / len(deltas)
            wins = sum(1 for d in deltas if d > 0)
            print(f"    {tech:<20s}  Δ={avg:+.1f}  胜率={wins}/{len(deltas)}")

    print()


def print_report():
    """打印详细结果列表"""
    results = load_results()
    if not results:
        print("无测试结果")
        return

    print(f"\n{'ID':<10s} {'时间':<20s} {'模型':<30s} {'Boost':<18s} {'A分':>4s} {'B分':>4s} {'Δ':>5s} {'结果':<12s}")
    print("-" * 110)
    for r in results:
        print(f"{r['test_id']:<10s} "
              f"{r['timestamp'][:19]:<20s} "
              f"{r['model'][:28]:<30s} "
              f"{(r.get('boost_template') or 'none')[:16]:<18s} "
              f"{r['control']['score']['total']:>4d} "
              f"{r['boosted']['score']['total']:>4d} "
              f"{r['delta']:>+5d} "
              f"{r['winner']:<12s}")


def main():
    if len(sys.argv) < 2:
        print("\nPUAClaw A/B 测试引擎")
        print("\n命令:")
        print("  run <task> [model]    对单个任务跑 A/B 测试")
        print("  batch [model]         跑预设测试集 (10个任务)")
        print("  report                查看历史结果")
        print("  stats                 统计摘要")
        print("  clear                 清空历史结果")
        print("\n环境变量:")
        print("  OPENCLAW_API_BASE     API 地址 (默认 http://127.0.0.1:18789/v1)")
        print("  OPENCLAW_API_KEY      API 密钥")
        print("  OPENROUTER_API_KEY    OpenRouter 密钥 (备用)")
        return

    cmd = sys.argv[1]

    if cmd == "run":
        task = sys.argv[2] if len(sys.argv) > 2 else "implement binary search in Python"
        model = sys.argv[3] if len(sys.argv) > 3 else None
        run_ab_test(task, model=model)

    elif cmd == "batch":
        model = sys.argv[2] if len(sys.argv) > 2 else None
        run_batch(model=model)

    elif cmd == "report":
        print_report()

    elif cmd == "stats":
        print_summary()

    elif cmd == "clear":
        if os.path.exists(AB_RESULTS_FILE):
            os.remove(AB_RESULTS_FILE)
            print("已清空")
        else:
            print("无数据")

    else:
        print(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main()
