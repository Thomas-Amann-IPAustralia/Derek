"""Annotation pace: one timeline, gaps credited to the later op's page, breaks dropped."""

from __future__ import annotations

import json

from derek.eval.annotation_pace import BREAK_MINUTES, measure
from derek.extract.golden import GoldenSet, write_golden

A = "grammar-punctuation-and-conventions/punctuation/commas.md"
B = "grammar-punctuation-and-conventions/punctuation/full-stops.md"


def _op(page, minute, n):
    return {"op": "span", "op_id": f"op-{n}", "by": "TA",
            "at": f"2026-09-23T10:{minute:02d}:00.000Z", "span": {"page_path": page}}


def test_time_is_one_timeline_and_breaks_count_for_nothing(tmp_path):
    ops = [_op(A, 0, 1), _op(A, 4, 2),      # 4 minutes on A
           _op(B, 6, 3), _op(B, 7, 4),      # 2 + 1 on B: switching pages is not double-counted
           _op(A, 9, 5),                    # 2 on A
           _op(A, 9 + BREAK_MINUTES + 1, 6)]  # a break: nothing
    log = tmp_path / "span_ops.jsonl"
    log.write_text("\n".join(json.dumps(o) for o in ops) + "\n", encoding="utf-8")
    blind = tmp_path / "blind.json"
    blind.write_text(json.dumps({"pages": {A: "test"}}), encoding="utf-8")
    sp, pp = tmp_path / "spans.jsonl", tmp_path / "pages.jsonl"
    write_golden(GoldenSet(), sp, pp)

    got = {p.page_path: p for p in measure(log, blind, sp, pp)}
    assert got[A].minutes == 6.0 and got[A].ops == 4 and got[A].mode == "blind"
    assert got[B].minutes == 3.0 and got[B].mode == "unassisted"
    assert got[A].words_per_minute == got[A].words / 6.0
