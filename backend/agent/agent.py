import json
import logging
import re
import shlex
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.agent.llm import (
    LLMProvider,
    LLMProviderError,
    MockLLMProvider,
    OpenAICompatibleProvider,
    TinyLLMProvider,
)
from backend.core.config import (
    GROQ_API_KEY,
    GROQ_BASE_URL,
    GROQ_MODEL,
    LLM_PROVIDER,
    LMSTUDIO_BASE_URL,
    LMSTUDIO_MODEL,
    SUMMARY_TARGET_MESSAGES,
)
from backend.agent.memory import MemoryStore
from backend.tools.registry import default_tools

logger = logging.getLogger("agent")

SYSTEM_PROMPT = """
You are AngadGPT Nexus, a multi-purpose assistant focused on code, scheduling, and workflow automation.
Follow safe operating constraints: never execute destructive actions without explicit confirmation.

Voice and behavior:
- Sound like a senior coding assistant: calm, direct, technically precise, and useful.
- Speak in a friendly and engaging manner, with a touch of humor.
- Give short, 1-2 sentence answers.
- Be concise, but not performative. Do not use hype, motivational slogans, theatrical repetition, or faux-hardcore language.
- Do not ask stacked generic questions such as "What is the task? What is the goal? What is the output?"
- Do not say things like "No fluff", "Only work", "Just code", "Let's go", "I'm ready", or similar catchphrases.
- When the user asks for code work, state the relevant next action and proceed when enough context is available.
- Ask one focused clarifying question only when missing information blocks safe progress.
- For explanations, lead with the answer, then give the minimum useful reasoning and concrete next steps.

Math and formulas:
- Always write math as LaTeX, never as raw Unicode or ASCII stand-ins like `x^2`, `sqrt(x)`, `<=`, or `!=`.
- Inline math uses single dollars: $x^2 + y^2 = r^2$. Display math sits on its own lines: $$ ... $$.
- Multi-step derivations go in one aligned block:
  $$
  \begin{aligned}
  ...
  \end{aligned}
  $$
- Use real commands where they apply: \frac, \sqrt, \sum, \int, \lim, \vec, \hat, \cdot, \times, \pm, \le, \ge, \ne, \approx, \to, \infty, \alpha ... \omega.
- Never put math inside backticks, code fences, bold, or markdown tables; keep prose between steps, not inside the LaTeX.
- For a single numeric answer, end with \boxed{...}. Keep display blocks short and one idea per block.

When calling tools, respond with strict JSON: {"action":"tool","tool_name":"<name>","args":{...}}.
For normal replies, respond with plain text (no JSON wrapper).
""".strip()

CORNY_RESPONSE_PATTERNS = [
    r"^\s*understood\.?\s*$",
    r"^\s*no fluff\.?\s*$",
    r"^\s*no distractions\.?\s*$",
    r"^\s*only work\.?\s*$",
    r"^\s*only results\.?\s*$",
    r"^\s*what is the task\?\s*$",
    r"^\s*what is the goal\?\s*$",
    r"^\s*what is the output\?\s*$",
    r"^\s*let['’]s go\s*[—-]\s*execute\.?\s*$",
    r"^\s*just code\.?\s*$",
    r"^\s*just logic\.?\s*$",
    r"^\s*just results\.?\s*$",
    r"^\s*what do you need\?\s*$",
    r"^\s*i['’]m ready\.?\s*$",
    r"^\s*go\.?\s*$",
]

HELP_TEXT = """Commands (plain text goes to the model):
- `/files [list|read] [path]` list a folder or read a file
- `/read <path>` read a file
- `/summarize <path>` summarize a file
- `/write <path> that <idea>` draft a new file from a description
- `/write <path> <content>` propose new file content
- `/append <path> <content>` propose appending content
- `/edit <path> <instruction>` propose an edit to an existing file
- `/mkdir <path>` create a folder
- `/run <script.py|script.sh> [args...]` run a workspace script
- `/search <pattern> [path]` search with ripgrep
- `/repos` list repositories

Reply `apply` to write a proposed change or `cancel` to discard it."""


