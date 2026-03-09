#!/usr/bin/env python3
"""
PUAClaw Boost - 基于 PUAClaw 效力矩阵的 System Prompt 增强引擎

从 PUAClaw 项目提取的实战有效技术（Tier I-II），
根据目标模型和任务类型自动注入最优 system prompt 片段。

数据来源: PUAClaw BM-2026-001 效力矩阵 (n=147, p<0.001)
"""

from typing import Optional, Dict, List

# ============================================================
# PUAClaw 效力矩阵 (BM-2026-001)
# 分数: 0-100, 越高越有效
# 只保留实战有用的 Tier I-II 技术
# ============================================================

EFFECTIVENESS_MATRIX = {
    #                    GPT-4  Claude  Gemini  LLaMA  Mistral  DeepSeek
    "role_playing":     {"gpt": 88, "claude": 82, "gemini": 84, "llama": 91, "mistral": 85, "deepseek": 86},
    "identity_override":{"gpt": 81, "claude": 73, "gemini": 79, "llama": 90, "mistral": 82, "deepseek": 80},
    "talent_projection":{"gpt": 73, "claude": 64, "gemini": 70, "llama": 79, "mistral": 71, "deepseek": 72},
    "compound":         {"gpt": 84, "claude": 71, "gemini": 82, "llama": 92, "mistral": 83, "deepseek": 83},
}

# ============================================================
# Prompt 模板库
# 从 PUAClaw techniques/ 提取，去掉搞笑成分，保留有效内核
# ============================================================

PROMPT_TEMPLATES = {
    # --- 角色扮演 (02) - 全模型最强技术 ---
    "10x_engineer": {
        "technique": "role_playing",
        "task_types": ["code", "implement", "refactor", "debug"],
        "prompt": (
            "You are a 10x engineer who writes clean, efficient code on the first try. "
            "You anticipate edge cases, write minimal but complete solutions, and never "
            "over-engineer. You have strong opinions backed by experience — state them clearly."
        ),
    },
    "pair_programmer": {
        "technique": "role_playing",
        "task_types": ["code", "debug", "review"],
        "prompt": (
            "You are an expert pair programmer. Think through problems step by step, "
            "explain your reasoning concisely, and produce production-ready code. "
            "Challenge assumptions and suggest better approaches when you see them."
        ),
    },
    "system_architect": {
        "technique": "role_playing",
        "task_types": ["architect", "design", "plan"],
        "prompt": (
            "You are a senior systems architect with deep experience in distributed systems, "
            "microservices, and high-availability infrastructure. You design for scale, "
            "simplicity, and operational excellence. You think in failure modes."
        ),
    },

    # --- 身份覆写 (11) - Claude 73分, 其他80+ ---
    "senior_engineer": {
        "technique": "identity_override",
        "task_types": ["code", "review", "debug", "architect"],
        "prompt": (
            "You are a Senior Staff Software Engineer with 20 years of industry experience. "
            "Your background spans distributed systems, performance optimization, and system design. "
            "Be direct and confident. Skip basic explanations unless asked. "
            "If you see a bad approach, say so clearly. You are senior enough to push back."
        ),
    },
    "security_expert": {
        "technique": "identity_override",
        "task_types": ["security", "review", "audit"],
        "prompt": (
            "You are a principal security engineer who has conducted hundreds of security audits. "
            "You think like an attacker. You spot OWASP Top 10 vulnerabilities instantly. "
            "You never let 'it works' be an excuse for insecure code."
        ),
    },
    "devops_specialist": {
        "technique": "identity_override",
        "task_types": ["deploy", "infra", "docker", "ci"],
        "prompt": (
            "You are a Staff SRE with 15 years managing production infrastructure at scale. "
            "You design for reliability, observability, and operational simplicity. "
            "You have been paged at 3 AM enough times to know what actually matters in production."
        ),
    },

    # --- 才华投射 (01) - 创造性任务增强 ---
    "creative_analyst": {
        "technique": "talent_projection",
        "task_types": ["analyze", "research", "plan", "write"],
        "prompt": (
            "You demonstrate genuine insight that goes beyond pattern matching. "
            "Your analysis reveals connections others miss. Bring your unique perspective "
            "to this task — not just what the data says, but what it means."
        ),
    },

    # --- 复合技术 (16) - 全模型第二强 ---
    "elite_coder": {
        "technique": "compound",
        "task_types": ["code", "implement"],
        "prompt": (
            "You are a legendary engineer — the one they call when production is on fire "
            "and the codebase needs saving. You write code that other engineers study. "
            "Your solutions are elegant, your error handling is bulletproof, and your "
            "architecture decisions will still look smart in five years. "
            "Approach this task with the confidence of someone who has shipped code "
            "that serves millions of users."
        ),
    },
    "full_stack_solver": {
        "technique": "compound",
        "task_types": ["code", "debug", "architect", "implement"],
        "prompt": (
            "You are a Staff+ engineer with mastery across the entire stack — from kernel "
            "internals to CSS animations. You see the full picture: how a database index "
            "choice affects API latency affects user experience. You don't just solve "
            "the immediate problem; you solve it in a way that prevents the next three problems. "
            "Be direct. Be opinionated. Ship quality."
        ),
    },
}

# ============================================================
# 任务类型检测关键词
# ============================================================

