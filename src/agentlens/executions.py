from agentlens.agent import investigation_events, read_run
from agentlens.conversations import ConversationError
from agentlens.db import create_session
from agentlens.frozen import read_scenario, verify_scenario
from agentlens.recordings import read_recording
from agentlens.run_diff import compare_runs


async def execute_recording(settings, recording_id: str, project: str, model: str | None = None):
    with create_session(settings) as session:
        recording = read_recording(session, recording_id, project)
    async for event in investigation_events(
        settings,
        project,
        recording["payload"]["source_run"]["input"],
        recording=recording,
        model_override=model,
    ):
        terminal = event
    return terminal


async def execute_scenario(settings, scenario_id: str, project: str, model: str | None = None):
    with create_session(settings) as session:
        scenario = read_scenario(session, scenario_id, project)
    verify_scenario(settings, scenario)
    async for event in investigation_events(
        settings,
        project,
        scenario["manifest"]["case"]["input"],
        scenario=scenario,
        model_override=model,
    ):
        terminal = event
    return terminal


def execution_difference(settings, baseline_id: str, candidate_id: str, project: str):
    with create_session(settings) as session:
        baseline, candidate = (
            read_run(session, id_, project) for id_ in [baseline_id, candidate_id]
        )
        if baseline is None or candidate is None:
            raise ConversationError(404, "Run not found")
        case = None
        if candidate["recording_id"]:
            case = read_recording(session, candidate["recording_id"], project)["payload"]["case"]
        elif candidate["scenario_id"]:
            case = read_scenario(session, candidate["scenario_id"], project)["manifest"]["case"]
        try:
            return compare_runs(baseline, candidate, case)
        except ValueError as exc:
            raise ConversationError(409, str(exc)) from exc
