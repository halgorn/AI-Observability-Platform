//! AI Observability Platform — Rust client
//! Uses blocking reqwest so no async runtime is required.

use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use chrono::Utc;
use hmac::{Hmac, Mac};
use reqwest::blocking::Client;
use serde::Serialize;
use serde_json::{json, Value};
use sha2::Sha256;
use std::cell::RefCell;
use std::sync::{OnceLock, RwLock};
use uuid::Uuid;

// --- global config ---

struct Config {
    ingest_url: String,
    token: String,
}

static CFG: OnceLock<RwLock<Config>> = OnceLock::new();

fn cfg_lock() -> &'static RwLock<Config> {
    CFG.get_or_init(|| {
        RwLock::new(Config {
            ingest_url: String::new(),
            token: String::new(),
        })
    })
}

/// Configure the client. Call once at startup.
pub fn configure(ingest_url: impl Into<String>, token: impl Into<String>) {
    let mut c = cfg_lock().write().unwrap();
    c.ingest_url = ingest_url.into().trim_end_matches('/').to_string();
    c.token = token.into();
}

// --- thread-local run state ---

struct RunState {
    run_id: String,
    agent: String,
    span_stack: Vec<String>,
}

thread_local! {
    static CURRENT: RefCell<Option<RunState>> = RefCell::new(None);
}

fn with_current<F, R>(f: F) -> Option<R>
where
    F: FnOnce(&RunState) -> R,
{
    CURRENT.with(|c| c.borrow().as_ref().map(f))
}

// --- event struct ---

#[derive(Serialize)]
struct Event {
    run_id: String,
    span_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    parent_span_id: Option<String>,
    #[serde(rename = "type")]
    event_type: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    agent: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    llm_model: Option<String>,
    started_at: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    ended_at: Option<String>,
    payload: Value,
}

fn emit(event: Event) {
    let (url, token) = {
        let c = cfg_lock().read().unwrap();
        (format!("{}/v1/events", c.ingest_url), c.token.clone())
    };
    let client = Client::new();
    let _ = client
        .post(&url)
        .header("Content-Type", "application/json")
        .header("Authorization", format!("Bearer {}", token))
        .json(&[event])
        .send();
}

fn rand_span() -> String {
    let bytes: Vec<u8> = (0..8).map(|_| rand::random::<u8>()).collect();
    hex::encode(bytes)
}

fn now_iso() -> String {
    Utc::now().to_rfc3339()
}

fn hash_of(v: &Value) -> String {
    use sha2::Digest;
    let s = serde_json::to_string(v).unwrap_or_default();
    let mut hasher = sha2::Sha256::new();
    hasher.update(s.as_bytes());
    format!("sha256:{}", hex::encode(hasher.finalize()))
}

// --- public API ---

/// Run context passed to the `run` callback.
pub struct RunContext {
    pub run_id: String,
    pub agent: String,
    pub steps: usize,
    pub total_tokens: u64,
    pub total_cost: f64,
    span_id: String,
}

impl RunContext {
    /// Emit a checkpoint event.
    pub fn checkpoint(&mut self, step: usize, state: &Value) {
        self.steps += 1;
        emit(Event {
            run_id: self.run_id.clone(),
            span_id: rand_span(),
            parent_span_id: None,
            event_type: "checkpoint".into(),
            agent: Some(self.agent.clone()),
            llm_model: None,
            started_at: now_iso(),
            ended_at: None,
            payload: json!({ "step": step, "state_hash": hash_of(state) }),
        });
    }

    /// Emit a handoff event.
    pub fn handoff(&self, to: &str, reason: &str, payload: &Value) {
        emit(Event {
            run_id: self.run_id.clone(),
            span_id: rand_span(),
            parent_span_id: None,
            event_type: "handoff".into(),
            agent: Some(self.agent.clone()),
            llm_model: None,
            started_at: now_iso(),
            ended_at: None,
            payload: json!({
                "from": self.agent,
                "to": to,
                "reason": reason,
                "payload_hash": hash_of(payload),
            }),
        });
    }
}

