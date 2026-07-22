# Sleep Analyzer

Compare **SleepScope** phone-sensor recordings with **Fitbit** as binary **Sleep vs Awake** timelines.

## Pipeline

```mermaid
flowchart TD
  subgraph inputs [Inputs]
    Manifest["Night manifest<br/>pairs reference + comparison paths"]
    SensorCSV["SleepScope sensor CSV<br/>accel / gyro / dB / Event"]
    FitbitJSON["Fitbit sleep JSON<br/>levels.data"]

    Manifest -->|"reference.path"| SensorCSV
    Manifest -->|"comparisons[].path"| FitbitJSON
  end

  subgraph phoneInfer [SleepScope inference]
    ParseCSV["Parse CSV + metadata"]
    Bin30s["Bin samples into 30s epochs"]
    Activity["Gravity-normalized activity<br/>plus gyro magnitude"]
    Webster["Webster weighted movement score"]
    Audio["Rolling-median dB baseline<br/>flag audio spikes"]
    Stage3["Stage each bin<br/>Awake / Restless / QuietSleep"]
    Collapse["Collapse to binary<br/>QuietSleep + Restless → Sleep"]
  end

  subgraph fitbitNorm [Fitbit normalizer]
    ParseFitbit["Parse main sleep log"]
    Resample["Resample stage intervals<br/>onto 30s grid"]
    FitbitBinary["Map stages to binary<br/>deep/light/REM → Sleep<br/>wake → Awake"]
  end

  subgraph outputs [Outputs]
    TimelineJSON["Two timeline JSONs<br/>SleepScope + Fitbit"]
    Hypnogram["One comparison hypnogram<br/>Awake / Sleep lanes"]
  end

  SensorCSV --> ParseCSV
  ParseCSV --> Bin30s
  Bin30s --> Activity
  Activity --> Webster
  Bin30s --> Audio
  Webster --> Stage3
  Audio --> Stage3
  Stage3 --> Collapse

  FitbitJSON --> ParseFitbit
  ParseFitbit --> Resample
  Resample --> FitbitBinary

  Collapse --> TimelineJSON
  FitbitBinary --> TimelineJSON
  Collapse --> Hypnogram
  FitbitBinary --> Hypnogram
```

## Outputs

1. **Two timeline JSON files** — SleepScope and Fitbit, each a sequence of 30s `{timestamp, state}` where `state` is `Sleep` or `Awake`
2. **One hypnogram PNG** — condensed two-lane chart (Awake / Sleep) with SleepScope and Fitbit in different colors

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Night manifest

```json
{
  "id": "2026-07-12-fitbit",
  "date": "2026-07-12",
  "reference": {
    "provider": "sleepscope",
    "path": "../raw/2026-07-12/sensor.csv"
  },
  "comparisons": [
    {
      "provider": "fitbit",
      "path": "../raw/2026-07-12/fitbit_sleep.json"
    }
  ]
}
```

## CLI

```bash
python compare.py data/nights/example-fitbit.json
```

Timelines and hypnograms write to `results/timelines` and `results/plots` by default. Override with `--out` / `--plots` if needed.
## Tests

```bash
python -m pytest -q
```
