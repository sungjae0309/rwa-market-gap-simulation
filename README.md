# RWA Market Gap Simulation

## 폴더 설명 

| 항목 | 역할 |
|---|---|
| `data/commodity_simulation/` | 원자재 모델의 근거 수치와 가정값 |
| `docs/` | 모델별 수식, 가정, 결과 해석 |
| `rwa_market_gap/` | 실제 계산 로직 |
| `scripts/` | 시뮬레이션 실행 진입점 |
| `tests/` | 수식, 경계조건, 결과 일관성 검증 |
| `.gitignore` | 로컬 전용 파일과 민감 파일의 GitHub 제외 설정 |
| `README.md` | 프로젝트 개요와 실행 방법 |

`data` = 입력 / `rwa_market_gap` = 계산 / `scripts` = 실행 / `tests` = 검증

## 모델

### 통합 공격 시나리오

토큰화 주식 담보의 주말 가격 공백, 신규 차입, 청산과 전략적 디폴트 분석

- 코드: `rwa_market_gap/weekend_gap/`
- 테스트: `tests/weekend_gap/`
- 실행: `python3 -m scripts.run_weekend_gap`
- 문서: [Weekend Gap 모델](docs/weekend_gap_protocol.md)

### 원자재 시나리오

공시 파라미터 메커니즘(밴드 항등식, 리앵커 하드캡, 마진 구간)과 WTI·천연가스·토큰화 금의 CoC, PfC, 순이익, 손익분기 조건 계산

- 코드: `rwa_market_gap/commodity_simulation/`
- 입력: `data/commodity_simulation/`
- 테스트: `tests/commodity_simulation/`
- 실행: `python3 -m scripts.run_commodity_simulation`
- 민감도: `python3 -m scripts.run_commodity_sensitivity`
- 문서: [원자재 시뮬레이션](docs/commodity_simulation.md)

두 모델 간 import 없는 독립 패키지

## 테스트

Python 3.10 이상, 외부 패키지 없이 실행 가능

```bash
python3 -m unittest discover -s tests -v
```

전체 테스트 93개 / 원자재 시나리오 전용 테스트 66개

원자재 전용 66개 구성: 공시 파라미터 메커니즘 33개 / 스트레스 경제 모델 33개

테스트 범위: 입력 수식과 경계조건의 코드 내 일관성 확인

한계: 실제 공격 성공 또는 확정 손실의 입증이 아닌 연구용 모델

사용 제외: 실제 공격 또는 금융·투자 지침
