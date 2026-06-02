"""Convert MemTest v4 output to TruLens GroundTruthAgreement format.

Usage:
    python convert_to_trulens.py output/hongloumeng.json [--output trulens_hongloumeng.json]

The conversion puts memory_id as the "text" field in expected_chunks,
so TruLens's exact text matching naturally becomes ID matching —
the correct semantics for curated ground truth.
"""

import json
import argparse
import sys


def convert(memtest_path: str, output_path: str | None = None):
    with open(memtest_path) as f:
        data = json.load(f)

    db_info = data.get("database_info", {})
    conversation_id = db_info.get("name", "unknown")

    golden_set = []
    stats = {"total": 0, "negative": 0, "multi_answer": 0}

    for q in data["queries"]:
        expected_ids = q.get("expected_memory_ids", [])
        entry = {
            "query": q["query_text"],
            "expected_chunks": [
                {"text": mid, "expect_score": 1}
                for mid in expected_ids
            ],
            "conversation_id": conversation_id,
            # Preserve MemTest metadata for reference
            "_memtest_meta": {
                "query_id": q["query_id"],
                "query_type": q["query_type"],
                "test_dimension": q["test_dimension"],
                "difficulty": q.get("difficulty", ""),
                "is_negative": q.get("is_negative", False),
                "expected_memory_ids": expected_ids,
            },
        }
        golden_set.append(entry)
        stats["total"] += 1
        if q.get("is_negative"):
            stats["negative"] += 1
        if len(expected_ids) > 1:
            stats["multi_answer"] += 1

    result = {
        "description": f"MemTest → TruLens conversion of {memtest_path}",
        "source": "MemTest v4",
        "conversation_id": conversation_id,
        "num_memories": len(data["memories"]),
        "golden_set": golden_set,
    }

    out = output_path or memtest_path.replace(".json", "_trulens.json")
    with open(out, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Converted {memtest_path} → {out}")
    print(f"  Queries: {stats['total']} | Negative: {stats['negative']} | Multi-answer: {stats['multi_answer']}")
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert MemTest v4 output to TruLens format")
    parser.add_argument("input", help="Path to MemTest v4 JSON")
    parser.add_argument("--output", "-o", help="Output path (default: input_trulens.json)")
    args = parser.parse_args()
    convert(args.input, args.output)
