'use strict';
// AI Observability Platform — Node.js client
// Requires Node.js >= 18 (native fetch + crypto — zero external deps)

const crypto = require('crypto');

const _cfg = { ingestUrl: '', token: '' };

// Thread-local equivalent via AsyncLocalStorage is overkill for most usage;
// module-level state works for sequential agent code.
const _ctx = { runId: null, agent: null, spanStack: [] };

function configure({ ingestUrl, token }) {
  _cfg.ingestUrl = ingestUrl.replace(/\/$/, '');
  _cfg.token = token;
}

async function run(agent, input, fn) {
  const runId   = crypto.randomUUID();
  const spanId  = _randSpan();
  const started = new Date().toISOString();

  _ctx.runId     = runId;
  _ctx.agent     = agent;
  _ctx.spanStack = [spanId];

  _emit({ run_id: runId, span_id: spanId, type: 'run.start',
          agent, started_at: started,
          payload: { agent, input_hash: _hashOf(input) } });

  const ctx = new RunContext(runId, agent, spanId);
  let status = 'succeeded';
  try {
    return await fn(ctx);
  } catch (e) {
    status = 'failed';
    throw e;
  } finally {
    _emit({ run_id: runId, span_id: _randSpan(), type: 'run.end',
            agent, started_at: started, ended_at: new Date().toISOString(),
            payload: {
              status,
              total_steps:    ctx.steps,
              total_tokens:   ctx.totalTokens,
              total_cost_usd: ctx.totalCost,
            } });
    _ctx.runId = null; _ctx.agent = null; _ctx.spanStack = [];
  }
}

async function observe({ llm, tool, agent: agentName }, fn) {
  const kind   = llm ? 'llm' : tool ? 'tool' : agentName ? 'agent' : null;
  const target = llm ?? tool ?? agentName;
  if (!kind) throw new Error('observe requires exactly one of llm, tool, or agent');
  if (!_ctx.runId) throw new Error('observe must be called inside run()');

  const parent  = _ctx.spanStack.at(-1);
  const spanId  = _randSpan();
  const started = new Date().toISOString();
  const type    = { llm: 'llm.call', tool: 'tool.invoke', agent: 'step.start' }[kind];
  const curAgent = _ctx.agent;

  let result, err;
  try {
    result = await fn();
    return result;
  } catch (e) {
    err = e;
    throw e;
  } finally {
    const payload =
      kind === 'llm'   ? { model: target, finish_reason: err ? 'error' : 'stop' } :
      kind === 'tool'  ? { tool: target, args_hash: `sha256:${'0'.repeat(64)}`, status: err ? 'error' : 'ok' } :
                         { step: 0, status: err ? 'error' : 'ok' };

    _emit({ run_id: _ctx.runId, span_id: spanId, parent_span_id: parent,
            type, agent: curAgent, llm_model: kind === 'llm' ? target : undefined,
            started_at: started, ended_at: new Date().toISOString(), payload });
  }
}

// Generates a signed token. Normally done server-side. For reference/testing only.
function issueToken(secret, { orgId, name = 'default', scopes = ['ingest.write'], ttlSeconds = 365 * 86400 }) {
  const payload = Buffer.from(JSON.stringify({
    org_id: orgId, scopes, exp: Math.floor(Date.now() / 1000) + ttlSeconds, name,
  })).toString('base64url');
  const sig = crypto.createHmac('sha256', secret).update(payload).digest('hex').slice(0, 32);
  return `ai_obs_v1.${payload}.${sig}`;
}

class RunContext {
  constructor(runId, agent, spanId) {
    this.runId       = runId;
    this.agent       = agent;
    this.spanId      = spanId;
    this.steps       = 0;
    this.totalTokens = 0;
    this.totalCost   = 0;
  }

  checkpoint(step, state) {
    this.steps++;
    _emit({ run_id: this.runId, span_id: _randSpan(), type: 'checkpoint',
            agent: this.agent, started_at: new Date().toISOString(),
            payload: { step, state_hash: _hashOf(state) } });
  }

  handoff(to, reason = 'delegation', payload = {}) {
    _emit({ run_id: this.runId, span_id: _randSpan(), type: 'handoff',
            agent: this.agent, started_at: new Date().toISOString(),
            payload: { from: this.agent, to, reason, payload_hash: _hashOf(payload) } });
  }
}

function _emit(event) {
  const body = JSON.stringify([_compact(event)]);
  // fire-and-forget; errors are swallowed to never block the caller
  fetch(`${_cfg.ingestUrl}/v1/events`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${_cfg.token}` },
    body,
  }).catch(() => {});
}

function _compact(obj) {
  return Object.fromEntries(Object.entries(obj).filter(([, v]) => v !== null && v !== undefined));
}

function _randSpan() {
  return crypto.randomBytes(8).toString('hex');
}

function _hashOf(v) {
  return 'sha256:' + crypto.createHash('sha256').update(JSON.stringify(v)).digest('hex');
}

module.exports = { configure, run, observe, issueToken, RunContext };
