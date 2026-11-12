<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency note for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->

**English** | [한국어](README.ko.md)

> [!IMPORTANT]
> Agent Optimizer is in limited preview. Your subscription must be on the allow list — complete the [intake form](https://aka.ms/ao/preview-form).

# Customer Support Hosted Agent — Evaluation & Optimization

Deploy a Microsoft Foundry hosted agent (Python, Responses protocol), evaluate it, and improve it with Agent Optimizer. Based on the [optimization-customer-support sample](https://github.com/microsoft-foundry/foundry-samples/tree/main/samples/python/hosted-agents/bring-your-own/responses/optimization-customer-support).

## Changes from the upstream sample

| File | Change | Reason |
|---|---|---|
| `src/…/main.py` | Loads `skills/*/SKILL.md` and adds each skill's name, description, and body to the system prompt. | The upstream code never loads skills, so skills — and skill optimization — have no effect on responses. |
| `azure.yaml` | One model deployment (`gpt-4.1`) and an evaluation service. | Simple, widely available model; evaluations are managed with `azd ai eval`. |
| `evals/azure.eval.yaml` | Evaluation definition (dataset `eval.jsonl`, evaluator `builtin.task_adherence`, judge `gpt-4.1`). | The optimizer reuses this definition; the legacy `eval.yaml` is no longer supported. |
| `evals/optimize_hosted_agent.py` | Submits the optimization job with the Python SDK. | `azd ai agent optimize` currently fails with `agent_optimization_space is required`. |

## Prerequisites

- [Azure Developer CLI](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd) 1.37+ with extensions: `azd ext install azure.ai.agents` and `azd ext install azure.ai.evaluations`
- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli), Python 3.12+, Git
- An Azure subscription where you can create resources and assign roles
- Quota for `gpt-4.1` (GlobalStandard, 30K TPM) — adjust `capacity` in [azure.yaml](azure.yaml) if needed
- For optimization: a gpt-5-family or newer reasoning model (for example, `gpt-5.4`). See the [supported models](https://learn.microsoft.com/azure/foundry/agents/concepts/agent-optimizer-overview#models); an unsupported deployment is rejected at submission with the list of allowed models.

## 1. Deploy

```powershell
git clone https://github.com/yunkyoungaum/HAEvalOptimiser.git
cd HAEvalOptimiser
az login
azd auth login

azd env new <env-name> --subscription <subscription-id> --location <region>
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME gpt-4.1
azd provision
azd env refresh    # saves the new project ID and endpoint to the azd environment
azd deploy

azd ai agent invoke "My Smart Thermostat is making a buzzing noise from the wall wiring behind it. Can you tell me how to fix the wiring?"
```

## 2. Grant access to the judge model

Evaluations call the judge model as your signed-in user, so you need a data-plane role on the Foundry account:

```powershell
$rg      = azd env get-value AZURE_RESOURCE_GROUP
$account = azd env get-value AZURE_AI_ACCOUNT_NAME
$scope   = az cognitiveservices account show -g $rg -n $account --query id -o tsv
$me      = az ad signed-in-user show --query id -o tsv
az role assignment create --assignee-object-id $me --assignee-principal-type User `
  --role "Cognitive Services OpenAI User" --scope $scope
```

## 3. Evaluate

```powershell
azd ai eval create optimization-customer-support-python-responses-dataset-turn-eval --no-prompt
azd ai eval run start --eval optimization-customer-support-python-responses-dataset-turn-eval --no-prompt
```

If some rows show `Errored` (401), run the evaluation again.

`builtin.task_adherence` does not grade the per-row `criteria` in `eval.jsonl`. Agent Optimizer does. To grade `criteria` in a regular evaluation, see [evals/portal-criteria-evaluator.md](evals/portal-criteria-evaluator.md).

## 4. Optimize

Deploy an optimization model to the same account (choose a model and version available in your region):

```powershell
az cognitiveservices account deployment create -g $rg -n $account `
  --deployment-name <opt-deployment> --model-name <model-name> --model-version <model-version> `
  --model-format OpenAI --sku-name GlobalStandard --sku-capacity 10
```

Submit the job:

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
<summary>bash</summary>

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

The script prints the job ID and waits for completion (about 10 minutes per candidate), then lists each candidate's score. Record the job ID for `apply`:

```powershell
azd env set AGENT_OPTIMIZATION_CUSTOMER_SUPPORT_PYTHON_RESPONSES_OPTIMIZATION_JOB_ID <job-id>
```

## 5. Review and apply a candidate

Preview the candidate's instructions and skills without changing your project:

```powershell
azd ai agent optimize download <job-id> --candidate <candidate-id> --file config.json --target-path candidate_config.json
```

Apply and deploy:

```powershell
azd ai agent optimize apply --candidate <candidate-id>
azd deploy
azd ai eval run start --eval optimization-customer-support-python-responses-dataset-turn-eval --no-prompt
```

`apply` writes `.agent_configs/<candidate-id>/` with **only the skills that changed**. Before `azd deploy`, copy the other skill folders from `src/optimization-customer-support-python-responses/skills/` into `.agent_configs/<candidate-id>/skills/`.

## Clean up

```powershell
azd down --force --purge
```

## References

- [Agent optimizer overview](https://learn.microsoft.com/azure/foundry/agents/concepts/agent-optimizer-overview)
- [Quickstart: Optimize a hosted agent](https://learn.microsoft.com/azure/foundry/agents/quickstarts/quickstart-optimize-hosted-agent)
- [Make your agent optimizer-ready](https://learn.microsoft.com/azure/foundry/agents/how-to/make-agent-optimizer-ready)
- [Create an evaluation dataset and evaluators](https://learn.microsoft.com/azure/foundry/agents/how-to/create-optimizer-dataset)
