"""Keep one model loaded on a compute machine; expose it through SSH loopback."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

from stacklab.paths import RUNS_ROOT
from stacklab.llm.runtime import LocalModel
from stacklab.llm.service import InferenceServer


def main(argv=None):
    parser = argparse.ArgumentParser(description='Persistent inference server for the local live simulation over SSH')
    parser.add_argument('--model', help='Model alias; must already be installed')
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    parser.add_argument('--threads', type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument('--port', type=int, default=8765, help='Loopback port forwarded by SSH')
    parser.add_argument('--load-timeout', type=int, default=180)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    client = None
    try:
        if not 0 < args.port < 65536 or args.load_timeout <= 0:
            raise ValueError('Use a valid port and positive load timeout')
        output = (args.output or RUNS_ROOT/('serve_'+time.strftime('%Y%m%d_%H%M%S'))).resolve()
        if output.exists() and any(output.iterdir()):
            raise ValueError('Choose a new output directory')
        output.mkdir(parents=True, exist_ok=True)
        client = LocalModel(args.model, threads=args.threads, device=args.device)
        # Reserve the requested port before loading a potentially large model.
        with InferenceServer(client, output, args.port) as server:
            print('Loading '+client.config['model_id']+' on '+args.device+'; logs: '+str(output), flush=True)
            client.start(output/'runtime', timeout=args.load_timeout)
            server.info['hardware'] = client.hardware
            (output/'server.json').write_text(json.dumps(server.info, indent=2)+'\n', encoding='utf-8')
            print('READY http://127.0.0.1:'+str(args.port), flush=True)
            print('Forward this loopback port over SSH. Ctrl+C stops the server.', flush=True)
            server.serve_forever(poll_interval=.2)
        return 0
    except KeyboardInterrupt:
        return 130
    except (ValueError, OSError, RuntimeError) as error:
        print('Server error: '+str(error), file=sys.stderr)
        return 1
    finally:
        if client:
            client.close()


if __name__ == '__main__':
    raise SystemExit(main())
