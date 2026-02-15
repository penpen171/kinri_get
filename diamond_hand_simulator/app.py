import streamlit as st
import pandas as pd
import calendar
from datetime import datetime
from core.logic import judge_all, calculate_statistics, DEFAULT_THRESHOLD_MIN, DEFAULT_JUDGMENT_HOURS
from core.liquidation import create_liquidation_model
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent

WEEKDAY_ORDER = ['月', '火', '水', '木', '金', '土', '日']
WEEKDAY_MAP = dict(enumerate(WEEKDAY_ORDER))

COLUMN_LABELS = {
    'date': '日付',
    'weekday_jp': '曜日',
    'symbol': 'シンボル',
    'move_vs_entry': '値幅（建値差）',
    'reach_time': '到達時間',
    'entry': '建値',
    'target_price': '価格',
    'skip_minutes': 'skip_minutes',
    'used_tier_index': 'used_tier_index',
    'used_mm_rate': 'used_mm_rate',
    'detail': '詳細',
    'is_loss_cut': 'ロスカ有無',
}

PRESET_COLUMNS = {
    '一覧': ['date', 'symbol', 'move_vs_entry', 'is_loss_cut', 'detail'],
    '分析': ['date', 'symbol', 'move_vs_entry', 'reach_time', 'skip_minutes', 'weekday_jp', 'detail'],
    '詳細': ['date', 'symbol', 'move_vs_entry', 'reach_time', 'target_price', 'used_tier_index', 'used_mm_rate', 'skip_minutes', 'detail'],
}

st.set_page_config(page_title="ゴールド戦略シミュレータ", page_icon="💎", layout="wide")
st.title("💎 ゴールド戦略シミュレータ")
st.markdown("レバレッジ500倍×閉場前ポジション戦略の分析ツール")

# サイドバー：パラメータ設定
st.sidebar.header("⚙️ 設定")

leverage = st.sidebar.number_input(
    "レバレッジ倍率",
    min_value=1,
    max_value=1000,
    value=500,
    step=10,
    help="ポジションのレバレッジ倍率"
)

position_margin = st.sidebar.number_input(
    "ポジション証拠金（USD）",
    min_value=1.0,
    max_value=10000.0,
    value=100.0,
    step=10.0,
    help="ポジションを持つために必要な証拠金"
)

additional_margin = st.sidebar.number_input(
    "追加証拠金（USD）",
    min_value=0.0,
    max_value=10000.0,
    value=0.0,
    step=10.0,
    help="ロスカット回避のための追加証拠金"
)

st.sidebar.markdown("---")
st.sidebar.markdown("### 📊 取引所設定")
exchange = st.sidebar.selectbox("取引所", ["BingX"])

# 判定期間の選択
st.sidebar.markdown("---")
st.sidebar.markdown("### ⏰ 判定設定")
st.sidebar.info(f"開場後 **{DEFAULT_THRESHOLD_MIN}分** で判定（固定）")

# 判定期間のプルダウン
judgment_options = {
    "次の閉場まで": None,
    "22時間後まで": 22,
    "21時間後まで": 21,
    "20時間後まで": 20,
    "19時間後まで": 19,
    "18時間後まで": 18,
    "17時間後まで": 17,
    "16時間後まで": 16,
    "15時間後まで": 15,
    "14時間後まで": 14,
    "13時間後まで": 13,
    "12時間後まで": 12,
    "11時間後まで": 11,
    "10時間後まで": 10,
    "9時間後まで": 9,
    "8時間後まで": 8,
    "7時間後まで": 7,
    "6時間後まで": 6,
    "5時間後まで": 5,
    "4時間後まで": 4,
    "3時間後まで": 3,
    "2時間後まで": 2,
    "1時間後まで": 1,
}

judgment_period_label = st.sidebar.selectbox(
    "判定期間",
    options=list(judgment_options.keys()),
    index=0,  # デフォルトは「次の閉場まで」
    help="ポジション保有期間（この時間後の結果で判定）"
)

judgment_hours = judgment_options[judgment_period_label]

