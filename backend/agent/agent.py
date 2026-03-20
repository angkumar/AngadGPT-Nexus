import json
import logging
import re
from typing import Any, Dict, List, Optional

from backend.agent.llm import LLMProvider, MockLLMProvider, OpenAICompatibleProvider, TinyLLMProvider
from backend.core.config import LMSTUDIO_BASE_URL, LMSTUDIO_MODEL
from backend.agent.memory import MemoryStore
from backend.tools.registry import default_tools

logger = logging.getLogger("agent")

SYSTEM_PROMPT = """
You are AngadGPT Nexus, a multi-purpose assistant focused on code, scheduling, and workflow automation.
Follow safe operating constraints: never execute destructive actions without explicit confirmation.
When calling tools, respond with strict JSON: {"action":"tool","tool_name":"<name>","args":{...}}.
For normal replies, respond with plain text (no JSON wrapper).
""".strip()


class Agent:
    def __init__(self, provider: Optional[LLMProvider] = None) -> None:
        self.provider = provider or self._load_provider()
        self.memory = MemoryStore()
        self.tools = default_tools()
        self.pending_edit = None

    def _load_provider(self) -> LLMProvider:
        try:
            if LMSTUDIO_BASE_URL:
                return OpenAICompatibleProvider(base_url=LMSTUDIO_BASE_URL, model=LMSTUDIO_MODEL)
            return TinyLLMProvider()
        except Exception as exc:
            logger.warning("Falling back to MockLLMProvider: %s", exc)
            return MockLLMProvider()

    def _summarize_if_needed(self) -> Optional[str]:
        def summarizer(prompt: str, target_messages: int) -> str:
            messages = [
                {"role": "system", "content": "Summarize the conversation briefly."},
                {"role": "user", "content": prompt},
            ]
            response = self.provider.generate(system="", messages=messages)
            return response.content[:4000]
        try:
            return self.memory.maybe_summarize(summarizer)
        except Exception as exc:
            logger.warning("Skipping summarization due to error: %s", exc)
            return None

    def step(self, user_input: str) -> Dict[str, Any]:
        self.memory.add_message("user", user_input)
        summary = self._summarize_if_needed()

        routed = self._try_route_tool(user_input)
        if routed is not None:
            self.memory.add_message("tool", json.dumps(routed))
            return routed

        messages: List[Dict[str, str]] = []
        if summary:
            messages.append({"role": "system", "content": f"Summary so far: {summary}"})
        messages.extend(
            [{"role": m.role, "content": m.content} for m in self.memory.list_messages(50)]
        )

        try:
            response = self.provider.generate(SYSTEM_PROMPT, messages)
        except RuntimeError as exc:
            logger.warning("Provider failed (%s). Falling back to MockLLMProvider.", exc)
            self.provider = MockLLMProvider()
            response = self.provider.generate(SYSTEM_PROMPT, messages)
        result = self._parse_response(response.content)

        if result.get("action") == "tool":
            tool_name = result.get("tool_name")
            args = result.get("args", {})
            tool = self.tools.get(tool_name)
            if not tool:
                tool_result = {"error": f"Unknown tool: {tool_name}"}
            else:
                tool_result = tool.run(**args)
            self.memory.add_message("tool", json.dumps(tool_result))
            return {"type": "tool", "tool": tool_name, "result": tool_result}

        content = result.get("content", response.content)
        self.memory.add_message("assistant", content)
        return {"type": "response", "content": content}

    def _parse_response(self, content: str) -> Dict[str, Any]:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {"action": "respond", "content": content}

    def _try_route_tool(self, user_input: str) -> Optional[Dict[str, Any]]:
        text = user_input.strip()
        lower = text.lower()

        # Apply/cancel pending edits
        if lower in {"apply", "confirm"}:
            if not self.pending_edit:
                return {"type": "response", "content": "No pending edit to apply."}
            pending = self.pending_edit
            self.pending_edit = None
            return self._run_tool(
                "workspace",
                {"action": "write", "path": pending["path"], "content": pending["content"]},
            )

        if lower in {"cancel", "discard"}:
            self.pending_edit = None
            return {"type": "response", "content": "Cancelled pending edit."}

        # Explicit tool syntax: /files list <path> or /files read <path>
        if lower.startswith("/files"):
            parts = text.split(maxsplit=2)
            action = parts[1] if len(parts) > 1 else "list"
            path = parts[2] if len(parts) > 2 else "."
            return self._run_tool("files", {"action": action, "path": path})

        # Natural language routing for file listing
        if any(phrase in lower for phrase in ["list files", "show files", "list projects"]):
            match = re.search(r"(in|under)\s+(.+)$", text, re.IGNORECASE)
            path = match.group(2).strip() if match else "."
            return self._run_tool("files", {"action": "list", "path": path})

        # Natural language routing for file read
        if lower.startswith("read ") or lower.startswith("open "):
            path = text.split(maxsplit=1)[1].strip()
            return self._run_tool("files", {"action": "read", "path": path})

        # Workspace create/write operations
        if lower.startswith("mkdir ") or lower.startswith("make folder "):
            path = text.split(maxsplit=1)[1].strip()
            return self._run_tool("workspace", {"action": "mkdir", "path": path})

        # Write a file from a description: "write path/to/file.py that <description>"
        m2 = re.match(r"^write\s+(\S+)\s+that\s+(.+)$", text, re.IGNORECASE)
        if m2:
            path = m2.group(1).strip()
            description = m2.group(2).strip()
            prompt = (
                "You are a coding assistant. Create a complete file that satisfies this description.\n"
                f"Description: {description}\n\n"
                "Return the full file content only, no markdown."
            )
            response = self.provider.generate(
                "You are a senior engineer.",
                [{"role": "user", "content": prompt}],
            )
            new_content = response.content
            diff_result = self._run_tool("workspace", {"action": "diff", "path": path, "content": new_content})
            self.pending_edit = {"path": path, "content": new_content}
            diff_text = diff_result.get("result", {}).get("diff", "")
            return {
                "type": "response",
                "content": (
                    "Proposed new file (diff below). Reply 'apply' to write, or 'cancel' to discard.\n\n"
                    + diff_text
                ),
            }

        if lower.startswith("write "):
            parts = text.split(maxsplit=2)
            if len(parts) >= 3:
                path = parts[1].strip()
                content = parts[2]
                return self._run_tool("workspace", {"action": "write", "path": path, "content": content})
            return {
                "type": "response",
                "content": "Please provide content. Example: write path/to/file.py <content> or say: write path/to/file.py that <description>.",
            }

        if lower.startswith("append "):
            parts = text.split(maxsplit=2)
            if len(parts) >= 3:
                path = parts[1].strip()
                content = parts[2]
                return self._run_tool("workspace", {"action": "append", "path": path, "content": content})

        # Run scripts
        if lower.startswith("run "):
            path = text.split(maxsplit=1)[1].strip()
            return self._run_tool("scripts", {"path": path})

        # Repo scan
        if "list repos" in lower or "scan repos" in lower:
            return self._run_tool("repos", {"include_non_git": False})

        # Search
        if lower.startswith("search "):
            pattern = text.split(maxsplit=1)[1].strip()
            return self._run_tool("search", {"pattern": pattern})

        # Summarize a file
        if lower.startswith("summarize "):
            path = text.split(maxsplit=1)[1].strip()
            file_result = self._run_tool("files", {"action": "read", "path": path})
            content = file_result.get("result", {}).get("content", "")

            if not content:
                return file_result

            summary_prompt = (
                "Summarize the following file succinctly, focusing on purpose, key files, and usage:\n\n"
                + content
            )
            try:
                response = self.provider.generate(
                    "You are a concise summarizer.",
                    [{"role": "user", "content": summary_prompt}],
                )
                return {"type": "response", "content": response.content}
            except RuntimeError:
                return {"type": "response", "content": content[:2000]}

        # Implement/fix/refactor/add in a specific file: "implement X in path/to/file"
        m = re.match(r"^(implement|fix|refactor|add)\s+(.+?)\s+in\s+(.+)$", text, re.IGNORECASE)
        if m:
            instruction = m.group(2).strip()
            path = m.group(3).strip()
            file_result = self._run_tool("files", {"action": "read", "path": path})
            content = file_result.get("result", {}).get("content", "")
            if not content:
                return file_result

            prompt = (
                "You are a coding assistant. Update the file to accomplish this task:\\n"
                f"Task: {instruction}\\n\\n"
                "Return the full updated file content only, no markdown.\\n\\n"
                "Current file content:\\n\\n"
                + content
            )
            response = self.provider.generate("You are a senior engineer.", [{"role": "user", "content": prompt}])
            new_content = response.content
            diff_result = self._run_tool("workspace", {"action": "diff", "path": path, "content": new_content})
            self.pending_edit = {"path": path, "content": new_content}
            diff_text = diff_result.get("result", {}).get("diff", "")
            return {
                "type": "response",
                "content": (
                    "Proposed changes (diff below). Reply 'apply' to write, or 'cancel' to discard.\\n\\n"
                    + diff_text
                ),
            }

        return None

    def _run_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        tool = self.tools.get(tool_name)
        if not tool:
            return {"type": "tool", "tool": tool_name, "result": {"error": "Unknown tool"}}
        result = tool.run(**args)
        return {"type": "tool", "tool": tool_name, "result": result}
