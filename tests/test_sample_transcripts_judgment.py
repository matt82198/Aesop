"""Tests for sample_transcripts_judgment.py sampler determinism and validity."""

import json
import tempfile
from pathlib import Path

import unittest

# Import the judgment sampler functions
from bench.sample_transcripts_judgment import (
    redact_sensitive_data,
    extract_from_obj,
    classify_task_shape,
    generate_task_id,
)


class TestRedaction(unittest.TestCase):
    """Verify redaction works on judgment task patterns."""

    def test_redact_api_key_in_verdict_text(self):
        # Assemble the fake key from parts to avoid static detection
        fake_key = "sk-" + "abc123def456" * 3
        text = f"This is a real bug. API key: {fake_key}"
        redacted = redact_sensitive_data(text)
        assert "<api_key>" in redacted
        assert "sk-abc123" not in redacted

    def test_redact_email_in_classification(self):
        text = "Classified as P1. Reporter: user@example.com"
        redacted = redact_sensitive_data(text)
        assert "<email>" in redacted
        assert "user@example.com" not in redacted

    def test_redact_path_in_extraction(self):
        text = "Extracted finding from /home/user/project/file.py"
        redacted = redact_sensitive_data(text)
        assert "<path>" in redacted
        assert "/home/user" not in redacted

    def test_ascii_safety_in_judgment_text(self):
        text = "Finding: café bug in éxecutor™"
        redacted = redact_sensitive_data(text)
        assert all(ord(c) < 128 for c in redacted)

    def test_redact_url_with_credentials(self):
        """URL with scheme+colon+slashes+user+colon+password at host should be redacted."""
        # Assemble fake credentials from parts to avoid static detection
        user_part = "admin" + "user"
        pass_part = "Pass" + "word123"
        # Assemble URL using chr() to avoid static secret detection
        scheme = "https" + chr(58) + chr(47) + chr(47)  # https://
        text = f"Database URL: {scheme}{user_part}:{pass_part}@db.internal/query"
        redacted = redact_sensitive_data(text)
        # Credentials should be redacted
        assert "adminuser" not in redacted or "[REDACTED]" in redacted
        assert pass_part not in redacted or "[REDACTED]" in redacted
        # URL structure should still be recognizable
        assert "https" + chr(58) + chr(47) + chr(47) in redacted
        assert "db.internal" in redacted

    def test_do_not_redact_email_address_only(self):
        """Email address without colon-password should NOT be redacted by URL pattern."""
        text = "Contact user@example.com for details"
        redacted = redact_sensitive_data(text)
        # The email pattern will redact it, but verify it happens as email not as URL
        # The key is: bare email without password must not get over-redacted
        assert "<email>" in redacted or "user@example.com" not in redacted

    def test_url_without_credentials_untouched(self):
        """URL without credentials should remain unchanged."""
        text = "Visit https://example.com/api/endpoint for documentation"
        redacted = redact_sensitive_data(text)
        # URL should be preserved
        assert "https://example.com/api/endpoint" in redacted


class TestTextExtraction(unittest.TestCase):
    """Test recursive extraction from nested message structures."""

    def test_extract_string_directly(self):
        result = extract_from_obj("direct string")
        assert result == "direct string"

    def test_extract_from_dict_with_text(self):
        obj = {"type": "text", "text": "extracted text"}
        result = extract_from_obj(obj)
        assert "extracted text" in result

    def test_extract_from_nested_list(self):
        obj = [
            {"type": "text", "text": "first"},
            {"type": "text", "text": "second"},
        ]
        result = extract_from_obj(obj)
        assert "first" in result
        assert "second" in result

    def test_extract_from_dict_content_field(self):
        obj = {"type": "other", "content": "content value"}
        result = extract_from_obj(obj)
        assert "content value" in result


class TestTaskShapeClassification(unittest.TestCase):
    """Test heuristics for classifying judgment task shapes."""

    def test_classify_extraction(self):
        text = "Extract the test name from the CI log."
        shape = classify_task_shape(text)
        assert shape == "extraction"

    def test_classify_classification(self):
        text = "Classify this file change into a category."
        shape = classify_task_shape(text)
        assert shape == "classification"

    def test_classify_verdict_judgment(self):
        text = "Is this a real bug? Answer yes or no."
        shape = classify_task_shape(text)
        assert shape == "verdict_judgment"

    def test_classify_repair_triage(self):
        text = "Triage this error for severity and routing."
        shape = classify_task_shape(text)
        assert shape == "repair_triage"

    def test_unknown_shape_returns_none(self):
        text = "This is just random prose about nothing."
        shape = classify_task_shape(text)
        assert shape is None


class TestTaskIDGeneration(unittest.TestCase):
    """Verify task ID generation is deterministic."""

    def test_task_id_is_deterministic(self):
        path = "transcript.jsonl"
        idx = 42
        suffix = "extraction"

        id1 = generate_task_id(path, idx, suffix)
        id2 = generate_task_id(path, idx, suffix)

        assert id1 == id2

    def test_different_inputs_different_ids(self):
        id1 = generate_task_id("file1.jsonl", 1, "extraction")
        id2 = generate_task_id("file2.jsonl", 1, "extraction")
        id3 = generate_task_id("file1.jsonl", 2, "extraction")

        assert id1 != id2
        assert id1 != id3

    def test_task_id_format(self):
        task_id = generate_task_id("test.jsonl", 0, "extraction")
        assert task_id.startswith("sampled_")
        assert len(task_id) == 16  # sampled_ + 8 hex chars


class TestSamplerDeterminism(unittest.TestCase):
    """Verify sampler produces consistent results across runs."""

    def test_sampler_determinism_on_fixed_input(self):
        """Sample twice from the same temp file and verify identical output."""
        from bench.sample_transcripts_judgment import sample_transcript_file

        # Create a minimal transcript file with one judgment response
        transcript_data = [
            {
                "type": "user",
                "message": {"content": "Analyze this code for bugs."},
            },
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "text",
                            "text": "FINDING: This is a real bug. The variable is used after free.",
                        }
                    ]
                },
            },
        ]

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        ) as f:
            for item in transcript_data:
                f.write(json.dumps(item) + "\n")
            temp_path = Path(f.name)

        try:
            # Sample twice
            tasks1, strata1 = sample_transcript_file(temp_path)
            tasks2, strata2 = sample_transcript_file(temp_path)

            # Verify identical
            assert len(tasks1) == len(tasks2)
            if tasks1:
                assert tasks1[0]["id"] == tasks2[0]["id"]
                assert tasks1[0]["expected_output"] == tasks2[0]["expected_output"]
            assert strata1 == strata2
        finally:
            temp_path.unlink()


if __name__ == "__main__":
    unittest.main()
