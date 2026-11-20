"""Local API and web entry point for IEG LevelEval."""
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
import os
import json

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import provider
from .evaluation import Evaluations
from .experiments import Experiments, Worker
from .store import ROOT, Invalid, Missing, Store, load


@lru_cache
def services():
    db = Path(os.environ.get("LEVEL_EVAL_DB", ROOT / "data/ieg/workspace.sqlite")).resolve()
    legacy = ROOT.parent / "ieg-level-eval"
    if db.is_relative_to(legacy) or (db.is_relative_to(ROOT) and not db.is_relative_to(ROOT / "data/ieg")):
        raise Invalid("IEG 数据库需放在独立存储目录")
    store = Store(db)
    return store, Experiments(store), Evaluations(store)


@asynccontextmanager
async def lifespan(_app):
    _, experiments, evaluation = services()
    with Worker(experiments, after=evaluation.evaluate).background():
        yield


app = FastAPI(title="LevelEval 2.0", lifespan=lifespan)


@app.middleware("http")
async def local_only(request: Request, call_next):
    host = request.headers.get("host", "")
    origin = request.headers.get("origin")
    if urlsplit(f"//{host}").hostname not in {"127.0.0.1", "localhost", "::1", "testserver"} or (
            origin is not None and urlsplit(origin).netloc != host):
        return JSONResponse({"detail": "请通过本机工作台访问"}, 403)
    return await call_next(request)


@app.exception_handler(Invalid)
def invalid(_request, exc):
    return JSONResponse({"detail": str(exc)}, 400)


@app.exception_handler(Missing)
def missing(_request, exc):
    return JSONResponse({"detail": str(exc)}, 404)


class DatasetInput(BaseModel):
    name: str = Field(default="", max_length=120)
    dataset_id: str | None = None
    note: str = Field(default="", max_length=3000)
    content: str = Field(min_length=2, max_length=3_000_000)


class ExperimentInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    dataset_version: str = "wxg24-v1"
    mode: Literal["REPLAY", "MOCK", "REAL"] = "REPLAY"
    models: list[Literal["A", "B", "C"]] = Field(min_length=1, max_length=3)
    task_ids: list[str] = Field(default_factory=list, max_length=1000)
    repeats: int = Field(default=3, ge=1, le=20)
    seed: int = Field(default=0, ge=0, le=2_147_483_000)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=128, le=12000)
    model_override: str | None = Field(default=None, max_length=180)
    prompt_override: Literal["gen_v1", "gen_v2"] | None = None
    judge_models: list[str] = Field(default_factory=list, max_length=3)
    judge_budget_cny: float = Field(default=0, ge=0, le=100, allow_inf_nan=False)
    budget_cny: float = Field(default=0, ge=0, le=100, allow_inf_nan=False)


@app.get("/api/catalog")
def catalog():
    return {**services()[0].catalog(), "real_enabled": provider.real_enabled()}


@app.get("/api/datasets/{version}/tasks")
def tasks(version: str):
    return services()[0].tasks(version)


@app.post("/api/datasets", status_code=201)
def create_dataset(body: DatasetInput):
    try:
        value = load(body.content)
        records = value if isinstance(value, list) else [value]
    except ValueError:
        try:
            records = [load(line) for line in body.content.splitlines() if line.strip()]
        except ValueError as exc:
            raise Invalid("题库必须为 JSON 数组或 JSONL") from exc
    return services()[0].version(dataset_id=body.dataset_id, name=body.name, tasks=records, note=body.note)


@app.post("/api/datasets/{version}/freeze")
def freeze(version: str):
    return services()[0].freeze(version)


@app.get("/api/experiments")
def experiments():
    return services()[1].list()


@app.post("/api/experiments", status_code=201)
def create_experiment(body: ExperimentInput):
    return services()[1].create(body.model_dump())


@app.get("/api/experiments/{ident}")
def experiment(ident: str):
    return services()[1].detail(ident)


@app.get("/api/runs/{ident}")
def run(ident: str):
    return services()[1].run_detail(ident)


@app.post("/api/runs/{ident}/retry", status_code=202)
def retry(ident: str):
    return services()[1].retry(ident)


@app.get("/api/outputs/{output_id}/evaluation")
def evaluation(output_id: str):
    return services()[2].detail(output_id)


@app.post("/api/outputs/{output_id}/evaluation")
def rerun_evaluation(output_id: str):
    return services()[2].evaluate(output_id, force=True)


@app.get("/api/calibration")
def calibration():
    return services()[2].calibration()
