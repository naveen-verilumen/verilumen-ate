"""
Verilumen ATE Intelligence — Pydantic Schemas for Structured MCP Outputs
========================================================================
Defines strict input parameter bounds and validated structured output envelopes
returned by the consolidated MCP tools in `mcp_server.py`.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

AgentName = Literal[
    "shmoo",
    "test_time",
    "dtl",
    "retest",
    "stil",
    "yield_advisor",
    "log_analyzer",
]


class RunAnalysisParams(BaseModel):
    """Typed, bounds-validated parameter container for `run_analysis`."""

    action: str = Field(
        default="default",
        description=(
            "Agent action: "
            "shmoo ('demo' | 'report'), "
            "test_time ('demo' | 'fail_logs'), "
            "dtl ('recommendations' | 'three_month'), "
            "retest ('predict' | 'batch'), "
            "stil ('analyze' | 'parse_async' | 'optimize' | 'explain'), "
            "yield_advisor ('dashboard' | 'recommendations' | 'retrain'), "
            "log_analyzer ('session' | 'evaluation')."
        ),
    )
    wafer_id: Optional[str] = Field(None, pattern=r"^(WFR-[A-Za-z0-9_-]+|W\d+|demo)?$")
    lot_id: Optional[str] = Field(None, pattern=r"^([A-Za-z0-9_-]+)?$")
    die_id: Optional[str] = Field(None, pattern=r"^([A-Za-z0-9_-]+)?$")
    dataset_id: Optional[str] = Field(None, pattern=r"^[A-Za-z0-9_.-]+$")
    filename: Optional[str] = Field(None, pattern=r"^[\w\-. ()]+\.stil$")
    filenames: Optional[List[str]] = Field(default=None, description="List of .stil filenames.")
    session_id: Optional[str] = Field(default=None, description="Shmoo session ID for report generation.")
    text_mode: Literal["template", "llm"] = "template"
    test_methodology: Literal["MBIST", "LBIST", "ATPG"] = "MBIST"
    vdd: Optional[float] = Field(None, ge=0.4, le=2.5, description="Supply voltage in Volts (0.4V - 2.5V).")
    freq_ghz: Optional[float] = Field(None, ge=0.1, le=10.0, description="Operating frequency in GHz (0.1 - 10.0 GHz).")
    fail_test: str = Field(default="MBIST_03", description="Failing test name for retest prediction.")
    voltage_v: float = Field(default=1.05, ge=0.4, le=2.5, description="Failure voltage in Volts.")
    temperature_c: float = Field(default=85.0, ge=-40.0, le=150.0, description="Die temperature in Celsius.")
    first_test_time_sec: float = Field(default=0.25, gt=0.0, le=600.0, description="Initial test duration in seconds.")
    ate_site: int = Field(default=1, ge=1, le=64)
    fail_bin: int = Field(default=45, ge=1, le=255)
    device_id: str = Field(default="DEV-001", pattern=r"^[A-Za-z0-9_-]+$")
    failure_event: int = Field(default=1, ge=1, le=100000)
    test_month: int = Field(default=12, ge=0, le=120)
    cost_per_hour: float = Field(default=250.0, ge=1.0, le=10000.0)
    log_summary: str = Field(default="demo")


class ServiceHealthItem(BaseModel):
    agent: str
    port: int
    status: Literal["ONLINE", "OFFLINE", "DEGRADED"]
    http_code: Optional[int] = None
    latency_ms: Optional[float] = None
    error: Optional[str] = None


class SuiteHealthEnvelope(BaseModel):
    status: Literal["healthy", "degraded", "offline"]
    online_count: int
    total_count: int
    cached: bool
    cache_age_sec: float
    services: Dict[str, ServiceHealthItem]
    summary: str


class ContextCatalogEnvelope(BaseModel):
    agent: str
    lots: List[Any] = Field(default_factory=list)
    datasets: List[Any] = Field(default_factory=list)
    stil_files: List[Any] = Field(default_factory=list)
    devices: List[Any] = Field(default_factory=list)
    parameters: List[str] = Field(default_factory=list)
    details: Dict[str, Any] = Field(default_factory=dict)
    summary: str


class AgentAnalysisEnvelope(BaseModel):
    agent: str
    action: str
    status: Literal["ok", "running", "fallback", "error"]
    source: Literal["live", "cached", "fallback"] = "live"
    resource_uri: str
    run_id: Optional[str] = None
    metrics: Dict[str, Any] = Field(default_factory=dict)
    data: Dict[str, Any] = Field(default_factory=dict)
    summary: str


class AgentResultsEnvelope(BaseModel):
    agent: Optional[str] = None
    view: str
    source: Literal["live", "cached", "fallback"] = "cached"
    resource_uri: str
    data: Dict[str, Any] = Field(default_factory=dict)
    summary: str


class RetestDriver(BaseModel):
    feature: str
    shap_value: float


class RetestExplanationEnvelope(BaseModel):
    device_id: str
    wafer_id: str
    fail_test: str
    fail_bin: int
    recommendation: Literal["RETEST", "SKIP"]
    probability_percent: float
    expected_base_rate: Optional[float] = None
    top_drivers: List[RetestDriver] = Field(default_factory=list)
    shap_explanation: Dict[str, float] = Field(default_factory=dict)
    source: Literal["live", "fallback"] = "live"
    summary: str


class ShmooReportEnvelope(BaseModel):
    session_id: str
    report_url: str
    pattern_type: str
    test_methodology: str
    source: Literal["live", "fallback"] = "live"
    summary: str


class FullWaferAnalysisEnvelope(BaseModel):
    wafer_id: str
    lot_id: str
    cost_per_hour: float
    agents_completed: List[str]
    resource_uri: str
    results: Dict[str, Dict[str, Any]]
    summary: str


class JobStatusEnvelope(BaseModel):
    run_id: str
    job_type: Literal["yield_retrain", "stil_parse"]
    target: str
    status: Literal["PENDING", "RUNNING", "COMPLETED", "FAILED"]
    progress: float = Field(ge=0.0, le=100.0)
    total: float = 100.0
    phase: str
    started_at: str
    updated_at: str
    completed_at: Optional[str] = None
    resource_uri: str
    result: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    logs: List[str] = Field(default_factory=list)
    summary: str
