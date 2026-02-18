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
                '上方向値幅_raw': pd.to_numeric(_series('move_vs_entry'), errors='coerce'),
                '下方向値幅_raw': pd.to_numeric(_series('low_move_vs_entry'), errors='coerce'),
                'skip_minutes_raw': pd.to_numeric(_series('skip_minutes', pd.Series([0] * len(detail_df), index=detail_df.index)), errors='coerce').fillna(0),
                'used_tier_index_raw': pd.to_numeric(_series('used_tier_index'), errors='coerce'),
                'detail_raw': _series('detail', pd.Series([''] * len(detail_df), index=detail_df.index)).fillna('').astype(str),
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
                tier_range = st.slider(
                    "used_tier_index 範囲",
                    min_value=tier_min,
                    max_value=tier_max,
                    value=(tier_min, tier_max),
                    key="detail_filter_tier_range",
                )

            check_col1, check_col2 = st.columns(2)
            with check_col1:
                only_skip = st.checkbox("skip_minutes > 0 のみ", key="detail_filter_only_skip")
            with check_col2:
                only_liq = st.checkbox("ロスカット日のみ", key="detail_filter_only_liq")

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

            if only_liq:
                filtered_df = filtered_df[filtered_df['ロスカット']]

            # --- ソート ---
            sort_columns = {
                '日付': '日付',
                '曜日': '曜日',
                'シンボル': 'シンボル',
                '建値': '建値_raw',
                '最高値時刻': '最高値時刻_raw',
                '最高値価格': '最高値価格_raw',
                '最高値建値差': '最高値建値差_raw',
                '最底値時刻': '最底値時刻_raw',
                '最底値価格': '最底値価格_raw',
                '最底値建値差': '最底値建値差_raw',
                '上方向値幅': '上方向値幅_raw',
                '下方向値幅': '下方向値幅_raw',
                'skip_minutes': 'skip_minutes_raw',
                'used_tier_index': 'used_tier_index_raw',
                'ロスカット': 'ロスカット',
                '詳細': 'detail_raw',
            }
            sort_col1, sort_col2 = st.columns([3, 1])
            with sort_col1:
                sort_label = st.selectbox(
                    "ソート列（非表示列も選択可）",
                    options=list(sort_columns.keys()),
                    key="detail_sort_column",
                )
            with sort_col2:
                sort_ascending = st.checkbox("昇順", value=False, key="detail_sort_ascending")

            filtered_df = filtered_df.sort_values(
                by=sort_columns[sort_label],
                ascending=sort_ascending,
                na_position='last',
            )

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

            def format_move(value):
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

            q_up = filtered_df['上方向値幅_raw'].abs().quantile(0.95) if len(filtered_df) else pd.NA
            q_down = filtered_df['下方向値幅_raw'].abs().quantile(0.95) if len(filtered_df) else pd.NA
            filtered_df['_is_outlier'] = (
                filtered_df['上方向値幅_raw'].abs().ge(q_up).fillna(False)
                | filtered_df['下方向値幅_raw'].abs().ge(q_down).fillna(False)
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
                '上方向値幅': filtered_df['上方向値幅_raw'].apply(format_move),
                '下方向値幅': filtered_df['下方向値幅_raw'].apply(format_move),
                'skip_minutes': filtered_df['skip_minutes_raw'].fillna(0).astype(int),
                'used_tier_index': filtered_df['used_tier_index_raw'].apply(lambda x: '-' if pd.isna(x) else int(x)),
                'ロスカット': filtered_df['ロスカット'].map({True: 'あり', False: '-'}),
                '詳細': [
                    append_skip_detail(d, s)
                    for d, s in zip(filtered_df['detail_raw'], filtered_df['skip_minutes_raw'])
                ],
            })

            st.markdown(
                "**表示条件** "
                f"シンボル: {', '.join(selected_symbols) if selected_symbols else '(未選択)'} / "
                f"曜日: {', '.join(selected_weekdays) if selected_weekdays else '(未選択)'} / "
                f"skip: {'ON' if only_skip else 'OFF'} / "
                f"ロスカ: {'ON' if only_liq else 'OFF'} / "
                f"ティア: {tier_range[0]} - {tier_range[1]}"
            )
            st.caption(f"表示件数: {len(display_df)} / {len(raw_df)}")

            # 列プリセット / 表示トグル
            all_display_columns = list(display_df.columns)
            preset_map = {
                '一覧': ['日付', '曜日', 'シンボル', '建値', '上方向値幅', '下方向値幅', 'ロスカット', '詳細'],
                '分析': ['日付', '曜日', 'シンボル', '建値', '最高値時刻', '最高値価格', '最高値建値差', '最底値時刻', '最底値価格', '最底値建値差', '上方向値幅', '下方向値幅', 'skip_minutes', 'used_tier_index'],
                '詳細': all_display_columns,
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
                help="列を個別に ON/OFF できます。非表示列でもソート可能です。",
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
                    .applymap(color_move, subset=[c for c in ['上方向値幅', '下方向値幅'] if c in visible_df.columns])
                )

                nonce_key = f"detail_table_{st.session_state['detail_table_nonce']}"
                st.dataframe(styled_df, use_container_width=True, height=600, key=nonce_key)

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
