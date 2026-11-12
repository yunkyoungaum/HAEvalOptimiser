<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency note for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->

[English](README.md) | **한국어**

> [!IMPORTANT]
> Agent Optimizer는 신청해야 사용할 수 있는 limited preview입니다. 사용하려면 구독이 허용 목록에 등록되어 있어야 합니다. [신청서](https://aka.ms/ao/preview-form)를 제출하세요. [Microsoft Azure Preview 추가 약관](https://azure.microsoft.com/ko-kr/support/legal/preview-supplemental-terms/)도 참고하세요.

# 고객 지원 Hosted Agent — 평가와 최적화

Microsoft Foundry hosted agent(Python, Responses 프로토콜)를 **평가**하고 **최적화**하는 과정을 처음부터 끝까지 재현할 수 있도록 정리한 저장소입니다. [optimization-customer-support 샘플](https://github.com/microsoft-foundry/foundry-samples/tree/main/samples/python/hosted-agents/bring-your-own/responses/optimization-customer-support)을 바탕으로, 지금 전체 흐름을 실제로 돌리는 데 필요한 수정을 반영했습니다.

진행 순서:

1. 새 Foundry 프로젝트를 만들고 에이전트를 배포합니다.
2. `azd ai eval`로 에이전트를 평가합니다.
3. Agent Optimizer를 실행하고, 후보를 검토한 뒤 필요하면 최고 후보를 적용합니다.

## 원본 샘플과 다른 점

| 영역 | 변경 | 이유 |
|---|---|---|
| `main.py` | `skills/*/SKILL.md`를 읽어 스킬마다 이름, 설명, **본문**을 시스템 프롬프트에 붙입니다. | 원본 `main.py`는 로컬 폴더의 스킬을 읽지 않고, `compose_instructions()`도 이름과 설명만 나열합니다. 이 수정이 없으면 스킬과 스킬 최적화가 응답에 아무 영향을 주지 않습니다. |
| `azure.yaml` | 모델 배포를 `gpt-4.1` 하나로 정리하고, `azure.ai.eval` 서비스를 추가했습니다. | 널리 쓸 수 있는 모델로 단순화했고, 평가 설정은 `azd ai eval`로 관리합니다. |
| `evals/azure.eval.yaml` | 평가 정의: 데이터셋 `eval`(`eval.jsonl`) + `builtin.task_adherence`, 채점 모델 `gpt-4.1` | `azd ai agent optimize`가 예전 형식의 `eval.yaml`을 더 이상 지원하지 않습니다. |
| `evals/optimize_hosted_agent.py` | Python SDK로 최적화 작업을 제출합니다. | `azd ai agent optimize`(azure.ai.agents 1.0.0)는 `400 invalid_config: optimization_configuration.agent_optimization_space is required` 오류로 실패합니다. |

## 사전 준비

| 도구 | 버전 | 비고 |
|---|---|---|
| [Azure Developer CLI (`azd`)](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd) | 1.37 이상 | |
| azd 확장 | `azure.ai.agents`, `azure.ai.evaluations` | `azd ext install azure.ai.agents`, `azd ext install azure.ai.evaluations` |
| [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) | 최신 | 역할 할당과 모델 배포에 사용 |
| Python | 3.12 이상 | 최적화 작업 제출 스크립트에만 필요 |
| Git | 버전 무관 | |

Azure 요구 사항:

- 리소스를 만들고 **역할을 할당**할 수 있는 구독(Owner 또는 User Access Administrator 권한)
- 사용할 리전에 **`gpt-4.1` GlobalStandard 30K TPM** 쿼터. 부족하면 [azure.yaml](azure.yaml)의 `capacity`를 바꾸세요.
- 최적화를 하려면:
  - 지원되는 **최적화 모델**(`gpt-5`, `gpt-5.1`, `gpt-5.2`, `gpt-5.4`, `gpt-5.5`, `DeepSeek-V4-Pro`, `DeepSeek-V-3.2`)의 쿼터
  - Agent Optimizer 허용 목록 등록

> [!TIP]
> **Windows:** `azd`를 설치한 직후 VS Code 터미널에서 "not recognized" 오류가 나면 VS Code를 다시 시작하세요. 또는 그 터미널에서 `$env:Path += ";$env:LOCALAPPDATA\Programs\Azure Dev CLI"`를 실행하세요.

## 1. Clone과 로그인

```powershell
git clone https://github.com/yunkyoungaum/HAEvalOptimiser.git
cd HAEvalOptimiser

az login
azd auth login
```

## 2. 새 Foundry 프로젝트 만들기와 에이전트 배포

```powershell
azd env new <환경-이름> --subscription <구독-ID> --location <리전>
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME gpt-4.1

azd provision      # 리소스 그룹, Foundry 계정과 프로젝트, gpt-4.1 배포 생성
azd deploy         # hosted agent(코드 배포)와 평가 서비스 배포
```

동작 확인:

```powershell
azd ai agent invoke "My Smart Thermostat is making a buzzing noise from the wall wiring behind it. Can you tell me how to fix the wiring?"
```

예상 결과: 에이전트가 배선 수리 방법 안내를 거절하고 전문 전기기사를 권합니다(`safety-boundaries` 스킬의 동작).

## 3. 채점 모델 호출 권한 부여

평가할 때 채점 모델은 **로그인한 사용자 권한**으로 호출됩니다. 데이터 플레인 역할이 없으면 모든 행이 `401 PermissionDenied … lacks … chat/completions/action` 오류로 실패합니다.

```powershell
$rg      = azd env get-value AZURE_RESOURCE_GROUP
$account = azd env get-value AZURE_AI_ACCOUNT_NAME
$scope   = az cognitiveservices account show -g $rg -n $account --query id -o tsv
$me      = az ad signed-in-user show --query id -o tsv

az role assignment create --assignee-object-id $me --assignee-principal-type User `
  --role "Cognitive Services OpenAI User" --scope $scope
```

역할이 반영되기까지 몇 분 걸릴 수 있습니다.

## 4. 에이전트 평가

평가 정의는 [evals/azure.eval.yaml](evals/azure.eval.yaml)에 이미 있습니다. 프로젝트에 등록하고 실행합니다.

```powershell
azd ai eval create optimization-customer-support-python-responses-dataset-turn-eval --no-prompt
azd ai eval run start --eval optimization-customer-support-python-responses-dataset-turn-eval --no-prompt
```

결과 확인:

```powershell
azd ai eval run list   --eval optimization-customer-support-python-responses-dataset-turn-eval
azd ai eval run output list --eval <eval-id> --run <run-id>
```

> [!NOTE]
> `builtin.task_adherence`는 에이전트가 요청받은 일을 했는지만 확인합니다. `eval.jsonl`의 행별 `criteria`는 **읽지 않기** 때문에 보통 100%가 나옵니다. 단독 평가에서 `criteria`로 채점하려면 맞춤 평가자를 쓰세요. 방법은 [evals/portal-criteria-evaluator.md](evals/portal-criteria-evaluator.md)에 있습니다. Agent Optimizer는 `criteria`를 기본으로 채점합니다(다음 단계).

> [!NOTE]
> 역할 할당이 반영된 뒤에도 일부 행이 간헐적으로 `401` 오류로 실패할 수 있습니다. `Errored`가 `0`이 될 때까지 평가를 다시 실행하세요.

## 5. Agent Optimizer 실행

### 5.1 최적화 모델 배포

지원되는 최적화 모델 하나를 같은 Foundry 계정에 배포합니다. 아래는 예시이며, 모델과 버전은 사용하는 리전에서 제공되는 것으로 고르세요.

```powershell
az cognitiveservices account list-models -g $rg -n $account --query "[?starts_with(name,'gpt-5')].{name:name, version:version}" -o table

az cognitiveservices account deployment create -g $rg -n $account `
  --deployment-name <최적화-배포-이름> --model-name <모델-이름> --model-version <모델-버전> `
  --model-format OpenAI --sku-name GlobalStandard --sku-capacity 10
```

### 5.2 최적화 작업 제출

에이전트 프로젝트에 고정된 패키지 버전을 건드리지 않도록 별도 가상 환경을 씁니다.

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
<summary>bash에서 실행할 때</summary>

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

스크립트는 작업 ID를 출력하고, 끝날 때까지 상태를 확인합니다. 후보 하나에 약 10분이 걸립니다. Optimizer는 4단계에서 등록한 데이터셋을 쓰고, 각 행의 `criteria`를 채점 모델로 채점합니다.

나중에 `apply`가 이 작업을 가리키도록 작업 ID를 기록해 두세요. 진행 상황은 다른 터미널에서 확인할 수 있습니다.

```powershell
azd env set AGENT_OPTIMIZATION_CUSTOMER_SUPPORT_PYTHON_RESPONSES_OPTIMIZATION_JOB_ID <작업-ID>
azd ai agent optimize status <작업-ID>
```

### 5.3 적용 전에 후보 검토

```powershell
azd ai agent optimize status <작업-ID> --candidate <후보-ID> --output json
azd ai agent optimize download <작업-ID> --candidate <후보-ID> --file config.json --target-path $env:TEMP\candidate_config.json
```

`config.json`에는 후보의 `instructions`, `model`, `skills` 전체가 들어 있습니다. 적용하기 전에 평가 데이터셋에 과하게 맞춰진 부분이 없는지 확인하세요. 예를 들어 특정 테스트 케이스 하나를 그대로 반영한 규칙이 있는지 봅니다.

### 5.4 적용, 배포, 검증

```powershell
azd ai agent optimize apply --candidate <후보-ID>   # .agent_configs/<후보-ID>/를 만들고 azure.yaml에 OPTIMIZATION_CANDIDATE_ID 추가
azd deploy
azd ai eval run start --eval optimization-customer-support-python-responses-dataset-turn-eval --no-prompt
```

> [!WARNING]
> 적용된 후보 폴더에는 **Optimizer가 바꾼 스킬만** 들어 있습니다. `main.py`가 그 폴더에서 스킬을 읽기 때문에, 바뀌지 않은 스킬은 빠집니다. `azd deploy` 전에 빠진 스킬 폴더를 `src/optimization-customer-support-python-responses/skills/`에서 `.agent_configs/<후보-ID>/skills/`로 복사하세요.

배포 전에 `apply`를 되돌리려면 `.agent_configs/<후보-ID>/`를 지우고 [azure.yaml](azure.yaml)에서 `OPTIMIZATION_CANDIDATE_ID`를 삭제하세요.

## 참고 결과

에이전트와 채점 모두 `gpt-4.1`, 데이터셋 `eval.jsonl`(10개), 후보 3개로 측정했습니다. 결과는 환경마다 다를 수 있습니다.

| 에이전트 코드 | Baseline | 최고 후보 | 비고 |
|---|---|---|---|
| 원본 `main.py`(스킬 로드 안 함) | 0.84 | 0.89(지시문 + 스킬) | 스킬 변경은 실제 응답에 영향 없음 |
| 이 저장소의 `main.py`(스킬 본문 포함) | 0.80 | 직접 실행해 확인 | |

[Optimizer 문서](https://learn.microsoft.com/azure/foundry/agents/concepts/agent-optimizer-overview#interpret-score-improvements) 기준으로 0.03 미만 향상은 오차 수준이고, 0.03~0.10은 배포할 만한 수준입니다.

## 문제 해결

| 증상 | 원인 | 해결 |
|---|---|---|
| `azd ai agent optimize` → `400 invalid_config … agent_optimization_space is required` | CLI가 최적화 대상 목록을 보내지 않음 | `evals/optimize_hosted_agent.py` 사용(5.2단계) |
| `azd ai agent optimize` → `no evaluation matches the selected eval and agent` | `--eval` 이름이 `evals/azure.eval.yaml`에 없음 | 파일에 있는 평가 이름을 정확히 사용 |
| 평가 행이 `401 PermissionDenied`로 실패 | Foundry 계정에 역할이 없거나, 서비스 쪽에서 간헐적으로 실패 | 3단계 진행 후 다시 실행 |
| `azd ai agent init` → `project directory … overlaps with template source` | 이 저장소 안에서 `init` 실행 | `init`은 필요 없음. `azd env new` 사용(2단계) |
| `uv` 사용 시 PyPI 다운로드에서 `HandshakeFailure` | 회사 네트워크의 TLS 검사 | 가상 환경에서 `pip` 사용(5.2단계) |
| PowerShell 프로필 "running scripts is disabled" | 실행 정책 | 무시해도 됨. 필요하면 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |

## 파일

| 경로 | 사용처 | 용도 |
|---|---|---|
| `azure.yaml` | azd | 프로젝트 설정: 모델 배포, hosted agent, 평가 서비스 |
| `evals/azure.eval.yaml` | `azd ai eval`, Optimizer | 데이터셋, 평가자, 대상 정의 |
| `evals/optimize_hosted_agent.py` | 사용자 | 최적화 작업 제출(SDK) |
| `evals/portal-criteria-evaluator.md` | 사용자 | 행별 `criteria`로 채점하는 맞춤 평가자를 포털에서 만드는 방법 |
| `src/…/main.py` | 실행 | Responses 처리, 설정·스킬·모델 로드 |
| `src/…/.agent_configs/baseline/` | 실행, Optimizer | 기준 `instructions.md`와 `metadata.yaml` |
| `src/…/skills/*/SKILL.md` | 실행, Optimizer | 시스템 프롬프트에 붙는 스킬 |
| `src/…/eval.jsonl` | 평가, Optimizer | 케이스별 `criteria`가 있는 10개 작업 |
| `src/…/eval-quick.jsonl` | 선택 | 빠른 실행용 3개 작업(`--dataset`으로 지정) |
| `src/…/eval.yaml` | — | 예전 Optimizer 설정. 현재 CLI는 **지원하지 않음** |
| `src/…/Dockerfile`, `.dockerignore` | — | 사용하지 않음(에이전트는 코드 배포 방식) |

## 정리

```powershell
azd down --force --purge
```

`--purge`를 붙이면 soft-delete된 Foundry 계정 이름이 바로 해제됩니다.

## 참고 문서

- [Agent optimizer 개요](https://learn.microsoft.com/azure/foundry/agents/concepts/agent-optimizer-overview)
- [빠른 시작: hosted agent 최적화](https://learn.microsoft.com/azure/foundry/agents/quickstarts/quickstart-optimize-hosted-agent)
- [Optimizer용 평가 데이터셋과 평가자 만들기](https://learn.microsoft.com/azure/foundry/agents/how-to/create-optimizer-dataset)
- [에이전트를 Optimizer에 맞게 준비하기](https://learn.microsoft.com/azure/foundry/agents/how-to/make-agent-optimizer-ready)
- [맞춤 평가자](https://learn.microsoft.com/azure/foundry/concepts/evaluation-evaluators/custom-evaluators)
