# RWA Market Gap Simulation

## 폴더 설명 

| 항목 | 역할 |
|---|---|
| `data/commodity_simulation/` | 원자재 모델의 근거 수치와 가정값 |
| `docs/` | 모델별 수식, 가정, 결과 해석 |
| `figures/commodity_simulation/` | 노션·보고서용 원자재 결과 그래프 영문·한글판 |
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

공시 가격 밴드와 마진 구조를 재현하고 WTI·천연가스·토큰화 금의 공격 비용(CoC), 조건부 수익(PfC), 순이익, 손익분기 조건 계산

WTI는 조건부 사후 경제성, 금은 가격 괴리 반증, 천연가스는 벤치마크 불일치를 각각 검증하며 세 결과를 하나의 공격 수익으로 합산하지 않음. 격리 마진은 청산 담보 범위만 구분하고 미확인 백스톱·ADL은 추정하지 않음.

- 코드: `rwa_market_gap/commodity_simulation/`
- 입력: `data/commodity_simulation/`
- 테스트: `tests/commodity_simulation/`
- 실행: `python3 -m scripts.run_commodity_simulation`
- 민감도: `python3 -m scripts.run_commodity_sensitivity`
- 그래프: `python3 -m scripts.plot_commodity_results` 영문·한국어 PNG 각 4개 생성
- 문서: [원자재 시뮬레이션](docs/commodity_simulation.md)

두 모델 간 import 없는 독립 패키지

## 테스트

핵심 모델과 테스트는 Python 3.10 이상에서 외부 패키지 없이 실행 가능

```bash
python3 -m unittest discover -s tests -v
```

전체 테스트 109개 / 원자재 시나리오 전용 테스트 82개

원자재 전용 82개 구성: 공시 파라미터 메커니즘 35개 / 비용·수익 계산 38개 / 시각화 수치 9개

테스트 범위: 입력 수식과 경계조건의 코드 내 일관성 확인

## 그래프 생성

그래프 생성에만 Pillow 필요

```bash
python3 -m pip install -r requirements-visualization.txt
python3 -m scripts.plot_commodity_results
```
