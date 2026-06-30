// Package aiobs is a minimal client for the AI Observability Platform.
// Zero external dependencies — stdlib only.
package aiobs

import (
	"bytes"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"sync"
	"time"
)

// --- configuration ---

var cfg struct {
	mu        sync.RWMutex
	ingestURL string
	token     string
}

// Configure sets the ingest URL and service token. Call once at startup.
func Configure(ingestURL, token string) {
	cfg.mu.Lock()
	defer cfg.mu.Unlock()
	cfg.ingestURL = strings.TrimRight(ingestURL, "/")
	cfg.token = token
}

// --- run context ---

type runState struct {
	runID     string
	agent     string
	spanStack []string
}

var state struct {
	mu      sync.Mutex
	current *runState
}

// RunContext carries per-run helpers passed to the Run callback.
type RunContext struct {
	RunID       string
	Agent       string
	Steps       int
	TotalTokens int
	TotalCost   float64
	spanID      string
}

// Checkpoint emits a checkpoint event and increments the step counter.
func (rc *RunContext) Checkpoint(step int, stateObj any) {
	rc.Steps++
	emit(event{ //nolint:errcheck
		RunID: rc.RunID, SpanID: randSpan(), Type: "checkpoint",
		Agent: rc.Agent, StartedAt: iso(time.Now().UTC()),
		Payload: map[string]any{"step": step, "state_hash": hashOf(stateObj)},
	})
}

// Handoff emits a handoff event.
func (rc *RunContext) Handoff(to, reason string, payload any) {
	if reason == "" {
		reason = "delegation"
	}
	emit(event{ //nolint:errcheck
		RunID: rc.RunID, SpanID: randSpan(), Type: "handoff",
		Agent: rc.Agent, StartedAt: iso(time.Now().UTC()),
		Payload: map[string]any{
			"from": rc.Agent, "to": to,
			"reason": reason, "payload_hash": hashOf(payload),
		},
	})
}

// --- Run ---

// Run emits run.start, invokes fn, then emits run.end.
func Run(agent string, input any, fn func(*RunContext) error) error {
	runID  := mustUUID()
	spanID := randSpan()
	started := time.Now().UTC()

	state.mu.Lock()
	state.current = &runState{runID: runID, agent: agent, spanStack: []string{spanID}}
	state.mu.Unlock()

	emit(event{ //nolint:errcheck
		RunID: runID, SpanID: spanID, Type: "run.start",
		Agent: agent, StartedAt: iso(started),
		Payload: map[string]any{"agent": agent, "input_hash": hashOf(input)},
	})

	rc := &RunContext{RunID: runID, Agent: agent, spanID: spanID}
	status := "succeeded"
	err := fn(rc)
	if err != nil {
		status = "failed"
	}

	emit(event{ //nolint:errcheck
		RunID: runID, SpanID: randSpan(), Type: "run.end",
		Agent: agent, StartedAt: iso(started), EndedAt: iso(time.Now().UTC()),
		Payload: map[string]any{
			"status":         status,
			"total_steps":    rc.Steps,
			"total_tokens":   rc.TotalTokens,
			"total_cost_usd": rc.TotalCost,
		},
	})

	state.mu.Lock()
	state.current = nil
	state.mu.Unlock()

	return err
}

// --- Observe ---

// Observe wraps fn with a telemetry event.
// Pass exactly one non-empty string in llm, tool, or agentName.
func Observe(llm, tool, agentName string, fn func() (any, error)) (any, error) {
	kind, target := "llm", llm
	switch {
	case tool != "":
		kind, target = "tool", tool
	case agentName != "":
		kind, target = "agent", agentName
	}

	state.mu.Lock()
	st := state.current
	state.mu.Unlock()
	if st == nil {
		return nil, fmt.Errorf("Observe must be called inside Run")
	}

	parent  := st.spanStack[len(st.spanStack)-1]
	spanID  := randSpan()
	started := time.Now().UTC()
	typeMap := map[string]string{"llm": "llm.call", "tool": "tool.invoke", "agent": "step.start"}
	curAgent := st.agent
	runID    := st.runID

	result, err := fn()

	llmModel := ""
	if kind == "llm" {
		llmModel = target
	}
	payload := buildPayload(kind, target, err)

	emit(event{ //nolint:errcheck
		RunID: runID, SpanID: spanID, ParentSpanID: parent,
		Type: typeMap[kind], Agent: curAgent, LLMModel: llmModel,
		StartedAt: iso(started), EndedAt: iso(time.Now().UTC()),
		Payload: payload,
	})

	return result, err
}

// IssueToken generates a signed ingest token.
// Normally done server-side via the ingest-api — for reference/testing only.
func IssueToken(secret, orgID, name string, scopes []string, ttlSeconds int64) string {
	p, _ := json.Marshal(map[string]any{
		"org_id": orgID, "scopes": scopes,
		"exp": time.Now().Unix() + ttlSeconds, "name": name,
	})
	b64 := base64.RawURLEncoding.EncodeToString(p)
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write([]byte(b64))
	sig := hex.EncodeToString(mac.Sum(nil))[:32]
	return "ai_obs_v1." + b64 + "." + sig
}

// --- internal ---

type event struct {
	RunID        string         `json:"run_id"`
	SpanID       string         `json:"span_id"`
	ParentSpanID string         `json:"parent_span_id,omitempty"`
	Type         string         `json:"type"`
	Agent        string         `json:"agent,omitempty"`
	LLMModel     string         `json:"llm_model,omitempty"`
	StartedAt    string         `json:"started_at"`
	EndedAt      string         `json:"ended_at,omitempty"`
	Payload      map[string]any `json:"payload"`
}

func emit(e event) error {
	cfg.mu.RLock()
	url := cfg.ingestURL + "/v1/events"
	tok := cfg.token
	cfg.mu.RUnlock()

	body, _ := json.Marshal([]event{e})
	req, err := http.NewRequest(http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+tok)

	go func() { http.DefaultClient.Do(req) }() //nolint:errcheck
	return nil
}

func buildPayload(kind, target string, err error) map[string]any {
	status := "ok"
	if err != nil {
		status = "error"
	}
	switch kind {
	case "llm":
		fr := "stop"
		if err != nil {
			fr = "error"
		}
		return map[string]any{"model": target, "finish_reason": fr}
	case "tool":
		return map[string]any{"tool": target, "args_hash": "sha256:" + strings.Repeat("0", 64), "status": status}
	default:
		return map[string]any{"step": 0, "status": status}
	}
}

func randSpan() string {
	b := make([]byte, 8)
	rand.Read(b) //nolint:errcheck
	return hex.EncodeToString(b)
}

func mustUUID() string {
	b := make([]byte, 16)
	rand.Read(b) //nolint:errcheck
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	return fmt.Sprintf("%08x-%04x-%04x-%04x-%012x",
		b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}

func iso(t time.Time) string { return t.Format(time.RFC3339) }

func hashOf(v any) string {
	b, _ := json.Marshal(v)
	h := sha256.Sum256(b)
	return "sha256:" + hex.EncodeToString(h[:])
}
