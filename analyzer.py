#!/usr/bin/env python3
"""analyzer.py — 제조 센서 CSV 분석 CLI.

센서 CSV를 읽어 기본 통계를 계산하고, 롤링 윈도우 z-score 방식으로
이상(anomaly)을 탐지한 뒤, 차트가 포함된 HTML 리포트를 생성합니다.

사용법:
    python analyzer.py --input sample_data.csv --output report.html
    python analyzer.py --input sample_data.csv --output report.html --window 120 --threshold 3.0 --top-n 15
"""
import argparse
import base64
import html as html_module
import io
from datetime import datetime

import matplotlib

matplotlib.use("Agg")  # 헤드리스 환경에서 렌더링
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# 센서 컬럼별 단위 (리포트 표시에 사용)
COLUMN_UNITS = {
    "temperature": "°C",
    "vibration": "mm/s",
    "pressure": "bar",
    "throughput": "units/h",
}


def load_data(path: str) -> tuple[pd.DataFrame, str, list[str]]:
    """CSV를 읽어 (데이터프레임, 시각 컬럼명, 센서 컬럼 목록)을 반환합니다."""
    df = pd.read_csv(path)

    # 시각 컬럼 찾기: 'timestamp' 우선, 없으면 datetime 파싱 가능한 컬럼
    ts_col = None
    for candidate in ["timestamp", "time", "datetime", "date"]:
        if candidate in df.columns:
            ts_col = candidate
            break
    if ts_col is None:
        for col in df.columns:
            try:
                pd.to_datetime(df[col])
                ts_col = col
                break
            except (ValueError, TypeError):
                continue
    if ts_col is None:
        raise ValueError("CSV에서 시각(time) 컬럼을 찾을 수 없습니다.")

    df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce")
    df = df.sort_values(ts_col).reset_index(drop=True)

    numeric_cols = [
        c for c in df.columns
        if c != ts_col and pd.api.types.is_numeric_dtype(df[c])
    ]
    if not numeric_cols:
        raise ValueError("분석할 수 있는 숫자형 센서 컬럼이 없습니다.")

    return df, ts_col, numeric_cols


