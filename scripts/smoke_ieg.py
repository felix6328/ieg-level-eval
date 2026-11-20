"""End-to-end API exercise, intended for a disposable IEG database."""
from pathlib import Path
from time import monotonic, sleep
from urllib.request import Request, urlopen
import argparse
import json


def request(base, path, body=None):
    encoded = json.dumps(body).encode() if body is not None else None
    with urlopen(Request(base + path, data=encoded, headers={"Content-Type":"application/json"}), timeout=10) as reply:
        return json.load(reply)


def until(fetch, complete):
    deadline = monotonic() + 80
    while monotonic() < deadline:
        result = fetch()
        if complete(result):
            return result
        sleep(.25)
    raise TimeoutError("LevelEval jobs did not complete")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8873")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    base = args.base

    def call(path, body=None):
        return request(base, "/api" + path, body)

    cat = call("/catalog")
    assert next(r for r in cat["versions"] if r["id"]=="wxg24-v1")["total"]==24
    experiment = call("/experiments", {"name": "E2E · 三组历史实验", "models":["A","B","C"], "mode":"REPLAY"})
    assert experiment["queued"] == 216
    findings = until(lambda:call(f"/experiments/{experiment['id']}"),
                     lambda x: all(r["status"] in ("SUCCEEDED","FAILED") for r in x["runs"]))
    assert sum(r["status"]=="SUCCEEDED" for r in findings["runs"])==212
    assert sum(r["status"]=="FAILED" for r in findings["runs"])==4
    until(lambda:call(f"/triage?experiment_id={experiment['id']}"),lambda x:len(x)==216)
    calibration = call("/calibration")
    assert calibration["source"]=="TERRA_MODEL_REFERENCE" and calibration["references"]==40
    assert calibration["evidence"]["terra"]["numerator"]==40
    assert calibration["human"]["independent_pairs"]==0
    decision = call("/reports/decision", {"experiments":[experiment["id"]]})
    assert sum(x["metrics"]["evaluations"] for x in decision["payload"]["groups"])==216
    assert all(row["metrics"]["human_acceptance"]["value"] is None for row in decision["payload"]["groups"])
    source = next(r for r in findings["runs"] if r["source_id"]=="B__adv_hard_casual")
    output_id = source["output_id"]
    trace = call(f"/outputs/{output_id}/trace")
    assert trace["nodes"]
    bad = call(f"/outputs/{output_id}/bad-case", {"root_cause":"Unknown", "note":"E2E fixture"})
    candidate = call(f"/bad-cases/{bad['id']}/golden", {"title":"E2E 测试候选", "assertions":[{"type":"hard_pass"}]})
    target = f"/golden/{candidate['id']}/action"
    assert call(target,{"action":"validate"})["state"]=="VALIDATING"
    call(target, {"action":"approve","reviewer":"E2E 自动测试夹具","reason":"仅验证审批门禁，非真人策划结论"})
    frozen = call(target, {"action":"publish","reviewer":"E2E 自动测试夹具","reason":"仅验证发布流程"})
    golden = call("/experiments", {"name":"E2E · Golden 回归","models":["B"],"repeats":1,
                                    "dataset_version":frozen["dataset_version"]})
    until(lambda:call(f"/experiments/{golden['id']}"),lambda x: all(r["status"]=="SUCCEEDED" for r in x["runs"]))
    until(lambda:call(f"/triage?experiment_id={golden['id']}"),lambda x:len(x)==1)
    regression = call("/reports/regression",{"baseline":experiment["id"],"candidate":golden["id"]})
    assert regression["payload"]["rows"][0]["assertions"]
    rw = call(f"/outputs/{output_id}/rewrite",{"reason":"E2E 使用原归档重写"})
    rewrite = until(lambda:call(f"/outputs/{output_id}/rewrite"),lambda x: x.get("after") is not None)
    assert rewrite["run"]["id"]==rw["run_id"] and rewrite["recorded_historical"]
    summary = {"replay_runs":216,"parsed":212,"parse_failures":4,"terra_model_reference":40,
               "human_independent_pairs":0, "source":"REPLAY", "human_approval_fixture":True,
               "decision":decision["payload"],"regression":regression["payload"],
               "rewrite":{"hard_pass_before":rewrite["before"]["hard_pass"],"hard_pass_after":rewrite["after"]["hard_pass"],
                          "source":"HISTORICAL_REWRITE_REPLAY","quality":rewrite["quality"]}}
    if args.output:
        args.output.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("PASS · 216 history REPLAY runs, Terra, decision, Bad Case, fixture-approved Golden publish, regression and rewrite")


if __name__ == "__main__":
    main()