/// Emits `run.start`, calls `f`, then emits `run.end`.
pub fn run<F, E>(agent: &str, input: &Value, f: F) -> Result<(), E>
where
    F: FnOnce(&mut RunContext) -> Result<(), E>,
{
    let run_id   = Uuid::new_v4().to_string();
    let span_id  = rand_span();
    let started  = now_iso();

    CURRENT.with(|c| {
        *c.borrow_mut() = Some(RunState {
            run_id: run_id.clone(),
            agent: agent.to_string(),
            span_stack: vec![span_id.clone()],
        });
    });

    emit(Event {
        run_id: run_id.clone(), span_id: span_id.clone(),
        parent_span_id: None, event_type: "run.start".into(),
        agent: Some(agent.to_string()), llm_model: None,
        started_at: started.clone(), ended_at: None,
        payload: json!({ "agent": agent, "input_hash": hash_of(input) }),
    });

    let mut ctx = RunContext {
        run_id: run_id.clone(), agent: agent.to_string(),
        steps: 0, total_tokens: 0, total_cost: 0.0,
        span_id: span_id.clone(),
    };

    let result = f(&mut ctx);
    let status = if result.is_ok() { "succeeded" } else { "failed" };

    emit(Event {
        run_id: run_id.clone(), span_id: rand_span(),
        parent_span_id: None, event_type: "run.end".into(),
        agent: Some(agent.to_string()), llm_model: None,
        started_at: started, ended_at: Some(now_iso()),
        payload: json!({
            "status":         status,
            "total_steps":    ctx.steps,
            "total_tokens":   ctx.total_tokens,
            "total_cost_usd": ctx.total_cost,
        }),
    });

    CURRENT.with(|c| *c.borrow_mut() = None);
    result
}

/// Wraps a closure with a telemetry event.
/// Pass exactly one of `llm`, `tool`, or `agent_name` (non-empty string).
pub fn observe<F, T>(llm: &str, tool: &str, agent_name: &str, f: F) -> T
where
    F: FnOnce() -> T,
{
    let (kind, target) = if !llm.is_empty() {
        ("llm", llm)
    } else if !tool.is_empty() {
        ("tool", tool)
    } else {
        ("agent", agent_name)
    };

    let (run_id, parent, cur_agent) = CURRENT.with(|c| {
        let b = c.borrow();
        let st = b.as_ref().expect("observe must be called inside run()");
        (
            st.run_id.clone(),
            st.span_stack.last().cloned().unwrap_or_default(),
            st.agent.clone(),
        )
    });

    let span_id  = rand_span();
    let started  = now_iso();
    let ev_type  = match kind { "llm" => "llm.call", "tool" => "tool.invoke", _ => "step.start" };
    let llm_model = if kind == "llm" { Some(target.to_string()) } else { None };

    let result = f();

    let payload = match kind {
        "llm"  => json!({ "model": target, "finish_reason": "stop" }),
        "tool" => json!({ "tool": target, "args_hash": format!("sha256:{}", "0".repeat(64)), "status": "ok" }),
        _      => json!({ "step": 0, "status": "ok" }),
    };

    emit(Event {
        run_id, span_id, parent_span_id: Some(parent),
        event_type: ev_type.into(),
        agent: Some(cur_agent), llm_model,
        started_at: started, ended_at: Some(now_iso()),
        payload,
    });

    result
}

/// Generates a signed ingest token.
/// Normally done server-side via the ingest-api — for reference/testing only.
pub fn issue_token(secret: &str, org_id: &str, name: &str, scopes: &[&str], ttl_seconds: i64) -> String {
    let exp = chrono::Utc::now().timestamp() + ttl_seconds;
    let payload = serde_json::to_string(&json!({
        "org_id": org_id, "scopes": scopes, "exp": exp, "name": name,
    }))
    .unwrap();
    let b64 = URL_SAFE_NO_PAD.encode(payload.as_bytes());
    let mut mac = <Hmac<Sha256>>::new_from_slice(secret.as_bytes()).unwrap();
    mac.update(b64.as_bytes());
    let sig = hex::encode(mac.finalize().into_bytes());
    format!("ai_obs_v1.{}.{}", b64, &sig[..32])
}