# データ読み込み
@st.cache_data
def load_data(threshold_min=2, judgment_hours=None):
    """
    指定された判定条件のファイルを読み込む（B案: ファイル分割版）
    """
    # ファイル名を生成
    if judgment_hours is None:
        j_label = 'close'
    else:
        j_label = int(judgment_hours)

    filename = f"daily_aggregates_t{threshold_min}_j{j_label}.parquet"
    path = APP_DIR / "data" / "derived" / filename

    if not path.exists():
        raise FileNotFoundError(
            f"データファイルが見つかりません: {filename}\n"
            f"build_daily_aggregates.py を実行してください。"
        )

    df = pd.read_parquet(path)
    
    st.sidebar.info(f"Aggregates file: {path}")
    
    return df

@st.cache_data
def load_1min_data():
    """1分足データを読み込み"""
    path = APP_DIR / "data" / "raw" / "gold_1min_20251101_.csv"
    df = pd.read_csv(path, parse_dates=['日時'])
    df = df.rename(columns={
        '日時': 'timestamp',
        '始値': 'open',
        '高値': 'high',
        '安値': 'low',
        '終値': 'close'
    })
    df.set_index('timestamp', inplace=True)
    return df

def _exchange_config_signature():
    """モデル設定の変更をキャッシュキーに反映するためのシグネチャ。"""
    config_path = APP_DIR / "config" / "exchanges" / "bingx.yaml"
    return config_path.read_text(encoding='utf-8')


@st.cache_resource
def load_model(config_signature):
    _ = config_signature
    return create_liquidation_model()


def derive_weekday_series(date_series):
    date_parsed = pd.to_datetime(date_series, errors='coerce')
    return date_parsed.dt.dayofweek.map(WEEKDAY_MAP)


def first_available(row, columns):
    for col in columns:
        val = row.get(col)
        if pd.notna(val):
            return val
    return pd.NA


def build_detail_view_dataframe(results_df, source_df):
    base_df = results_df.copy()
    base_df['date'] = pd.to_datetime(base_df.get('date'), errors='coerce').dt.date

    source_meta = source_df.copy()
    source_meta['date'] = pd.to_datetime(source_meta.get('date'), errors='coerce').dt.date

    optional_cols = [
        'date', 'skip_minutes', 'used_tier_index', 'used_mm_rate',
        'used_notional', 'used_tier_min_notional', 'used_tier_max_notional',
    ]
    available_meta_cols = [c for c in optional_cols if c in source_meta.columns]
    if available_meta_cols:
        source_meta = source_meta[available_meta_cols].drop_duplicates(subset=['date'])

    merged_df = base_df.merge(source_meta, on='date', how='left', suffixes=('', '_src'))

    merged_df['weekday_jp'] = derive_weekday_series(merged_df.get('date'))
    merged_df['is_loss_cut'] = merged_df.get('symbol', '').astype(str).str.contains('❌|🔵')

    merged_df['move_vs_entry'] = merged_df.apply(
        lambda row: first_available(row, ['phase2_high', 'phase2_low']) - row.get('entry')
        if pd.notna(first_available(row, ['phase2_high', 'phase2_low'])) and pd.notna(row.get('entry')) else pd.NA,
        axis=1,
    )
    merged_df['reach_time'] = merged_df.apply(
        lambda row: first_available(row, ['phase2_high_time', 'phase2_low_time']),
        axis=1,
    )
    merged_df['target_price'] = merged_df.apply(
        lambda row: first_available(row, ['phase2_high', 'phase2_low']),
        axis=1,
    )
    merged_df['skip_minutes'] = pd.to_numeric(merged_df.get('skip_minutes'), errors='coerce').fillna(0)

    return merged_df


