from __future__ import annotations

from uuid import uuid4
from langchain_core.tools import StructuredTool
from pydantic import Field

from ..schemas.models import Model, ToolResult, ToolTrace
from ..services.workflow_service import ToolSession


class NoArguments(Model):
    pass


class UpdateArguments(Model):
    patch: dict = Field(default_factory=dict)
    clear_fields: list[str] = Field(default_factory=list)


DESCRIPTIONS = {
    "load_case": "Load the case bound to the authenticated session.",
    "find_existing_application": "Find active cases for the authorized current borrower.",
    "update_request": "Apply a validated request patch, revise and invalidate dependencies.",
    "get_product_candidates": "Ask module 2 for product candidates for this case revision.",
    "get_data_requirements": "Ask module 2 for requirements of the returned product routes.",
    "request_evidence": "Ask module 3 for evidence, with valid consent and idempotency key.",
    "get_assessment_status": "Poll an existing assessment through module 4.",
    "get_bank_status": "Poll an existing application through module 5; never create a payment.",
}


class ToolBox:
    def __init__(self, session: ToolSession):
        self.session = session
        self.traces: list[ToolTrace] = []
        self.tools = {}
        for name, description in DESCRIPTIONS.items():
            def build_call(operation):
                def call(**kwargs):
                    result = session.execute(operation, kwargs)
                    return result.model_dump_json(), result.model_dump(mode="json")
                return call
            self.tools[name] = StructuredTool.from_function(
                func=build_call(name), name=name, description=description,
                args_schema=UpdateArguments if name == "update_request" else NoArguments,
                response_format="content_and_artifact",
            )

    def invoke(self, name: str, **arguments) -> ToolResult:
        call_id = uuid4().hex
        message = self.tools[name].invoke({"type": "tool_call", "name": name, "id": call_id, "args": arguments})
        result = ToolResult.model_validate(message.artifact)
        self.traces.append(ToolTrace(tool_name=name, tool_call_id=call_id, revision=self.session.case.revision,
                                     correlation_id=self.session.case.correlation_id, result=result))
        return result
