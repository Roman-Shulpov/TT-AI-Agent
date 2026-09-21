import pytest
from pydantic import ValidationError

from browser_agent.models import TOOL_MODELS, Action


@pytest.mark.parametrize(
    "name,args",
    [
        ("click", '{"element_id":"invented", "risk":"read_only"}'),
        ("click", '{"element_id":"s1-e1", "risk":"read_only", "script":"bad"}'),
        ("wait", '{"milliseconds":10000}'),
        ("wait", '{"milliseconds":"500"}'),
        ("navigate", '{"url":"javascript:alert(1)"}'),
        ("navigate", '{"url":"file:///etc/passwd"}'),
        ("navigate", '{"url":"https://user:password@example.com"}'),
        ("press_key", '{"element_id":"s1-e1", "key":"Control+L", "risk":"read_only"}'),
        ("execute_python", "{}"),
    ],
)
def test_invalid_actions_rejected(name, args):
    with pytest.raises((ValidationError, ValueError)):
        Action.parse(name, args)


def test_function_arguments_are_strict_and_required():
    for model in TOOL_MODELS.values():
        schema = model.model_json_schema()
        assert schema["additionalProperties"] is False
        assert set(schema.get("required", [])) == set(schema["properties"])
