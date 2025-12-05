import streamlit as st
import pandas as pd
import io

# 1. 페이지 설정
st.set_page_config(page_title="가스 원단위 분석 시스템", layout="wide")

st.title("🔥 가열로 가스 원단위(효율) 분석기")
st.markdown("""
파일을 업로드하면 **가스 사용량**과 **원단위(사용량/중량)**를 일간/주간/월간으로 분석합니다.
- **가스 데이터:** 시간, 가스누적지침 포함
- **생산 데이터:** 작업일자, 가열로명, 중량(kg) 포함
""")

# 2. 파일 업로드 (한 번에 여러 개 가능)
uploaded_files = st.file_uploader(
    "가스 이력 파일과 생산 일보 파일을 모두 선택해서 올려주세요.", 
    type=['csv', 'xlsx'], 
    accept_multiple_files=True
)

if uploaded_files:
    st.info("파일 분석 및 병합 중입니다...")
    
    # 데이터를 저장할 리스트
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
            
            # --- Case A: 가스 데이터 파일 (시간, 가스누적지침) ---
            if '시간' in df.columns and '가스누적지침' in df.columns:
                # 파일명에서 호기 추출 (예: 가열로17호기_...)
                furnace_name = uploaded_file.name.split('_')[0]
                
                df['시간'] = pd.to_datetime(df['시간'])
                df = df.set_index('시간').sort_index()
                
                # 전처리 (숫자변환, 결측치처리, 이상치제거)
                df['가스누적지침'] = pd.to_numeric(df['가스누적지침'], errors='coerce').fillna(method='ffill')
                df['사용량'] = df['가스누적지침'].diff().clip(lower=0)
                df.loc[df['사용량'] > 10000, '사용량'] = 0 # 이상치 제거
                
                # 일간 합계 계산
                daily_sum = df['사용량'].resample('D').sum().reset_index()
                daily_sum.columns = ['날짜', '가스사용량']
                daily_sum['가열로명'] = furnace_name
                
                daily_gas_list.append(daily_sum)

            # --- Case B: 생산 데이터 파일 (작업일자, 중량) ---
            elif '작업일자' in df.columns and '중량(kg)' in df.columns:
                # 날짜 변환
                df['날짜'] = pd.to_datetime(df['작업일자'])
                df['중량(kg)'] = pd.to_numeric(df['중량(kg)'], errors='coerce').fillna(0)
                
                # 필요한 컬럼만 선택 (가열로명이 없으면 파일명에서 추측하거나 에러 처리 필요하지만, 일단 있다고 가정)
                if '가열로명' in df.columns:
                    daily_weight = df.groupby(['날짜', '가열로명'])['중량(kg)'].sum().reset_index()
                    daily_weight_list.append(daily_weight)
                else:
                    st.warning(f"⚠️ {uploaded_file.name}: '가열로명' 컬럼이 없어 제외되었습니다.")
                    
        except Exception as e:
            st.error(f"❌ {uploaded_file.name} 처리 중 오류: {e}")

    # 3. 데이터 병합 및 원단위 계산
    if daily_gas_list:
        # 1) 가스 데이터 합치기
        all_gas_df = pd.concat(daily_gas_list)
        
        # 2) 생산 데이터 합치기 (파일이 있다면)
        if daily_weight_list:
            all_weight_df = pd.concat(daily_weight_list)
            # 날짜와 가열로명을 기준으로 병합 (Outer Join)
            merged_df = pd.merge(all_gas_df, all_weight_df, on=['날짜', '가열로명'], how='outer')
        else:
            merged_df = all_gas_df
            merged_df['중량(kg)'] = 0 # 생산 데이터 없으면 0 처리
            
        # 결측치 0으로 채우기
        merged_df[['가스사용량', '중량(kg)']] = merged_df[['가스사용량', '중량(kg)']].fillna(0)
        
        # --- 계산 함수 (일간/주간/월간) ---
        def calculate_report(df, freq):
            # freq: 'D'(일간), 'W-MON'(주간), 'MS'(월간)
            grouped = df.set_index('날짜').groupby(['가열로명', pd.Grouper(freq=freq)])[['가스사용량', '중량(kg)']].sum().reset_index()
            
            # 원단위 계산 (0으로 나누기 방지)
            grouped['원단위'] = grouped.apply(
                lambda x: x['가스사용량'] / x['중량(kg)'] if x['중량(kg)'] > 0 else 0, axis=1
            )
            return grouped

        daily_final = calculate_report(merged_df, 'D')
        weekly_final = calculate_report(merged_df, 'W-MON') # 매주 월요일 기준
        monthly_final = calculate_report(merged_df, 'MS')   # 매월 1일 기준

        # 4. 결과 출력 (탭으로 구분)
        st.success("✅ 분석 완료! 아래 탭을 눌러 결과를 확인하세요.")
        
        tab1, tab2, tab3 = st.tabs(["📅 일간(Daily)", "🗓 주간(Weekly)", "📊 월간(Monthly)"])
        
        # 포맷 설정 함수
        def format_df(df):
            return df.style.format({
                '날짜': '{:%Y-%m-%d}',
                '가스사용량': '{:,.0f}', 
                '중량(kg)': '{:,.0f}',
                '원단위': '{:.4f}'
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
            daily_final.to_excel(writer, sheet_name='일간_원단위', index=False)
            weekly_final.to_excel(writer, sheet_name='주간_원단위', index=False)
            monthly_final.to_excel(writer, sheet_name='월간_원단위', index=False)
            
            # 엑셀 포맷팅 (날짜 포맷)
            workbook = writer.book
            date_format = workbook.add_format({'num_format': 'yyyy-mm-dd'})
            
            for sheet in writer.sheets.values():
                sheet.set_column('B:B', 15, date_format) # 날짜 컬럼 넓게
                sheet.set_column('C:E', 15) # 숫자 컬럼 넓게

        st.download_button(
            label="📥 전체 분석 결과 엑셀 다운로드",
            data=output.getvalue(),
            file_name="가열로_가스원단위_분석.xlsx",
            mime="application/vnd.ms-excel"
        )
        
    else:
        st.warning("분석 가능한 가스 데이터 파일이 없습니다.")
