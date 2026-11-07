"""Keep native counters and wall-clock rates separate in Workbench reports."""
import json
import unittest

from stacklab.llm.metrics import GenerationMetrics


class Clock:
    def __init__(self):
        self.now = 0.

    def __call__(self):
        return self.now


class MetricsTests(unittest.TestCase):
    def test_native_counters_include_hidden_reasoning_not_characters_or_chunks(self):
        clock = Clock()
        meter = GenerationMetrics(clock)
        clock.now = 4
        meter.ready(4)
        clock.now = 5
        meter.update(dict(choices=[dict(delta=dict(reasoning_content='ä'*100))],
                          timings=dict(predicted_n=2, predicted_ms=250, prompt_n=50, prompt_ms=100)))
        clock.now = 6
        meter.update(dict(choices=[dict(delta=dict(content='OK'))],
                          usage=dict(prompt_tokens=200, completion_tokens=3),
                          timings=dict(predicted_n=3, predicted_ms=500)))
        result = meter.snapshot(finished=True)
        self.assertEqual(result['output_tokens'], 3)
        self.assertEqual(result['decode_tokens_per_second'], 4)
        self.assertEqual(result['native_predicted_tokens'], 3)
        self.assertEqual(result['native_decode_tokens'], 2)
        self.assertEqual(result['prompt_tokens_per_second'], 500)  # 50 processed, not 200 with cache.
        self.assertEqual(result['time_to_first_token_seconds'], 1)
        self.assertEqual(result['model_load_seconds'], 4)
        self.assertEqual(result['request_seconds'], 2)


    def test_missing_native_timings_never_turn_characters_into_a_token_estimate(self):
        clock = Clock()
        meter = GenerationMetrics(clock)
        meter.ready(0)
        meter.update(dict(choices=[dict(delta=dict(content='many characters'))]))
        self.assertIsNone(meter.snapshot()['output_tokens'])
        clock.now = 2
        meter.update(dict(usage=dict(completion_tokens=10)))
        result = meter.snapshot(finished=True)
        self.assertIsNone(result['decode_tokens_per_second'])
        self.assertEqual(result['effective_tokens_per_second'], 5)


    def test_invalid_or_zero_duration_does_not_produce_infinite_rates(self):
        meter = GenerationMetrics()
        meter.ready(0)
        meter.update(dict(timings=dict(predicted_n=2, predicted_ms=0, predicted_per_second=float('nan'))))
        result = meter.snapshot()
        self.assertIsNone(result['decode_tokens_per_second'])
        json.dumps(result, allow_nan=False)
        meter.update(dict(timings=dict(predicted_n=1, predicted_ms=0, predicted_per_second=0)))
        self.assertIsNone(meter.snapshot()['decode_tokens_per_second'])
