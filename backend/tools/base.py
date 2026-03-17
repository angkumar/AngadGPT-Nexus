from typing import Any, Dict


class Tool:
    name: str = "tool"
    description: str = ""
    input_schema: Dict[str, Any] = {}

    def run(self, **kwargs) -> Dict[str, Any]:
        raise NotImplementedError

