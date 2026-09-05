# 설명
PoS 체인이 정상적으로 작동하더라도 온체인이 참조하는 원자재 가격과 실제
시장 위험이 어긋날 때 경제적 손실이 남는지를 검증하는 Python 모델

공식값·관측값·가정값을 분리하고, 선언한 조건에서 비용·수익·손익분기점을
재현하는 것이 목적

## 실행 순서

Python 3.10 이상에서 저장소 최상위 경로를 기준으로 실행

```bash
# 1. 원자재 기본 결과
python3 -m scripts.run_commodity_simulation

# 2. 원자재 가정값 민감도
python3 -m scripts.run_commodity_sensitivity

# 3. 전체 테스트
python3 -m unittest discover -s tests -v
```

그래프를 다시 만들 때만 Pillow가 필요

```bash
python3 -m pip install -r requirements-visualization.txt
python3 -m scripts.plot_commodity_results
```

## 저장소에 포함된 모델

| 모델 | 포함 범위 | 포함하지 않는 것 |
|---|---|---|
| 원자재 시뮬레이션 | WTI 조건부 사후 경제성, 토큰화 금 반증 테스트, 천연가스 벤치마크 불일치 | 실제 체결 재현, 임의 공격 성공확률, 미확인 ADL·백스톱 손실 |

## 원자재 읽는 순서

1. [`docs/commodity_simulation.md`](docs/commodity_simulation.md): 검증 질문·수식·결과·한계
2. [`data/commodity_simulation/evidence.json`](data/commodity_simulation/evidence.json): 공식값과 관측값
3. [`data/commodity_simulation/assumptions.json`](data/commodity_simulation/assumptions.json): 연구상 가정값
4. [`rwa_market_gap/commodity_simulation/`](rwa_market_gap/commodity_simulation/): 계산 로직
5. [`tests/commodity_simulation/`](tests/commodity_simulation/): 수식과 경계조건 검증

입력값으로 계산한 순이익과 손익분기점은 실측값이 아니라 모델 결과

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

## 모델 상세

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

## 테스트

핵심 모델과 테스트는 Python 3.10 이상에서 외부 패키지 없이 실행 가능

```bash
python3 -m unittest discover -s tests -v
```

전체 테스트 82개

구성: 공시 파라미터 메커니즘 35개 / 비용·수익 계산 38개 / 시각화 수치 9개

테스트 범위: 입력 수식과 경계조건의 코드 내 일관성 확인
