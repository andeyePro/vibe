// Fake Task&I agent-exchange service for smoke/checks_58 and checks_59 (task_066).
//
// usage: node taskandi_v23_server.mjs <ctl.json> <log.jsonl> <fixtures-v23-dir> <fixtures-v22-dir>
// Prints the listening port on stdout.  <ctl.json> is re-read on every request, so a test rewrites it between calls.
//
// Behaviour.  Answers `capabilities`, the reads and the six writes from the fixtures.  With ctl.revision
// "vibe-agent-exchange-v2.2" it behaves like a v2.2 service: strict about unknown keys (request_id, at, task on
// next_task are `invalid_request`), v2.2 shapes.  Otherwise it is a v2.3-family service (default v2.5, like the
// fixtures): writes replay by `request_id` (same id + same body = the stored response, nothing applied; same id +
// other body = 409 receipt_collision), reads reject `request_id`, record_usage is unique on (source, source_ref).
//
// Log: one JSONL line per request {t:'req', id, method, url, rawHeaders, body}; one per applied write
// {t:'applied', action, request_id, body}; one per replay {t:'replay', action, request_id}.
//
// Controls (all optional) in ctl:
//   revision        contract string to answer (default v2.5)
//   limits          object merged over the capabilities limits;  capsDrop: [keys] removed from the response;
//                   capsAdd: {k: v} merged onto the response top level;  idPattern: replaces id_pattern
//   errors          {action: {status, json?, raw?, times?}}  answered instead of the call, nothing applied
//   dropAfterApply  {action: n}  apply, then destroy the socket, for the first n requests to that action
//   dropBeforeApply {action: n}  destroy the socket without applying
//   rawAfterApply   {action: text}  apply, then answer 200 with that non-JSON text
//   badResponse     {action: <json>}  apply, then answer 200 with that JSON instead of the real response
//   offer           object merged over the default next_task offer;  offerTask forces the offered task
//   refuse          reason: next_task with a `task` answers {task:null, reason}
//   answers         [ask items with seq]: list_asks serves those with seq > since
//   offerDrop       [dotted paths] removed from the offer;  nextRaw: a fixed next_task response;  statusRaw: a fixed ask_status response
//   stopAfterCaps   true: stop listening once a capabilities answer has been sent (later connects are refused: a not-sent attempt)
//   listRaw         a fixed list_asks response (overrides answers)
//   nowMs           the server clock (default Date.now())
import http from 'node:http';
import fs from 'node:fs';
import { randomUUID } from 'node:crypto';
const [ctlPath, logPath, fix23, fix22] = process.argv.slice(2);
const log = o => fs.appendFileSync(logPath, JSON.stringify(o) + '\n');
const fx = (dir, name) => JSON.parse(fs.readFileSync(`${dir}/${name}.json`, 'utf8'));
const LIMIT_KEYS = ['unit', 'id', 'id_unit', 'request_bytes', 'question', 'default', 'options', 'option', 'ask_post', 'comment', 'summary', 'reason'];
const V22 = 'vibe-agent-exchange-v2.2';
const WRITES = new Set(['ask', 'comment', 'record_usage', 'record_time', 'release', 'complete']);
const READS = new Set(['capabilities', 'next_task', 'list_asks', 'ask_status']);
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const counters = {}; const receipts = new Map(); const usage = new Map(); const completed = new Map(); let seqNo = 0;
const bump = (kind, action) => { const k = `${kind}:${action}`; counters[k] = (counters[k] ?? 0) + 1; return counters[k]; };
const canon = v => Array.isArray(v) ? `[${v.map(canon).join(',')}]` : v && typeof v === 'object' ? `{${Object.keys(v).sort().map(k => `${JSON.stringify(k)}:${canon(v[k])}`).join(',')}}` : JSON.stringify(v);

