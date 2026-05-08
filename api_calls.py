import json

import requests

AZURE_OPENAI_API_VERSION = "2024-10-21"


def normalize_base_url(base_url: str) -> str:
    return base_url.strip().rstrip("/")


def provider_requires_api_key(api_type: str) -> bool:
    return api_type not in ("Ollama", "LM Studio")


def format_error(prefix: str, response) -> str:
    try:
        details = response.json()
    except Exception:
        details = response.text
    return f"{prefix}: {response.status_code} - {str(details)[:250]}"


def _extract_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(part.get("text", "") for part in content if isinstance(part, dict) and part.get("type") == "text")
    return str(content)


def convert_messages_for_anthropic(messages):
    anthropic_messages = []
    system_notes = []

    for message in messages:
        role = message["role"]
        content = message["content"]

        if role == "system":
            system_notes.append(_extract_text(content))
            continue

        mapped_role = "assistant" if role == "assistant" else "user"
        anthropic_messages.append({"role": mapped_role, "content": _extract_text(content)})

    if system_notes:
        system_text = "\n".join(system_notes)
        if anthropic_messages and anthropic_messages[0]["role"] == "user":
            anthropic_messages[0]["content"] = f"{system_text}\n\n{anthropic_messages[0]['content']}"
        else:
            anthropic_messages.insert(0, {"role": "user", "content": system_text})

    if not anthropic_messages:
        anthropic_messages.append({"role": "user", "content": "Hi"})

    return anthropic_messages


def convert_messages_for_google(messages):
    contents = []
    system_notes = []

    for message in messages:
        role = message["role"]
        content = message["content"]

        if role == "system":
            system_notes.append(_extract_text(content))
            continue

        mapped_role = "model" if role == "assistant" else "user"
        text = _extract_text(content)
        parts = [{"text": text}] if text else []
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    url = part.get("image_url", {}).get("url", "")
                    if url.startswith("data:"):
                        _, b64data = url.split(",", 1)
                        mtype = url.split(";")[0].split(":")[1] if ";" in url else "image/png"
                        parts.append({"inline_data": {"mime_type": mtype, "data": b64data}})
        contents.append({"role": mapped_role, "parts": parts})

    if system_notes:
        system_text = "\n".join(system_notes)
        if contents and contents[0]["role"] == "user":
            first_part = contents[0]["parts"][0]
            if first_part.get("text", ""):
                contents[0]["parts"][0]["text"] = f"{system_text}\n\n{first_part['text']}"
        else:
            contents.insert(0, {"role": "user", "parts": [{"text": system_text}]})

    if not contents:
        contents.append({"role": "user", "parts": [{"text": "Hi"}]})

    return contents


def call_openai(api_key: str, base_url: str, model: str, messages) -> str:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    data = {"model": model, "messages": messages, "max_tokens": 2000}

    try:
        response = requests.post(
            f"{normalize_base_url(base_url)}/chat/completions",
            headers=headers,
            json=data,
            timeout=60,
        )
        if response.status_code == 200:
            payload = response.json()
            return payload["choices"][0]["message"]["content"]
        return format_error("API 錯誤", response)
    except Exception as exc:
        return f"連線錯誤: {str(exc)}"


def call_openai_with_tools(api_key: str, base_url: str, model: str, messages, tools, tool_handler) -> str:
    from tools import handle_tool_call, _get_project_root

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    project_root = _get_project_root(messages)
    max_turns = 10

    for turn in range(max_turns):
        data = {
            "model": model,
            "messages": messages,
            "max_tokens": 4000,
        }
        if tools:
            data["tools"] = tools

        try:
            response = requests.post(
                f"{normalize_base_url(base_url)}/chat/completions",
                headers=headers,
                json=data,
                timeout=120,
            )
            if response.status_code != 200:
                return format_error("API 錯誤", response)

            payload = response.json()
            choice = payload["choices"][0]
            msg = choice["message"]

            if not msg.get("tool_calls"):
                return msg.get("content", "")

            messages.append({
                "role": "assistant",
                "content": msg.get("content") or "",
                "tool_calls": msg["tool_calls"],
            })

            for tc in msg["tool_calls"]:
                fn = tc["function"]
                try:
                    fn_args = json.loads(fn["arguments"])
                except json.JSONDecodeError:
                    fn_args = {}
                result = handle_tool_call(fn["name"], fn_args, project_root)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result,
                })

        except Exception as exc:
            return f"連線錯誤: {str(exc)}"

    return "工具呼叫超過最大次數，請簡化操作。"


