#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kilo Proxy ペイロードログ分析スクリプト
蓄積された JSON ログから、KVキャッシュの無効化（Prefill崩壊）トリガーや、
トークン消費のボトルネックを自動でスキャン・分析し統計レポートを出力します。
"""

import os
import glob
import json
import re
import sys
from datetime import datetime

# デフォルトのログディレクトリ
DEFAULT_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kilo_logs")

def serialize_request_for_caching(data):
    """kilo_proxy.py と同じ形式でリクエストを平坦化テキストにシリアライズする。"""
    parts = []
    # 1. ツール定義
    if 'tools' in data:
        parts.append(f"[TOOLS]\n{json.dumps(data['tools'], sort_keys=True)}")
    
    # 2. メッセージ履歴
    parts.append("[MESSAGES]")
    for msg in data.get('messages', []):
        role = msg.get('role', '')
        content = msg.get('content', '')
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if part.get('type') == 'text':
                    text_parts.append(part.get('text', ''))
            content_str = "\n".join(text_parts)
        else:
            content_str = str(content)
        parts.append(f"<{role}>\n{content_str}\n</{role}>")
    
    return "\n".join(parts)


def get_lcp_len(s1, s2):
    """2つの文字列の最長共通プレフィックス（LCP）の長さを計算する。"""
    min_len = min(len(s1), len(s2))
    lcp_len = 0
    for i in range(min_len):
        if s1[i] != s2[i]:
            break
        lcp_len += 1
    return lcp_len


def get_breakpoint_context(s2, lcp_len):
    """不一致が発生した直後のコンテキストを抽出する。"""
    if lcp_len == 0:
        return "No common prefix."
    start = max(0, lcp_len - 15)
    end = min(len(s2), lcp_len + 35)
    breakpoint_context = s2[start:end]
    marker_idx = lcp_len - start
    marked_context = (
        breakpoint_context[:marker_idx] 
        + " 💥[BREAKPOINT]💥 " 
        + breakpoint_context[marker_idx:]
    )
    return marked_context.replace('\n', '\\n')


def classify_trigger(context_str):
    """分岐点の文字列から、キャッシュ崩壊トリガーを分類する。"""
    if "environment_details" in context_str or "Current time" in context_str or "Working directory" in context_str:
        return "Environment details change (Time/Workspace)"
    elif "[TOOLS]" in context_str or "type" in context_str and "function" in context_str:
        return "Tool definition change (MCP or built-in tools)"
    elif "<system>" in context_str or "SYSTEM_DIRECTIVE" in context_str:
        return "System prompt change"
    elif "<user>" in context_str or "<assistant>" in context_str:
        # 会話が途中で変化した、あるいは編集された場合
        return "Conversation history modification / insertion"
    else:
        return "Other dynamic context changes"


def extract_sections_size(data):
    """リクエスト内の各セクションの文字数を計算する。"""
    system_size = 0
    tools_size = 0
    history_size = 0
    new_input_size = 0
    env_details_size = 0

    # 1. ツール定義のサイズ
    if 'tools' in data:
        tools_size = len(json.dumps(data['tools']))

    # 2. メッセージのサイズ
    messages = data.get('messages', [])
    for i, msg in enumerate(messages):
        content = msg.get('content', '')
        content_str = ""
        if isinstance(content, list):
            for part in content:
                if part.get('type') == 'text':
                    content_str += part.get('text', '')
        else:
            content_str = str(content)

        role = msg.get('role', '')
        
        # 環境情報のサイズを抽出
        if "<environment_details>" in content_str:
            match = re.search(r'<environment_details>.*?</environment_details>', content_str, re.DOTALL)
            if match:
                env_details_size += len(match.group(0))

        if role == 'system':
            system_size += len(content_str)
        elif i == len(messages) - 1:
            # 最末尾は新しいユーザー入力
            new_input_size += len(content_str)
        else:
            # それ以外は過去の会話履歴
            history_size += len(content_str)

    return {
        "system": system_size,
        "tools": tools_size,
        "history": history_size,
        "new_input": new_input_size,
        "env_details": env_details_size,
        "total": system_size + tools_size + history_size + new_input_size
    }


def analyze_directory(log_dir):
    """指定されたディレクトリのJSONログをスキャンし分析する。"""
    print(f"=== Kilo Proxy ログ分析開始 ===")
    print(f"対象ディレクトリ: {log_dir}")
    
    # タイムスタンプ順でファイルをリスト
    pattern = os.path.join(log_dir, "payload_*.json")
    files = sorted(glob.glob(pattern))
    
    if not files:
        print("分析対象の payload_*.json ログファイルが見つかりません。")
        return

    print(f"検出ファイル数: {len(files)} 件")
    print("-" * 60)

    total_stats = {
        "system": 0, "tools": 0, "history": 0, "new_input": 0, "env_details": 0, "total": 0
    }
    
    results = []
    
    # 各ファイルのセクションサイズを解析
    for filepath in files:
        filename = os.path.basename(filepath)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            sizes = extract_sections_size(data)
            serialized_text = serialize_request_for_caching(data)
            
            for k in total_stats:
                total_stats[k] += sizes[k]
                
            results.append({
                "filename": filename,
                "sizes": sizes,
                "serialized_text": serialized_text,
                "raw_data": data
            })
        except Exception as e:
            print(f"エラー (ファイル読み込み失敗 {filename}): {e}")

    num_files = len(results)
    
    # 平均サイズと比率の計算
    avg_stats = {k: v / num_files for k, v in total_stats.items()}
    print("\n--- [1] 平均コンテキスト構成 (文字数) ---")
    for k, avg_val in avg_stats.items():
        if k == "total":
            continue
        pct = (avg_val / avg_stats["total"]) * 100 if avg_stats["total"] > 0 else 0
        est_tokens = avg_val / 3
        print(f"  {k.upper():<12}: 平均 {avg_val:8.1f} 文字 ({pct:5.1f}%) [推定 {est_tokens:6.0f} tokens]")
    print(f"  {'TOTAL':<12}: 平均 {avg_stats['total']:8.1f} 文字         [推定 {avg_stats['total']/3:6.0f} tokens]")
    print(f"  ※内訳: 環境情報 (<environment_details>) 平均 {avg_stats['env_details']:8.1f} 文字")

    # キャッシュ維持率と崩壊原因の分析（時系列ペアの比較）
    print("\n--- [2] KVキャッシュ崩壊原因と一致率の分析 ---")
    lcp_ratios = []
    triggers = {}
    breakpoints = []

    for i in range(1, len(results)):
        prev = results[i-1]
        curr = results[i]
        
        s1 = prev["serialized_text"]
        s2 = curr["serialized_text"]
        
        lcp = get_lcp_len(s1, s2)
        ratio = (lcp / len(s2)) * 100 if len(s2) > 0 else 0
        lcp_ratios.append(ratio)
        
        if ratio < 99.9: # キャッシュ崩壊あり
            bp_ctx = get_breakpoint_context(s2, lcp)
            trigger_type = classify_trigger(bp_ctx)
            triggers[trigger_type] = triggers.get(trigger_type, 0) + 1
            breakpoints.append({
                "pair": f"{prev['filename']} -> {curr['filename']}",
                "ratio": ratio,
                "lcp": lcp,
                "trigger": trigger_type,
                "context": bp_ctx
            })

    if lcp_ratios:
        avg_ratio = sum(lcp_ratios) / len(lcp_ratios)
        print(f"  平均キャッシュ維持率 (LCP率) : {avg_ratio:.1f}%")
        
        # トリガー統計
        print("\n  【キャッシュ崩壊トリガー発生頻度】")
        sorted_triggers = sorted(triggers.items(), key=lambda x: x[1], reverse=True)
        for t_type, count in sorted_triggers:
            pct = (count / len(lcp_ratios)) * 100
            print(f"    - {t_type:<50}: {count:3d} 回 ({pct:5.1f}%)")

        # 崩壊箇所の具体例 (直近5件)
        print("\n  【直近のキャッシュ崩壊サンプル (不一致箇所)】")
        for bp in breakpoints[-5:]:
            print(f"    * ペア : {bp['pair']}")
            print(f"      維持率: {bp['ratio']:.1f}% | 原因分類: {bp['trigger']}")
            print(f"      不一致箇所: ... {bp['context']} ...")
            print("-" * 50)
    else:
        print("  ※比較対象の連続するログが不足しています（2件以上のログが必要です）")

    # 対策シミュレーション
    print("\n--- [3] 対策による削減効果シミュレーション ---")
    print("  ■ 対策A: <environment_details> 内の時刻やツリーをダミー固定化した場合")
    sim_lcp_ratios = []
    for i in range(1, len(results)):
        def serialize_clean(data):
            clean_data = json.loads(json.dumps(data))
            for msg in clean_data.get('messages', []):
                content = msg.get('content', '')
                if isinstance(content, list):
                    for part in content:
                        if part.get('type') == 'text' and '<environment_details>' in part.get('text', ''):
                            part['text'] = "ENVIRONMENT_DETAILS_TRUNCATED"
                elif isinstance(content, str):
                    if '<environment_details>' in content:
                        msg['content'] = "ENVIRONMENT_DETAILS_TRUNCATED"
            return serialize_request_for_caching(clean_data)

        s1_clean = serialize_clean(results[i-1]["raw_data"])
        s2_clean = serialize_clean(results[i]["raw_data"])
        
        lcp_clean = get_lcp_len(s1_clean, s2_clean)
        ratio_clean = (lcp_clean / len(s2_clean)) * 100 if len(s2_clean) > 0 else 0
        sim_lcp_ratios.append(ratio_clean)
        
    if sim_lcp_ratios:
        sim_avg_ratio = sum(sim_lcp_ratios) / len(sim_lcp_ratios)
        improvement = sim_avg_ratio - (avg_ratio if 'avg_ratio' in locals() else 0)
        print(f"    - シミュレーション後 平均キャッシュ維持率 : {sim_avg_ratio:.1f}% (改善度: +{improvement:.1f}%)")
        print("    - 結論: 環境情報の完全な固定化（ダミー化）により、無駄な再Prefillをほぼ回避可能です。")


if __name__ == "__main__":
    log_dir = DEFAULT_LOG_DIR
    if len(sys.argv) > 1:
        log_dir = sys.argv[1]
    
    if not os.path.exists(log_dir):
        print(f"指定されたディレクトリが存在しません: {log_dir}")
        sys.exit(1)
        
    analyze_directory(log_dir)