def compute_stats(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """센서별 기본 통계(평균/표준편차/최소/최대/결측수)를 계산합니다."""
    stats = df[columns].agg(["mean", "std", "min", "max"]).T
    stats["missing"] = df[columns].isna().sum()
    stats["count"] = df[columns].notna().sum()
    return stats


def detect_anomalies(
    df: pd.DataFrame,
    ts_col: str,
    column: str,
    window: int,
    threshold: float,
) -> pd.DataFrame:
    """롤링 윈도우 z-score로 이상을 탐지합니다.

    현재 시점의 값과 '직전 window개'의 롤링 평균/표준편차를 비교합니다.
    z = (x - rolling_mean) / rolling_std, |z| > threshold 이면 이상으로 판정.
    """
    series = df[column]
    rolling_mean = series.shift(1).rolling(window, min_periods=max(2, window // 3)).mean()
    rolling_std = series.shift(1).rolling(window, min_periods=max(2, window // 3)).std()
    # 표준편차가 0이면 z-score를 0으로 처리 (0으로 나누기 방지)
    safe_std = rolling_std.replace(0, np.nan)
    z_scores = (series - rolling_mean) / safe_std
    z_scores = z_scores.fillna(0)

    mask = z_scores.abs() > threshold
    anomalies = pd.DataFrame(
        {
            "timestamp": df.loc[mask, ts_col],
            "sensor": column,
            "value": series[mask],
            "z_score": z_scores[mask],
        }
    )
    return anomalies.reset_index(drop=True)


def fig_to_base64(fig: plt.Figure) -> str:
    """matplotlib Figure를 base64 PNG 문자열로 변환합니다."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("ascii")


def plot_timeseries(
    df: pd.DataFrame,
    ts_col: str,
    columns: list[str],
    anomalies_by_col: dict[str, pd.DataFrame],
) -> str:
    """센서별 시계열 차트(이상 구간 빨간색 표시)를 그립니다."""
    n = len(columns)
    fig, axes = plt.subplots(n, 1, figsize=(12, 3 * n), sharex=True)
    if n == 1:
        axes = [axes]

    for ax, col in zip(axes, columns):
        unit = COLUMN_UNITS.get(col, "")
        ax.plot(df[ts_col], df[col], linewidth=0.8, color="#3b82f6", label="value")
        col_anom = anomalies_by_col.get(col)
        if col_anom is not None and not col_anom.empty:
            ax.scatter(
                col_anom["timestamp"],
                col_anom["value"],
                color="#ef4444",
                s=24,
                zorder=5,
                label="anomaly",
            )
        ax.set_title(f"{col} ({unit}) - time series with anomalies")
        ax.set_ylabel(unit or col)
        ax.legend(loc="upper right", fontsize=8)
        ax.grid(alpha=0.3)

    axes[-1].set_xlabel("time")
    fig.tight_layout()
    return fig_to_base64(fig)


def plot_histograms(df: pd.DataFrame, columns: list[str]) -> str:
    """센서별 분포 히스토그램을 그립니다."""
    n = len(columns)
    ncols = 2
    nrows = (n + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(12, 3.5 * nrows))
    axes = np.atleast_1d(axes).ravel()

    for ax, col in zip(axes, columns):
        unit = COLUMN_UNITS.get(col, "")
        values = df[col].dropna()
        ax.hist(values, bins=50, color="#60a5fa", edgecolor="white", alpha=0.9)
        ax.axvline(values.mean(), color="#ef4444", linestyle="--", linewidth=1.5,
                   label=f"mean={values.mean():.2f}")
        ax.set_title(f"{col} ({unit}) - distribution")
        ax.set_xlabel(unit or col)
        ax.set_ylabel("count")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3)

    for ax in axes[len(columns):]:
        ax.axis("off")
    fig.tight_layout()
    return fig_to_base64(fig)


def format_number(x) -> str:
    if pd.isna(x):
        return "-"
    return f"{x:,.4f}"


def build_html(
    *,
    input_path: str,
    stats: pd.DataFrame,
    top_anomalies: pd.DataFrame,
    total_anomalies: int,
    ts_image_b64: str,
    hist_image_b64: str,
    row_count: int,
    time_range: str,
    window: int,
    threshold: float,
    top_n: int,
) -> str:
    """분석 결과를 한국어 HTML 리포트로 렌더링합니다."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 통계 테이블
    stat_rows = []
    for col in stats.index:
        unit = COLUMN_UNITS.get(col, "")
        stat_rows.append(
            "<tr>"
            f"<td>{html_module.escape(str(col))}</td>"
            f"<td>{html_module.escape(unit)}</td>"
            f"<td>{format_number(stats.loc[col, 'mean'])}</td>"
            f"<td>{format_number(stats.loc[col, 'std'])}</td>"
            f"<td>{format_number(stats.loc[col, 'min'])}</td>"
            f"<td>{format_number(stats.loc[col, 'max'])}</td>"
            f"<td>{int(stats.loc[col, 'missing'])}</td>"
            "</tr>"
        )

    # 이상 상위 N 테이블
    if top_anomalies.empty:
        anomaly_rows = '<tr><td colspan="4" class="center">탐지된 이상이 없습니다.</td></tr>'
    else:
        anomaly_rows = []
        for _, row in top_anomalies.iterrows():
            unit = COLUMN_UNITS.get(row["sensor"], "")
            anomaly_rows.append(
                "<tr>"
                f"<td>{row['timestamp']}</td>"
                f"<td>{html_module.escape(str(row['sensor']))}</td>"
                f"<td>{format_number(row['value'])} {html_module.escape(unit)}</td>"
                f"<td class='z'>{row['z_score']:+.2f}</td>"
                "</tr>"
            )
        anomaly_rows = "\n".join(anomaly_rows)

    # 요약
    if top_anomalies.empty:
        worst = "이상 없음"
    else:
        w = top_anomalies.iloc[0]
        worst = (
            f"{w['sensor']} 센서, {w['timestamp']} (z-score {w['z_score']:+.2f})"
        )

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>제조 센서 데이터 분석 리포트</title>
<style>
  body {{ font-family: -apple-system, 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif;
         max-width: 1100px; margin: 0 auto; padding: 32px; color: #1f2937; }}
  h1 {{ border-bottom: 3px solid #3b82f6; padding-bottom: 12px; }}
  h2 {{ color: #1d4ed8; margin-top: 40px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 16px 0; }}
  th, td {{ border: 1px solid #d1d5db; padding: 8px 12px; text-align: right; }}
  th {{ background: #eff6ff; text-align: center; }}
  td:first-child, th:first-child {{ text-align: left; }}
  .z {{ color: #dc2626; font-weight: bold; }}
  .center {{ text-align: center; }}
  .meta {{ color: #6b7280; font-size: 0.95em; }}
  img.chart {{ width: 100%; border: 1px solid #e5e7eb; border-radius: 8px; margin: 8px 0; }}
  .note {{ background: #f9fafb; border-left: 4px solid #3b82f6; padding: 12px 16px; }}
</style>
</head>
<body>
<h1>📊 제조 센서 데이터 분석 리포트</h1>
<p class="meta">분석 일시: {now} ｜ 입력 파일: {html_module.escape(input_path)}</p>

<h2>1. 분석 요약</h2>
<ul>
  <li><strong>총 데이터 행 수:</strong> {row_count:,}행</li>
  <li><strong>데이터 기간:</strong> {html_module.escape(time_range)}</li>
  <li><strong>탐지된 이상 이벤트:</strong> {total_anomalies:,}건 (상위 {top_n}건 표시)</li>
  <li><strong>가장 심한 이상:</strong> {html_module.escape(str(worst))}</li>
</ul>

<h2>2. 센서별 기본 통계</h2>
<table>
  <tr><th>센서 (sensor)</th><th>단위</th><th>평균 (mean)</th><th>표준편차 (std)</th>
      <th>최소 (min)</th><th>최대 (max)</th><th>결측값</th></tr>
  {''.join(stat_rows)}
</table>
<p class="meta">※ 결측값은 통계 계산에서 제외됩니다.</p>

<h2>3. 이상 탐지 결과 (상위 {top_n}건)</h2>
<table>
  <tr><th>발생 시각</th><th>센서</th><th>측정값</th><th>z-score</th></tr>
  {anomaly_rows}
</table>

<h2>4. 시계열 차트 (이상 구간 표시)</h2>
<img class="chart" src="data:image/png;base64,{ts_image_b64}" alt="시계열 차트">

<h2>5. 센서별 분포 히스토그램</h2>
<img class="chart" src="data:image/png;base64,{hist_image_b64}" alt="히스토그램">

<h2>부록: 이상 탐지 방식</h2>
<div class="note">
  <p>각 센서마다 <strong>롤링 윈도우 z-score</strong> 방식으로 이상을 탐지합니다.</p>
  <ol>
    <li>현재 시점의 측정값과 <strong>직전 {window}개</strong> 데이터의 평균·표준편차를 비교합니다.</li>
    <li>z = (현재값 − 롤링 평균) ÷ 롤링 표준편차 를 계산합니다.</li>
    <li><strong>|z| &gt; {threshold}</strong> 이면 이상으로 판정합니다.</li>
    <li>모든 이상의 |z-score|가 큰 순서대로 상위 {top_n}건을 리포트에 표시합니다.</li>
  </ol>
  <p class="meta">※ 표준편차가 0인 구간은 z-score를 0으로 처리합니다. 결측값은 탐지에서 제외됩니다.</p>
</div>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="제조 센서 CSV를 분석하고 HTML 리포트를 생성합니다."
    )
    parser.add_argument("--input", "-i", required=True, help="입력 CSV 파일 경로")
    parser.add_argument("--output", "-o", required=True, help="출력 HTML 파일 경로")
    parser.add_argument(
        "--window", type=int, default=60,
        help="롤링 윈도우 크기 (기본값: 60)",
    )
    parser.add_argument(
        "--threshold", type=float, default=3.0,
        help="이상 판정 z-score 임계값 (기본값: 3.0)",
    )
    parser.add_argument(
        "--top-n", type=int, default=10,
        help="리포트에 표시할 상위 이상 건수 (기본값: 10)",
    )
    args = parser.parse_args()

    df, ts_col, sensor_cols = load_data(args.input)
    print(f"데이터 로드: {len(df):,}행, 센서 {len(sensor_cols)}개 ({', '.join(sensor_cols)})")

    # 통계
    stats = compute_stats(df, sensor_cols)

    # 이상 탐지
    all_anomalies = []
    anomalies_by_col: dict[str, pd.DataFrame] = {}
    for col in sensor_cols:
        col_anom = detect_anomalies(df, ts_col, col, args.window, args.threshold)
        anomalies_by_col[col] = col_anom
        if not col_anom.empty:
            all_anomalies.append(col_anom)

    if all_anomalies:
        combined = pd.concat(all_anomalies, ignore_index=True)
        combined["abs_z"] = combined["z_score"].abs()
        combined = combined.sort_values("abs_z", ascending=False).drop(columns="abs_z")
    else:
        combined = pd.DataFrame(columns=["timestamp", "sensor", "value", "z_score"])
    total_anomalies = len(combined)
    top_anomalies = combined.head(args.top_n).copy()
    print(f"이상 탐지: {total_anomalies:,}건")

    # 차트
    print("차트 생성 중...")
    ts_image_b64 = plot_timeseries(df, ts_col, sensor_cols, anomalies_by_col)
    hist_image_b64 = plot_histograms(df, sensor_cols)

    # 리포트 렌더링
    time_range = (
        f"{df[ts_col].min()} ~ {df[ts_col].max()}"
        if df[ts_col].notna().any()
        else "알 수 없음"
    )
    html_report = build_html(
        input_path=args.input,
        stats=stats,
        top_anomalies=top_anomalies,
        total_anomalies=total_anomalies,
        ts_image_b64=ts_image_b64,
        hist_image_b64=hist_image_b64,
        row_count=len(df),
        time_range=time_range,
        window=args.window,
        threshold=args.threshold,
        top_n=args.top_n,
    )
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html_report)
    print(f"리포트 생성 완료: {args.output}")


if __name__ == "__main__":
    main()
