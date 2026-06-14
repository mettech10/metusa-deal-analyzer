"""
Metalyzi AI Gateway (backend / Python)
======================================

Single seam for every Claude (or future provider) call made by the Flask
backend. Created for the Metalyzi "proprietary intelligence layer" build —
the point is sovereignty: the model and provider are chosen in ONE place
(env vars), and the accumulated Metalyzi context is injected here, so we can
swap the underlying AI model without touching any calling code, and the
proprietary intelligence stays owned by Metusa Property Ltd regardless of
which model we use.

Mirrors the TypeScript gateway in dealcheck-uk/lib/aiGateway.ts — both
runtimes resolve provider/model from the same env vars:

    AI_PROVIDER   anthropic | openai          (default: anthropic)
    AI_MODEL      e.g. claude-opus-4-8         (overrides the default model)
    ANTHROPIC_MODEL                            (legacy alias, still honoured)

Usage:
    from ai_gateway import ai_gateway
    result = ai_gateway.complete(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,
        system=optional_system_prompt,
        timeout=optional_seconds,
        context=optional_metalyzi_context,   # injected before the model call
    )
    text = result["content"]
"""

import os
import json
import uuid
import logging

logger = logging.getLogger(__name__)

# Resolved once at import. Default model keeps the backend's existing
# Sonnet cost profile but upgrades the (now-invalid) "claude-sonnet-4-5"
# string to the current "claude-sonnet-4-6". Set AI_MODEL=claude-opus-4-8
# for the highest-quality analysis.
DEFAULT_MODEL = "claude-sonnet-4-6"


def _resolve_model(explicit=None):
    return (
        explicit
        or os.environ.get("AI_MODEL")
        or os.environ.get("ANTHROPIC_MODEL")
        or DEFAULT_MODEL
    )


class MetalyziAIGateway:
    """Provider-agnostic completion gateway with Metalyzi context injection."""

    def __init__(self):
        self.provider = (os.environ.get("AI_PROVIDER") or "anthropic").lower()

    # ── Public API ───────────────────────────────────────────────────────
    def complete(self, messages, system=None, max_tokens=1000, model=None,
                 temperature=None, timeout=None, context=None):
        """Run a completion and return a normalised dict:
            {"content": str, "model": str, "tokens_used": int, "cached": bool}

        `messages` is the standard Anthropic messages list (each item a dict
        with role + content, where content may be a string or a list of
        content blocks — PDF/document blocks pass through unchanged).
        """
        enriched = self._inject_context(messages, context)
        call_id = self._log_call(enriched, model)

        if self.provider == "openai":
            response = self._call_openai(enriched, system, max_tokens, model,
                                         temperature, timeout)
        else:  # default + explicit 'anthropic'
            response = self._call_anthropic(enriched, system, max_tokens, model,
                                            temperature, timeout)

        self._log_response(call_id, response)
        return response

    # ── Metalyzi proprietary context injection ───────────────────────────
    def _inject_context(self, messages, context):
        """Prepend Metalyzi proprietary context to the first user message.

        `context` is a dict with optional keys: area_deals, user_profile,
        platform_benchmarks, relevant_patterns. When None/empty the messages
        are returned unchanged, so today's behaviour is identical until the
        intelligence pipeline (Section 5) starts passing context.
        """
        if not context:
            return messages

        blocks = []

        area = context.get("area_deals")
        if area:
            blocks.append(
                "METALYZI AREA INTELLIGENCE "
                f"(from {area.get('deal_count', 0)} platform analyses):\n"
                f"Median BTL yield in area: {area.get('median_btl_yield')}%\n"
                f"Median HMO yield in area: {area.get('median_hmo_yield')}%\n"
                f"Typical void rate observed: {area.get('observed_void_rate')}\n"
                f"SA occupancy observed: {area.get('observed_sa_occupancy')}%\n"
                f"Most common strategy used by investors in area: "
                f"{area.get('dominant_strategy')}"
            )

        profile = context.get("user_profile")
        if profile:
            blocks.append(
                "INVESTOR PROFILE (learned from their history):\n"
                f"Preferred strategies: {', '.join(profile.get('preferred_strategies', []))}\n"
                f"Typical budget range: £{profile.get('typical_budget_min')}"
                f"–£{profile.get('typical_budget_max')}\n"
                f"Preferred areas: {', '.join(profile.get('preferred_areas', []))}\n"
                f"Risk appetite: {profile.get('risk_appetite')}\n"
                f"Previous analyses: {profile.get('total_analyses')} deals"
            )

        bench = context.get("platform_benchmarks")
        if bench:
            blocks.append(
                "METALYZI PLATFORM BENCHMARKS "
                f"(from {bench.get('total_deals', 0)} UK deals analysed):\n"
                f"National median BTL yield: {bench.get('national_btl_yield')}%\n"
                f"National median HMO yield: {bench.get('national_hmo_yield')}%\n"
                f"Deals with positive cashflow: {bench.get('positive_cashflow_pct')}%"
            )

        patterns = context.get("relevant_patterns") or []
        if patterns:
            lines = "\n".join(
                f"- {p.get('description')} (observed in {p.get('frequency')} deals)"
                for p in patterns[:3]
            )
            blocks.append("METALYZI PATTERN INTELLIGENCE:\nSimilar deals on this platform:\n" + lines)

        if not blocks:
            return messages

        prefix = (
            "[METALYZI PROPRIETARY CONTEXT]\n"
            + "\n\n".join(blocks)
            + "\n[END METALYZI CONTEXT]\n\n"
        )

        out = []
        injected = False
        for m in messages:
            if not injected and m.get("role") == "user":
                content = m.get("content")
                if isinstance(content, str):
                    out.append({**m, "content": prefix + content})
                    injected = True
                    continue
                if isinstance(content, list):
                    # Prepend a text block to multimodal content.
                    out.append({**m, "content": [{"type": "text", "text": prefix}] + content})
                    injected = True
                    continue
            out.append(m)
        return out

    # ── Providers ────────────────────────────────────────────────────────
    def _call_anthropic(self, messages, system, max_tokens, model, temperature, timeout):
        import anthropic

        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not configured")

        client = (anthropic.Anthropic(api_key=api_key, timeout=timeout)
                  if timeout else anthropic.Anthropic(api_key=api_key))

        kwargs = {
            "model": _resolve_model(model),
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        if temperature is not None:
            kwargs["temperature"] = temperature

        message = client.messages.create(**kwargs)

        # Concatenate all text blocks (robust to thinking/tool blocks).
        text = "".join(
            getattr(b, "text", "") for b in message.content
            if getattr(b, "type", "") == "text"
        )
        usage = getattr(message, "usage", None)
        tokens = (getattr(usage, "input_tokens", 0) + getattr(usage, "output_tokens", 0)) if usage else 0
        return {
            "content": text,
            "model": getattr(message, "model", kwargs["model"]),
            "tokens_used": tokens,
            "cached": False,
        }

    def _call_openai(self, messages, system, max_tokens, model, temperature, timeout):
        # Future: OpenAI implementation — same interface, swappable via AI_PROVIDER.
        raise NotImplementedError("OpenAI provider not yet configured")

    # ── Learning hooks (filled in by the intelligence pipeline) ──────────
    def _log_call(self, messages, model):
        # Store call for the learning pipeline (Section 3+). No-op for now.
        return str(uuid.uuid4())

    def _log_response(self, call_id, response):
        # Store response for quality tracking. No-op for now.
        return None


# Module-level singleton — import this everywhere.
ai_gateway = MetalyziAIGateway()
