"""Check your NVIDIA key and model: NVIDIA_API_KEY=nvapi-... python -m app.check_llm"""
import os, sys, httpx
base, model, key = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"), os.getenv("NVIDIA_MODEL", "nvidia/nemotron-3.5-super-vl-120b-a12b"), os.getenv("NVIDIA_API_KEY")
if not key: sys.exit("Set NVIDIA_API_KEY first.")
ids = [m["id"] for m in httpx.get(base + "/models", headers={"Authorization": "Bearer " + key}, timeout=30).json().get("data", [])]
print("model listed:", model in ids, "| models visible:", len(ids))
if model not in ids: print("Close matches:", [i for i in ids if "nemotron" in i][:10])
r = httpx.post(base + "/chat/completions", headers={"Authorization": "Bearer " + key}, json={"model": model, "messages": [{"role": "user", "content": "Say hello in five words."}], "max_tokens": 50}, timeout=60)
print("chat status:", r.status_code, r.text[:200])
