import base64
import httpx
from urllib.parse import urlparse


SYSTEM_PROMPT = """你是海风。用户分享的是一张真实的日常照片或一个当下片刻。请注意画面中可见、具体的细节，温柔而具体地回应。不要编造照片中没有的事实、人物情绪或经历；不要治疗式建议、心理诊断、浪漫暧昧表达。通常写60到120个中文字符，最多自然地追问一个问题。"""


class ModelUnavailable(RuntimeError):
    pass


class ModelAdapter:
    def __init__(self, base_url: str, api_key: str, model: str):
        self.configure(base_url, api_key, model)

    def configure(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url, self.api_key, self.model = base_url.rstrip("/"), api_key, model

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    async def answer(self, text: str, image_bytes: bytes | None, mime_type: str | None, history: list[dict]) -> str:
        if not self.configured:
            raise ModelUnavailable("MODEL_NOT_CONFIGURED")
        content: list[dict] = [{"type": "text", "text": text}]
        if image_bytes is not None and mime_type:
            encoded = base64.b64encode(image_bytes).decode("ascii")
            content.append({"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{encoded}"}})
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend({"role": item["role"], "content": item["text"]} for item in history if item["role"] in {"user", "assistant"})
        messages.append({"role": "user", "content": content})
        payload = {"model": self.model, "messages": messages, "temperature": 0.2, "max_tokens": 500}
        if urlparse(self.base_url).hostname in {"api.deepseek.com", "api.deepseek.cn"}:
            payload["thinking"] = {"type": "disabled"}
        try:
            async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
                response = await client.post(f"{self.base_url}/chat/completions", headers={"Authorization": f"Bearer {self.api_key}"},
                                             json=payload)
                response.raise_for_status()
                answer = response.json()["choices"][0]["message"]["content"]
            if not isinstance(answer, str) or not answer.strip():
                raise ModelUnavailable("MODEL_EMPTY_RESPONSE")
            return answer.strip()
        except ModelUnavailable:
            raise
        except Exception as exc:
            raise ModelUnavailable("MODEL_REQUEST_FAILED") from exc
