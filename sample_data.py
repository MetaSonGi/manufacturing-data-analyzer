#!/usr/bin/env python3
"""sample_data.py — 제조 센서 샘플 CSV 데이터 생성기.

현실적인 센서 신호(온도, 진동, 압력, 생산량)를 생성하고,
의도적으로 이상(anomaly)과 결측값(missing value)을 섞어
analyzer.py 테스트용 샘플 데이터를 만듭니다.

사용법:
    python sample_data.py --output sample.csv --rows 2000 --seed 42
"""
import argparse

import numpy as np
import pandas as pd

SENSOR_COLUMNS = ["temperature", "vibration", "pressure", "throughput"]

COLUMN_UNITS = {
    "temperature": "°C",
    "vibration": "mm/s",
    "pressure": "bar",
    "throughput": "units/h",
}


def generate_sample_data(rows: int, start: str, seed: int) -> pd.DataFrame:
    """현실적인 제조 센서 시계열 데이터를 생성합니다."""
    rng = np.random.default_rng(seed)
    timestamps = pd.date_range(start=start, periods=rows, freq="1min")
    t = np.arange(rows)

    # 온도: 24°C 근처에서 천천히 드리프트 + 노이즈
    temperature = 24.0 + np.cumsum(rng.normal(0, 0.02, rows)) + rng.normal(0, 0.3, rows)
    # 진동: 2.5 mm/s 근처, 서서히 증가하는 경향 + 노이즈
    vibration = 2.5 + np.cumsum(rng.normal(0.0005, 0.005, rows)) + rng.normal(0, 0.15, rows)
    # 압력: 5.0 bar, 주기적 변동 + 노이즈
    pressure = 5.0 + 0.3 * np.sin(t / 50) + rng.normal(0, 0.1, rows)
    # 생산량: 시간당 100개, 주기적 변동 + 노이즈
    throughput = 100 + 5 * np.sin(t / 120) + rng.normal(0, 3, rows)

    df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "temperature": temperature,
            "vibration": vibration,
            "pressure": pressure,
            "throughput": throughput,
        }
    )

    # --- 이상(anomaly) 주입: 각 센서마다 2~4개의 급격한 스파이크/급락 ---
    anomaly_specs = {
        "temperature": 6.0,   # ±6°C 급변
        "vibration": 3.0,     # ±3 mm/s 급변
        "pressure": 1.5,      # ±1.5 bar 급변
        "throughput": 25.0,   # ±25 units/h 급변
    }
    n_anomalies = max(2, rows // 500)
    for col, magnitude in anomaly_specs.items():
        indices = rng.choice(rows, size=n_anomalies, replace=False)
        directions = rng.choice([-1, 1], size=n_anomalies)
        magnitudes = magnitude * rng.uniform(1.0, 1.5, n_anomalies)
        df.loc[df.index[indices], col] += directions * magnitudes

    # --- 결측값 주입: 전체의 약 0.5% ---
    n_missing = max(5, rows // 200)
    miss_rows = rng.choice(rows, size=n_missing, replace=False)
    miss_cols = rng.choice(SENSOR_COLUMNS, size=n_missing)
    for row, col in zip(miss_rows, miss_cols):
        df.loc[df.index[row], col] = np.nan

    return df


def main() -> None:
    parser = argparse.ArgumentParser(
        description="제조 센서 샘플 CSV 데이터를 생성합니다."
    )
    parser.add_argument(
        "--output", "-o", default="sample_data.csv", help="생성할 CSV 파일 경로"
    )
    parser.add_argument("--rows", type=int, default=2000, help="생성할 행 수 (기본값: 2000)")
    parser.add_argument(
        "--start", default="2026-10-01 00:00", help="시작 시각 (기본값: 2026-10-01 00:00)"
    )
    parser.add_argument("--seed", type=int, default=42, help="난수 시드 (기본값: 42)")
    args = parser.parse_args()

    df = generate_sample_data(args.rows, args.start, args.seed)
    df.to_csv(args.output, index=False)
    print(f"생성 완료: {args.output} ({len(df)}행, 결측값 {int(df.isna().sum().sum())}개)")


if __name__ == "__main__":
    main()