def call_azure_openai(api_key: str, base_url: str, deployment_name: str, messages) -> str:
    headers = {"api-key": api_key, "Content-Type": "application/json"}
    data = {"messages": messages, "max_tokens": 2000}

    try:
        response = requests.post(
            f"{normalize_base_url(base_url)}/openai/deployments/{deployment_name}/chat/completions",
            headers=headers,
            params={"api-version": AZURE_OPENAI_API_VERSION},
            json=data,
            timeout=60,
        )
        if response.status_code == 200:
            payload = response.json()
            return payload["choices"][0]["message"]["content"]
        return format_error("API 錯誤", response)
    except Exception as exc:
        return f"連線錯誤: {str(exc)}"


def call_anthropic(api_key: str, model: str, messages) -> str:
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    data = {
        "model": model,
        "max_tokens": 2000,
        "messages": convert_messages_for_anthropic(messages),
    }

    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=data,
            timeout=60,
        )
        if response.status_code == 200:
            payload = response.json()
            text_parts = [item.get("text", "") for item in payload.get("content", []) if item.get("type") == "text"]
            return "\n".join(part for part in text_parts if part).strip()
        return format_error("API 錯誤", response)
    except Exception as exc:
        return f"連線錯誤: {str(exc)}"


def _extract_ollama_images(content):
    images = []
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "image_url":
                url = part.get("image_url", {}).get("url", "")
                if url.startswith("data:"):
                    _, b64data = url.split(",", 1)
                    images.append(b64data)
    return images


def call_ollama(base_url: str, model: str, messages) -> str:
    ollama_messages = []
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        if isinstance(content, list):
            text = _extract_text(content)
            images = _extract_ollama_images(content)
            entry = {"role": role, "content": text}
            if images:
                entry["images"] = images
            ollama_messages.append(entry)
        else:
            ollama_messages.append({"role": role, "content": content})
    data = {"model": model, "messages": ollama_messages, "stream": False}

    try:
        response = requests.post(
            f"{normalize_base_url(base_url)}/api/chat",
            json=data,
            timeout=300,
        )
        if response.status_code == 200:
            return response.json()["message"]["content"]
        return format_error("API 錯誤", response)
    except Exception as exc:
        return f"連線錯誤: {str(exc)}"


def call_google(api_key: str, base_url: str, model: str, messages) -> str:
    data = {
        "contents": convert_messages_for_google(messages),
        "generationConfig": {"maxOutputTokens": 2000},
    }

    try:
        url = f"{normalize_base_url(base_url)}/models/{model}:generateContent"
        response = requests.post(
            url,
            params={"key": api_key},
            headers={"Content-Type": "application/json"},
            json=data,
            timeout=60,
        )
        payload = response.json()
        if response.status_code == 200:
            candidates = payload.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                return "\n".join(part.get("text", "") for part in parts if part.get("text")).strip()
            return "回應格式錯誤: 缺少 candidates"
        msg = str(payload.get("error", {}).get("message", str(payload)[:200]))
        return f"Gemini API 錯誤 ({response.status_code}): {msg} (模型: {model})"
    except Exception as exc:
        return f"連線錯誤: {str(exc)}"


def call_provider(api_type: str, api_key: str, base_url: str, model: str, messages) -> str:
    if api_type in ("OpenAI", "Custom", "LM Studio"):
        return call_openai(api_key, base_url, model, messages)
    if api_type == "Azure OpenAI":
        return call_azure_openai(api_key, base_url, model, messages)
    if api_type == "Anthropic":
        return call_anthropic(api_key, model, messages)
    if api_type == "Ollama":
        return call_ollama(base_url, model, messages)
    if api_type == "Google Gemini":
        return call_google(api_key, base_url, model, messages)
    return f"不支援的供應商類型: {api_type}"


