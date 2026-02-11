import streamlit as st
import pandas as pd
import calendar
from datetime import datetime
from core.logic import judge_all, calculate_statistics, DEFAULT_THRESHOLD_MIN, DEFAULT_JUDGMENT_HOURS
from core.liquidation.simple_af import SimpleAFModel
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
def load_data():
    path = APP_DIR / "data" / "derived" / "daily_aggregates.parquet"
    return pd.read_parquet(path)


# ↓ここに追加
@st.cache_data
def load_1min_data():
    """1分足データを読み込み"""
    df = pd.read_csv(
        'data/raw/gold_1min_20251101_.csv',
        parse_dates=['日時']
    )
    df = df.rename(columns={
        '日時': 'timestamp',
        '始値': 'open',
        '高値': 'high',
        '安値': 'low',
        '終値': 'close'
    })
    df.set_index('timestamp', inplace=True)
    return df

@st.cache_resource
def load_model():
    return SimpleAFModel()


try:
    df = load_data()
    df_1min = load_1min_data()  # ← この行を追加
    model = load_model()

    
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
    with st.spinner('判定中...'):
        results = judge_all(
            df,
            model,
            leverage,
            position_margin,
            additional_margin,
            threshold_min=DEFAULT_THRESHOLD_MIN,
            judgment_hours=judgment_hours,
            df_1min=df_1min  # ← この行を追加
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
                                # ⚠️/✅/🟠の場合は建値割れ時間を表示
                                elif ('⚠️' in symbol or '✅' in symbol or '🟠' in symbol) and info and 'breach_time' in info:
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
                                # データがない日は「閉場」と表示
                                table_html += f'<td style="border: 1px solid #ddd; padding: 8px; text-align: center; color: #999;">'
                                table_html += f'<div style="font-weight: bold;">{day}</div><div style="font-size: 12px;">閉場</div></td>'
                    
                    table_html += '</tr>'
                table_html += '</table>'
                st.markdown(table_html, unsafe_allow_html=True)
                st.markdown("")
    
    with tab2:
        st.subheader("詳細リスト")
        
        if len(results) == 0:
            st.warning(f"データがありません。")
        else:
            display_df = results_df[['date', 'type', 'symbol', 'detail', 'judgment_label']].copy()
            display_df.columns = ['日付', 'タイプ', '判定', '詳細', '判定期間']
            st.dataframe(display_df, use_container_width=True, height=600)
    
    with tab3:
        st.subheader("統計情報")
        
        st.markdown("#### 絵文字別カウント")
        symbol_df = pd.DataFrame([
            {'絵文字': k, 'カウント': v, '割合': f"{v/stats['total']*100:.1f}%"}
            for k, v in sorted(stats['symbol_counts'].items(), key=lambda x: -x[1])
        ])
        st.dataframe(symbol_df, use_container_width=True)
        
        st.markdown("#### パラメータ")
        param_df = pd.DataFrame([
            {'項目': 'レバレッジ', '値': f"{leverage}x"},
            {'項目': 'ポジション証拠金', '値': f"${position_margin:.0f}"},
            {'項目': '追加証拠金', '値': f"${additional_margin:.0f}"},
            {'項目': '総証拠金', '値': f"${position_margin + additional_margin:.0f}"},
            {'項目': '開場閾値', '値': f"{DEFAULT_THRESHOLD_MIN}分（固定）"},
            {'項目': '判定期間', '値': judgment_period_label},
            {'項目': 'Adjustment Factor', '値': f"{model.adjustment_factor * 100}%"},
        ])
        st.dataframe(param_df, use_container_width=True)

except FileNotFoundError:
    st.error("データファイルが見つかりません。先に build_daily_aggregates.py を実行してください。")
except Exception as e:
    st.error(f"エラーが発生しました: {e}")
    import traceback
    st.code(traceback.format_exc())
