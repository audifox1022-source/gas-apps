import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="가스 사용량 분석기", layout="wide")

st.title("🔥 가열로 가스 사용량 분석 시스템")
st.markdown("엑셀/CSV 파일을 업로드하면 **일간/주간 가스 사용량**을 자동으로 계산합니다.")

uploaded_files = st.file_uploader("가열로 데이터 파일을 모두 선택해서 올려주세요.", 
                                  type=['csv', 'xlsx'], accept_multiple_files=True)

if uploaded_files:
    st.success(f"총 {len(uploaded_files)}개의 파일이 업로드되었습니다. 분석을 시작합니다...")
    
    daily_combined = pd.DataFrame()
    weekly_combined = pd.DataFrame()
    
    for uploaded_file in uploaded_files:
        try:
            file_name = uploaded_file.name
            furnace_name = file_name.split('_')[0]
            
            if file_name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)
                
            df.columns = df.columns.str.strip()
            
            if '시간' in df.columns and '가스누적지침' in df.columns:
                df['시간'] = pd.to_datetime(df['시간'])
                df = df.set_index('시간').sort_index()
                
                df['가스누적지침'] = pd.to_numeric(df['가스누적지침'], errors='coerce').fillna(method='ffill')
                df['사용량'] = df['가스누적지침'].diff().clip(lower=0)
                df.loc[df['사용량'] > 10000, '사용량'] = 0
                
                daily_combined[furnace_name] = df['사용량'].resample('D').sum()
                weekly_combined[furnace_name] = df['사용량'].resample('W-MON').sum()
                
        except Exception as e:
            st.error(f"{file_name} 처리 중 오류 발생: {e}")

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📅 일간 가스 사용량")
        st.dataframe(daily_combined.style.format("{:,.1f}"))
    with col2:
        st.subheader("WEEK 주간 가스 사용량")
        st.dataframe(weekly_combined.style.format("{:,.1f}"))

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        daily_combined.to_excel(writer, sheet_name='일간사용량')
        weekly_combined.to_excel(writer, sheet_name='주간사용량')
    
    st.download_button(
        label="📥 분석 결과 엑셀 다운로드",
        data=output.getvalue(),
        file_name="가스사용량_분석결과.xlsx",
        mime="application/vnd.ms-excel"
    )