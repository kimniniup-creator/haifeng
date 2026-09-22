import base64
import httpx


class ModelUnavailable(RuntimeError):
    pass


class ModelAdapter:
    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    async def answer(self, text: str, image_bytes: bytes | None, mime_type: str | None,
                     history: list[dict]) -> str:
        if not self.configured:
            raise ModelUnavailable("MODEL_NOT_CONFIGURED")
        content: list[dict] = [{"type": "text", "text": text}]
        if image_bytes is not None and mime_type:
            encoded = base64.b64encode(image_bytes).decode("ascii")
            content.append({"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{encoded}"}})
        messages = [{"role": item["role"], "content": item["text"]} for item in history if item["role"] in {"user", "assistant"}]
        messages.append({"role": "user", "content": content})
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {"model": self.model, "messages": messages, "temperature": 0.2}
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
            answer = data["choices"][0]["message"]["content"]
            if not isinstance(answer, str) or not answer.strip():
                raise ModelUnavailable("MODEL_EMPTY_RESPONSE")
            return answer.strip()
        except ModelUnavailable:
            raise
        except Exception as exc:
            raise ModelUnavailable("MODEL_REQUEST_FAILED") from exc
