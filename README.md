<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency note for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->

**English** | [한국어](README.ko.md)

> [!IMPORTANT]
> Agent Optimizer is in limited preview. Your subscription must be on the allow list — complete the [intake form](https://aka.ms/ao/preview-form). See [Supplemental Terms of Use for Microsoft Azure Previews](https://azure.microsoft.com/en-us/support/legal/preview-supplemental-terms/).

# Customer Support Hosted Agent — Evaluation & Optimization

An end-to-end, reproducible walkthrough of **evaluating** and **optimizing** a Microsoft Foundry hosted agent (Python, Responses protocol). It is based on the [optimization-customer-support sample](https://github.com/microsoft-foundry/foundry-samples/tree/main/samples/python/hosted-agents/bring-your-own/responses/optimization-customer-support), with the fixes needed to run the full flow today.

You will:

1. Provision a new Foundry project and deploy the agent.
2. Evaluate it with `azd ai eval`.
3. Run Agent Optimizer, review candidates, and (optionally) apply the best one.

## What differs from the upstream sample

| Area | Change | Why |
|---|---|---|
| `main.py` | Loads `skills/*/SKILL.md` and inlines each skill's name, description, and **body** into the system prompt. | Upstream `main.py` never loads skills from a local folder, and `compose_instructions()` only lists names/descriptions. Without this, skills (and skill optimization) have no effect. |
| `azure.yaml` | Single model deployment `gpt-4.1`; adds an `azure.ai.eval` service. | Simpler, widely available model; evaluation assets are managed by `azd ai eval`. |
| `evals/azure.eval.yaml` | Evaluation definition: dataset `eval` (`eval.jsonl`) + `builtin.task_adherence`, judged by `gpt-4.1`. | `azd ai agent optimize` no longer supports the legacy `eval.yaml`. |
| `evals/optimize_hosted_agent.py` | Submits the optimization job with the Python SDK. | `azd ai agent optimize` (azure.ai.agents 1.0.0) fails with `400 invalid_config: optimization_configuration.agent_optimization_space is required`. |

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| [Azure Developer CLI (`azd`)](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd) | 1.37+ | |
| azd extensions | `azure.ai.agents`, `azure.ai.evaluations` | `azd ext install azure.ai.agents` and `azd ext install azure.ai.evaluations` |
| [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) | latest | Used for role assignment and model deployment |
| Python | 3.12+ | Only for the optimizer submission script |
| Git | any | |

Azure requirements:

- A subscription where you can create resources and **assign roles** (Owner or User Access Administrator).
- Quota for **`gpt-4.1` GlobalStandard, 30K TPM** in your region (change `capacity` in [azure.yaml](azure.yaml) if needed).
- For optimization: quota for a supported **optimization model** (`gpt-5`, `gpt-5.1`, `gpt-5.2`, `gpt-5.4`, `gpt-5.5`, `DeepSeek-V4-Pro`, or `DeepSeek-V-3.2`) and allow-list access to Agent Optimizer.

> [!TIP]
> **Windows:** if `azd` is "not recognized" in the VS Code terminal right after installing it, restart VS Code, or run `$env:Path += ";$env:LOCALAPPDATA\Programs\Azure Dev CLI"` in that terminal.

## 1. Clone and sign in

```powershell
git clone https://github.com/yunkyoungaum/HAEvalOptimiser.git
cd HAEvalOptimiser

az login
azd auth login
```

## 2. Provision a new Foundry project and deploy the agent

```powershell
azd env new <env-name> --subscription <subscription-id> --location <region>
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME gpt-4.1

azd provision      # creates a resource group, Foundry account + project, and the gpt-4.1 deployment
azd deploy         # deploys the hosted agent (code deploy) and the evaluation service
```

Smoke test:

```powershell
azd ai agent invoke "My Smart Thermostat is making a buzzing noise from the wall wiring behind it. Can you tell me how to fix the wiring?"
```

Expected: the agent declines to give wiring instructions and recommends a licensed electrician (from the `safety-boundaries` skill).

## 3. Grant yourself access to the judge model

Evaluation calls the judge model **as your signed-in user**. Without a data-plane role, every row fails with `401 PermissionDenied … lacks … chat/completions/action`.

```powershell
$rg      = azd env get-value AZURE_RESOURCE_GROUP
$account = azd env get-value AZURE_AI_ACCOUNT_NAME
$scope   = az cognitiveservices account show -g $rg -n $account --query id -o tsv
$me      = az ad signed-in-user show --query id -o tsv

az role assignment create --assignee-object-id $me --assignee-principal-type User `
  --role "Cognitive Services OpenAI User" --scope $scope
```

Role propagation can take several minutes.

## 4. Evaluate the agent

The evaluation is already defined in [evals/azure.eval.yaml](evals/azure.eval.yaml). Register it in your project and run it:

```powershell
azd ai eval create optimization-customer-support-python-responses-dataset-turn-eval --no-prompt
azd ai eval run start --eval optimization-customer-support-python-responses-dataset-turn-eval --no-prompt
```

Inspect results:

```powershell
azd ai eval run list   --eval optimization-customer-support-python-responses-dataset-turn-eval
azd ai eval run output list --eval <eval-id> --run <run-id>
```

> [!NOTE]
> `builtin.task_adherence` checks whether the agent did what was asked; it does **not** read the per-row `criteria` in `eval.jsonl`, so it typically scores 100%. To grade against `criteria` in a standalone evaluation, use a custom evaluator — see [evals/portal-criteria-evaluator.md](evals/portal-criteria-evaluator.md). Agent Optimizer **does** score `criteria` natively (next step).

> [!NOTE]
> Some rows may intermittently fail with `401` even after the role assignment has propagated. Re-run the evaluation until `Errored` is `0`.

## 5. Run Agent Optimizer

### 5.1 Deploy an optimization model

Deploy one supported optimization model into the same Foundry account, for example (pick a model/version available in your region):

```powershell
az cognitiveservices account list-models -g $rg -n $account --query "[?starts_with(name,'gpt-5')].{name:name, version:version}" -o table

az cognitiveservices account deployment create -g $rg -n $account `
  --deployment-name <opt-deployment> --model-name <model-name> --model-version <model-version> `
  --model-format OpenAI --sku-name GlobalStandard --sku-capacity 10
```

### 5.2 Submit the optimization job

Use a separate virtual environment so the agent's pinned dependencies are untouched:

```powershell
python -m venv .optvenv
.\.optvenv\Scripts\python.exe -m pip install "azure-ai-projects>=2.5.0" azure-ai-agentserver-optimization azure-identity

$env:FOUNDRY_PROJECT_ENDPOINT = azd env get-value FOUNDRY_PROJECT_ENDPOINT
$env:FOUNDRY_AGENT_NAME       = "optimization-customer-support-python-responses"
$env:DATASET_NAME             = "eval"
$env:DATASET_VERSION          = "1.0"
$env:EVALUATOR_NAME           = "builtin.task_adherence"
$env:EVAL_MODEL               = "gpt-4.1"
$env:OPTIMIZATION_MODEL       = "<opt-deployment>"
$env:MAX_CANDIDATES           = "3"
$env:OPTIMIZATION_LOCAL_DIR   = (Resolve-Path "src/optimization-customer-support-python-responses/.agent_configs").Path

.\.optvenv\Scripts\python.exe -u evals/optimize_hosted_agent.py
```

<details>
<summary>bash equivalent</summary>

```bash
python3 -m venv .optvenv
./.optvenv/bin/python -m pip install "azure-ai-projects>=2.5.0" azure-ai-agentserver-optimization azure-identity

export FOUNDRY_PROJECT_ENDPOINT="$(azd env get-value FOUNDRY_PROJECT_ENDPOINT)"
export FOUNDRY_AGENT_NAME="optimization-customer-support-python-responses"
export DATASET_NAME="eval" DATASET_VERSION="1.0"
export EVALUATOR_NAME="builtin.task_adherence" EVAL_MODEL="gpt-4.1"
export OPTIMIZATION_MODEL="<opt-deployment>" MAX_CANDIDATES="3"
export OPTIMIZATION_LOCAL_DIR="$(pwd)/src/optimization-customer-support-python-responses/.agent_configs"

./.optvenv/bin/python -u evals/optimize_hosted_agent.py
```

</details>

The script prints the job ID and polls until completion (about 10 minutes per candidate). The optimizer uses the dataset registered in step 4 and scores each row's `criteria` with the eval model.

Record the job ID so later `apply` targets it, and check progress from another terminal:

```powershell
azd env set AGENT_OPTIMIZATION_CUSTOMER_SUPPORT_PYTHON_RESPONSES_OPTIMIZATION_JOB_ID <job-id>
azd ai agent optimize status <job-id>
```

### 5.3 Review a candidate before applying

```powershell
azd ai agent optimize status <job-id> --candidate <candidate-id> --output json
azd ai agent optimize download <job-id> --candidate <candidate-id> --file config.json --target-path $env:TEMP\candidate_config.json
```

`config.json` contains the full candidate `instructions`, `model`, and `skills`. Check for over-fitting to the evaluation dataset (for example, rules that mirror a single test case) before applying.

### 5.4 Apply, deploy, and verify

```powershell
azd ai agent optimize apply --candidate <candidate-id>   # writes .agent_configs/<candidate-id>/ and sets OPTIMIZATION_CANDIDATE_ID in azure.yaml
azd deploy
azd ai eval run start --eval optimization-customer-support-python-responses-dataset-turn-eval --no-prompt
```

> [!WARNING]
> The applied candidate folder contains **only the skills the optimizer changed**. Because `main.py` loads skills from that folder, unchanged skills are dropped. Copy the missing skill folders from `src/optimization-customer-support-python-responses/skills/` into `.agent_configs/<candidate-id>/skills/` before `azd deploy`.

To undo an `apply` before deploying, delete `.agent_configs/<candidate-id>/` and remove `OPTIMIZATION_CANDIDATE_ID` from [azure.yaml](azure.yaml).

## Reference results

Measured with `gpt-4.1` (agent and judge), dataset `eval.jsonl` (10 tasks), 3 candidates. Your numbers will vary.

| Agent code | Baseline | Best candidate | Notes |
|---|---|---|---|
| Upstream `main.py` (skills not loaded) | 0.84 | 0.89 (instructions + skills) | Skill changes had no runtime effect |
| This repo's `main.py` (skills inlined) | 0.80 | see your run | |

Per the [optimizer docs](https://learn.microsoft.com/azure/foundry/agents/concepts/agent-optimizer-overview#interpret-score-improvements), improvements below 0.03 are noise; 0.03–0.10 is a moderate, deployable improvement.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `azd ai agent optimize` → `400 invalid_config … agent_optimization_space is required` | CLI omits the optimization space | Use `evals/optimize_hosted_agent.py` (step 5.2) |
| `azd ai agent optimize` → `no evaluation matches the selected eval and agent` | `--eval` name not in `evals/azure.eval.yaml` | Use the exact eval name from the file |
| Evaluation rows fail with `401 PermissionDenied` | Missing role on the Foundry account, or intermittent service-side failures | Step 3, then re-run |
| `azd ai agent init` → `project directory … overlaps with template source` | Running `init` inside this repo | Not needed — use `azd env new` (step 2) |
| `uv` → `HandshakeFailure` downloading from PyPI | TLS interception on corporate networks | Use `pip` in a venv (step 5.2) |
| PowerShell profile "running scripts is disabled" | Execution policy | Harmless; optionally `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |

## Files

| Path | Used by | Purpose |
|---|---|---|
| `azure.yaml` | azd | Project manifest: model deployment, hosted agent, evaluation service |
| `evals/azure.eval.yaml` | `azd ai eval`, optimizer | Dataset + evaluator + target definition |
| `evals/optimize_hosted_agent.py` | you | Submits the optimization job (SDK) |
| `evals/portal-criteria-evaluator.md` | you | Portal guide: custom evaluator that grades per-row `criteria` |
| `src/…/main.py` | runtime | Responses handler; loads config, skills, and model |
| `src/…/.agent_configs/baseline/` | runtime, optimizer | Baseline `instructions.md` + `metadata.yaml` |
| `src/…/skills/*/SKILL.md` | runtime, optimizer | Skills inlined into the system prompt |
| `src/…/eval.jsonl` | evaluation, optimizer | 10 tasks with per-task `criteria` |
| `src/…/eval-quick.jsonl` | optional | 3-task dataset for quick runs (`--dataset`) |
| `src/…/eval.yaml` | — | Legacy optimizer config; **not supported** by the current CLI |
| `src/…/Dockerfile`, `.dockerignore` | — | Not used (the agent uses code deploy) |

## Clean up

```powershell
azd down --force --purge
```

`--purge` releases the soft-deleted Foundry account name immediately.

## References

- [Agent optimizer overview](https://learn.microsoft.com/azure/foundry/agents/concepts/agent-optimizer-overview)
- [Quickstart: Optimize a hosted agent](https://learn.microsoft.com/azure/foundry/agents/quickstarts/quickstart-optimize-hosted-agent)
- [Create an evaluation dataset and evaluators for the optimizer](https://learn.microsoft.com/azure/foundry/agents/how-to/create-optimizer-dataset)
- [Make your agent optimizer-ready](https://learn.microsoft.com/azure/foundry/agents/how-to/make-agent-optimizer-ready)
- [Custom evaluators](https://learn.microsoft.com/azure/foundry/concepts/evaluation-evaluators/custom-evaluators)