def format_display_dataframe(df, selected_cols):
    display_df = pd.DataFrame()
    for col in selected_cols:
        if col not in df.columns:
            continue
        label = COLUMN_LABELS.get(col, col)
        if col == 'date':
            display_df[label] = pd.to_datetime(df[col], errors='coerce').dt.strftime('%Y-%m-%d').fillna('-')
        elif col == 'move_vs_entry':
            display_df[label] = df[col].apply(lambda v: '-' if pd.isna(v) else f"{v:+.2f}")
        elif col in ('entry', 'target_price'):
            display_df[label] = df[col].apply(lambda v: '-' if pd.isna(v) else f"${v:,.2f}")
        elif col == 'reach_time':
            display_df[label] = pd.to_datetime(df[col], errors='coerce').dt.strftime('%H:%M').fillna('-')
        elif col == 'used_mm_rate':
            display_df[label] = df[col].apply(lambda v: '-' if pd.isna(v) else f"{v * 100:.3f}%")
        elif col == 'is_loss_cut':
            display_df[label] = df[col].apply(lambda v: 'あり' if bool(v) else 'なし')
        elif col == 'weekday_jp':
            display_df[label] = df[col].fillna('-')
        elif col == 'detail':
            display_df[label] = df.apply(
                lambda row: f"{row.get('detail', '')} | open bar skipped: +{int(row.get('skip_minutes', 0))}min"
                if row.get('skip_minutes', 0) > 0 and 'open bar skipped' not in str(row.get('detail', ''))
                else row.get('detail', ''),
                axis=1,
            )
        else:
            display_df[label] = df[col]
    return display_df

