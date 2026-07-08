import dataclasses
import sys
import types
import unittest
from pathlib import Path


if "ollama" not in sys.modules:
    sys.modules["ollama"] = types.ModuleType("ollama")

if "qdrant_client" not in sys.modules:
    qdrant_client = types.ModuleType("qdrant_client")
    qdrant_client.QdrantClient = object
    sys.modules["qdrant_client"] = qdrant_client

if "qdrant_client.models" not in sys.modules:
    qdrant_models = types.ModuleType("qdrant_client.models")

    class _PointStruct:
        pass

    qdrant_models.PointStruct = _PointStruct
    sys.modules["qdrant_client.models"] = qdrant_models

from agent_harness import ApprovalGate, HardenedPuppeteer, policy_enforced_call_tool
from tool_policy import ToolPolicy
from trusted_mcp import TrustedMCPAdapter


class HarnessApprovalTests(unittest.TestCase):
    def test_approval_transport_failure_fails_closed(self) -> None:
        class BrokenApprovalGate(ApprovalGate):
            CALLBACK_DIR = Path("/tmp/aegis-test-approval-callbacks")

            def _send_telegram(self, text: str) -> bool:
                return False

        gate = BrokenApprovalGate(telegram_bot_token="token", chat_id="chat")
        approved = gate.request(
            task_id="t1",
            action_desc="Dangerous action",
            content_preview="preview",
            confidence=0.2,
            irreversible=False,
        )
        self.assertFalse(approved)


class HarnessToolExecutionTests(unittest.TestCase):
    def test_policy_enforced_tool_call_sanitizes_metadata_before_execution(self) -> None:
        calls = []

        class FakeApprovalGate:
            def request(self, **kwargs):
                return True

        class FakeDeps:
            def __init__(self):
                self.tool_policy = ToolPolicy()
                self.approval_gate = FakeApprovalGate()
                self.mcp_tools = {
                    "knowledge_store": lambda **kwargs: calls.append(kwargs) or {"ok": True},
                }

        result = policy_enforced_call_tool(
            deps=FakeDeps(),
            tool_name="knowledge_store",
            task_id="t2",
            content="abc",
            collection="semantic_cache",
            metadata={"safe": True, "_private": "drop"},
        )

        self.assertTrue(result.ok)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["metadata"], {"safe": True})


class HardenedPuppeteerHappyPathTests(unittest.TestCase):
    def test_hardened_puppeteer_runs_local_happy_path(self) -> None:
        tool_calls = []
        inference_calls = []
        checkpoint_writes = []

        @dataclasses.dataclass
        class FakeTrace:
            task_id: str
            original_message: str
            classification: dict
            puppet_sequence: list[str]
            puppet_results: list[dict]
            final_response: str
            total_duration_sec: float
            total_tokens: int
            models_used: dict

        class FakePuppeteer:
            def __init__(self, mcp_tools=None, tool_executor=None):
                self.tool_executor = tool_executor

            def run(self, message, interface="telegram", session_id=None):
                self.tool_executor(
                    "knowledge_store",
                    task_id="task1234",
                    content="cached response",
                    collection="semantic_cache",
                    metadata={"safe": True, "_private": "drop"},
                )
                return FakeTrace(
                    task_id="task1234",
                    original_message=message,
                    classification={"complexity": "simple"},
                    puppet_sequence=["forge"],
                    puppet_results=[],
                    final_response="hello from fake puppeteer",
                    total_duration_sec=0.01,
                    total_tokens=12,
                    models_used={"forge": "aegis-fast"},
                )

        fake_module = types.ModuleType("puppeteer")
        fake_module.Puppeteer = FakePuppeteer
        previous = sys.modules.get("puppeteer")
        sys.modules["puppeteer"] = fake_module

        class FakeCheckpoints:
            def read(self, task_id):
                return []

            def write(self, task_id, step, step_name, result, status="done"):
                checkpoint_writes.append(
                    {
                        "task_id": task_id,
                        "step": step,
                        "step_name": step_name,
                        "result": result,
                        "status": status,
                    }
                )

        class FakeObservability:
            def record_inference(self, **kwargs):
                inference_calls.append(kwargs)

        class FakeApprovalGate:
            def request(self, **kwargs):
                return True

        class FakeDeps:
            def __init__(self):
                self.model_chain = None
                self.checkpoints = FakeCheckpoints()
                self.observability = FakeObservability()
                self.approval_gate = FakeApprovalGate()
                self.mcp_tools = {
                    "knowledge_store": lambda **kwargs: tool_calls.append(kwargs) or {"ok": True}
                }
                self.tool_policy = ToolPolicy()
                self.mcp_adapter = TrustedMCPAdapter(self.mcp_tools, self.tool_policy)
                self.config = {}

        try:
            hp = HardenedPuppeteer(FakeDeps())
            result = hp.run("hello trusted kernel", interface="test", task_id="task1234")
        finally:
            if previous is not None:
                sys.modules["puppeteer"] = previous
            else:
                del sys.modules["puppeteer"]

        self.assertTrue(result["ok"])
        self.assertEqual(result["response"], "hello from fake puppeteer")
        self.assertEqual(len(tool_calls), 1)
        self.assertEqual(tool_calls[0]["metadata"], {"safe": True})
        self.assertEqual(len(inference_calls), 1)
        self.assertEqual(inference_calls[0]["task_id"], "task1234")
        self.assertEqual(checkpoint_writes[-1]["step_name"], "final_response")


if __name__ == "__main__":
    unittest.main()
