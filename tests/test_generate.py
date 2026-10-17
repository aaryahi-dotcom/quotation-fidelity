"""Offline tests for generate.call_model with a stand-in google-genai client.

No network and no API key are used. The stand-in records each request so the
tests can check the model name, the prompt condition and the retry loop.

Run from the project root:  venv/bin/python -m unittest tests/test_generate.py
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import generate  # noqa: E402
from generate import PromptCondition, call_model  # noqa: E402

CHUNKS = {"C1": "The auditors noted a material uncertainty related to going concern."}

VALID_JSON = json.dumps({
    "theme": "going-concern disclosures",
    "finding": "material uncertainty",
    "severity": "High",
    "verbatim_quotation": "a material uncertainty related to going concern",
    "chunk_id": "C1",
})


class _Response:
    def __init__(self, text):
        self.text = text


class _Models:
    def __init__(self, replies):
        self._replies = list(replies)
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        return _Response(self._replies.pop(0))


class FakeClient:
    def __init__(self, replies):
        self.models = _Models(replies)


class CallModel(unittest.TestCase):
    def test_free_form_parses_and_stops_after_one_call(self):
        reply = ("Theme: going-concern disclosures\nFinding: material uncertainty\n"
                 "Severity: High\nVerbatim quotation: a material uncertainty related "
                 "to going concern\nChunk ID: C1")
        client = FakeClient([reply])
        gen = call_model("going-concern disclosures", CHUNKS, k=1, company="T",
                         fiscal_year="2020", condition=PromptCondition.FREE_FORM,
                         client=client)
        self.assertEqual(gen.attempts, 1)
        self.assertIsNotNone(gen.parsed)
        self.assertEqual(gen.parsed["chunk_id"], "C1")

    def test_free_form_unparsable_is_parsed_none(self):
        client = FakeClient(["I cannot help with that."] * 3)
        gen = call_model("going-concern disclosures", CHUNKS, k=1, company="T",
                         fiscal_year="2020", condition=PromptCondition.FREE_FORM,
                         client=client, max_retries=3)
        self.assertIsNone(gen.parsed)
        self.assertEqual(gen.attempts, 3)  # parse miss triggers the same retry guard

    def test_schema_retries_after_invalid_json(self):
        client = FakeClient(["not json", VALID_JSON])
        gen = call_model("going-concern disclosures", CHUNKS, k=1, company="T",
                         fiscal_year="2020", condition=PromptCondition.SCHEMA_JSON,
                         client=client, max_retries=3)
        self.assertEqual(gen.attempts, 2)
        self.assertEqual(gen.parsed["severity"], "High")

    def test_schema_gives_up_after_max_retries(self):
        client = FakeClient(["bad", "bad", "bad"])
        gen = call_model("going-concern disclosures", CHUNKS, k=1, company="T",
                         fiscal_year="2020", condition=PromptCondition.SCHEMA_JSON,
                         client=client, max_retries=3)
        self.assertIsNone(gen.parsed)
        self.assertEqual(gen.attempts, 3)

    def test_request_uses_model_name_and_schema_config(self):
        client = FakeClient([VALID_JSON])
        call_model("going-concern disclosures", CHUNKS, k=1, company="T",
                   fiscal_year="2020", condition=PromptCondition.SCHEMA_JSON,
                   client=client, model_name="gemini-test-model")
        call = client.models.calls[0]
        self.assertEqual(call["model"], "gemini-test-model")
        self.assertEqual(call["config"].response_mime_type, "application/json")
        self.assertIsNotNone(call["config"].response_schema)
        self.assertEqual(call["config"].response_schema.required,
                         generate.RESPONSE_SCHEMA["required"])

    def test_free_form_request_has_no_schema(self):
        client = FakeClient(["Theme: x\nFinding: y\nSeverity: None\nQuotation: z\nChunk ID: C1"])
        call_model("going-concern disclosures", CHUNKS, k=1, company="T",
                   fiscal_year="2020", condition=PromptCondition.FREE_FORM, client=client)
        self.assertIsNone(client.models.calls[0]["config"].response_schema)


if __name__ == "__main__":
    unittest.main()
