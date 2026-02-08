# modules/__init__.py
# このファイルは空でOK（Pythonパッケージとして認識させるため）

'''

金利ーマン/
├── main.py                    # エントリーポイント（150行）
│   ├── CSS定義
│   ├── サイドバーUI
│   └── モード選択・表示
│
├── modules/
│   ├── __init__.py
│   ├── data_api.py           # API取得（200行）
│   │   ├── fetch_mexc_data()
│   │   ├── fetch_bitget_data()
│   │   ├── fetch_bingx_data()
│   │   └── fetch_variational_data()
│   │
│   ├── mode_simultaneous.py  # 同時刻版（150行）
│   │   └── run_simultaneous_engine()
│   │   └── render_simultaneous_table()
│   │
│   ├── mode_time_diff.py     # 時間差版（150行）
│   │   └── run_hedge_engine()
│   │   └── render_hedge_table()
│   │
│   ├── mode_single.py        # 単体金利版（150行）
│   │   └── run_single_exchange_engine()
│   │   └── render_single_table()
│   │
│   ├── user_settings.py      # ユーザー設定（100行）← フェーズ2で追加
│   │   ├── load_user_settings()
│   │   └── save_user_settings()
│   │
│   └── utils.py              # 共通関数（150行）
│       ├── interval_to_seconds()
│       ├── normalize_time()
│       ├── calculate_risk()
│       └── fmt_rem()
│
├── requirements.txt
└── README.md

'''