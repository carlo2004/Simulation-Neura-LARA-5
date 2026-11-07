"""Token throughput from runtime counters, never from character or SSE-chunk counts."""
import math
import time


def positive(value, allow_zero=True):
    if type(value) not in (int, float) or not math.isfinite(value):
        return None
    return value if value >= 0 and (allow_zero or value > 0) else None


class GenerationMetrics:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.started = clock()
        self.request_started = None
        self.first_token = None
        self.load_seconds = None
        self.timings = {}
        self.usage = {}

    def ready(self, load_seconds):
        self.load_seconds = load_seconds
        self.request_started = self.clock()

    def update(self, chunk):
        if isinstance(chunk.get('timings'), dict):
            self.timings.update(chunk['timings'])
        if isinstance(chunk.get('usage'), dict):
            self.usage.update(chunk['usage'])
        generated = positive(self.timings.get('predicted_n'))
        text = any((c.get('delta') or {}).get(k) for c in chunk.get('choices', [])
                   for k in ('content', 'reasoning_content'))
        if self.first_token is None and (text or generated is not None and generated > 0):
            self.first_token = self.clock()

    def snapshot(self, finished=False, partial=False):
        now = self.clock()
        timings = self.timings
        request_seconds = max(0., now-self.request_started) if self.request_started is not None else None
        output_tokens = positive(self.usage.get('completion_tokens'))
        native_tokens = positive(timings.get('predicted_n'))
        decode_tokens = max(0, native_tokens-1) if native_tokens is not None else None
        native_prompt_tokens = positive(timings.get('prompt_n'))
        if output_tokens is None:
            output_tokens = native_tokens
        input_tokens = positive(self.usage.get('prompt_tokens'))
        if input_tokens is None:
            input_tokens = native_prompt_tokens
        decode_ms = positive(timings.get('predicted_ms'), allow_zero=False)
        prompt_ms = positive(timings.get('prompt_ms'), allow_zero=False)
        decode_rate = positive(timings.get('predicted_per_second'))
        prompt_rate = positive(timings.get('prompt_per_second'))
        if native_tokens is not None and native_tokens < 2:
            # The first sampled token belongs to prefill; there is no decode interval yet.
            decode_rate, decode_ms = None, None
        if decode_rate is None and decode_ms is not None and decode_tokens is not None:
            decode_rate = decode_tokens/(decode_ms/1000)
        if prompt_rate is None and prompt_ms is not None and native_prompt_tokens is not None:
            prompt_rate = native_prompt_tokens/(prompt_ms/1000)
        effective = output_tokens/request_seconds if output_tokens is not None and request_seconds else None
        phase = ('finished' if finished else 'loading' if self.request_started is None else
                 'generating' if self.first_token is not None else 'prompt')
        return dict(schema_version=2, phase=phase, input_tokens=input_tokens, output_tokens=output_tokens,
                    native_prompt_tokens=native_prompt_tokens,
                    native_predicted_tokens=native_tokens, native_decode_tokens=decode_tokens,
                    decode_seconds=decode_ms/1000 if decode_ms else None,
                    prompt_seconds=prompt_ms/1000 if prompt_ms else None,
                    decode_tokens_per_second=decode_rate, prompt_tokens_per_second=prompt_rate,
                    effective_tokens_per_second=effective, request_seconds=request_seconds,
                    total_seconds=max(0., now-self.started), model_load_seconds=self.load_seconds,
                    time_to_first_token_seconds=(self.first_token-self.request_started
                                                if self.first_token is not None and self.request_started is not None else None),
                    partial=partial, output_includes_reasoning=True,
                    rate_source='runtime' if decode_rate is not None else 'request_wall_clock' if effective is not None else None)