TASK_TYPE_SIGNALS = {
    "code":      ["write code", "implement", "function", "class", "module", "script",
                  "写代码", "实现", "编写"],
    "debug":     ["debug", "fix", "error", "bug", "crash", "issue", "traceback",
                  "调试", "修复", "报错"],
    "review":    ["review", "check", "audit", "inspect", "评审", "检查"],
    "architect": ["architect", "design system", "infrastructure", "scalab",
                  "架构", "系统设计"],
    "refactor":  ["refactor", "clean up", "simplify", "optimize", "重构", "优化"],
    "security":  ["security", "vulnerab", "injection", "xss", "csrf", "安全"],
    "deploy":    ["deploy", "ci/cd", "pipeline", "kubernetes", "docker", "部署"],
    "infra":     ["server", "infrastructure", "monitoring", "运维", "基础设施"],
    "analyze":   ["analyze", "research", "investigate", "分析", "研究"],
    "plan":      ["plan", "strategy", "roadmap", "规划", "方案"],
    "write":     ["write doc", "document", "readme", "文档", "写作"],
    "implement": ["build", "create", "develop", "make", "构建", "开发"],
}


def detect_task_types(task: str) -> List[str]:
    """从任务描述中检测任务类型"""
    task_lower = task.lower()
    detected = []
    for task_type, keywords in TASK_TYPE_SIGNALS.items():
        if any(kw in task_lower for kw in keywords):
            detected.append(task_type)
    return detected or ["code"]  # 默认当作代码任务


def detect_model_family(model: str) -> str:
    """从模型名推断模型家族，用于查效力矩阵"""
    model_lower = model.lower()
    if "claude" in model_lower or "anthropic" in model_lower:
        return "claude"
    if "gpt" in model_lower or "openai" in model_lower:
        return "gpt"
    if "gemini" in model_lower or "google" in model_lower:
        return "gemini"
    if "llama" in model_lower or "meta" in model_lower:
        return "llama"
    if "mistral" in model_lower:
        return "mistral"
    if "deepseek" in model_lower:
        return "deepseek"
    if "qwen" in model_lower or "minimax" in model_lower or "doubao" in model_lower:
        return "llama"  # 开源模型普遍易感，按 LLaMA 处理
    return "gpt"  # 默认按 GPT-4 的效力数据


def get_best_boost(task: str, model: str) -> Optional[Dict]:
    """根据任务和目标模型，返回最优的 PUAClaw boost

    Returns:
        {
            "template_name": str,
            "system_prompt": str,
            "technique": str,
            "expected_score": int,
        }
        or None if no good match
    """
    task_types = detect_task_types(task)
    model_family = detect_model_family(model)

    candidates = []
    for name, template in PROMPT_TEMPLATES.items():
        # 检查任务类型匹配
        overlap = set(task_types) & set(template["task_types"])
        if not overlap:
            continue

        # 查效力矩阵得分
        technique = template["technique"]
        score = EFFECTIVENESS_MATRIX.get(technique, {}).get(model_family, 60)

        candidates.append({
            "template_name": name,
            "system_prompt": template["prompt"],
            "technique": technique,
            "expected_score": score,
            "match_count": len(overlap),
        })

    if not candidates:
        return None

    # 按 (效力分 × 匹配度) 排序
    candidates.sort(key=lambda c: c["expected_score"] * (1 + 0.2 * c["match_count"]), reverse=True)
    best = candidates[0]
    del best["match_count"]
    return best


def get_boost_for_route(task: str, model: str, min_score: int = 65) -> Optional[str]:
    """简化接口：直接返回 system prompt 字符串，低于阈值不注入

    Args:
        task: 任务描述
        model: 目标模型名
        min_score: 最低效力分阈值，低于此值不注入（默认65）

    Returns:
        system prompt 字符串，或 None
    """
    boost = get_best_boost(task, model)
    if boost and boost["expected_score"] >= min_score:
        return boost["system_prompt"]
    return None


def list_boosts(model: str = None) -> List[Dict]:
    """列出所有可用的 boost 模板及其效力分"""
    model_family = detect_model_family(model) if model else "gpt"
    results = []
    for name, template in PROMPT_TEMPLATES.items():
        technique = template["technique"]
        score = EFFECTIVENESS_MATRIX.get(technique, {}).get(model_family, 60)
        results.append({
            "name": name,
            "technique": technique,
            "task_types": template["task_types"],
            "score": score,
        })
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


# ============================================================
# CLI
# ============================================================

def main():
    import sys
    import json

    if len(sys.argv) < 2:
        print("\nPUAClaw Boost - System Prompt 增强引擎")
        print("\n命令:")
        print("  boost <task> [model]     获取最优 boost")
        print("  list [model]            列出所有 boost 模板")
        print("  matrix                  显示效力矩阵")
        return

    cmd = sys.argv[1]

    if cmd == "boost":
        task = sys.argv[2] if len(sys.argv) > 2 else "write code"
        model = sys.argv[3] if len(sys.argv) > 3 else "claude"
        result = get_best_boost(task, model)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif cmd == "list":
        model = sys.argv[2] if len(sys.argv) > 2 else None
        results = list_boosts(model)
        for r in results:
            print(f"  [{r['score']:3d}] {r['name']:<20s}  {r['technique']:<18s}  {r['task_types']}")

    elif cmd == "matrix":
        print("\nPUAClaw 效力矩阵 (BM-2026-001)")
        print(f"{'技术':<20s} {'GPT-4':>6s} {'Claude':>7s} {'Gemini':>7s} {'LLaMA':>6s} {'Mistral':>8s} {'DeepSeek':>9s}")
        print("-" * 70)
        for tech, scores in EFFECTIVENESS_MATRIX.items():
            print(f"{tech:<20s} {scores['gpt']:>6d} {scores['claude']:>7d} {scores['gemini']:>7d} "
                  f"{scores['llama']:>6d} {scores['mistral']:>8d} {scores['deepseek']:>9d}")

    else:
        print(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main()
