# Protocol-aware Weekend Gap 모델

이 모델은 `rwa_market_gap/weekend_gap/baseline.py`를 교체하지 않는다. 기존 파일은 연구 초안의 수식을 재현하는 결정론적 기준선이고, 새 모델은 실제 프로토콜에 적용하기 전에 확인해야 할 조건을 별도 입력으로 분리한다.

## 새 파일

- `rwa_market_gap/weekend_gap/protocol_config.py`: 오라클 정책, 준비금 상태, 캡, 금리곡선, 부분청산, 유동성 및 근거 상태
- `rwa_market_gap/weekend_gap/protocol.py`: 대출 가능 여부, 부분청산 경로, 전략적 디폴트, 부실채권 및 갭 표본 기대값
- `tests/weekend_gap/test_protocol.py`: 신규 모델의 경계조건 테스트

## 기본 실행

```bash
python3 -m scripts.run_weekend_gap
```

기본값은 실제 프로토콜 스냅샷이 아니다. 따라서 전통시장이 닫혀 있고 가격이 오래된 상태의 신규 대출을 차단한다.

## 연구 가정을 명시적으로 활성화하는 예시

```python
from dataclasses import replace

from rwa_market_gap.weekend_gap.protocol_config import (
    DEFAULT_PROTOCOL_AWARE_WEEKEND_GAP_CONFIG,
)
from rwa_market_gap.weekend_gap.protocol import ProtocolAwareWeekendGapEngine

base = DEFAULT_PROTOCOL_AWARE_WEEKEND_GAP_CONFIG
config = replace(
    base,
    protocol_name="검증할 프로토콜명",
    collateral_symbol="검증할 종목",
    snapshot_label="스냅샷 시각과 블록 번호",
    oracle=replace(
        base.oracle,
        allow_new_loans_when_market_closed=True,
        closed_market_staleness_exemption=True,
    ),
)

engine = ProtocolAwareWeekendGapEngine(config)
outcome = engine.realized(0.35)  # 금요일 종가 대비 35% 하락
print(outcome)
```

위 두 불리언은 공격 가능성을 가정하는 스위치다. 실제 트랜잭션이나 온체인 설정으로 확인하기 전에는 `True`가 실증 결과를 의미하지 않는다.

## 실제 갭 표본 사용

```python
gaps = (-0.03, 0.01, 0.04, 0.12, 0.35)
summary = engine.evaluate_gap_samples(
    gaps,
    sample_source="데이터 파일·기간·산출 방법",
)
print(summary.expected_attacker_net_profit_usd)
print(summary.expected_protocol_bad_debt_usd)
```

- 양수 갭: 가격 하락
- 음수 갭: 가격 상승
- `evaluate_gap_samples`는 성공/실패 두 상태로 축약하지 않고 모든 표본의 경로를 계산한다.

## 실증 모델로 표시하기 전에 필요한 자료

1. 대상 프로토콜·마켓·자산과 스냅샷 블록 번호
2. Max LTV, Liquidation LTV, Borrow Factor, 공급·대출 캡과 남은 유동성
3. 전통시장 폐장 중 신규 차입 가능 여부, 오라클 가격 신선도 예외와 가격 밴드
4. 이용률별 실제 차입금리 곡선
5. close factor, 청산 보너스 상승식, 회당 한도와 자동 디레버리징 조건
6. 포지션 규모별 실제 애그리게이터 견적 또는 풀별 준비금·수수료
7. 종목별 주말 가격 갭 원자료와 전처리 방법
8. 스테이블코인 동결·회수, 법적 상환청구 또는 기타 제한 여부

`EvidenceConfig`의 검증 플래그는 위 근거를 확보한 뒤에만 켠다. 하나라도 검증 플래그를 켜려면 `source_notes`에 재현 가능한 출처를 남겨야 한다.

## 해석할 때 구분할 값

- `liquidation_start_gap`: 부분청산이 시작될 수 있는 가격 하락률
- `principal_insolvency_gap`: 이자를 포함한 부채가 담보가치를 넘어서는 하락률
- `attacker_net_profit_vs_hold_usd`: 같은 담보를 계속 보유했을 때와 비교한 공격자 순손익
- `protocol_bad_debt_usd`: 부분청산 후 남은 담보를 처분해도 회수하지 못하는 원금
- `empirically_calibrated`: 프로토콜·오라클·유동성·갭 데이터가 모두 검증됐는지 여부

테스트 통과는 입력된 규칙을 코드가 일관되게 계산한다는 의미다. 실제 공격 가능성은 위 자료를 채운 뒤 별도로 판단해야 한다.