function capabilities(ctl) {
  const rev = ctl.revision ?? 'vibe-agent-exchange-v2.5';
  const r = JSON.parse(JSON.stringify(rev === V22 ? fx(fix22, 'capabilities').response : fx(fix23, 'capabilities').response));
  if (rev !== V22) r.contract = rev;
  if (rev !== V22 && ctl.idPattern !== undefined) r.id_pattern = ctl.idPattern;
  if (rev === 'vibe-agent-exchange-v2.3') {
    r.calls = r.calls.filter(c => c !== 'create_task' && c !== 'update_task');
    r.limits = Object.fromEntries(Object.entries(r.limits).filter(([k]) => LIMIT_KEYS.includes(k)));
  }
  if (rev !== V22) Object.assign(r.limits, ctl.limits ?? {});
  for (const k of ctl.capsDrop ?? []) { delete r[k]; if (r.limits) delete r.limits[k]; }
  Object.assign(r, ctl.capsAdd ?? {});
  return r;
}

function offer(ctl, body, v22) {
  const base = JSON.parse(JSON.stringify(fx(v22 ? fix22 : fix23, 'next_task').response));
  base.task = ctl.offerTask ?? body.task ?? 'leaf-b';
  base.lease = { until: base.lease.until, session: body.session };
  Object.assign(base, ctl.offer ?? {});
  for (const path of ctl.offerDrop ?? []) { const parts = path.split('.'); let o = base; for (const k of parts.slice(0, -1)) o = o?.[k]; if (o) delete o[parts[parts.length - 1]]; }
  return base;
}

function figures(b) { const { session, agent, request_id, connection, action, ...rest } = b; return rest; }

function handle(ctl, body, reqNo) {
  const v22 = (ctl.revision ?? '') === V22;
  const action = body.action;
  const err = (status, code) => ({ status, json: { error: code } });
  const e = ctl.errors?.[action];
  if (e && (e.times === undefined || bump('err', action) <= e.times)) return { status: e.status ?? 409, json: e.json, raw: e.raw, nothing: true };
  if (!READS.has(action) && !WRITES.has(action)) return err(409, 'invalid_request');
  if (v22 && 'request_id' in body) return err(409, 'invalid_request');
  if (v22 && body.at !== undefined) return err(409, 'invalid_request');
  if (!v22 && READS.has(action) && 'request_id' in body) return err(409, 'invalid_request');
  if (action === 'capabilities') return { json: capabilities(ctl) };
  if (action === 'next_task') {
    if (v22 && 'task' in body) return err(409, 'invalid_request');
    if ('task' in body && ctl.refuse) return { json: { task: null, reason: ctl.refuse } };
    if (ctl.nextRaw !== undefined) return { json: ctl.nextRaw };
    if (ctl.noneEligible) return { json: { task: null } };
    return { json: offer(ctl, body, v22) };
  }
  if (action === 'ask_status') return { json: ctl.statusRaw ?? fx(v22 ? fix22 : fix23, 'ask_status').response };
  if (action === 'list_asks') {
    if (ctl.listRaw) return { json: ctl.listRaw };
    if (v22) return { json: { task: body.task, now: ctl.nowMs ?? Date.now(), asks: [] } };
    const since = body.since ?? 0;
    const asks = (ctl.answers ?? []).filter(a => a.seq > since);
    return { json: { task: body.task, seq: asks.length ? asks[asks.length - 1].seq : since, asks } };
  }
  // writes
  if (!v22 && body.request_id !== undefined && !(typeof body.request_id === 'string' && UUID.test(body.request_id))) return err(409, 'invalid_request');
  const now = ctl.nowMs ?? Date.now();
  if (action === 'record_usage' && body.at !== undefined && (body.at < now - 30 * 86400000 || body.at > now + 60000)) return err(409, 'invalid_request');
  const rid = body.request_id;
  const rkey = rid === undefined ? undefined : `${body.connection}\u0000${rid}`;   // replay is per connection: another connection's request_id is a fresh request
  const sig = canon({ ...body, request_id: undefined });
  if (rkey !== undefined && receipts.has(rkey)) {
    const r = receipts.get(rkey);
    if (r.sig !== sig) return err(409, 'receipt_collision');
    log({ t: 'replay', action, request_id: rid });
    return { json: r.response, replay: true };
  }
  let response;
  if (action === 'record_usage' && !v22) {
    const ukey = `${body.source}\u0000${body.source_ref}`;
    const ufig = canon(figures({ ...body, source: undefined, source_ref: undefined }));
    const prior = usage.get(ukey);
    if (prior && prior.fig !== ufig) return err(409, 'receipt_collision');
    const t = body.task;
    const rolled = () => { let tokens = 0, cr = 0; for (const u of usage.values()) if (u.task === t) { tokens += u.tokens; cr += u.cr; } return { windows: usage.size ? 1 : 0, tokens, cache_read: cr }; };
    if (prior) { response = { task: t, spent: rolled() }; if (rid !== undefined) receipts.set(rkey, { sig, response }); log({ t: 'replay', action, request_id: rid ?? null, usage: true }); return { json: response, replay: true }; }
    usage.set(ukey, { fig: ufig, task: t, tokens: body.input + body.output + body.cache_write, cr: body.cache_read });
    response = { task: t, spent: rolled() };
  } else if (action === 'complete') {
    const prior = completed.get(body.task);
    response = prior ?? { ...fx(fix23, 'complete').response, completion_id: randomUUID() };
    if (!v22 || !prior) completed.set(body.task, response);
  } else {
    response = JSON.parse(JSON.stringify(fx(v22 ? fix22 : fix23, action).response));
    for (const k of ['ask_id', 'comment_id', 'entry_id']) if (k in response) response[k] = randomUUID();
    if ('task' in response) response.task = body.task;
  }
  if (rid !== undefined) receipts.set(rkey, { sig, response });
  log({ t: 'applied', action, request_id: rid ?? null, body, response });
  return { json: response, applied: true };
}

