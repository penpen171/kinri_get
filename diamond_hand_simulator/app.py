import streamlit as st
import pandas as pd
import calendar
from datetime import datetime
from core.logic import judge_all, calculate_statistics, DEFAULT_THRESHOLD_MIN, DEFAULT_JUDGMENT_HOURS
from core.liquidation import create_liquidation_model
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent


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
    index=0,
    help="ポジション保有期間（この時間後の結果で判定）"
)


judgment_hours = judgment_options[judgment_period_label]


# データ読み込み
@st.cache_data
def load_data(threshold_min=2, judgment_hours=None):
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
    config_path = APP_DIR / "config" / "exchanges" / "bingx.yaml"
    return config_path.read_text(encoding='utf-8')


@st.cache_resource
def load_model(config_signature):
    _ = config_signature
    return create_liquidation_model()


try:
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
        _ = model.calc_liq_distance_pct(
            leverage=leverage,
            position_margin=position_margin,
            additional_margin=additional_margin,
            entry_price=5000,
        )
        mm_rate = getattr(model, "current_mm_rate", None)
        notional = getattr(model, "current_notional", None)
        if mm_rate is not None:
            st.sidebar.caption(f"TierMM: mm_rate={mm_rate*100:.3f}%  notional≈{notional:,.0f}")

    # ロスカット目安を表示
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📉 ロスカット目安")
    entry_sample = 5000.0

    liq_price_base = model.calc_liq_price_long(entry_sample, leverage, position_margin, 0)
    liq_distance_pct_base = model.calc_liq_distance_pct(leverage, position_margin, 0)

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

                                if '❌' in symbol and info and 'liq_time' in info:
                                    liq_time = info['liq_time']
                                    if pd.notna(liq_time):
                                        time_str = pd.to_datetime(liq_time).strftime('%H:%M')
                                        display_text = f'{symbol}<br><small>{time_str}</small>'
                                    else:
                                        display_text = symbol
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
            detail_df = pd.DataFrame(results)

            weekday_map = {0: '月', 1: '火', 2: '水', 3: '木', 4: '金', 5: '土', 6: '日'}
            weekday_order = ['月', '火', '水', '木', '金', '土', '日']

            def _series(name, default=None):
                if default is None:
                    default = pd.Series([pd.NA] * len(detail_df), index=detail_df.index)
                return detail_df.get(name, default)

            raw_df = pd.DataFrame({
                '日付': pd.to_datetime(_series('date'), errors='coerce'),
                'シンボル': _series('symbol', pd.Series(['-'] * len(detail_df), index=detail_df.index)).fillna('-').astype(str),
                '建値_raw': pd.to_numeric(_series('entry'), errors='coerce'),
                '最高値時刻_raw': pd.to_datetime(_series('phase2_high_time'), errors='coerce'),
                '最高値価格_raw': pd.to_numeric(_series('phase2_high'), errors='coerce'),
                '最底値時刻_raw': pd.to_datetime(_series('phase2_low_time'), errors='coerce'),
                '最底値価格_raw': pd.to_numeric(_series('phase2_low'), errors='coerce'),
                'skip_minutes_raw': pd.to_numeric(_series('skip_minutes', pd.Series([0] * len(detail_df), index=detail_df.index)), errors='coerce').fillna(0),
                'used_tier_index_raw': pd.to_numeric(_series('used_tier_index'), errors='coerce'),
                'detail_raw': _series('detail', pd.Series([''] * len(detail_df), index=detail_df.index)).fillna('').astype(str),
                'liq_time_raw': pd.to_datetime(
                    detail_df.get('info', pd.Series([{}] * len(detail_df), index=detail_df.index))
                    .apply(lambda x: x.get('liq_time') if isinstance(x, dict) else None),
                    errors='coerce'
                ),
                'breach_time_raw': pd.to_datetime(
                    detail_df.get('info', pd.Series([{}] * len(detail_df), index=detail_df.index))
                    .apply(lambda x: x.get('breach_time') if isinstance(x, dict) else None),
                    errors='coerce'
                ),
            })

            raw_df['曜日'] = raw_df['日付'].dt.weekday.map(weekday_map)
            liquidated_flag = _series('liquidated', pd.Series([False] * len(detail_df), index=detail_df.index)).fillna(False).astype(bool)
            raw_df['ロスカット'] = liquidated_flag | raw_df['シンボル'].str.contains('❌', na=False)
            raw_df['最高値建値差_raw'] = raw_df['最高値価格_raw'] - raw_df['建値_raw']
            raw_df['最底値建値差_raw'] = raw_df['最底値価格_raw'] - raw_df['建値_raw']

            # --- フィルタ ---
            st.markdown("#### フィルタ")
            filter_col1, filter_col2, filter_col3 = st.columns(3)

            symbol_options = sorted(raw_df['シンボル'].dropna().unique().tolist())
            with filter_col1:
                selected_symbols = st.multiselect(
                    "シンボル",
                    options=symbol_options,
                    default=symbol_options,
                    key="detail_filter_symbols",
                )

            weekday_options = [wd for wd in weekday_order if wd in raw_df['曜日'].dropna().unique().tolist()]
            with filter_col2:
                selected_weekdays = st.multiselect(
                    "曜日",
                    options=weekday_options,
                    default=weekday_options,
                    key="detail_filter_weekdays",
                )

            tier_series = raw_df['used_tier_index_raw'].dropna()
            if len(tier_series) > 0:
                tier_min, tier_max = int(tier_series.min()), int(tier_series.max())
            else:
                tier_min, tier_max = 0, 0

            with filter_col3:
                if tier_min >= tier_max:
                    st.caption(f"Tier: {tier_min}（1種類のみ）")
                    tier_range = (tier_min, tier_max)
                else:
                    tier_range = st.slider(
                        "used_tier_index 範囲",
                        min_value=tier_min,
                        max_value=tier_max,
                        value=(tier_min, tier_max),
                        key="detail_filter_tier_range",
                    )

            only_skip = st.checkbox("skip_minutes > 0 のみ", key="detail_filter_only_skip")

            filtered_df = raw_df.copy()
            if selected_symbols:
                filtered_df = filtered_df[filtered_df['シンボル'].isin(selected_symbols)]
            else:
                filtered_df = filtered_df.iloc[0:0]

            if selected_weekdays:
                filtered_df = filtered_df[filtered_df['曜日'].isin(selected_weekdays)]
            else:
                filtered_df = filtered_df.iloc[0:0]

            filtered_df = filtered_df[
                filtered_df['used_tier_index_raw'].fillna(tier_range[0]).between(tier_range[0], tier_range[1])
            ]

            if only_skip:
                filtered_df = filtered_df[filtered_df['skip_minutes_raw'] > 0]

            # --- 表示整形 ---
            def format_price(value):
                if pd.isna(value):
                    return "-"
                return f"${value:,.2f}"

            def format_time(ts):
                if pd.isna(ts):
                    return "-"
                return pd.to_datetime(ts).strftime('%H:%M')

            def format_diff(value):
                if pd.isna(value):
                    return "-"
                sign = '+' if value >= 0 else '-'
                return f"{sign}{abs(value):,.2f}"

            def append_skip_detail(detail, skip_minutes):
                if pd.isna(skip_minutes) or skip_minutes <= 0:
                    return detail
                append_text = f"open bar skipped: +{int(skip_minutes)}min"
                base_detail = detail if isinstance(detail, str) else ""
                if append_text in base_detail:
                    return base_detail
                if base_detail:
                    return f"{base_detail} | {append_text}"
                return append_text

            q_up = filtered_df['最高値建値差_raw'].abs().quantile(0.95) if len(filtered_df) else pd.NA
            q_down = filtered_df['最底値建値差_raw'].abs().quantile(0.95) if len(filtered_df) else pd.NA
            filtered_df['_is_outlier'] = (
                filtered_df['最高値建値差_raw'].abs().ge(q_up).fillna(False)
                | filtered_df['最底値建値差_raw'].abs().ge(q_down).fillna(False)
            ) if len(filtered_df) else False

            display_df = pd.DataFrame({
                '日付': filtered_df['日付'].dt.strftime('%Y-%m-%d').fillna('-'),
                '曜日': filtered_df['曜日'].fillna('-'),
                'シンボル': filtered_df['シンボル'],
                '建値': filtered_df['建値_raw'].apply(format_price),
                '最高値時刻': filtered_df['最高値時刻_raw'].apply(format_time),
                '最高値価格': filtered_df['最高値価格_raw'].apply(format_price),
                '最高値建値差': filtered_df['最高値建値差_raw'].apply(format_diff),
                '最底値時刻': filtered_df['最底値時刻_raw'].apply(format_time),
                '最底値価格': filtered_df['最底値価格_raw'].apply(format_price),
                '最底値建値差': filtered_df['最底値建値差_raw'].apply(format_diff),
                'skip_minutes': filtered_df['skip_minutes_raw'].fillna(0).astype(int),
                'used_tier_index': filtered_df['used_tier_index_raw'].apply(lambda x: '-' if pd.isna(x) else int(x)),
                'ロスカット': filtered_df['ロスカット'].map({True: 'あり', False: '-'}),
                '詳細': [
                    append_skip_detail(d, s)
                    for d, s in zip(filtered_df['detail_raw'], filtered_df['skip_minutes_raw'])
                ],
            })

            # 列プリセット / 表示トグル
            all_display_columns = list(display_df.columns)
            preset_map = {
                '簡易': ['日付', '曜日', 'シンボル', '詳細'],
                '詳細': ['日付', '曜日', 'シンボル', '建値', '最高値時刻', '最高値価格', '最高値建値差', '最底値時刻', '最底値価格', '最底値建値差', '詳細'],
                '全表示': all_display_columns,
            }

            preset = st.radio(
                "列プリセット",
                options=list(preset_map.keys()),
                horizontal=True,
                key="detail_column_preset",
            )

            if "detail_table_nonce" not in st.session_state:
                st.session_state["detail_table_nonce"] = 0

            last_preset = st.session_state.get("detail_column_preset_last")
            if last_preset != preset:
                st.session_state.pop("visible_columns", None)
                st.session_state["detail_table_nonce"] += 1
                st.session_state["detail_column_preset_last"] = preset

            if "visible_columns" not in st.session_state:
                st.session_state["visible_columns"] = preset_map[preset]

            st.multiselect(
                "表示列トグル",
                options=all_display_columns,
                key="visible_columns",
                help="列を個別に ON/OFF できます。",
            )

            visible_columns = [c for c in st.session_state.get("visible_columns", []) if c in all_display_columns]
            if not visible_columns:
                st.warning("表示列が0件です。列トグルから1つ以上選択してください。")
            else:
                visible_df = display_df[visible_columns].copy()

                def color_move(val):
                    if isinstance(val, str):
                        if val.startswith('+'):
                            return 'color: #0066cc;'
                        if val.startswith('-'):
                            return 'color: #cc0000;'
                    return ''

                outlier_index = filtered_df.index[filtered_df['_is_outlier']].tolist()

                def highlight_row(row):
                    if row.name in outlier_index:
                        return ['background-color: #fff7d6;'] * len(row)
                    return [''] * len(row)

                styled_df = (
                    visible_df.style
                    .apply(highlight_row, axis=1)
                    .applymap(color_move, subset=[c for c in ['最高値建値差', '最底値建値差'] if c in visible_df.columns])
                )

                nonce_key = f"detail_table_{st.session_state['detail_table_nonce']}"
                st.dataframe(styled_df, use_container_width=True, height=600, key=nonce_key, column_order=visible_columns)

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

        # ---- ロスカットモデル情報 ----
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

        # ─── Phase4: 傾向統計 ────────────────────────────
        if len(results) > 0:
            st.markdown("---")

            s4 = pd.DataFrame(results)
            weekday_map4 = {0: '月', 1: '火', 2: '水', 3: '木', 4: '金', 5: '土', 6: '日'}
            s4['曜日'] = pd.to_datetime(s4['date']).dt.weekday.map(weekday_map4)

            # reference_open_time を df から結合（経過時間計算に使用）
            df_ref = df[['date', 'reference_open_time']].copy()
            df_ref['_date_str'] = df_ref['date'].astype(str)
            s4['_date_str'] = pd.to_datetime(s4['date']).dt.strftime('%Y-%m-%d')
            s4 = s4.merge(
                df_ref[['_date_str', 'reference_open_time']],
                on='_date_str', how='left'
            )
            s4['reference_open_time'] = pd.to_datetime(s4['reference_open_time'], errors='coerce')

            # 各イベント時刻を整備
            s4['phase2_high_time'] = pd.to_datetime(
                s4['phase2_high_time'] if 'phase2_high_time' in s4.columns else pd.NaT,
                errors='coerce'
            )
            s4['phase2_low_time'] = pd.to_datetime(
                s4['phase2_low_time'] if 'phase2_low_time' in s4.columns else pd.NaT,
                errors='coerce'
            )
            info_col = s4['info'] if 'info' in s4.columns else pd.Series([{}] * len(s4), index=s4.index)
            s4['liq_time']    = pd.to_datetime(info_col.apply(lambda x: x.get('liq_time')    if isinstance(x, dict) else None), errors='coerce')
            s4['breach_time'] = pd.to_datetime(info_col.apply(lambda x: x.get('breach_time') if isinstance(x, dict) else None), errors='coerce')

            # 開場からの経過時間（分）を計算
            def elapsed_min(ts_col, ref_col):
                return (
                    pd.to_datetime(ts_col, errors='coerce') -
                    pd.to_datetime(ref_col, errors='coerce')
                ).dt.total_seconds() / 60

            s4['high_elapsed']   = elapsed_min(s4['phase2_high_time'], s4['reference_open_time'])
            s4['low_elapsed']    = elapsed_min(s4['phase2_low_time'],  s4['reference_open_time'])
            s4['liq_elapsed']    = elapsed_min(s4['liq_time'],         s4['reference_open_time'])
            s4['breach_elapsed'] = elapsed_min(s4['breach_time'],      s4['reference_open_time'])

            # 値幅
            s4['high_diff'] = (
                pd.to_numeric(s4['phase2_high'] if 'phase2_high' in s4.columns else None, errors='coerce') -
                pd.to_numeric(s4['entry']       if 'entry'       in s4.columns else None, errors='coerce')
            )
            s4['low_diff'] = (
                pd.to_numeric(s4['phase2_low'] if 'phase2_low' in s4.columns else None, errors='coerce') -
                pd.to_numeric(s4['entry']      if 'entry'      in s4.columns else None, errors='coerce')
            )

            # ── 曜日別シンボル出現数 ──────────────────────
            st.markdown("#### 曜日別シンボル出現数")
            wd_cross = s4.groupby(['曜日', 'symbol']).size().unstack(fill_value=0)
            wd_order = [w for w in ['月', '火', '水', '木', '金'] if w in wd_cross.index]
            st.dataframe(wd_cross.reindex(wd_order), use_container_width=True)

            # ── 曜日別値幅統計 ────────────────────────────
            st.markdown("#### 曜日別 値幅統計（建値差）")
            wd_range = s4.groupby('曜日').agg(
                件数            =('high_diff', 'count'),
                最高値建値差_平均=('high_diff', 'mean'),
                最高値建値差_最大=('high_diff', 'max'),
                最底値建値差_平均=('low_diff',  'mean'),
                最底値建値差_最小=('low_diff',  'min'),
            ).round(2)
            wd_range = wd_range.reindex([w for w in ['月', '火', '水', '木', '金'] if w in wd_range.index])
            st.dataframe(wd_range, use_container_width=True)

            # ── 開場からの経過時間 目安 ───────────────────
            st.markdown("#### 開場からの経過時間 目安")
            st.caption("reference_open_time（実際の基準足）からの経過分数")

            def elapsed_summary(col, label):
                s = s4[col].dropna()
                if len(s) == 0:
                    return {'イベント': label, '件数': 0, '中央値': '-', '平均': '-', '25%ile': '-', '75%ile': '-', '最小': '-', '最大': '-'}
                return {
                    'イベント': label,
                    '件数':   len(s),
                    '中央値': f"{s.median():.0f}分",
                    '平均':   f"{s.mean():.0f}分",
                    '25%ile': f"{s.quantile(0.25):.0f}分",
                    '75%ile': f"{s.quantile(0.75):.0f}分",
                    '最小':   f"{s.min():.0f}分",
                    '最大':   f"{s.max():.0f}分",
                }

            elapsed_df = pd.DataFrame([
                elapsed_summary('high_elapsed',   '最高値を記録'),
                elapsed_summary('low_elapsed',    '最底値を記録'),
                elapsed_summary('liq_elapsed',    'ロスカット発生'),
                elapsed_summary('breach_elapsed', '建値割れ発生'),
            ])
            st.dataframe(elapsed_df, use_container_width=True, hide_index=True)


except FileNotFoundError as e:
    st.error(f"❌ {e}")
    st.info("💡 build_daily_aggregates.py を実行してデータを生成してください。")

except Exception as e:
    st.error(f"エラーが発生しました: {e}")
    import traceback
    st.code(traceback.format_exc())
