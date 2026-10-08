# 🏭 manufacturing-data-analyzer

제조 센서 CSV 데이터를 분석하고, 이상(anomaly) 탐지 결과와 차트가 포함된
**HTML 리포트**를 자동 생성하는 Python CLI 도구입니다.

A Python CLI tool that analyzes manufacturing sensor CSV data, detects
anomalies with rolling-window z-scores, and auto-generates an HTML report
with embedded charts (English summary below).

## 설치 (Installation)

```bash
pip install -r requirements.txt
```

의존성: `pandas`, `numpy`, `matplotlib`

## 사용법 (Usage)

```bash
# 1. 샘플 데이터 생성 (온도/진동/압력/생산량 + 이상/결측값 포함)
python sample_data.py --output sample_data.csv --rows 2000 --seed 42

# 2. 분석 + HTML 리포트 생성
python analyzer.py --input sample_data.csv --output report.html

# 3. 탐지 민감도 조정
python analyzer.py --input sample_data.csv --output report.html \
    --window 120 --threshold 3.0 --top-n 15
```

### CLI 옵션

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--input`, `-i` | (필수) | 입력 CSV 파일 경로 |
| `--output`, `-o` | (필수) | 출력 HTML 파일 경로 |
| `--window` | 60 | 롤링 윈도우 크기 (직전 N개 데이터 기준) |
| `--threshold` | 3.0 | 이상 판정 z-score 임계값 |
| `--top-n` | 10 | 리포트에 표시할 상위 이상 건수 |

## 입력 CSV 형식

`timestamp` 컬럼(시각)과 숫자형 센서 컬럼으로 구성됩니다.
결측값(NaN)이 있어도 자동으로 제외하고 분석합니다.

```csv
timestamp,temperature,vibration,pressure,throughput
2026-10-01 00:00:00,24.12,2.53,5.02,101.3
2026-10-01 00:01:00,23.98,2.61,4.95,99.8
...
```

## 리포트 구성 (Sample Output)

생성되는 HTML 리포트는 다음을 포함합니다 (모든 설명은 한국어):

1. **분석 요약** — 총 행 수, 데이터 기간, 이상 이벤트 수, 가장 심한 이상
2. **센서별 기본 통계** — 평균 / 표준편차 / 최소 / 최대 / 결측값 표
3. **이상 탐지 결과 (상위 N건)** — 발생 시각, 센서, 측정값, z-score 표
4. **시계열 차트** — 센서별 추세선 + 이상 구간 빨간색 표시 (base64 PNG 내장)
5. **분포 히스토그램** — 센서별 값 분포 + 평균선
6. **부록** — 이상 탐지 방식 설명

차트는 base64로 HTML에 내장되므로, 리포트 파일 하나만으로 공유할 수 있습니다.

## 이상 탐지 방식 (How Anomaly Detection Works)

각 센서마다 **롤링 윈도우 z-score** 방식을 사용합니다:

1. 현재 시점의 측정값과 **직전 `window`개** 데이터의 평균·표준편차를 비교합니다.
2. `z = (현재값 − 롤링 평균) ÷ 롤링 표준편차` 를 계산합니다.
3. **|z| > threshold** 이면 이상으로 판정합니다.
4. 모든 이상의 |z-score|가 큰 순서대로 상위 N건을 리포트에 표시합니다.

롤링 기준을 사용하므로 센서값이 천천히 드리프트해도 오탐이 적고,
급격한 스파이크/급락만 이상으로 잡아냅니다.
표준편차가 0인 구간은 z-score를 0으로 처리하며, 결측값은 탐지에서 제외됩니다.

---

## English Summary

**manufacturing-data-analyzer** is a Python CLI that reads a manufacturing
sensor CSV (`timestamp`, `temperature`, `vibration`, `pressure`, `throughput`),
computes per-sensor statistics (mean/std/min/max), detects anomalies with a
rolling-window z-score method, and renders a self-contained HTML report
(Korean UI) with embedded base64 PNG charts: time series with anomaly markers
and distribution histograms.

```bash
pip install -r requirements.txt
python sample_data.py --output sample_data.csv
python analyzer.py --input sample_data.csv --output report.html
```