try:
    # 選択された判定期間に応じたファイルを読み込む
    df = load_data(
        threshold_min=DEFAULT_THRESHOLD_MIN,
        judgment_hours=judgment_hours
    )

    st.info(f"📊 読み込んだデータ: {len(df)} 件（判定期間: {judgment_period_label}）")

    df_1min = load_1min_data()
    model = load_model(_exchange_config_signature())

    # TierMM の場合、mm_rate を確実に計算させて表示する
    info = model.get_info() if hasattr(model, "get_info") else {}
    if info.get("model") == "TierMM":
        # 目安表示の計算を1回走らせて current_mm_rate を更新させる
        _ = model.calc_liq_distance_pct(
            leverage=leverage,
            position_margin=position_margin,
            additional_margin=additional_margin,
            entry_price=5000,  # 目安用の基準価格（既存の基準変数があるならそれに置換）
        )
        mm_rate = getattr(model, "current_mm_rate", None)
        notional = getattr(model, "current_notional", None)
        if mm_rate is not None:
            st.sidebar.caption(f"TierMM: mm_rate={mm_rate*100:.3f}%  notional≈{notional:,.0f}")


    # ロスカット目安を表示
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📉 ロスカット目安")
    entry_sample = 5000.0

    # 追加証拠金なしの場合
    liq_price_base = model.calc_liq_price_long(entry_sample, leverage, position_margin, 0)
    liq_distance_pct_base = model.calc_liq_distance_pct(leverage, position_margin, 0)

    # 追加証拠金ありの場合
    liq_price_with_add = model.calc_liq_price_long(entry_sample, leverage, position_margin, additional_margin)
    liq_distance_pct_with_add = model.calc_liq_distance_pct(leverage, position_margin, additional_margin)

    col_liq1, col_liq2 = st.sidebar.columns(2)
    with col_liq1:
        st.metric(
            "基本",
            f"{liq_distance_pct_base * 100:.3f}%",
            help="追加証拠金なしの場合"
        )
        st.caption(f"${entry_sample:,.0f} → ${liq_price_base:,.0f}")

    with col_liq2:
        st.metric(
            "追加後",
            f"{liq_distance_pct_with_add * 100:.3f}%",
            delta=f"{(liq_distance_pct_with_add - liq_distance_pct_base) * 100:.3f}%",
            help="追加証拠金込みの場合"
        )
        st.caption(f"${entry_sample:,.0f} → ${liq_price_with_add:,.0f}")

    # 判定実行
    with st.spinner(f'判定中...（{len(df)}件のデータ）'):
        results = judge_all(
            df,
            model,
            leverage,
            position_margin,
            additional_margin,
            threshold_min=DEFAULT_THRESHOLD_MIN,
            judgment_hours=judgment_hours,
            df_1min=df_1min
        )

    stats = calculate_statistics(results)

    # 統計情報を表示
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("総日数", stats['total'])
    with col2:
        st.metric("💎 完全勝利", f"{stats['win_count']} ({stats['win_rate']:.1f}%)")
    with col3:
        st.metric("✅ 回復", stats['recovery_count'])
    with col4:
        st.metric("🟠 マイナス継続", stats['warning_count'])
    with col5:
        st.metric("❌ ロスカット", stats['loss_count'])

    # タブで表示切替
    tab1, tab2, tab3 = st.tabs(["📅 カレンダー表示", "📊 詳細リスト", "📈 統計"])

    with tab1:
        st.subheader("月次カレンダー")

        if len(results) == 0:
            st.warning(f"データがありません。先に build_daily_aggregates.py を実行してください。")
        else:
            results_df = pd.DataFrame(results)
            results_df['year_month'] = results_df['date'].apply(lambda x: x.strftime('%Y-%m'))

            for ym in sorted(results_df['year_month'].unique()):
                year, month = map(int, ym.split('-'))
                st.markdown(f"### {year}年{month}月")

                month_data = results_df[results_df['year_month'] == ym]

                # 月曜始まりのカレンダーを作成
                cal = calendar.monthcalendar(year, month)
                weekdays = ['月', '火', '水', '木', '金', '土', '日']

                table_html = '<table style="width:100%; border-collapse: collapse;"><tr>'
                for wd in weekdays:
                    table_html += f'<th style="border: 1px solid #ddd; padding: 8px; text-align: center; background-color: #f2f2f2;">{wd}</th>'
                table_html += '</tr>'

                for week in cal:
                    table_html += '<tr>'
                    for day in week:
                        if day == 0:
                            table_html += '<td style="border: 1px solid #ddd; padding: 8px;"></td>'
                        else:
                            date_obj = datetime(year, month, day).date()
                            day_result = month_data[month_data['date'] == date_obj]

                            if len(day_result) > 0:
                                symbol = day_result.iloc[0]['symbol']
                                detail = day_result.iloc[0]['detail']
                                info = day_result.iloc[0]['info']

                                # ❌の場合はロスカット時間を表示
                                if '❌' in symbol and info and 'liq_time' in info:
                                    liq_time = info['liq_time']
                                    if pd.notna(liq_time):
                                        time_str = pd.to_datetime(liq_time).strftime('%H:%M')
                                        display_text = f'{symbol}<br><small>{time_str}</small>'
                                    else:
                                        display_text = symbol
                                # ✅, 🟠の場合は建値割れ時刻を表示
                                elif ('✅' in symbol or '🟠' in symbol or '💎' in symbol) and info and 'breach_time' in info:
                                    breach_time = info['breach_time']
                                    if pd.notna(breach_time):
                                        time_str = pd.to_datetime(breach_time).strftime('%H:%M')
                                        display_text = f'{symbol}<br><small>{time_str}</small>'
                                    else:
                                        display_text = symbol
                                else:
                                    display_text = symbol

                                table_html += f'<td style="border: 1px solid #ddd; padding: 8px; text-align: center;" title="{detail}">'
                                table_html += f'<div style="font-weight: bold;">{day}</div><div style="font-size: 18px;">{display_text}</div></td>'
                            else:
                                # データがない日は「休場」と表示（グレー）
                                table_html += f'<td style="border: 1px solid #ddd; padding: 8px; text-align: center; color: #999;">'
                                table_html += f'<div style="font-weight: bold;">{day}</div><div style="font-size: 12px;">休場</div></td>'

                    table_html += '</tr>'

                table_html += '</table>'
                st.markdown(table_html, unsafe_allow_html=True)
                st.markdown("---")

    with tab2:
        st.subheader("詳細リスト")

        if len(results) == 0:
            st.warning(f"データがありません。")
        else:
            detail_df = build_detail_view_dataframe(pd.DataFrame(results), df)
            total_count = len(detail_df)

            preset = st.selectbox('列プリセット', options=list(PRESET_COLUMNS.keys()), index=0, key='detail_preset')
            preset_cols = [c for c in PRESET_COLUMNS[preset] if c in detail_df.columns]

            if 'visible_cols_draft' not in st.session_state:
                st.session_state.visible_cols_draft = preset_cols
            if 'visible_cols_committed' not in st.session_state:
                st.session_state.visible_cols_committed = preset_cols
            if 'detail_table_nonce' not in st.session_state:
                st.session_state.detail_table_nonce = 0
            if 'detail_table_last_key' not in st.session_state:
                st.session_state.detail_table_last_key = None

            if st.session_state.get('last_preset') != preset:
                st.session_state.visible_cols_draft = preset_cols
                st.session_state.visible_cols_committed = preset_cols
                st.session_state.last_preset = preset
                prev_table_key = st.session_state.detail_table_last_key
                st.session_state.detail_table_nonce += 1
                if prev_table_key is not None:
                    st.session_state.pop(prev_table_key, None)

            col_candidates = [c for c in COLUMN_LABELS.keys() if c in detail_df.columns]
            draft_cols = [c for c in st.session_state.visible_cols_draft if c in col_candidates]
            committed_cols = [c for c in st.session_state.visible_cols_committed if c in col_candidates]
            if draft_cols != st.session_state.visible_cols_draft:
                st.session_state.visible_cols_draft = draft_cols
            if committed_cols != st.session_state.visible_cols_committed:
                st.session_state.visible_cols_committed = committed_cols

            st.multiselect(
                '表示列トグル',
                options=col_candidates,
                format_func=lambda c: COLUMN_LABELS.get(c, c),
                key='visible_cols_draft',
            )
            if st.button('列変更を適用', key='apply_visible_cols'):
                next_committed = [c for c in st.session_state.visible_cols_draft if c in col_candidates]
                if next_committed != st.session_state.visible_cols_committed:
                    prev_table_key = st.session_state.detail_table_last_key
                    st.session_state.visible_cols_committed = next_committed
                    st.session_state.detail_table_nonce += 1
                    if prev_table_key is not None:
                        st.session_state.pop(prev_table_key, None)
                    st.rerun()
            visible_cols = [c for c in st.session_state.visible_cols_committed if c in col_candidates]

            st.markdown('#### フィルタ')
            filter_col1, filter_col2, filter_col3 = st.columns(3)

            symbols = sorted(detail_df.get('symbol', pd.Series(dtype='object')).dropna().unique().tolist())
            selected_symbols = filter_col1.multiselect('シンボル', options=symbols, default=symbols)

            weekday_series = detail_df.get('weekday_jp', pd.Series(dtype='object')).dropna()
            available_weekdays = [wd for wd in WEEKDAY_ORDER if wd in weekday_series.unique().tolist()]
            selected_weekdays = filter_col2.multiselect('曜日', options=WEEKDAY_ORDER, default=available_weekdays)

            skip_only = filter_col3.checkbox('skip_minutes > 0 のみ')
            loss_only = filter_col3.checkbox('ロスカット発生日のみ')

            # --- used_tier_index の値を安全に取り出す（Series前提にする） ---
            if isinstance(detail_df, pd.DataFrame) and ("used_tier_index" in detail_df.columns):
                tier_series = pd.to_numeric(detail_df["used_tier_index"], errors="coerce")
            else:
                tier_series = pd.Series([], dtype="float64")

            tier_values = tier_series.dropna()

            tier_range = None
            if not tier_values.empty:
                tier_min = int(tier_values.min())
                tier_max = int(tier_values.max())
                tier_range = st.slider('used_tier_index 範囲', min_value=tier_min, max_value=tier_max, value=(tier_min, tier_max))

            filtered_df = detail_df.copy()
            if selected_symbols:
                filtered_df = filtered_df[filtered_df.get('symbol').isin(selected_symbols)]
            if selected_weekdays:
                filtered_df = filtered_df[filtered_df.get('weekday_jp').isin(selected_weekdays)]
            if skip_only:
                filtered_df = filtered_df[pd.to_numeric(filtered_df.get('skip_minutes'), errors='coerce').fillna(0) > 0]
            if loss_only:
                filtered_df = filtered_df[filtered_df.get('is_loss_cut', False)]
            if tier_range is not None:
                tier_col = pd.to_numeric(filtered_df.get('used_tier_index'), errors='coerce')
                filtered_df = filtered_df[tier_col.between(tier_range[0], tier_range[1], inclusive='both')]

            sort_options = [c for c in col_candidates if c != 'detail']
            sort_key = st.selectbox('ソート列', options=sort_options, format_func=lambda c: COLUMN_LABELS.get(c, c), index=0)
            sort_asc = st.checkbox('昇順', value=False)
            filtered_df = filtered_df.sort_values(by=sort_key, ascending=sort_asc, na_position='last')

            condition_parts = [
                f"シンボル={','.join(selected_symbols) if selected_symbols else 'なし'}",
                f"曜日={','.join(selected_weekdays) if selected_weekdays else 'なし'}",
            ]
            if skip_only:
                condition_parts.append('skipあり')
            if loss_only:
                condition_parts.append('ロスカットのみ')
            if tier_range is not None:
                condition_parts.append(f"ティア={tier_range[0]}-{tier_range[1]}")
            st.caption(f"表示条件：{' ｜ '.join(condition_parts)}")
            st.caption(f"表示件数：{len(filtered_df)} / {total_count}")

            display_df = format_display_dataframe(filtered_df, visible_cols)
            move_col_label = COLUMN_LABELS['move_vs_entry']

            styled = display_df.style
            if move_col_label in display_df.columns:
                styled = styled.map(
                    lambda value: 'color: #1976D2' if str(value).startswith('+') else 'color: #D32F2F' if str(value).startswith('-') else '',
                    subset=[move_col_label],
                )

                numeric_move = pd.to_numeric(filtered_df.get('move_vs_entry'), errors='coerce').abs()
                if numeric_move.notna().any():
                    threshold = numeric_move.quantile(0.95)
                    outlier_mask = numeric_move >= threshold
                    style_rows = pd.DataFrame('', index=display_df.index, columns=display_df.columns)
                    style_rows.loc[outlier_mask.values, :] = 'background-color: #FFF3CD'
                    styled = styled.apply(lambda _: style_rows, axis=None)

            detail_table_key = f"detail_table_{st.session_state.detail_table_nonce}"
            st.session_state.detail_table_last_key = detail_table_key
            st.dataframe(
                styled,
                use_container_width=True,
                height=600,
                key=detail_table_key,
            )

    with tab3:
        st.subheader("統計情報")

        st.markdown("#### シンボル別集計")
        symbol_df = pd.DataFrame([
            [k, v, f"{v/stats['total']*100:.1f}%"]
            for k, v in sorted(stats['symbol_counts'].items(), key=lambda x: -x[1])
        ], columns=['シンボル', '回数', '割合'])
        st.dataframe(symbol_df, use_container_width=True)

        st.markdown("#### パラメータ")
        param_df = pd.DataFrame({
            "項目": ["レバレッジ", "ポジション証拠金", "追加証拠金", "合計証拠金", "閾値（分）", "判定期間"],
            "値": [
                f"{leverage}x",
                f"${position_margin:.0f}",
                f"${additional_margin:.0f}",
                f"${position_margin + additional_margin:.0f}",
                f"{DEFAULT_THRESHOLD_MIN}分",
                judgment_period_label,
            ],
        })
        st.dataframe(param_df, use_container_width=True)

        # ---- ロスカットモデル情報（DataFrameの外で表示）----
        if hasattr(model, "adjustment_factor"):
            st.write(f"Adjustment Factor: {model.adjustment_factor * 100:.4f}%")
        else:
            mm_rate = getattr(model, "current_mm_rate", None)
            notional = getattr(model, "current_notional", None)

            if mm_rate is not None:
                if notional is not None:
                    st.write(f"TierMMModel: notional={notional:,.0f}, mm_rate={mm_rate*100:.3f}%")
                else:
                    st.write(f"TierMMModel: mm_rate={mm_rate*100:.3f}%")
            else:
                st.write("TierMMModel: mm_rate not computed yet (run a calculation first)")



except FileNotFoundError as e:
    st.error(f"❌ {e}")
    st.info("💡 build_daily_aggregates.py を実行してデータを生成してください。")

except Exception as e:
    # エラー詳細を表示
    st.error(f"エラーが発生しました: {e}")
    import traceback
    st.code(traceback.format_exc())
