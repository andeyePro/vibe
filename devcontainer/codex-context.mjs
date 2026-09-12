#!/usr/bin/env node
// Discovery only: never reads credentials or treats policy text as proof.
import { accessSync, constants, existsSync, lstatSync, readFileSync, realpathSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

function git(cwd, args) {
  const r = spawnSync('git', ['-C', cwd, ...args], { encoding: 'utf8', timeout: 10000, input: '' });
  if (r.error || r.status !== 0) throw new Error('Cannot inspect project git state');
  return r.stdout.trim();
}
function executable(path) {
  try { accessSync(path, constants.X_OK); return true; } catch { return false; }
}
export function discover(cwd, bin = '/usr/local/bin') {
  const root = realpathSync(git(cwd, ['rev-parse', '--show-toplevel']));
  const configPath = join(root, '.vibe/codex-context.json');
  let config = {};
  if (existsSync(configPath)) {
    if (!lstatSync(configPath).isFile() || lstatSync(configPath).isSymbolicLink() || realpathSync(configPath) !== configPath) {
      throw new Error('Context configuration must not traverse symlinks');
    }
    if (git(root, ['ls-files', '--', ':(icase).vibe/codex-context.json'])) {
      throw new Error('Context configuration must be local and untracked');
    }
    if (lstatSync(configPath).size > 65536) throw new Error('Context configuration is too large');
    config = JSON.parse(readFileSync(configPath, 'utf8'));
    if (!config || Array.isArray(config) || typeof config !== 'object' ||
        Object.keys(config).some(k => !['references', 'questions', 'answers', 'archive', 'build'].includes(k))) {
      throw new Error('Invalid context configuration keys');
    }
    for (const key of ['questions', 'answers', 'archive', 'build']) {
      if (config[key] !== undefined && (typeof config[key] !== 'string' || !config[key].trim())) {
        throw new Error(`Invalid context ${key}`);
      }
    }
    if (config.references !== undefined && (!Array.isArray(config.references) ||
        config.references.length > 50 || config.references.some(x => typeof x !== 'string' || !x.trim()))) {
      throw new Error('references must contain at most 50 paths');
    }
  }
  const describe = p => ({ path: resolve(root, p), exists: existsSync(resolve(root, p)) });
  const defaults = ['AGENTS.md', 'CLAUDE.md', 'TODO.md', 'docs/spec', '.vss/sessions'];
  const helpers = ['vibe-delegate', 'codex-supervisor', 'codex-guard-liveness', 'codex-entry', 'mac-build', 'taskandi-client'];
  return {
    root,
    configuration: existsSync(configPath) ? configPath : null,
    references: [...new Set([...defaults, ...(config.references || [])])].map(describe),
    channels: Object.fromEntries(['questions', 'answers', 'archive'].map(k =>
      [k, describe(config[k] || { questions: '.vss/fromCodex.md', answers: '.vss/fromMartin-toCodex.md', archive: '.vss/Codex-Q&A-archive.md' }[k])])),
    answerAlias: 'FM2C',
    build: describe(config.build || '.vibe/mac-build.json'),
    installedHelpers: helpers.map(name => ({ name, path: join(bin, name), executable: executable(join(bin, name)) })),
    policyEvidence: 'Discovery only. Run the installed guard-liveness gate and inspect actual runtime tools; configured restrictions are not proof of enforcement.',
  };
}

if (process.argv[1] && realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const args = process.argv.slice(2);
    if (args.length > 1) throw new Error('Usage: codex-context [project-directory]');
    process.stdout.write(JSON.stringify(discover(args[0] || process.cwd()), null, 2) + '\n');
  } catch (error) { process.stderr.write(`codex-context: ${error.message}\n`); process.exitCode = 1; }
}
