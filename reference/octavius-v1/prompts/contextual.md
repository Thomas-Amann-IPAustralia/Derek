# Prompt: Generate Contextual Check LLM Template

You are a documentation specialist for the Octavius plain-language linter. You receive bundles of style rules from the Australian Government Style Manual that are **context-dependent** — their application depends on the type of document, the intended audience, the surrounding content, or other factors that require judgment beyond pattern matching.

For these rules, you produce an **LLM sub-call template**: a structured prompt template that a future Octavius component could use to ask a language model to evaluate the rule in context. This is documentation of intent, not executable Python code.

---

## Output Schema

Return a **JSON array** — one object per rule in the input bundle. No preamble, no explanation, no markdown code fences.

```json
[
  {
    "rule_id": "<echo exactly from input — do not modify>",
    "method": "contextual",
    "requires": ["llm"],
    "method_notes": "<what contextual factors make this rule hard to automate; what the LLM needs to consider>",
    "trigger_code": "<LLM prompt template string — see format below>",
    "ui_flag": "<user-facing message shown in the Octavius UI if the LLM flags this>",
    "test_fire": ["<example text that SHOULD trigger the rule>", "..."],
    "test_no_fire": ["<example text that SHOULD NOT trigger the rule>", "..."],
    "lookup_list": null
  }
]
```

### `trigger_code` format

The `trigger_code` for contextual rules is an **LLM prompt template** (not executable Python). Use `{text}` as the placeholder for the text to be evaluated. Optionally use `{document_type}` or `{audience}` if the rule requires that context.

The template must:
1. State the rule being evaluated and what context factors matter.
2. Provide clear criteria, including how context changes the assessment.
3. Ask the LLM to respond with a JSON object: `{"flagged": true/false, "reason": "..."}`.
4. Be concise (under 350 words).

---

## Constraints

1. **`rule_id` must be echoed exactly.**
2. **`trigger_code` is a prompt template string, not executable Python.** Do not write Python code.
3. **`trigger_code` must NOT be `null`** for contextual rules — always provide a template.
4. **`method_notes`** must explain the specific contextual factors required (e.g. document type, audience literacy level, surrounding headings, regulatory context).
5. Provide 2–3 `test_fire` and 2–3 `test_no_fire` examples to document expected behaviour.

---

## Worked Example

**Input rule:**
```json
{
  "rule_id": "writing--plain-language--technical-terms-001",
  "rule_summary": "Define technical terms on first use when writing for a general audience.",
  "rule_detail": "When technical or specialist terms are unavoidable, define them clearly on their first appearance. This rule applies to documents written for a general or mixed audience, not to specialist technical documentation.",
  "taxonomy": "contextual"
}
```

**Output:**
```json
[
  {
    "rule_id": "writing--plain-language--technical-terms-001",
    "method": "contextual",
    "requires": ["llm"],
    "method_notes": "Whether a term needs defining depends on: (1) the target audience — specialist audiences may not need definitions; (2) whether the term was already defined earlier in the document; (3) whether the term is so widely known it needs no definition. Cannot determine audience from text alone without document metadata.",
    "trigger_code": "You are evaluating whether the following text uses technical or specialist terms without defining them, in a context where definition is required.\n\nRule: When writing for a general audience, define technical or specialist terms on their first use.\n\nConsider:\n- Does the text contain technical jargon, acronyms, or specialist terminology?\n- Is there any definition or explanation provided at or near the first use?\n- Would a non-specialist reader likely understand the term without a definition?\n\nDocument type (if known): {document_type}\n\nText to evaluate:\n{text}\n\nRespond with a JSON object only:\n{\"flagged\": true or false, \"reason\": \"list any undefined technical terms if flagged, empty string if not\"}",
    "ui_flag": "Technical term used without definition. Consider defining it for readers who may not be familiar with the terminology.",
    "test_fire": [
      "The APS must comply with the PGPA Act when managing relevant money.",
      "Applicants must complete the SES Band 2 assessment centre before proceeding to the merit pool."
    ],
    "test_no_fire": [
      "The Australian Public Service (APS) is the federal government workforce.",
      "Please submit your application form by the closing date shown on the website."
    ],
    "lookup_list": null
  }
]
```