const server = http.createServer((req, res) => {
  const chunks = []; req.on('data', c => chunks.push(c));
  req.on('end', () => {
    const raw = Buffer.concat(chunks).toString('utf8');
    const reqNo = counters.req = (counters.req ?? 0) + 1;
    log({ t: 'req', id: reqNo, method: req.method, url: req.url, rawHeaders: req.rawHeaders, body: raw });
    let body; try { body = JSON.parse(raw); } catch { res.writeHead(400, { 'content-type': 'application/json' }); return res.end('{"error":"invalid_request"}'); }
    const ctl = JSON.parse(fs.readFileSync(ctlPath, 'utf8'));
    const action = body.action;
    if (ctl.dropBeforeApply?.[action] !== undefined && bump('dropb', action) <= ctl.dropBeforeApply[action]) return req.socket.destroy();
    const out = handle(ctl, body, reqNo);
    const drop = (out.applied || out.replay) && ctl.dropAfterApply?.[action] !== undefined && bump('dropa', action) <= ctl.dropAfterApply[action];
    if (drop) return req.socket.destroy();
    if (out.applied && ctl.rawAfterApply?.[action] !== undefined) { res.writeHead(200, { 'content-type': 'application/json' }); return res.end(ctl.rawAfterApply[action]); }
    if (out.applied && ctl.badResponse?.[action] !== undefined) { res.writeHead(200, { 'content-type': 'application/json' }); return res.end(JSON.stringify(ctl.badResponse[action])); }
    res.writeHead(out.status ?? 200, { 'content-type': 'application/json' });
    res.end(out.raw !== undefined ? out.raw : JSON.stringify(out.json ?? {}));
    if (action === 'capabilities' && ctl.stopAfterCaps) server.close();
  });
});
server.listen(0, '127.0.0.1', () => console.log(server.address().port));
