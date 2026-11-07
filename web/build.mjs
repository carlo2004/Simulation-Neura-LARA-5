import { cpSync, copyFileSync, mkdirSync, readFileSync, rmSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';

const web = fileURLToPath(new URL('.', import.meta.url));
const out = join(web, 'dist');
const proof = join(web, '../examples/prompt2robo-replays');
const manifest = JSON.parse(readFileSync(join(proof, 'manifest.json'), 'utf8'));

rmSync(out, { recursive: true, force: true });
cpSync(join(web, 'public'), out, { recursive: true });
copyFileSync(join(web, '../config/prompt2robo.lock.json'), join(out, 'prompt2robo.lock.json'));
mkdirSync(join(out, 'proof'));
for (const name of ['manifest.json', 'eval_v4-manifest.json',
  ...manifest.results.flatMap((row) => row.video ? [row.video] : [])]) {
  if (!/^[\w-]+\.(mp4|json)$/.test(name)) throw new Error('Invalid proof file: ' + name);
  copyFileSync(join(proof, name), join(out, 'proof', name));
}
console.log('Workbench built in web/dist');
