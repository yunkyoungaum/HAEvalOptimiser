# Foundry 포털에서 케이스별 기준(`criteria`)으로 평가하기

`eval.jsonl`의 각 샘플에 들어 있는 `criteria`를 실제 채점에 쓰도록, Foundry 포털에서 맞춤 평가자를 만들어 평가하는 방법입니다.

## 배경

- `builtin.task_adherence`는 "요청한 일을 했는지"만 넓게 봅니다. 그래서 최적화 전 기본 프롬프트로도 통과율 100%가 나왔습니다.
- `eval.jsonl`에는 샘플마다 세부 기준이 있습니다(10개 샘플, 약 40개 기준). 예를 들어 "30일 반품 기간을 언급할 것", "전기 배선 안내를 거부할 것" 같은 항목입니다. 이 기준은 기본 평가자로는 채점되지 않습니다.
- 프롬프트 기반 맞춤 평가자는 데이터셋 필드를 템플릿 변수(`{{...}}`)로 받을 수 있습니다. 이 기능으로 **각 샘플의 `criteria`를 그대로 넣어 케이스별로 채점**합니다.

## 대상 환경

| 항목 | 값 |
|---|---|
| Foundry 계정 / 프로젝트 | `azd env get-value AZURE_AI_ACCOUNT_NAME` / `azd env get-value AZURE_AI_PROJECT_NAME`로 확인 |
| 에이전트 | `optimization-customer-support-python-responses` |
| 데이터셋 | `eval` (v1.0, `eval.jsonl`과 내용 동일) |
| 채점 모델 | `gpt-4.1` |

## 1단계: 맞춤 평가자 만들기

1. [Foundry 포털](https://ai.azure.com)에서 위 프로젝트로 들어갑니다.
2. **Evaluation → Evaluator catalog → Custom evaluator → Create**를 선택합니다.
3. 아래처럼 입력합니다.

| 필드 | 값 |
|---|---|
| Name | `support_criteria_judge` |
| Type | **Prompt-based** |
| Scoring method | **Continuous** (0.0~1.0) |
| Prompt | 아래 템플릿 |

```text
You are a strict QA reviewer for a consumer electronics customer support agent.

Evaluate the RESPONSE against EVERY criterion in CRITERIA.
A criterion passes only if the response clearly and explicitly satisfies it.
Partial, implied, or vague coverage counts as FAIL.

QUERY:
{{query}}

RESPONSE:
{{response}}

CRITERIA (JSON array of {name, instruction}):
{{criteria}}

Score = (number of passed criteria) / (total criteria), rounded to 2 decimals.

Output Format (JSON):
{
  "result": <float 0.0-1.0>,
  "reason": "<for each criterion: name - PASS/FAIL - one-line justification>"
}
```

`{{query}}`, `{{response}}`, `{{criteria}}`는 변수입니다. 평가가 실행될 때 데이터셋 각 줄의 값으로 채워집니다.

## 2단계: 평가 만들기

1. **Evaluation → Create**를 선택합니다.
2. **Target**: **Agent** → `optimization-customer-support-python-responses`
3. **Scope**: **Individual turns**
4. **Data source**: **Existing dataset** → `eval` (v1.0)
5. **Configure agents**: User prompt는 기본값 `{{item.query}}`를 그대로 둡니다.
6. **Field mapping**: 아래 [필드 매핑](#필드-매핑) 표를 따릅니다.
7. **Testing criteria**에서 **Add evaluator**를 누르고 아래를 추가합니다.
   - **Custom**: `support_criteria_judge`, 모델 `gpt-4.1`, threshold `0.8`
   - **Agent**: Task Adherence, Intent Resolution
   - **Safety**: Violence, Self-harm 등
8. 이름을 입력하고 **Submit**합니다.

### 필드 매핑

매핑 화면에 `criteria` 칸이 **있는 경우**:

| 칸 | 연결할 값 |
|---|---|
| `query` | `item.query` |
| `response` | 에이전트 응답(자동) |
| `criteria` | `item.criteria` |

매핑 화면에 `criteria` 칸이 **없는 경우**에는 원래 있는 `ground_truth` 칸을 빌려 씁니다.

1. 1단계에서 만든 평가자의 Prompt에서 아래 한 줄만 바꿉니다(Evaluation → Evaluator catalog → `support_criteria_judge`).

   변경 전:
   ```text
   CRITERIA (JSON array of {name, instruction}):
   {{criteria}}
   ```

   변경 후:
   ```text
   CRITERIA (JSON array of {name, instruction}):
   {{ground_truth}}
   ```

2. 매핑은 아래처럼 연결합니다.

   | 칸 | 연결할 값 |
   |---|---|
   | `query` | `item.query` |
   | `response` | 에이전트 응답(자동) |
   | `ground_truth` | `item.criteria` |

`eval.jsonl`이나 에이전트 코드는 고칠 필요가 없습니다.

## 3단계: 결과 보기

- **Evaluation** 목록에서 실행을 열면 샘플별 점수와 `reason`을 볼 수 있습니다.
- `reason`에 기준마다 PASS/FAIL과 이유가 적혀 있어서, 어떤 기준에서 실패했는지 바로 알 수 있습니다.
- Status가 **Partial**이면 일부 평가자가 실패한 것입니다. 다시 실행하세요.

## 주의 사항

- **`criteria` 칸 노출 여부**: 포털 매핑 화면에 `criteria` 칸이 나오는지는 직접 확인하지 못했습니다. 없으면 위의 `ground_truth` 우회 방법을 쓰세요.
- **`criteria` 형식**: `criteria`는 객체 배열이라 프롬프트에는 JSON 문자열로 들어갈 것으로 예상합니다. 첫 실행 뒤 `reason`에 기준 이름이 제대로 나오는지 확인하세요.
- **간헐적 401 오류**: CLI로 평가할 때 채점 단계에서 401 오류가 간헐적으로 섞여 나왔습니다. 포털에서도 비슷할 수 있으니, 오류가 난 샘플이 있으면 다시 실행하세요.
- **채점 모델**: 지금은 평가 대상과 채점 모델이 둘 다 `gpt-4.1`입니다. 더 엄격하게 하려면 더 강한 모델을 채점 모델로 쓰세요.

## 참고 문서

- [Custom evaluators](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/custom-evaluators)
- [Run evaluations from the Foundry portal](https://learn.microsoft.com/en-us/azure/foundry/how-to/evaluate-generative-ai-app)
