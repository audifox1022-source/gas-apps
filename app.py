import streamlit as st
import pandas as pd
import io

# 1. 페이지 설정
st.set_page_config(page_title="가스 원단위 분석 시스템", layout="wide")

st.title("🔥 가열로 가스 원단위(효율) 분석기")
st.markdown("""
파일을 업로드하면 **가스 사용량**과 **톤당 원단위($m^3/ton$)**를 일간/주간/월간으로 분석합니다.
- **가스 데이터:** 시간, 가스누적지침 포함
- **생산 데이터:** 작업일자, 가열로명, 중량(kg) 포함
""")

# 2. 파일 업로드
uploaded_files = st.file_uploader(
    "가스 이력 파일(.csv)과 생산 일보 파일(.xlsx)을 모두 선택해서 올려주세요.", 
    type=['csv', 'xlsx'], 
    accept_multiple_files=True
)

if uploaded_files:
    st.info("파일 분석 및 병합 중입니다...")
    
    daily_gas_list = []
    daily_weight_list = []
    
    for uploaded_file in uploaded_files:
        try:
            # 파일 읽기
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)
            
            df.columns = df.columns.str.strip() # 공백 제거
            
            # --- Case A: 가스 데이터 파일 ---
            if '시간' in df.columns and '가스누적지침' in df.columns:
                furnace_name = uploaded_file.name.split('_')[0]
                
                df['시간'] = pd.to_datetime(df['시간'])
                df = df.set_index('시간').sort_index()
                
                # 전처리
                df['가스누적지침'] = pd.to_numeric(df['가스누적지침'], errors='coerce').fillna(method='ffill')
                df['사용량'] = df['가스누적지침'].diff().clip(lower=0)
                df.loc[df['사용량'] > 10000, '사용량'] = 0 # 이상치 제거
                
                # 일간 합계
                daily_sum = df['사용량'].resample('D').sum().reset_index()
                daily_sum.columns = ['날짜', '가스사용량']
                daily_sum['가열로명'] = furnace_name
                
                daily_gas_list.append(daily_sum)

            # --- Case B: 생산 데이터 파일 ---
            elif '작업일자' in df.columns and '중량(kg)' in df.columns:
                df['날짜'] = pd.to_datetime(df['작업일자'])
                df['중량(kg)'] = pd.to_numeric(df['중량(kg)'], errors='coerce').fillna(0)
                
                if '가열로명' in df.columns:
                    daily_weight = df.groupby(['날짜', '가열로명'])['중량(kg)'].sum().reset_index()
                    daily_weight_list.append(daily_weight)
                    
        except Exception as e:
            st.error(f"❌ {uploaded_file.name} 처리 중 오류: {e}")

    # 3. 데이터 병합 및 계산
    if daily_gas_list:
        all_gas_df = pd.concat(daily_gas_list)
        
        if daily_weight_list:
            all_weight_df = pd.concat(daily_weight_list)
            merged_df = pd.merge(all_gas_df, all_weight_df, on=['날짜', '가열로명'], how='outer')
        else:
            merged_df = all_gas_df
            merged_df['중량(kg)'] = 0
            
        merged_df[['가스사용량', '중량(kg)']] = merged_df[['가스사용량', '중량(kg)']].fillna(0)
        
        # --- [핵심 수정] 원단위 계산 함수 (Ton 기준) ---
        def calculate_report(df, freq):
            # freq: 'D'(일간), 'W-MON'(주간), 'MS'(월간)
            grouped = df.set_index('날짜').groupby(['가열로명', pd.Grouper(freq=freq)])[['가스사용량', '중량(kg)']].sum().reset_index()
            
            # 원단위 = 가스사용량 / (중량kg / 1000)
            # 즉, 1톤당 가스를 몇 m3 썼는지 계산
            grouped['원단위(m3/ton)'] = grouped.apply(
                lambda x: x['가스사용량'] / (x['중량(kg)'] / 1000) if x['중량(kg)'] > 0 else 0, axis=1
            )
            return grouped

        daily_final = calculate_report(merged_df, 'D')
        weekly_final = calculate_report(merged_df, 'W-MON')
        monthly_final = calculate_report(merged_df, 'MS')

        # 4. 결과 출력
        st.success("✅ 분석 완료! (원단위 기준: m³/ton)")
        
        tab1, tab2, tab3 = st.tabs(["📅 일간", "🗓 주간", "📊 월간"])
        
        # 포맷 설정 (원단위 소수점 1자리까지 표시)
        def format_df(df):
            return df.style.format({
                '날짜': '{:%Y-%m-%d}',
                '가스사용량': '{:,.0f}', 
                '중량(kg)': '{:,.0f}',
                '원단위(m3/ton)': '{:.1f}' 
            })

        with tab1:
            st.dataframe(format_df(daily_final), use_container_width=True)
        with tab2:
            st.dataframe(format_df(weekly_final), use_container_width=True)
        with tab3:
            st.dataframe(format_df(monthly_final), use_container_width=True)

        # 5. 엑셀 다운로드
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            # 엑셀에도 m3/ton 컬럼명으로 저장
            daily_final.to_excel(writer, sheet_name='일간_원단위', index=False)
            weekly_final.to_excel(writer, sheet_name='주간_원단위', index=False)
            monthly_final.to_excel(writer, sheet_name='월간_원단위', index=False)
            
            workbook = writer.book
            date_format = workbook.add_format({'num_format': 'yyyy-mm-dd'})
            num_format = workbook.add_format({'num_format': '#,##0.0'}) # 소수점 1자리
            
            for sheet in writer.sheets.values():
                sheet.set_column('A:A', 15) # 가열로명
                sheet.set_column('B:B', 12, date_format) # 날짜
                sheet.set_column('C:D', 15) # 사용량, 중량
                sheet.set_column('E:E', 15, num_format) # 원단위

        st.download_button(
            label="📥 톤당 원단위 분석 결과 다운로드",
            data=output.getvalue(),
            file_name="가열로_톤당원단위_분석.xlsx",
            mime="application/vnd.ms-excel"
        )
        
    else:
        st.warning("분석 가능한 가스 데이터 파일이 없습니다.")