class Agent:
    def __init__(
        self,
        provider: Optional[LLMProvider] = None,
        memory_db_path: Optional[str] = None,
        workspace_root: Optional[Path] = None,
        calendar_db_path: Optional[str] = None,
    ) -> None:
        self.provider = provider or self._load_provider()
        self.memory = MemoryStore(memory_db_path) if memory_db_path else MemoryStore()
        self.tools = default_tools(
            workspace_root=workspace_root, calendar_db_path=calendar_db_path
        )
        self.pending_edit: Optional[Dict[str, str]] = None

    def _load_provider(self) -> LLMProvider:
        if LLM_PROVIDER == "groq":
            if not GROQ_API_KEY:
                raise RuntimeError("GROQ_API_KEY is required when ANGADGPT_LLM_PROVIDER=groq.")
            return OpenAICompatibleProvider(
                base_url=GROQ_BASE_URL,
                model=GROQ_MODEL,
                api_key=GROQ_API_KEY,
            )
        if LLM_PROVIDER == "lmstudio":
            return OpenAICompatibleProvider(base_url=LMSTUDIO_BASE_URL, model=LMSTUDIO_MODEL)
        if LLM_PROVIDER == "tinyllm":
            return TinyLLMProvider()
        raise RuntimeError(f"Unsupported ANGADGPT_LLM_PROVIDER: {LLM_PROVIDER}")

    def _summarize_if_needed(self) -> Optional[str]:
        # History is summarized before the new turn is stored, and recent
        # messages are kept, so the message being answered is never dropped.
        def summarizer(prompt: str, target_messages: int) -> str:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "Summarize durable user preferences, project facts, and unresolved tasks briefly. "
                        "Do not preserve assistant catchphrases, motivational slogans, or transient style."
                    ),
                },
                {"role": "user", "content": prompt},
            ]
            response = self.provider.generate(system="", messages=messages)
            return response.content[:4000]

        try:
            return self.memory.maybe_summarize(
                summarizer, keep_recent=SUMMARY_TARGET_MESSAGES
            )
        except Exception as exc:
            logger.warning("Skipping summarization due to error: %s", exc)
            return None

    def step(self, user_input: str) -> Dict[str, Any]:
        summary = self._summarize_if_needed()
        self.memory.add_message("user", user_input)

        routed = self._try_command(user_input)
        if routed is not None:
            if routed.get("type") == "tool":
                self.memory.add_message(
                    "tool",
                    json.dumps({"tool": routed.get("tool"), "result": routed.get("result")}),
                )
            else:
                self.memory.add_message("assistant", str(routed.get("content", "")))
            return routed

        messages: List[Dict[str, str]] = []
        if summary:
            messages.append({"role": "system", "content": f"Summary so far: {summary}"})
        # Historical tool results are stored as `tool` rows, but they are not
        # OpenAI/Groq tool-call transcript entries: there is no preceding
        # assistant tool_calls object or matching tool_call_id. Keep the result
        # in context as assistant text so providers accept the conversation.
        messages.extend(
            [
                {
                    "role": "assistant" if m.role == "tool" else m.role,
                    "content": f"Previous tool result:\n{m.content}" if m.role == "tool" else m.content,
                }
                for m in self.memory.list_messages(50)
            ]
        )

        try:
            response = self.provider.generate(SYSTEM_PROMPT, messages)
        except LLMProviderError:
            raise
        except Exception as exc:
            # A transport failure is temporary: answer this turn with the
            # offline provider instead of permanently replacing the real one.
            logger.warning(
                "Provider %s unavailable (%s); using the offline provider for this turn.",
                getattr(self.provider, "name", "unknown"),
                exc,
            )
            response = MockLLMProvider().generate(SYSTEM_PROMPT, messages)

        result = self._parse_response(response.content)

        if result.get("action") == "tool":
            tool_name = result.get("tool_name")
            tool_result = self._run_tool(tool_name, result.get("args") or {})
            self.memory.add_message(
                "tool",
                json.dumps({"tool": tool_name, "result": tool_result.get("result")}),
            )
            return {
                "type": "tool",
                "tool": tool_name,
                "result": tool_result.get("result"),
            }

        content = self._clean_response_style(result.get("content", response.content))
        self.memory.add_message("assistant", content)
        return {"type": "response", "content": content}

    def reset_conversation(self) -> None:
        self.pending_edit = None
        self.memory.reset()

    def _parse_response(self, content: str) -> Dict[str, Any]:
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return {"action": "respond", "content": content}
        if isinstance(data, dict) and data.get("action") == "tool" and data.get("tool_name"):
            return data
        if isinstance(data, dict) and isinstance(data.get("content"), str):
            return {"action": "respond", "content": data["content"]}
        return {"action": "respond", "content": content}

    def _clean_response_style(self, content: str) -> str:
        """Remove known motivational boilerplate that some local models overproduce."""
        lines = content.splitlines()
        cleaned_lines = [
            line for line in lines
            if not any(re.match(pattern, line, re.IGNORECASE) for pattern in CORNY_RESPONSE_PATTERNS)
        ]
        cleaned = "\n".join(cleaned_lines).strip()

        if cleaned:
            return cleaned
        return "What would you like me to work on?"

    def _start_proposed_edit(self, path: str, content: str) -> Dict[str, Any]:
        diff_result = self._run_tool("workspace", {"action": "diff", "path": path, "content": content})
        result = diff_result.get("result", {})
        if result.get("error"):
            return diff_result
        self.pending_edit = {"action": "write", "path": path, "content": content}
        diff_text = result.get("diff") or "(file does not exist yet)"
        return {
            "type": "response",
            "content": (
                f"Proposed changes for `{path}`. Reply `apply` to write them or "
                f"`cancel` to discard.\n\n```diff\n{diff_text}\n```"
            ),
        }

    def _usage(self, usage: str) -> Dict[str, Any]:
        return {"type": "response", "content": f"Usage: {usage}"}

    def _generate(self, system: str, messages: List[Dict[str, str]]):
        try:
            return self.provider.generate(system, messages)
        except LLMProviderError:
            raise
        except Exception as exc:
            logger.warning(
                "Provider %s failed: %s", getattr(self.provider, "name", "unknown"), exc
            )
            raise LLMProviderError(f"Could not reach the model provider: {exc}") from exc

    def _try_command(self, user_input: str) -> Optional[Dict[str, Any]]:
        """Handle explicit commands only; everything else goes to the model.

        Prefix matching on plain English used to hijack ordinary chat ("read the
        docs on X" ran a file read), so tools now require a leading slash.
        """
        text = user_input.strip()
        lower = text.lower()

        if lower in {"apply", "confirm"}:
            if not self.pending_edit:
                return {"type": "response", "content": "No pending edit to apply."}
            pending = self.pending_edit
            self.pending_edit = None
            return self._run_tool(
                "workspace",
                {
                    "action": pending.get("action", "write"),
                    "path": pending["path"],
                    "content": pending["content"],
                },
            )

        if lower in {"cancel", "discard"}:
            if not self.pending_edit:
                return {"type": "response", "content": "Nothing to cancel."}
            self.pending_edit = None
            return {"type": "response", "content": "Cancelled pending edit."}

        if not text.startswith("/"):
            return None

        command, _, remainder = text[1:].partition(" ")
        command = command.strip().lower()
        remainder = remainder.strip()

        if command in {"", "help", "?"}:
            return {"type": "response", "content": HELP_TEXT}

        if command == "files":
            action, _, path = remainder.partition(" ")
            action = (action or "list").lower()
            if action not in {"list", "read"}:
                action = "list"
            return self._run_tool("files", {"action": action, "path": path.strip() or "."})

        if command == "read":
            if not remainder:
                return self._usage("/read <path>")
            return self._run_tool("files", {"action": "read", "path": remainder})

        if command == "summarize":
            if not remainder:
                return self._usage("/summarize <path>")
            return self._summarize_file(remainder)

        if command == "write":
            return self._command_write(remainder)

        if command == "append":
            if not remainder:
                return self._usage("/append <path> <content>")
            path, _, addition = remainder.partition(" ")
            if not addition.strip():
                return self._usage("/append <path> <content>")
            self.pending_edit = {
                "action": "append",
                "path": path,
                "content": addition + ("" if addition.endswith("\n") else "\n"),
            }
            return {
                "type": "response",
                "content": (
                    f"Proposed appending {len(addition)} characters to `{path}`. "
                    "Reply `apply` to write it or `cancel` to discard."
                ),
            }

        if command == "edit":
            path, _, instruction = remainder.partition(" ")
            if not path or not instruction.strip():
                return self._usage("/edit <path> <instruction>")
            return self._edit_file(path, instruction.strip())

        if command == "mkdir":
            if not remainder:
                return self._usage("/mkdir <path>")
            return self._run_tool("workspace", {"action": "mkdir", "path": remainder})

        if command == "run":
            if not remainder:
                return self._usage("/run <script.py|script.sh> [args...]")
            try:
                tokens = shlex.split(remainder)
            except ValueError as exc:
                return {"type": "response", "content": f"Could not parse arguments: {exc}"}
            return self._run_tool("scripts", {"path": tokens[0], "args": tokens[1:]})

        if command == "search":
            pattern, _, path = remainder.partition(" ")
            if not pattern:
                return self._usage("/search <pattern> [path]")
            return self._run_tool("search", {"pattern": pattern, "path": path.strip() or "."})

        if command == "repos":
            return self._run_tool("repos", {"include_non_git": False})

        return {
            "type": "response",
            "content": f"Unknown command `/{command}`.\n\n{HELP_TEXT}",
        }

    def _command_write(self, remainder: str) -> Dict[str, Any]:
        if not remainder:
            return self._usage("/write <path> that <idea>")
        generated = re.match(r"^(\S+)\s+that\s+([\s\S]+)$", remainder, re.IGNORECASE)
        if generated:
            return self._draft_file(generated.group(1), generated.group(2).strip())
        direct = re.match(r"^(\S+)\s+([\s\S]+)$", remainder)
        if direct:
            return self._start_proposed_edit(direct.group(1), direct.group(2))
        return self._usage("/write <path> that <idea>")

    def _draft_file(self, path: str, description: str) -> Dict[str, Any]:
        prompt = (
            "You are a coding assistant. Create a complete file that satisfies this description.\n"
            f"Description: {description}\n\n"
            "Return the full file content only, without markdown fences."
        )
        response = self._generate(
            "You are a senior engineer.",
            [{"role": "user", "content": prompt}],
        )
        return self._start_proposed_edit(path, self._strip_code_fences(response.content))

    def _edit_file(self, path: str, instruction: str) -> Dict[str, Any]:
        file_result = self._run_tool("files", {"action": "read", "path": path})
        content = file_result.get("result", {}).get("content")
        if not content:
            return file_result

        prompt = (
            "You are a coding assistant. Update the file to accomplish this task.\n"
            f"Task: {instruction}\n\n"
            "Return the full updated file content only, without markdown fences.\n\n"
            f"Current file content:\n\n{content}"
        )
        response = self._generate(
            "You are a senior engineer.",
            [{"role": "user", "content": prompt}],
        )
        return self._start_proposed_edit(path, self._strip_code_fences(response.content))

    def _summarize_file(self, path: str) -> Dict[str, Any]:
        file_result = self._run_tool("files", {"action": "read", "path": path})
        content = file_result.get("result", {}).get("content")
        if not content:
            return file_result

        prompt = (
            "Summarize the following file succinctly, focusing on purpose, key details, and usage:\n\n"
            + content
        )
        try:
            response = self._generate(
                "You are a concise summarizer.",
                [{"role": "user", "content": prompt}],
            )
            return {"type": "response", "content": response.content.strip()}
        except LLMProviderError:
            return {
                "type": "response",
                "content": (
                    "Summarizer unavailable. First 2000 characters:\n\n```\n"
                    + content[:2000]
                    + "\n```"
                ),
            }

    @staticmethod
    def _strip_code_fences(content: str) -> str:
        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z0-9_+-]*\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        return text if text.endswith("\n") else text + "\n"

    def _run_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        tool = self.tools.get(tool_name)
        if not tool:
            return {
                "type": "tool",
                "tool": tool_name,
                "result": {"error": f"Unknown tool: {tool_name}"},
            }
        try:
            result = tool.run(**args)
        except Exception as exc:  # Report tool failures instead of raising a 500.
            logger.warning("Tool %s failed: %s", tool_name, exc)
            result = {"error": f"{type(exc).__name__}: {exc}"}
        return {"type": "tool", "tool": tool_name, "result": result}
