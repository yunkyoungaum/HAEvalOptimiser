"""Submit a hosted-agent optimization job via the Python SDK and wait for the result.

Based on the Foundry "Optimize a hosted agent" quickstart (Python SDK path).
Used instead of `azd ai agent optimize` because the CLI omits
`agent_optimization_space`, which the service requires.

Required env vars: FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_AGENT_NAME, DATASET_NAME,
EVALUATOR_NAME, EVAL_MODEL, OPTIMIZATION_MODEL, OPTIMIZATION_LOCAL_DIR.
Optional: DATASET_VERSION (default "1"), MAX_CANDIDATES (default 3),
POLL_INTERVAL_SECONDS (default 15), OPTIMIZATION_JOB_ID (resume an existing job).
"""

import os
import time
from pathlib import Path

from azure.ai.agentserver.optimization import load_config, load_skills_from_dir
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    AgentOptimizationBaselineAgentConfiguration,
    AgentOptimizationCandidateExpand,
    AgentOptimizationCandidateSearchConfiguration,
    AgentOptimizationConfiguration,
    AgentOptimizationEvaluationConfiguration,
    AgentOptimizationEvaluator,
    AgentOptimizationFoundryAgentTargetConfiguration,
    AgentOptimizationJob,
    AgentOptimizationModelConfiguration,
    AgentOptimizationSkill,
    AgentOptimizationSpace,
    AgentOptimizationTargetCompletionDatasetReferenceDataSource,
    AgentOptimizationTargetCompletionEvaluationSet,
    EvaluationModelConfiguration,
    JobStatus,
    TargetAttribute,
)
from azure.identity import DefaultAzureCredential

endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
agent_name = os.environ["FOUNDRY_AGENT_NAME"]
dataset_name = os.environ["DATASET_NAME"]
dataset_version = os.environ.get("DATASET_VERSION", "1")
evaluator_name = os.environ["EVALUATOR_NAME"]
eval_model = os.environ["EVAL_MODEL"]
optimization_model = os.environ["OPTIMIZATION_MODEL"]
max_candidates = int(os.environ.get("MAX_CANDIDATES", "3"))
poll_interval_seconds = int(os.environ.get("POLL_INTERVAL_SECONDS", "15"))
existing_job_id = os.environ.get("OPTIMIZATION_JOB_ID")

# Reads .agent_configs/baseline via OPTIMIZATION_LOCAL_DIR.
optimization_config = load_config()
if optimization_config is None:
    raise RuntimeError("No baseline config found. Check OPTIMIZATION_LOCAL_DIR.")

target_attributes = [TargetAttribute.INSTRUCTIONS]

loaded_skills = optimization_config.skills
if not loaded_skills and optimization_config.skills_dir:
    loaded_skills = load_skills_from_dir(Path(optimization_config.skills_dir))
skills = [
    AgentOptimizationSkill(
        name=skill.name,
        description=skill.description,
        body=skill.body or None,
    )
    for skill in loaded_skills or []
]
if skills:
    target_attributes.append(TargetAttribute.SKILLS)
if optimization_config.tool_definitions:
    target_attributes.append(TargetAttribute.TOOLS)

print(f"Baseline source: {optimization_config.source}")
print(f"Baseline model: {optimization_config.model}")
print(f"Skills: {[s.name for s in skills]}")
print(f"Targets: {[str(t) for t in target_attributes]}")

baseline_configuration = AgentOptimizationBaselineAgentConfiguration(
    system_prompt=optimization_config.instructions,
    current_model=optimization_config.model,
    skills=skills or None,
    tools=optimization_config.tool_definitions or None,
)

with (
    DefaultAzureCredential() as credential,
    AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
):
    if existing_job_id:
        job_id = existing_job_id
    else:
        job_request = AgentOptimizationJob(
            target_configuration=AgentOptimizationFoundryAgentTargetConfiguration(
                name=agent_name
            ),
            optimization_model_configuration=AgentOptimizationModelConfiguration(
                model=optimization_model
            ),
            optimization_configuration=AgentOptimizationConfiguration(
                evaluation_configuration=AgentOptimizationEvaluationConfiguration(
                    training_set=AgentOptimizationTargetCompletionEvaluationSet(
                        source=AgentOptimizationTargetCompletionDatasetReferenceDataSource(
                            name=dataset_name,
                            version=dataset_version,
                        )
                    ),
                    evaluators=[AgentOptimizationEvaluator(name=evaluator_name)],
                    evaluation_model=EvaluationModelConfiguration(model=eval_model),
                ),
                candidate_search_configuration=AgentOptimizationCandidateSearchConfiguration(
                    max_candidates=max_candidates
                ),
                baseline_agent_configuration=baseline_configuration,
                agent_optimization_space=AgentOptimizationSpace(
                    target_attributes=target_attributes
                ),
            ),
        )
        poller = project_client.agents.begin_create_optimization_job(
            job=job_request,
            polling=False,
        )
        job_id = poller.details.get("job_id")
        if not isinstance(job_id, str):
            raise RuntimeError("The create operation did not return an optimization job ID.")

    print(f"Optimization job ID: {job_id}", flush=True)

    terminal_statuses = {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}
    job = project_client.agents.get_optimization_job(job_id=job_id)
    while job.status not in terminal_statuses:
        print(f"\tstatus=`{job.status}`", flush=True)
        time.sleep(poll_interval_seconds)
        job = project_client.agents.get_optimization_job(job_id=job_id)
    print(f"\tstatus=`{job.status}`")

    for warning in job.warnings or []:
        print(f"[WARNING] {warning}")

    if job.status == JobStatus.FAILED:
        message = job.error.message if job.error else "<no error message>"
        raise RuntimeError(f"Optimization job `{job.id}` failed: {message}")
    if job.status == JobStatus.CANCELLED:
        raise RuntimeError(f"Optimization job `{job.id}` was cancelled.")
    if job.result is None:
        raise RuntimeError(f"Optimization job `{job.id}` completed without a result.")

    result = job.result
    summary = result.candidate_summary
    if summary:
        print(f"Baseline candidate: {summary.baseline_id}")
        print(f"Best candidate: {summary.best_id}")
        print(f"Completed optimized candidates: {summary.completed_candidate_count}")
        if summary.baseline_score is not None:
            print(f"Baseline score: {summary.baseline_score:.4f}")
        if summary.best_score is not None:
            print(f"Best score: {summary.best_score:.4f}")
    if result.termination_reason:
        print(f"Termination reason: {result.termination_reason}")

    for candidate in project_client.agents.list_optimization_candidates(
        job_id=job_id,
        expand=[AgentOptimizationCandidateExpand.MUTATIONS],
    ):
        details = [
            f"{candidate.name}: candidate_id={candidate.candidate_id}",
            f"status={candidate.status}",
        ]
        if candidate.evaluation:
            if candidate.evaluation.score is not None:
                details.append(f"score={candidate.evaluation.score:.4f}")
            if candidate.evaluation.avg_tokens is not None:
                details.append(f"avg_tokens={candidate.evaluation.avg_tokens:.0f}")
        print(", ".join(details))
