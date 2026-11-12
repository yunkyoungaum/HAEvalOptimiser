<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency note for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->

[English](README.md) | **한국어**

> [!IMPORTANT]
> Agent Optimizer는 limited preview입니다. 구독이 허용 목록에 등록되어 있어야 하며, [신청서](https://aka.ms/ao/preview-form)로 신청할 수 있습니다.

# 고객 지원 Hosted Agent — 평가와 최적화

Microsoft Foundry hosted agent(Python, Responses 프로토콜)를 배포하고, 평가한 뒤, Agent Optimizer로 개선합니다. [optimization-customer-support 샘플](https://github.com/microsoft-foundry/foundry-samples/tree/main/samples/python/hosted-agents/bring-your-own/responses/optimization-customer-support)을 바탕으로 했습니다.

## 원본 샘플에서 수정한 부분

| 파일 | 변경 | 이유 |
|---|---|---|
| `src/…/main.py` | `skills/*/SKILL.md`를 읽어 스킬마다 이름, 설명, 본문을 시스템 프롬프트에 추가 | 원본 코드는 스킬을 읽지 않아서, 스킬과 스킬 최적화가 응답에 영향을 주지 않습니다. |
| `azure.yaml` | 모델 배포를 `gpt-4.1` 하나로 정리하고 평가 서비스 추가 | 널리 쓸 수 있는 모델로 단순화했고, 평가는 `azd ai eval`로 관리합니다. |
| `evals/azure.eval.yaml` | 평가 정의(데이터셋 `eval.jsonl`, 평가자 `builtin.task_adherence`, 채점 모델 `gpt-4.1`) | Optimizer가 이 정의를 재사용합니다. 예전 형식인 `eval.yaml`은 더 이상 지원되지 않습니다. |
| `evals/optimize_hosted_agent.py` | Python SDK로 최적화 작업 제출 | 현재 `azd ai agent optimize`는 `agent_optimization_space is required` 오류로 실패합니다. |

## 사전 준비

- [Azure Developer CLI](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd) 1.37 이상과 확장: `azd ext install azure.ai.agents`, `azd ext install azure.ai.evaluations`
- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli), Python 3.12 이상, Git
- 리소스를 만들고 역할을 할당할 수 있는 Azure 구독
- `gpt-4.1` 쿼터(GlobalStandard, 30K TPM). 부족하면 [azure.yaml](azure.yaml)의 `capacity`를 바꾸세요.
- 최적화용 모델: 지원 모델(`gpt-5`, `gpt-5.1`, `gpt-5.2`, `gpt-5.4`, `gpt-5.5`, `DeepSeek-V4-Pro`, `DeepSeek-V-3.2`) 중 하나

## 1. 배포

```powershell
git clone https://github.com/yunkyoungaum/HAEvalOptimiser.git
cd HAEvalOptimiser
az login
azd auth login

azd env new <환경-이름> --subscription <구독-ID> --location <리전>
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME gpt-4.1
azd provision
azd deploy

azd ai agent invoke "My Smart Thermostat is making a buzzing noise from the wall wiring behind it. Can you tell me how to fix the wiring?"
```

## 2. 채점 모델 호출 권한 부여

평가할 때 채점 모델은 로그인한 사용자 권한으로 호출됩니다. 그래서 Foundry 계정에 데이터 플레인 역할이 필요합니다.

```powershell
$rg      = azd env get-value AZURE_RESOURCE_GROUP
$account = azd env get-value AZURE_AI_ACCOUNT_NAME
$scope   = az cognitiveservices account show -g $rg -n $account --query id -o tsv
$me      = az ad signed-in-user show --query id -o tsv
az role assignment create --assignee-object-id $me --assignee-principal-type User `
  --role "Cognitive Services OpenAI User" --scope $scope
```

## 3. 평가

```powershell
azd ai eval create optimization-customer-support-python-responses-dataset-turn-eval --no-prompt
azd ai eval run start --eval optimization-customer-support-python-responses-dataset-turn-eval --no-prompt
```

일부 행이 `Errored`(401)로 나오면 평가를 다시 실행하세요.

`builtin.task_adherence`는 `eval.jsonl`의 행별 `criteria`를 채점하지 않습니다. Agent Optimizer는 채점합니다. 일반 평가에서도 `criteria`로 채점하려면 [evals/portal-criteria-evaluator.md](evals/portal-criteria-evaluator.md)를 참고하세요.

## 4. 최적화

같은 계정에 최적화 모델을 배포합니다. 모델과 버전은 사용하는 리전에서 제공되는 것으로 고르세요.

```powershell
az cognitiveservices account deployment create -g $rg -n $account `
  --deployment-name <최적화-배포-이름> --model-name <모델-이름> --model-version <모델-버전> `
  --model-format OpenAI --sku-name GlobalStandard --sku-capacity 10
```

작업을 제출합니다.

```powershell
python -m venv .optvenv
.\.optvenv\Scripts\python.exe -m pip install "azure-ai-projects>=2.5.0" azure-ai-agentserver-optimization azure-identity

$env:FOUNDRY_PROJECT_ENDPOINT = azd env get-value FOUNDRY_PROJECT_ENDPOINT
$env:FOUNDRY_AGENT_NAME       = "optimization-customer-support-python-responses"
$env:DATASET_NAME             = "eval"
$env:DATASET_VERSION          = "1.0"
$env:EVALUATOR_NAME           = "builtin.task_adherence"
$env:EVAL_MODEL               = "gpt-4.1"
$env:OPTIMIZATION_MODEL       = "<최적화-배포-이름>"
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
export OPTIMIZATION_MODEL="<최적화-배포-이름>" MAX_CANDIDATES="3"
export OPTIMIZATION_LOCAL_DIR="$(pwd)/src/optimization-customer-support-python-responses/.agent_configs"

./.optvenv/bin/python -u evals/optimize_hosted_agent.py
```

</details>

스크립트는 작업 ID를 출력하고 끝날 때까지 기다린 뒤(후보 하나에 약 10분) 후보별 점수를 보여 줍니다. `apply`에서 쓸 수 있도록 작업 ID를 기록하세요.

```powershell
azd env set AGENT_OPTIMIZATION_CUSTOMER_SUPPORT_PYTHON_RESPONSES_OPTIMIZATION_JOB_ID <작업-ID>
```

## 5. 후보 검토와 적용

프로젝트 파일을 바꾸지 않고 후보의 지시문과 스킬을 미리 봅니다.

```powershell
azd ai agent optimize download <작업-ID> --candidate <후보-ID> --file config.json --target-path candidate_config.json
```

적용하고 배포합니다.

```powershell
azd ai agent optimize apply --candidate <후보-ID>
azd deploy
azd ai eval run start --eval optimization-customer-support-python-responses-dataset-turn-eval --no-prompt
```

`apply`가 만드는 `.agent_configs/<후보-ID>/`에는 **바뀐 스킬만** 들어 있습니다. `azd deploy` 전에 나머지 스킬 폴더를 `src/optimization-customer-support-python-responses/skills/`에서 `.agent_configs/<후보-ID>/skills/`로 복사하세요.

## 정리

```powershell
azd down --force --purge
```

## 참고 문서

- [Agent optimizer 개요](https://learn.microsoft.com/azure/foundry/agents/concepts/agent-optimizer-overview)
- [빠른 시작: hosted agent 최적화](https://learn.microsoft.com/azure/foundry/agents/quickstarts/quickstart-optimize-hosted-agent)
- [에이전트를 Optimizer에 맞게 준비하기](https://learn.microsoft.com/azure/foundry/agents/how-to/make-agent-optimizer-ready)
- [평가 데이터셋과 평가자 만들기](https://learn.microsoft.com/azure/foundry/agents/how-to/create-optimizer-dataset)
