"""Measured token counts, partial generations and default terminal visibility."""
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from stacklab.cli.chat import Presenter
from stacklab.cli.speed import format_speed
from stacklab.llm.metrics import GenerationMetrics, summarize
from stacklab.llm.runtime import GenerationCancelled, LocalModel


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
        self.assertIn('inkl. Prompt', format_speed(result))

    def test_invalid_or_zero_duration_does_not_produce_infinite_rates(self):
        meter = GenerationMetrics()
        meter.ready(0)
        meter.update(dict(timings=dict(predicted_n=2, predicted_ms=0, predicted_per_second=float('nan'))))
        result = meter.snapshot()
        self.assertIsNone(result['decode_tokens_per_second'])
        json.dumps(result, allow_nan=False)
        meter.update(dict(timings=dict(predicted_n=1, predicted_ms=0, predicted_per_second=0)))
        self.assertIsNone(meter.snapshot()['decode_tokens_per_second'])

    def test_summary_weights_each_rate_by_its_actual_decode_duration(self):
        def item(tokens, seconds):
            return dict(performance=dict(output_tokens=tokens, native_decode_tokens=tokens,
                                         decode_seconds=seconds, request_seconds=seconds,
                                         model_load_seconds=0, partial=False))
        result = summarize([item(10, 1), item(10, 10)])
        self.assertAlmostEqual(result['decode_tokens_per_second'], 20/11)
        self.assertEqual(result['output_tokens'], 20)
        self.assertFalse(result['partial'])
        self.assertTrue(summarize([item(10, 1), {}])['partial'])

    def test_first_prefill_token_is_excluded_exactly_like_the_real_runtime(self):
        # Captured llama.cpp timings; predicted_n includes the first prefill token.
        timing = dict(predicted_n=325, predicted_ms=15218.515, predicted_per_second=21.289856467598845)
        meter = GenerationMetrics()
        meter.ready(0)
        meter.update(dict(timings=timing))
        current = meter.snapshot(finished=True)
        self.assertEqual(current['native_decode_tokens'], 324)
        self.assertAlmostEqual(summarize([dict(performance=current)])['decode_tokens_per_second'],
                               timing['predicted_per_second'])
        legacy = dict(schema_version=1, native_decode_tokens=325, decode_seconds=15.218515, output_tokens=325)
        self.assertAlmostEqual(summarize([dict(performance=legacy)])['decode_tokens_per_second'],
                               timing['predicted_per_second'])

    def test_first_token_times_keep_their_counts_when_combining_episode_summaries(self):
        first = summarize([dict(performance=dict(time_to_first_token_seconds=1)),
                           dict(performance=dict(time_to_first_token_seconds=2))])
        second = summarize([dict(performance=dict(time_to_first_token_seconds=9))])
        combined = summarize([dict(performance=first), dict(performance=second)])
        self.assertEqual(combined['first_token_measurements'], 3)
        self.assertEqual(combined['first_token_seconds_mean'], 4)

    def test_terminal_shows_speed_without_showing_response_or_reasoning(self):
        target = io.StringIO()
        display = Presenter(stats_stream=target)
        display.event('inference', dict(phase='finished', output_tokens=12, decode_tokens_per_second=8,
                                        prompt_tokens_per_second=100, total_seconds=3, model_load_seconds=1))
        display.drain()
        self.assertIn('8.0 Token/s', target.getvalue())
        self.assertIn('100.0 Token/s', target.getvalue())
        self.assertIn('12 Ausgabetoken', target.getvalue())

    def test_waiting_time_keeps_updating_without_new_backend_chunks(self):
        clock = Clock()
        target = io.StringIO()
        with patch('stacklab.cli.presentation.time.monotonic', side_effect=clock):
            display = Presenter(stats_stream=target)
            display.event('inference', dict(phase='prompt', total_seconds=0))
            display.drain()
            clock.now = 2
            display.drain()
        self.assertIn('auf erstes Token warten', target.getvalue())
        self.assertIn('2.0 s', target.getvalue())

    def test_progress_without_total_time_keeps_the_chat_alive(self):
        for extra, expected in [({}, '2.0 s'), ({'request_seconds': 3}, '5.0 s'),
                                ({'total_seconds': None}, '2.0 s')]:
            with self.subTest(extra=extra):
                clock = Clock()
                target = io.StringIO()
                with patch('stacklab.cli.presentation.time.monotonic', side_effect=clock):
                    display = Presenter(stats_stream=target)
                    display.event('inference', dict(phase='prompt', **extra))
                    display.drain()
                    clock.now = 2
                    display.drain()
                self.assertIn('auf erstes Token warten', target.getvalue())
                self.assertIn(expected, target.getvalue())
                self.assertEqual({k: v for k, v in display.metrics.items()
                                  if k not in ('event', 'phase')}, extra)

    def test_sse_reports_native_progress_and_saves_partial_throughput(self):
        pieces = [dict(choices=[dict(delta=dict(reasoning_content='hidden'), finish_reason=None)],
                       timings=dict(predicted_n=2, predicted_ms=500, prompt_n=40, prompt_ms=100)),
                  dict(choices=[dict(delta=dict(content='incomplete'), finish_reason='length')],
                       usage=dict(prompt_tokens=40, completion_tokens=3),
                       timings=dict(predicted_n=3, predicted_ms=1000))]
        data = ''.join('data: '+json.dumps(p)+'\n\n' for p in pieces)+'data: [DONE]\n\n'
        with tempfile.TemporaryDirectory() as temp:
            progress = []
            client = LocalModel('qwen9b')
            client.address = 'http://127.0.0.1:12345'
            with patch.object(client, 'start'), patch.object(client.opener, 'open', return_value=io.BytesIO(data.encode())) as opened:
                with self.assertRaisesRegex(ValueError, 'finish normally'):
                    client.complete([dict(role='system', content='fixture'), dict(role='user', content='fixture')],
                                    temp, on_progress=progress.append)
            saved = json.loads((Path(temp)/'generation.json').read_text())
            self.assertTrue(saved['performance']['partial'])
            self.assertEqual(saved['performance']['decode_tokens_per_second'], 2)
            self.assertEqual(saved['performance']['output_tokens'], 3)
            self.assertEqual(saved['usage']['completion_tokens'], 3)
            self.assertTrue(json.loads(opened.call_args.args[0].data)['timings_per_token'])
            self.assertEqual(progress[0]['phase'], 'loading')
            self.assertIn('generating', [p['phase'] for p in progress])
            self.assertEqual(progress[-1]['phase'], 'finished')

    def test_cancellation_preserves_the_tokens_that_were_already_generated(self):
        chunk = dict(choices=[dict(delta=dict(reasoning_content='thinking'), finish_reason=None)],
                     timings=dict(predicted_n=2, predicted_ms=500))
        data = ('data: '+json.dumps(chunk)+'\n\ndata: [DONE]\n\n').encode()
        stopped = threading.Event()

        def progress(value):
            if value['phase'] == 'generating':
                stopped.set()

        with tempfile.TemporaryDirectory() as temp:
            client = LocalModel('qwen9b')
            client.address = 'http://127.0.0.1:12345'
            with patch.object(client, 'start'), patch.object(client.opener, 'open', return_value=io.BytesIO(data)):
                with self.assertRaises(GenerationCancelled):
                    client.complete([dict(role='system', content='fixture'), dict(role='user', content='fixture')],
                                    temp, cancelled=stopped.is_set, on_progress=progress)
            saved = json.loads((Path(temp)/'generation.json').read_text())['performance']
            self.assertTrue(saved['partial'])
            self.assertEqual(saved['output_tokens'], 2)
            self.assertEqual(saved['decode_tokens_per_second'], 2)

    def test_lfm_constrains_the_transport_envelope_without_supplying_a_program(self):
        chunk = dict(choices=[dict(delta=dict(content='{"code":"robot.step(.1)","done":true}'),
                                   finish_reason='stop')], usage=dict(completion_tokens=10))
        data = ('data: '+json.dumps(chunk)+'\n\ndata: [DONE]\n\n').encode()
        with tempfile.TemporaryDirectory() as temp:
            client = LocalModel('lfm2.6b')
            client.cache_prompt = False
            client.address = 'http://127.0.0.1:12345'
            with patch.object(client, 'start'), patch.object(client.opener, 'open', return_value=io.BytesIO(data)) as opened:
                _, metadata = client.complete([dict(role='system', content='fixture'), dict(role='user', content='fixture')], temp)
            request = json.loads(opened.call_args.args[0].data)
            schema = request['response_format']['json_schema']['schema']
            self.assertEqual(schema['properties']['code'], {'type': 'string'})
            self.assertEqual(set(schema['required']), {'code', 'done'})
            self.assertIs(request['cache_prompt'], False)
            self.assertIs(metadata['prompt_cache_enabled'], False)
            self.assertTrue(metadata['constrained_decoding'])
            self.assertNotIn('enable_thinking', request['chat_template_kwargs'])

    def test_slim_local_recording_keeps_native_counters_without_writing_token_chunks(self):
        chunk = dict(choices=[dict(delta=dict(content='{"code":"","done":true}'), finish_reason='stop')],
                     usage=dict(completion_tokens=3), timings=dict(predicted_n=3, predicted_ms=1000))
        data = ('data: '+json.dumps(chunk)+'\n\ndata: [DONE]\n\n').encode()
        with tempfile.TemporaryDirectory() as temp:
            client = LocalModel('lfm2.6b')
            client.record_stream = False
            client.address = 'http://127.0.0.1:12345'
            with patch.object(client, 'start'), patch.object(client.opener, 'open', return_value=io.BytesIO(data)):
                _, metadata = client.complete([dict(role='system', content='fixture'), dict(role='user', content='fixture')], temp)
            self.assertEqual(metadata['performance']['native_decode_tokens'], 2)
            self.assertEqual(metadata['performance']['decode_tokens_per_second'], 2)
            self.assertIs(metadata['native_stream_recorded'], False)
            self.assertFalse((Path(temp)/'stream.jsonl').exists())

    def test_hidden_token_text_is_not_queued_for_the_terminal(self):
        display = Presenter(stats_stream=io.StringIO())
        for _ in range(1000):
            display.event('token', dict(kind='reasoning_content', text='unused display text'))
        self.assertTrue(display.events.empty())


if __name__ == '__main__':
    unittest.main()
