"""Skip / jump logic engine — translated from skip-engine.ts.

Supports four skip-rule types:
  - forward_skip:   skip specified question IDs, jump to next after last skipped
  - forward_jump:   jump to a target question directly
  - conditional_show: show/hide based on conditions (operators: >=, <=, ==, !=, in)
  - branch:         branch logic (pick next question from a branch map)
"""

from __future__ import annotations

from typing import Any


def _eval_condition(value: Any, condition: dict[str, Any]) -> bool:
    """Evaluate a single condition against a value.

    condition keys: operator, target
    Supported operators: >=, <=, ==, !=, in, not_in
    """
    op = condition.get("operator", "==")
    target = condition.get("target")

    if op == ">=":
        return float(value) >= float(target)
    if op == "<=":
        return float(value) <= float(target)
    if op == "==":
        return value == target or float(value) == float(target)
    if op == "!=":
        return value != target and float(value) != float(target)
    if op == "in":
        return value in target if isinstance(target, list) else False
    if op == "not_in":
        return value not in target if isinstance(target, list) else True
    return False


def evaluate_skip_rules(
    question: dict[str, Any],
    answers: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate skip rules for a single question.

    Returns
    -------
    dict with keys:
        skipped_ids: list[str]  — question IDs to skip
        jump_to: str | None    — target question to jump to
        has_skip: bool
    """
    skip_rules = question.get("skip_rules", [])
    skipped_ids: list[str] = []
    jump_to: str | None = None

    for rule in skip_rules:
        rule_type = rule.get("type", "")
        target = rule.get("target")
        condition = rule.get("condition")

        if rule_type == "forward_skip" and isinstance(target, list):
            skipped_ids.extend(target)
        elif rule_type == "forward_jump" and isinstance(target, str):
            jump_to = target
        elif rule_type == "conditional_show" and condition:
            q_value = answers.get(question.get("id"))
            if q_value is not None and _eval_condition(q_value, condition):
                # When condition is met and target is a list, those are the
                # questions to skip (hide).
                if isinstance(target, list):
                    skipped_ids.extend(target)
                elif isinstance(target, str):
                    jump_to = target
        elif rule_type == "branch" and condition:
            q_value = answers.get(question.get("id"))
            if q_value is not None and _eval_condition(q_value, condition):
                if isinstance(target, str):
                    jump_to = target
                elif isinstance(target, list):
                    skipped_ids.extend(target)

    return {
        "skipped_ids": skipped_ids,
        "jump_to": jump_to,
        "has_skip": bool(skipped_ids or jump_to),
    }


def should_show_question(
    question: dict[str, Any],
    answers: dict[str, Any],
) -> bool:
    """Determine if a question should be shown based on its skip rules.

    A question is hidden when any of its skip_rules marks it as to-be-skipped
    (via a previous question's forward_skip rule).
    """
    skip_rules = question.get("skip_rules", [])
    for rule in skip_rules:
        if rule.get("type") == "conditional_show":
            condition = rule.get("condition")
            if condition:
                q_value = answers.get(question.get("id"))
                if q_value is not None and _eval_condition(q_value, condition):
                    target = rule.get("target")
                    if target is None or target == "":
                        return True
                    return True
                else:
                    target = rule.get("target")
                    if target is not None and target != "":
                        return False
    return True


def compute_visibility(
    questions: list[dict[str, Any]],
    answers: dict[str, Any],
    dimension: str | None = None,
) -> dict[str, Any]:
    """Batch compute visible / skipped questions.

    Parameters
    ----------
    questions : list of question dicts (each with id, skip_rules, optionally dimension)
    answers : mapping of question_id -> answer value
    dimension : optional filter (E, S, G)

    Returns
    -------
    dict with keys:
        visible_ids: list[str]
        skipped_ids: list[str]
        visible_questions: list[dict]
    """
    # Apply dimension filter first
    filtered = questions
    if dimension:
        filtered = [q for q in questions if q.get("dimension") == dimension]

    # Collect all skip targets from answered questions
    all_skipped: set[str] = set()
    for q in filtered:
        qid = q.get("id")
        if qid in answers:
            result = evaluate_skip_rules(q, answers)
            all_skipped.update(result.get("skipped_ids", []))

    visible_ids: list[str] = []
    skipped_ids: list[str] = []
    visible_questions: list[dict[str, Any]] = []

    for q in filtered:
        qid = q.get("id", "")
        if qid in all_skipped:
            skipped_ids.append(qid)
        else:
            if should_show_question(q, answers):
                visible_ids.append(qid)
                visible_questions.append(q)
            else:
                skipped_ids.append(qid)

    return {
        "visible_ids": visible_ids,
        "skipped_ids": skipped_ids,
        "visible_questions": visible_questions,
    }
