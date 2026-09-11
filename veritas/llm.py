"""AI backends. Both expose the same two methods, so the rest of Veritas doesn't care which is used."""
import json
import re
import urllib.error
import urllib.request

from . import config


class LocalLLM:
    """A small model running on your own machine through Ollama (https://ollama.com).
    No internet, no API key, and far less hardware per answer than a data-center model.
    Uses only the Python standard library."""

    def __init__(self, model=None, url=None):
        self.model = model or config.LOCAL_MODEL
        self.url = (url or config.OLLAMA_URL).rstrip("/")

    def complete(self, system, user, max_tokens=600, json_mode=False):
        body = {
            "model": self.model,
            "stream": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {"num_predict": max_tokens, "temperature": 0.1, "num-ctx": 8192},
        }
        if json_mode:
            body["format"] = "json"  # forces valid JSON, which small models otherwise fumble
        req = urllib.request.Request(
            f"{self.url}/api/chat", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                data = json.loads(r.read())
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"Can't reach Ollama at {self.url}. Is it running, and have you run "
                f"`ollama pull {self.model}`? ({e})"
            )
        return data.get("message", {}).get("content", "")

    def complete_json(self, system, user, max_tokens=600):
        return extract_json(self.complete(system, user, max_tokens, json_mode=True))


class CloudLLM:
    """A large model through the Anthropic API."""

    def __init__(self, model=None):
        from anthropic import Anthropic  # only needed if you use the cloud backend

        self.client = Anthropic()
        self.model = model or config.MODEL

    def complete(self, system, user, max_tokens=600):
        resp = self.client.messages.create(
            model=self.model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in resp.content if b.type == "text")

    def complete_json(self, system, user, max_tokens=600):
        return extract_json(self.complete(system, user, max_tokens))


LLM = CloudLLM  # backward compatibility


def make_llm(backend=None):
    backend = (backend or config.BACKEND).lower()
    if backend == "ollama":
        return LocalLLM()
    if backend == "anthropic":
        return CloudLLM()
    raise ValueError(f"Unknown backend '{backend}'. Use 'ollama' or 'anthropic'.")


def extract_json(text):
    """Find the first complete JSON object in a model response, even if it's surrounded by prose."""
    text = re.sub(r"```(?:json)?", "", text)
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch == "{":
            try:
                obj, _ = decoder.raw_decode(text, i)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                return obj
    raise ValueError("No JSON object found in model response")
