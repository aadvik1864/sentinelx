# Free local investigation AI

SentinelX can generate explanations with **Qwen3 1.7B** through Ollama, with thinking disabled and schema-constrained JSON output. There is no subscription, API key, or per-request fee. Downloads need internet access; inference uses your CPU and RAM (and electricity). This small general-purpose model is not a security expert and can make mistakes.

## Enable it

Keep your existing `.env`, databases, source keys, and collector state. Add or update only these settings in `.env`:

```dotenv
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=qwen3:1.7b
LLM_TIMEOUT_SECONDS=180
```

Then run from the repository root:

```bash
docker compose --profile local-ai up -d --no-deps --wait ollama
docker compose exec -T ollama ollama pull qwen3:1.7b
docker compose up -d --no-deps --build --wait backend frontend nginx
docker compose restart nginx
```

The model is approximately 1.4 GB; the Ollama image is an additional multi-GB download. Downloads are retained in the `ollama-models` volume. Never use `down -v` to change AI mode: that would also delete your application databases. The larger `qwen3:4b-instruct-2507-q4_K_M` is an optional alternative for faster hardware; it exceeded the CPU time budget during local testing, so it is not the default.

The optional `local-ai` profile does not affect installations that use offline summaries. The Ollama service is CPU-only, capped at **4 GiB RAM / 6 CPU cores**, and runs one generation at a time. Allow roughly 6–8 GB total host RAM for the stack, and adjust limits for your own hardware. No NVIDIA driver or privileged host installation is required. For an already installed host Ollama with a non-Docker backend, use `OLLAMA_BASE_URL=http://127.0.0.1:11434`, disable Ollama cloud features, and pull the same model locally.

## Use it

Open **Assistant** in Advanced tools, select an investigation, and choose **Explain**. You can also choose **Explain this investigation** or **Explain this alert** from their details. The UI shows **Local AI configured**, the selected model, and **Local AI analysis** on generated output. “Configured” is not a readiness guarantee: a missing model or stopped service produces an error, not a fake explanation. Viewers cannot request analysis.

Explanations run **only when requested**, not on every new record. On a CPU, an explanation may take a couple of minutes, especially the first time a model loads. A simultaneous local request receives a busy message rather than queuing more work. Ingestion and programmed detection do not depend on the AI service. The model unloads after two minutes idle to release memory.

## Privacy and safety

- In the bundled setup, evidence is sent only from the backend to the private Ollama container. There is no published Ollama port, host-filesystem mount, Docker socket, or action executor. Cloud models/web search are disabled with `OLLAMA_NO_CLOUD=1`.
- Ollama retains only its own model/configuration volume. It has outbound networking for model downloads; this is not an air-gap or a guarantee against a compromised container. Keep Docker, Ollama, and the host patched.
- Local AI sees at most **20 recent linked records**, messages shortened to **300 characters**, selected investigation fields, asset names, technique codes, and selected reputation fields. The context has a **12,000-character JSON budget**, which can reduce the sample further. Arbitrary event/indicator metadata, notes, credentials, and configuration are excluded. Custom log messages can still contain sensitive data: redact at the source. The character budget is not an exact tokenizer guarantee.
- Evidence is marked as sampled/truncated where applicable. A record count is not evidence of every record's contents. For alert explanations, only the triggering record is available, even if the rule counted more matches.
- Log text is untrusted data. The prompt instructs the model to ignore embedded commands, distinguish hypotheses from facts, cite actual records, consider false positives, and require human approval for containment. The generation schema constrains asset names, technique codes, citation prefixes, and list lengths; the backend validates the result again and prefixes containment advice with mandatory verification/approval wording. These checks do **not** prove factual accuracy or immunity to prompt injection.
- The AI can never block an address, disable an account, execute a command, or change a monitored system. Advice must be verified and acted on manually by an authorized person.
- There is **no automatic external-provider fallback**. Errors return 502; another active local generation returns 503. This avoids unexpected disclosure or charges. Successful explanations add an audit entry but are not saved as investigation notes automatically.

## Check or troubleshoot

```bash
docker compose exec -T ollama ollama list
docker compose exec -T ollama ollama ps
docker compose logs --tail=50 ollama
```

`ollama list` confirms a downloaded model; the health check only confirms a responding service. `ollama ps` shows CPU/GPU allocation while a model is loaded. If the model is missing, run the pull command again. If requests time out or the container runs out of memory, reduce the model size or adjust CPU/RAM limits deliberately. Do not remove source checkpoints or rotate collector keys to troubleshoot AI.

The backend timeout is at most 180 seconds, the gateway allows 190 seconds on AI routes, and the browser allows 200 seconds; ordinary API requests retain their shorter timeout. Concurrent-generation protection is per backend process; Ollama additionally limits parallelism. This is an MVP, not a distributed AI job queue.

The optional browser check `SENTINELX_E2E_LOCAL_AI=1 npm run test:e2e -- e2e/local-ai.spec.ts` (from `frontend`, with `SENTINELX_E2E_PASSWORD` set privately) requests an explanation for existing evidence. It never inserts simulated records or changes source configuration. Backend unit tests mock both providers and do not download models or contact external services.

## Disable or choose another provider

Set `LLM_PROVIDER=offline`, recreate the backend, and restart Nginx to return to explicitly labeled programmed summaries. You can stop the AI container with `docker compose --profile local-ai stop ollama`; retain its model volume for later reuse.

Existing OpenAI-compatible integrations remain available through `LLM_PROVIDER=openai`, `LLM_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL`. They may charge fees and receive selected evidence; review their privacy policies first. `LLM_PROVIDER=auto` preserves legacy behavior: an external key enables that integration, otherwise output is deterministic/offline. A stale external key is ignored when you explicitly select `ollama` or `offline`.

Model reference: [Ollama Qwen3 1.7B](https://ollama.com/library/qwen3:1.7b). Qwen3 uses the Apache 2.0 license; Ollama is MIT licensed. Review the upstream model's license and limitations before distributing it.
