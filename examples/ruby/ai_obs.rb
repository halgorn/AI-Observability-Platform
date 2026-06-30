# frozen_string_literal: true

require 'net/http'
require 'json'
require 'securerandom'
require 'digest'
require 'openssl'
require 'time'

module AiObs
  class << self
    attr_accessor :ingest_url, :token

    def configure(ingest_url:, token:)
      @ingest_url = ingest_url.chomp('/')
      @token      = token
    end

    def run(agent:, input:)
      run_id  = SecureRandom.uuid
      span_id = SecureRandom.hex(8)
      started = Time.now.utc

      Thread.current[:ai_obs_run_id]     = run_id
      Thread.current[:ai_obs_agent]      = agent
      Thread.current[:ai_obs_span_stack] = [span_id]

      _emit(run_id: run_id, span_id: span_id, type: 'run.start',
            agent: agent, started_at: started.iso8601,
            payload: { agent: agent, input_hash: _hash(input) })

      ctx    = RunContext.new(run_id: run_id, agent: agent, span_id: span_id)
      status = 'succeeded'
      begin
        yield ctx
      rescue StandardError
        status = 'failed'
        raise
      ensure
        _emit(run_id: run_id, span_id: SecureRandom.hex(8), type: 'run.end',
              agent: agent, started_at: started.iso8601, ended_at: Time.now.utc.iso8601,
              payload: {
                status:         status,
                total_steps:    ctx.steps,
                total_tokens:   ctx.total_tokens,
                total_cost_usd: ctx.total_cost
              })
        Thread.current[:ai_obs_run_id]     = nil
        Thread.current[:ai_obs_agent]      = nil
        Thread.current[:ai_obs_span_stack] = nil
      end
    end

    def observe(llm: nil, tool: nil, agent: nil)
      kind, target = [['llm', llm], ['tool', tool], ['agent', agent]].find { |_, v| v }
      raise ArgumentError, 'observe requires exactly one of llm:, tool:, or agent:' unless kind

      run_id = Thread.current[:ai_obs_run_id]
      raise 'AiObs.observe must be called inside AiObs.run' unless run_id

      parent  = Thread.current[:ai_obs_span_stack]&.last
      span_id = SecureRandom.hex(8)
      started = Time.now.utc
      type    = { 'agent' => 'step.start', 'tool' => 'tool.invoke', 'llm' => 'llm.call' }.fetch(kind)
      cur_agent = Thread.current[:ai_obs_agent]

      error = nil
      begin
        yield
      rescue StandardError => e
        error = e
        raise
      ensure
        payload = case kind
                  when 'llm'   then { model: target, finish_reason: error ? 'error' : 'stop' }
                  when 'tool'  then { tool: target, args_hash: "sha256:#{'0' * 64}", status: error ? 'error' : 'ok' }
                  when 'agent' then { step: 0, status: error ? 'error' : 'ok' }
                  end
        _emit(run_id: run_id, span_id: span_id, parent_span_id: parent,
              type: type, agent: cur_agent, llm_model: (kind == 'llm' ? target : nil),
              started_at: started.iso8601, ended_at: Time.now.utc.iso8601,
              payload: payload)
      end
    end

    # Generates a signed token. Normally done server-side — call the ingest-api
    # POST /v1/tokens endpoint instead. This is only for reference/testing.
    def issue_token(secret:, org_id:, name: 'default', scopes: ['ingest.write'], ttl: 365 * 86_400)
      raw  = JSON.generate({ org_id: org_id, scopes: scopes, exp: Time.now.to_i + ttl, name: name })
      b64  = Base64.urlsafe_encode64(raw).gsub('=', '')
      sig  = OpenSSL::HMAC.hexdigest('sha256', secret, b64)[0, 32]
      "ai_obs_v1.#{b64}.#{sig}"
    end

    def _hash(obj)
      "sha256:#{Digest::SHA256.hexdigest(JSON.generate(obj))}"
    end

    def _emit(**event)
      uri = URI("#{ingest_url}/v1/events")
      http = Net::HTTP.new(uri.host, uri.port)
      http.use_ssl = uri.scheme == 'https'
      req = Net::HTTP::Post.new(uri.path,
                                'Content-Type'  => 'application/json',
                                'Authorization' => "Bearer #{token}")
      req.body = [event.compact].to_json
      Thread.new { http.request(req) rescue nil }
    end
    private :_hash, :_emit
  end

  # Mixin that adds an `observe` class macro for decorating methods.
  module Decorator
    def observe(method_name, llm: nil, tool: nil, agent: nil)
      opts = { llm: llm, tool: tool, agent: agent }
      prepend(Module.new do
        define_method(method_name) do |*args, **kwargs, &blk|
          AiObs.observe(**opts) { super(*args, **kwargs, &blk) }
        end
      end)
    end
  end

  class RunContext
    attr_reader :run_id, :agent, :steps, :total_tokens, :total_cost

    def initialize(run_id:, agent:, span_id:)
      @run_id       = run_id
      @agent        = agent
      @span_id      = span_id
      @steps        = 0
      @total_tokens = 0
      @total_cost   = 0.0
    end

    def checkpoint(step:, state:)
      @steps += 1
      AiObs.send(:_emit,
                 run_id: run_id, span_id: SecureRandom.hex(8), type: 'checkpoint',
                 agent: agent, started_at: Time.now.utc.iso8601,
                 payload: { step: step, state_hash: AiObs.send(:_hash, state) })
    end

    def handoff(to:, reason: 'delegation', payload: {})
      AiObs.send(:_emit,
                 run_id: run_id, span_id: SecureRandom.hex(8), type: 'handoff',
                 agent: agent, started_at: Time.now.utc.iso8601,
                 payload: { from: agent, to: to, reason: reason,
                            payload_hash: AiObs.send(:_hash, payload) })
    end
  end
end
