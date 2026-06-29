"""OTLP gRPC receiver (PRD §5.1)."""
from __future__ import annotations

import grpc
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2_grpc
from opentelemetry.proto.collector.trace.v1 import trace_pb2

from app.main import AppContext
from app.pipeline import process_batch
from app.receivers.otlp import otlp_to_events


class TraceServiceServicer(trace_service_pb2_grpc.TraceServiceServicer):
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx

    async def Export(self, request: trace_pb2.ExportTraceServiceRequest, context):
        from google.protobuf.json_format import MessageToDict
        try:
            body = MessageToDict(request, preserving_proto_field_name=True)
        except Exception:
            from app.observability import capture_exception
            capture_exception(Exception("otlp gRPC parse failed"))
            return trace_pb2.ExportTraceServiceResponse()
        events = otlp_to_events(body, org_id="otlp-grpc")
        await process_batch(events, org_id="otlp-grpc", deps=self.ctx.deps)
        return trace_pb2.ExportTraceServiceResponse()


async def serve_grpc(ctx: AppContext, port: int = 4317) -> None:
    from app.observability import capture_exception
    server = grpc.aio.server()
    trace_service_pb2_grpc.add_TraceServiceServicer_to_server(TraceServiceServicer(ctx), server)
    server.add_insecure_port(f"0.0.0.0:{port}")
    await server.start()
    import asyncio
    try:
        await server.wait_for_termination()
    except asyncio.CancelledError:
        await server.stop(grace=5)