def call_provider_with_tools(api_type: str, api_key: str, base_url: str, model: str, messages, tools, tool_handler=None) -> str:
    if api_type in ("OpenAI", "Custom", "LM Studio"):
        return call_openai_with_tools(api_key, base_url, model, messages, tools, tool_handler)
    if api_type == "Azure OpenAI":
        return call_openai_with_tools(api_key, base_url, model, messages, tools, tool_handler)
    return call_provider(api_type, api_key, base_url, model, messages)


def verify_provider_config(api_type: str, api_key: str, base_url: str, model: str):
    if provider_requires_api_key(api_type) and not api_key:
        return False, "請輸入 API Key"
    if not base_url and api_type not in ("Anthropic",):
        return False, "請輸入 Base URL"
    if not model:
        return False, "請先指定模型"

    test_messages = [{"role": "user", "content": "Reply with OK only."}]
    result = call_provider(api_type, api_key, base_url, model, test_messages)
    if not result or "API 錯誤" in result or "連線錯誤" in result or "回應格式錯誤" in result:
        return False, result
    return True, f"驗證成功，模型可用: {model}"


def fetch_models_for_provider(api_type: str, api_key: str, base_url: str):
    if provider_requires_api_key(api_type) and not api_key:
        return False, "請先輸入 API Key", []
    if not base_url and api_type not in ("Anthropic",):
        return False, "請先輸入 Base URL", []

    try:
        if api_type in ("OpenAI", "Custom", "LM Studio"):
            response = requests.get(
                f"{normalize_base_url(base_url)}/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=30,
            )
            if response.status_code != 200:
                return False, format_error("查詢失敗", response), []
            models = sorted(model["id"] for model in response.json().get("data", []))
            return True, f"找到 {len(models)} 個模型", models

        if api_type == "Azure OpenAI":
            response = requests.get(
                f"{normalize_base_url(base_url)}/openai/models",
                headers={"api-key": api_key},
                params={"api-version": AZURE_OPENAI_API_VERSION},
                timeout=30,
            )
            if response.status_code != 200:
                return False, format_error("查詢失敗", response), []
            models = sorted(model["id"] for model in response.json().get("data", []))
            note = "找到可用模型。Azure 對話時通常仍需填入部署名稱。"
            return True, note, models

        if api_type == "Anthropic":
            response = requests.get(
                "https://api.anthropic.com/v1/models",
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                timeout=30,
            )
            if response.status_code != 200:
                return False, format_error("查詢失敗", response), []
            models = sorted(model["id"] for model in response.json().get("data", []))
            return True, f"找到 {len(models)} 個模型", models

        if api_type == "Ollama":
            response = requests.get(f"{normalize_base_url(base_url)}/api/tags", timeout=30)
            if response.status_code != 200:
                return False, format_error("查詢失敗", response), []
            models = sorted({model.get("name") or model.get("model") for model in response.json().get("models", []) if model.get("name") or model.get("model")})
            return True, f"找到 {len(models)} 個本機模型", models

        if api_type == "Google Gemini":
            response = requests.get(
                f"{normalize_base_url(base_url)}/models",
                params={"key": api_key},
                timeout=30,
            )
            if response.status_code != 200:
                return False, format_error("查詢失敗", response), []
            models = []
            for model in response.json().get("models", []):
                methods = model.get("supportedGenerationMethods", [])
                if "generateContent" in methods:
                    model_name = model.get("name", "").replace("models/", "")
                    if model_name:
                        models.append(model_name)
            models = sorted(set(models))
            return True, f"找到 {len(models)} 個 Gemini 模型", models

        return False, "不支援的供應商類型", []
    except Exception as exc:
        return False, f"連線錯誤: {str(exc)}", []
