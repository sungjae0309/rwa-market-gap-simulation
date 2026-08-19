# RWA Market Gap Simulation

전통시장과 24시간 온체인 시장의 운영시간·가격 기준 차이를 분석하는 파이썬 연구 코드입니다.

## 모델 구분

### 1. 통합 공격 시나리오

토큰화 주식 담보의 주말 가격 공백, 신규 차입, 청산과 전략적 디폴트를 다룹니다.

- 코드: `rwa_market_gap/weekend_gap/`
- 테스트: `tests/weekend_gap/`
- 실행: `python3 -m scripts.run_weekend_gap`
- 문서: [Weekend Gap 모델](docs/weekend_gap_protocol.md)

### 2. 원자재 오라클 시나리오

WTI, 천연가스와 토큰화 금의 시장시간·오라클·벤치마크 공백을 다룹니다.

- 기초 메커니즘: `rwa_market_gap/commodity_oracle/`
- 검토 반영 경제 모델: `rwa_market_gap/reviewed_commodity_economics/`
- 입력 데이터: `data/commodity_oracle/`, `data/reviewed_commodity_economics/`
- 테스트: `tests/commodity_oracle/`, `tests/reviewed_commodity_economics/`

원자재 검토 반영본은 CoC, PfC, 순이익과 손익분기 조건을 계산합니다. 근거가 없는 공격 성공확률이나 청산·ADL 손실은 생성하지 않습니다.

## 실행

Python 3.10 이상에서 외부 패키지 없이 실행할 수 있습니다.

```bash
# 통합 공격 시나리오
python3 -m scripts.run_weekend_gap

# 원자재 메커니즘과 검토 반영 결과
python3 -m scripts.run_commodity_oracle
python3 -m scripts.run_reviewed_commodity_economics
python3 -m scripts.run_reviewed_sensitivity

# 전체 테스트
python3 -m unittest discover -s tests -v
```

현재 전체 테스트는 98개이며, 원자재 검토 반영본 전용 테스트는 33개입니다.

## 문서

- [원자재 메커니즘](docs/commodity_oracle.md)
- [원자재 검토 반영 결과](docs/reviewed_commodity_economics.md)
- [원자재 모델의 한계와 추가 데이터](docs/commodity_oracle_limitations.md)
- [초기 공격경제 실험본](docs/attack_economics.md)

## 해석 범위

테스트 통과는 입력된 수식과 경계조건이 코드에서 일관되게 작동한다는 의미입니다. 실제 공격 성공이나 확정 손실을 입증하지 않으며, 검증되지 않은 가정과 입력은 결과에 명시합니다.

본 저장소는 연구용이며 실제 공격 또는 금융·투자 지침을 제공하지 않습니다.
