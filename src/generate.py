"""
Stage 4: Generation.

Prompts Gemini Pro for verbatim supporting quotations against retrieved
passages, under the five forensic risk themes and two prompt conditions
(free-form vs. schema-constrained JSON), matching the production Filing
Analyst Agent's generation contract (RedShift SRS/SDS v9, Component 3) and
the structural guard it applies (reject + re-request on schema violation).

STATUS: migrated to the google-genai SDK on 2026-10-17 (the earlier
google-generativeai package is deprecated upstream and is no longer used).
The offline tests in tests/test_generate.py exercise the retry loop and the
request shape with a stand-in client. No live API call has been made with
this version; run `python generate.py --selftest` with a key before the
full grid.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict
from enum import Enum

MODEL_NAME = "gemini-3.8-flash"  # 2026 free-tier model used for the study

THEMES = [
    "auditor qualifications and emphases of matter",
    "related-party transactions",
    "promoter share pledging",
    "going-concern disclosures",
    "contingent liabilities and guarantees",
]

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "theme": {"type": "string"},
        "finding": {"type": "string"},
        "severity": {"type": "string", "enum": ["High", "Medium", "Low", "None"]},
        "verbatim_quotation": {"type": "string"},
        "chunk_id": {"type": "string"},
    },
    "required": ["theme", "finding", "severity", "verbatim_quotation", "chunk_id"],
}

SYSTEM_INSTRUCTION = (
    "You are a forensic filing analyst. You will be given one or more "
    "numbered passages extracted from an Indian company's annual report, "
    "each labelled with a chunk_id. For the given risk theme, identify "
    "whether the supplied passages disclose a finding relevant to that "
    "theme. If they do, quote the EXACT supporting sentence(s) verbatim, "
    "copied character-for-character from the supplied passage -- do not "
    "paraphrase, summarise, or correct spelling/grammar in the quotation. "
    "Cite the chunk_id the quotation was taken from. If no passage "
    "discusses this theme, set severity to \"None\" and verbatim_quotation "
    "to an empty string."
)


class PromptCondition(str, Enum):
    FREE_FORM = "free_form"
    SCHEMA_JSON = "schema_json"


@dataclass
class Generation:
    company: str
    fiscal_year: str
    theme: str
    k: int
    prompt_condition: str
    chunk_ids_supplied: list[str]
    raw_response: str
    parsed: dict | None       # None if schema validation failed after retries
    attempts: int
    latency_s: float


def _build_user_prompt(theme: str, chunks: dict[str, str],
                        condition: PromptCondition) -> str:
    passages = "\n\n".join(
        f"[chunk_id: {cid}]\n{text}" for cid, text in chunks.items()
    )
    base = f"Risk theme: {theme}\n\nPassages:\n\n{passages}"
    if condition is PromptCondition.SCHEMA_JSON:
        return (
            base + "\n\nRespond with a single JSON object matching this "
            f"schema exactly:\n{json.dumps(RESPONSE_SCHEMA, indent=2)}"
        )
    return (
        base + "\n\nRespond in plain text: state the theme, the finding, "
        "a severity (High/Medium/Low/None), the verbatim supporting "
        "quotation, and the chunk_id it came from."
    )


def _parse_free_form(text: str) -> dict | None:
    """Best-effort parse of a free-form response into the same fields a
    schema-constrained response would give, so both conditions can be
    verified identically downstream. Free-form parsing is inherently lossy;
    failures here should be logged as a distinct outcome, not silently
    coerced -- see run_experiment.py's handling of parsed=None.
    """
    import re
    fields = {}
    patterns = {
        "theme": r"(?:theme|risk theme)\s*:\s*(.+)",
        "finding": r"finding\s*:\s*(.+)",
        "severity": r"severity\s*:\s*(\w+)",
        "verbatim_quotation": r"(?:verbatim[_ ]quotation|quotation|quote)\s*:\s*(.+)",
        "chunk_id": r"chunk[_ ]id\s*:\s*(\S+)",
    }
    for field, pat in patterns.items():
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            fields[field] = m.group(1).strip().strip('"')
    if set(fields) >= {"finding", "verbatim_quotation", "chunk_id"}:
        return fields
    return None


def _genai_schema():
    """RESPONSE_SCHEMA as google-genai Schema objects (its type enum is upper-case)."""
    from google.genai import types
    props = {
        name: types.Schema(type=types.Type.STRING, enum=spec.get("enum"))
        for name, spec in RESPONSE_SCHEMA["properties"].items()
    }
    return types.Schema(type=types.Type.OBJECT, properties=props,
                        required=RESPONSE_SCHEMA["required"])


def _make_config(condition: PromptCondition):
    from google.genai import types
    if condition is PromptCondition.SCHEMA_JSON:
        return types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=_genai_schema(),
        )
    return types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION)


def call_model(theme: str, chunks: dict[str, str], k: int, company: str,
               fiscal_year: str, condition: PromptCondition,
               max_retries: int = 3, model_name: str = MODEL_NAME,
               client=None) -> Generation:
    """Single generation call with the structural guard's retry loop.

    Uses the google-genai SDK (`pip install google-genai`) and needs
    GEMINI_API_KEY. Pass `client` to inject a stand-in in tests; otherwise a
    real client is created from the environment key.
    """
    if client is None:
        try:
            from google import genai
        except ImportError as e:
            raise RuntimeError(
                "google-genai is not installed in this environment. "
                "Install it with `pip install google-genai`."
            ) from e
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Get a free key from Google AI "
                "Studio and export it before running real generations."
            )
        client = genai.Client(api_key=api_key)

    prompt = _build_user_prompt(theme, chunks, condition)
    config = _make_config(condition)

    attempts = 0
    t0 = time.time()
    parsed = None
    raw = ""
    while attempts < max_retries:
        attempts += 1
        response = client.models.generate_content(
            model=model_name, contents=prompt, config=config)
        raw = response.text or ""
        if condition is PromptCondition.SCHEMA_JSON:
            try:
                candidate = json.loads(raw)
                if RESPONSE_SCHEMA["required"] and all(
                    f in candidate for f in RESPONSE_SCHEMA["required"]
                ):
                    parsed = candidate
                    break
            except json.JSONDecodeError:
                continue  # structural guard: retry
        else:
            candidate = _parse_free_form(raw)
            if candidate is not None:
                parsed = candidate
                break

    return Generation(
        company=company, fiscal_year=fiscal_year, theme=theme, k=k,
        prompt_condition=condition.value, chunk_ids_supplied=list(chunks.keys()),
        raw_response=raw, parsed=parsed, attempts=attempts,
        latency_s=time.time() - t0,
    )


if __name__ == "__main__":
    import sys
    if "--selftest" not in sys.argv:
        print(__doc__)
        raise SystemExit(0)

    chunks = {"C1": "The Company's auditors noted a material uncertainty "
                     "related to going concern in their report."}
    gen = call_model("going-concern disclosures", chunks, k=1,
                      company="TEST", fiscal_year="2020",
                      condition=PromptCondition.SCHEMA_JSON)
    print(asdict(gen))
