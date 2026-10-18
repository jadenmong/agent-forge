"""Responses HTTP adapter; the Runtime owns the loop and tool execution."""

import json
import os

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI

from .models import ModelReply, ToolCall
from .tools import RuntimeFault


class OpenAIResponsesAdapter:
    def __init__(self, client: AsyncOpenAI | None = None, *, model: str | None = None):
        self.model = model or os.environ.get("OPENAI_MODEL", "").strip()
        if not self.model or (
            client is None and not os.environ.get("OPENAI_API_KEY", "").strip()
        ):
            raise RuntimeFault("LIVE_NOT_CONFIGURED")
        self.client = client or AsyncOpenAI(
            base_url="https://api.openai.com/v1", max_retries=0, timeout=30.0
        )

    async def aclose(self):
        await self.client.close()

    async def respond(self, context, tools) -> ModelReply:
        history = []
        instructions = ""
        for item in context:
            if item["kind"] == "system":
                instructions = item["text"]
            elif item["kind"] == "input":
                history.append({"role": "user", "content": item["text"]})
            elif item["kind"] == "model":
                history.extend(item["continuation"])
            elif item["kind"] == "tool_result":
                history.append(
                    {
                        "type": "function_call_output",
                        "call_id": item["call_id"],
                        "output": json.dumps(
                            item["result"], ensure_ascii=False, allow_nan=False
                        ),
                    }
                )
        try:
            response = await self.client.responses.create(
                model=self.model,
                instructions=instructions,
                input=history,
                tools=[{"type": "function", **tool, "strict": False} for tool in tools],
                store=False,
                include=["reasoning.encrypted_content"],
                max_output_tokens=2048,
            )
        except APITimeoutError:
            raise RuntimeFault("MODEL_TIMEOUT") from None
        except APIConnectionError:
            raise RuntimeFault("PROVIDER_UNAVAILABLE") from None
        except APIStatusError as exc:
            code = (
                "PROVIDER_RATE_LIMIT"
                if exc.status_code == 429
                else "PROVIDER_AUTH"
                if exc.status_code in {401, 403}
                else "PROVIDER_UNAVAILABLE"
                if exc.status_code >= 500
                else "PROVIDER_REQUEST_REJECTED"
            )
            raise RuntimeFault(code) from None
        if response.status != "completed":
            raise RuntimeFault(
                "MODEL_INCOMPLETE"
                if response.status == "incomplete"
                else "MODEL_NOT_COMPLETED"
            )
        calls = []
        continuation = []
        texts = []
        reasoning_missing = False
        try:
            for item in response.output:
                data = item.model_dump(mode="json", exclude_none=True)
                if item.type == "reasoning":
                    # Opaque encrypted state is replayed, never reasoning text or summaries.
                    encrypted = data.get("encrypted_content")
                    reasoning_missing |= not bool(encrypted)
                    continuation.append(
                        {
                            "type": "reasoning",
                            "id": item.id,
                            "summary": [],
                            **({"encrypted_content": encrypted} if encrypted else {}),
                        }
                    )
                elif item.type == "function_call":
                    if item.status not in {None, "completed"}:
                        raise RuntimeFault("MODEL_PROTOCOL_ERROR")
                    arguments = json.loads(item.arguments)
                    calls.append(
                        ToolCall(
                            call_id=item.call_id,
                            tool_name=item.name,
                            arguments=arguments,
                        )
                    )
                    continuation.append(data)
                elif item.type == "message":
                    for part in item.content:
                        if part.type == "refusal":
                            raise RuntimeFault("MODEL_REFUSAL")
                        if part.type != "output_text":
                            raise RuntimeFault("MODEL_PROTOCOL_ERROR")
                        texts.append(part.text)
                    continuation.append(data)
                else:
                    raise RuntimeFault("MODEL_PROTOCOL_ERROR")
            if calls and reasoning_missing:
                raise RuntimeFault("MODEL_CONTINUATION_UNAVAILABLE")
            if not calls and not texts:
                raise RuntimeFault("MODEL_EMPTY_OUTPUT")
            return ModelReply(
                calls=tuple(calls),
                final_text=None if calls else "\n".join(texts),
                usage_tokens=response.usage.total_tokens if response.usage else None,
                continuation=tuple(continuation),
            )
        except (ValueError, TypeError):
            raise RuntimeFault("MODEL_PROTOCOL_ERROR") from None
