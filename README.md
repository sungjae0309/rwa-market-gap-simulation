# RWA Market Gap Simulation

전통시장과 24시간 온체인 시장의 운영시간·가격 기준 차이를 분석하는 파이썬 연구 코드입니다.

## 모델

### 통합 공격 시나리오

토큰화 주식 담보의 주말 가격 공백, 신규 차입, 청산과 전략적 디폴트를 다룹니다.

- 코드: `rwa_market_gap/weekend_gap/`
- 테스트: `tests/weekend_gap/`
- 실행: `python3 -m scripts.run_weekend_gap`
- 문서: [Weekend Gap 모델](docs/weekend_gap_protocol.md)

### 원자재 시나리오

WTI, 천연가스와 토큰화 금의 CoC, PfC, 순이익과 손익분기 조건을 계산합니다.

- 코드: `rwa_market_gap/commodity_simulation/`
- 입력: `data/commodity_simulation/`
- 테스트: `tests/commodity_simulation/`
- 실행: `python3 -m scripts.run_commodity_simulation`
- 민감도: `python3 -m scripts.run_commodity_sensitivity`
- 문서: [원자재 시뮬레이션](docs/commodity_simulation.md)

두 모델은 서로 import하지 않는 독립된 패키지입니다.

## 테스트

Python 3.10 이상에서 외부 패키지 없이 실행할 수 있습니다.

```bash
python3 -m unittest discover -s tests -v
```

현재 전체 테스트는 60개이며, 원자재 시나리오 전용 테스트는 33개입니다.

테스트 통과는 입력된 수식과 경계조건이 코드에서 일관되게 작동한다는 의미입니다. 실제 공격 성공이나 확정 손실을 입증하지 않습니다.

본 저장소는 연구용이며 실제 공격 또는 금융·투자 지침을 제공하지 않습니다.
