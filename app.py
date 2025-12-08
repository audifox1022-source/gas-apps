import streamlit as st
import pandas as pd
import io

# 1. 페이지 설정
st.set_page_config(page_title="가스 원단위 분석 시스템 (누적보정)", layout="wide")

st.title("🔥 가열로 가스 원단위 분석기 (누적 보정 기능)")
st.markdown("""
- **기능:** 가열은 했으나 생산(중량)이 없는 날의 가스 사용량을 모아서, **생산이 있는 날에 합산**하여 정확한 원단위를 계산합니다.
- **원단위 기준:** m³/ton
""")

# 2. 파일 업로드
uploaded_files = st.file_uploader(
    "가스 이력 파일(.csv)과 생산 일보 파일(.xlsx)을 모두 선택해주세요.", 
    type=['csv', 'xlsx'], 
    accept_multiple_files=True
)

if uploaded_files:
    st.info("데이터 분석 중... (가스 누적 로직 적용)")
    
    daily_gas_list = []
    daily_weight_list = []
    
    # 3. 데이터 읽기 및 1차 전처리
    for uploaded_file in uploaded_files:
        try:
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)
            
            df.columns = df.columns.str.strip()
            
            # (A) 가스 데이터 처리
            if '시간' in df.columns and '가스누적지침' in df.columns:
                furnace_name = uploaded_file.name.split('_')[0]
                df['시간'] = pd.to_datetime(df['시간'])
                df = df.set_index('시간').sort_index()
                
                # 이상치/결측치 처리
                df['가스누적지침'] = pd.to_numeric(df['가스누적지침'], errors='coerce').fillna(method='ffill')
                df['사용량'] = df['가스누적지침'].diff().clip(lower=0)
                df.loc[df['사용량'] > 10000, '사용량'] = 0 
                
                # 일간 합계
                daily_sum = df['사용량'].resample('D').sum().reset_index()
                daily_sum.columns = ['날짜', '가스사용량']
                daily_sum['가열로명'] = furnace_name
                daily_gas_list.append(daily_sum)

            # (B) 생산 데이터 처리
            elif '작업일자' in df.columns and '중량(kg)' in df.columns:
                df['날짜'] = pd.to_datetime(df['작업일자'])
                df['중량(kg)'] = pd.to_numeric(df['중량(kg)'], errors='coerce').fillna(0)
                if '가열로명' in df.columns:
                    daily_weight = df.groupby(['날짜', '가열로명'])['중량(kg)'].sum().reset_index()
                    daily_weight_list.append(daily_weight)
                    
        except Exception as e:
            st.error(f"❌ {uploaded_file.name} 처리 오류: {e}")

    # 4. 데이터 병합 및 핵심 계산 로직
    if daily_gas_list:
        all_gas_df = pd.concat(daily_gas_list)
        if daily_weight_list:
            all_weight_df = pd.concat(daily_weight_list)
            merged_df = pd.merge(all_gas_df, all_weight_df, on=['날짜', '가열로명'], how='outer')
        else:
            merged_df = all_gas_df
            merged_df['중량(kg)'] = 0
            
        merged_df[['가스사용량', '중량(kg)']] = merged_df[['가스사용량', '중량(kg)']].fillna(0)
        merged_df = merged_df.sort_values(['가열로명', '날짜'])

        # --- [핵심] 가스 누적 할당 함수 ---
        def apply_accumulation(group):
            adjusted_gas_list = []
            current_gas_acc = 0
            
            for _, row in group.iterrows():
                # 일단 가스를 누적함
                current_gas_acc += row['가스사용량']
                
                if row['중량(kg)'] > 0:
                    # 생산이 있으면 누적된 가스를 모두 여기에 할당
                    adjusted_gas_list.append(current_gas_acc)
                    current_gas_acc = 0 # 초기화
                else:
                    # 생산이 없으면 가스는 0으로 표시 (다음 생산일로 이월됨)
                    adjusted_gas_list.append(0)
            
            group['보정_가스사용량'] = adjusted_gas_list
            return group

        # 가열로별로 누적 로직 적용
        final_df = merged_df.groupby('가열로명').apply(apply_accumulation).reset_index(drop=True)

        # 원단위 계산 (보정된 가스량 사용)
        final_df['원단위(m3/ton)'] = final_df.apply(
            lambda x: x['보정_가스사용량'] / (x['중량(kg)']/1000) if x['중량(kg)'] > 0 else 0, 
            axis=1
        )

        # 5. 주간/월간 집계 (단순 합산)
        # 주간/월간은 이미 기간이 길어서 누적 로직보다는 단순 합산 후 나눗셈이 더 정확함
        final_df['주'] = final_df['날짜'].dt.to_period('W-MON').apply(lambda r: r.start_time)
        final_df['월'] = final_df['날짜'].dt.to_period('M').apply(lambda r: r.start_time)
        
        # 주간 계산
        weekly_group = final_df.groupby(['가열로명', '주'])[['가스사용량', '중량(kg)']].sum().reset_index()
        weekly_group['원단위(m3/ton)'] = weekly_group.apply(
            lambda x: x['가스사용량'] / (x['중량(kg)']/1000) if x['중량(kg)'] > 0 else 0, axis=1
        )
        weekly_group.rename(columns={'주': '날짜'}, inplace=True)
        
        # 월간 계산
        monthly_group = final_df.groupby(['가열로명', '월'])[['가스사용량', '중량(kg)']].sum().reset_index()
        monthly_group['원단위(m3/ton)'] = monthly_group.apply(
            lambda x: x['가스사용량'] / (x['중량(kg)']/1000) if x['중량(kg)'] > 0 else 0, axis=1
        )
        monthly_group.rename(columns={'월': '날짜'}, inplace=True)

        # 6. 결과 보여주기
        st.success("✅ 분석 완료! (생산 없는 날의 가스는 생산일까지 이월 합산됨)")
        
        tab1, tab2, tab3 = st.tabs(["📅 일간 (Daily)", "🗓 주간 (Weekly)", "📊 월간 (Monthly)"])
        
        # 포맷팅
        def format_df(df, is_daily=False):
            fmt = {
                '날짜': '{:%Y-%m-%d}',
                '중량(kg)': '{:,.0f}',
                '원단위(m3/ton)': '{:.1f}'
            }
            if is_daily:
                # 일간 데이터는 보정된 가스량도 보여줌
                fmt['보정_가스사용량'] = '{:,.0f}'
                cols = ['날짜', '가열로명', '보정_가스사용량', '중량(kg)', '원단위(m3/ton)']
                return df[cols].style.format(fmt)
            else:
                fmt['가스사용량'] = '{:,.0f}'
                cols = ['날짜', '가열로명', '가스사용량', '중량(kg)', '원단위(m3/ton)']
                return df[cols].style.format(fmt)

        with tab1:
            st.dataframe(format_df(final_df, is_daily=True), use_container_width=True)
        with tab2:
            st.dataframe(format_df(weekly_group), use_container_width=True)
        with tab3:
            st.dataframe(format_df(monthly_group), use_container_width=True)

        # 7. 엑셀 다운로드
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            final_df[['날짜', '가열로명', '가스사용량', '보정_가스사용량', '중량(kg)', '원단위(m3/ton)']].to_excel(writer, sheet_name='일간', index=False)
            weekly_group.to_excel(writer, sheet_name='주간', index=False)
            monthly_group.to_excel(writer, sheet_name='월간', index=False)
            
            # 서식 적용
            workbook = writer.book
            fmt_date = workbook.add_format({'num_format': 'yyyy-mm-dd'})
            fmt_num = workbook.add_format({'num_format': '#,##0'})
            
            for sheet in writer.sheets.values():
                sheet.set_column('A:A', 12, fmt_date)
                sheet.set_column('C:E', 15, fmt_num)

        st.download_button(
            label="📥 분석 결과 엑셀 다운로드",
            data=output.getvalue(),
            file_name="가열로_원단위_누적보정.xlsx",
            mime="application/vnd.ms-excel"
        )
    else:
        st.warning("분석할 가스 데이터가 없습니다.")
