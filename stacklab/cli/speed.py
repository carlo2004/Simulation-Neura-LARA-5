"""Compact terminal representation of measured inference performance."""


def format_speed(metrics):
    phase = metrics.get('phase')
    elapsed = metrics.get('total_seconds')
    if elapsed is None:
        elapsed = metrics.get('request_seconds') or 0
    if phase == 'loading':
        return f'Modell laden: {elapsed:.1f} s | Token/s nach dem Start'
    parts = []
    rate = metrics.get('decode_tokens_per_second')
    effective = metrics.get('effective_tokens_per_second')
    if rate is not None:
        parts.append(f'Ausgabe: {rate:.1f} Token/s')
    elif effective is not None:
        parts.append(f'Gesamt inkl. Prompt: {effective:.1f} Token/s')
    else:
        parts.append('Prompt verarbeiten / auf erstes Token warten' if phase == 'prompt' else 'Token/s noch nicht gemeldet')
    prompt = metrics.get('prompt_tokens_per_second')
    if prompt is not None:
        parts.append(f'Prompt: {prompt:.1f} Token/s')
    tokens = metrics.get('output_tokens')
    if tokens is not None:
        parts.append(f'{int(tokens)} Ausgabetoken')
    parts.append(f'{elapsed:.1f} s')
    if phase == 'finished' or phase is None:
        load = metrics.get('model_load_seconds')
        first = metrics.get('time_to_first_token_seconds')
        if load is not None:
            parts.append(f'Laden: {load:.1f} s')
        if first is not None:
            parts.append(f'Erstes Token: {first:.2f} s')
    if metrics.get('partial'):
        parts.append('Teilmessung')
    return ' | '.join(parts)
