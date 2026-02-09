import streamlit as st
import pandas as pd
import re
from datetime import datetime
import io

st.set_page_config(page_title="BSNL Link Polisher", layout="centered")
st.title(" BSNL Link Outage App")

def format_duration(seconds):
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02}:{int(m):02}:{int(s):02}"

uploaded_file = st.file_uploader("Upload BSNL raw file", type=['xlsx', 'csv'])

if uploaded_file:
    if uploaded_file.name.endswith('.csv'):
        content = uploaded_file.getvalue().decode('utf-8', errors='ignore')
        lines = content.splitlines()
    else:
        raw_df = pd.read_excel(uploaded_file, header=None)
        lines = raw_df[0].astype(str).tolist()

    header_idx = -1
    for i, line in enumerate(lines):
        if "#" in line and "Time" in line and "Information" in line:
            header_idx = i
            break

    if header_idx != -1:
        pattern = re.compile(r'(\d+)\s+(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2}:\d{2})\s+(.*?)\s{2,}([A-Z0-9\-_.]+)')
        records = []
        for line in lines[header_idx + 1:]:
            match = pattern.search(line.strip())
            if match:
                evt_no, date_str, time_str, info, obj = match.groups()
                info_clean = info.strip()
                if info_clean in ["Link Down", "Cleared Link Down"]:
                    dt_obj = pd.to_datetime(f"{date_str} {time_str}", dayfirst=True)
                    records.append({'Event Number': int(evt_no), 'Date': date_str, 'Time': time_str, 'Information': info_clean, 'Object  Additional Information': obj.strip(), 'dt': dt_obj, 'MonthYear': dt_obj.strftime('%B %Y')})
        
        full_df = pd.DataFrame(records)
        available_months = sorted(full_df['MonthYear'].unique(), key=lambda x: datetime.strptime(x, '%B %Y'), reverse=True)
        selected_month = st.selectbox(" Select Month:", available_months)
        
        if st.button("Generate Report"):
            df_month = full_df[full_df['MonthYear'] == selected_month].copy()
            df_month = df_month.sort_values(['Object  Additional Information', 'dt'], ascending=True)
            df_month['prev_info'] = df_month.groupby('Object  Additional Information')['Information'].shift(1)
            df_filtered = df_month[df_month['Information'] != df_month['prev_info']].copy()

            final_list = []
            total_sec = 0
            for obj, group in df_filtered.groupby('Object  Additional Information'):
                group = group.sort_values('dt', ascending=False)
                i = 0
                while i < len(group):
                    row = group.iloc[i].copy()
                    if row['Information'] == "Cleared Link Down" and i+1 < len(group):
                        down_row = group.iloc[i+1].copy()
                        sec = int((row['dt'] - down_row['dt']).total_seconds())
                        total_sec += sec
                        row['Outage Hours'] = format_duration(sec)
                        down_row['Outage Hours'] = ""
                        final_list.append(row); final_list.append(down_row); i += 2
                    else:
                        row['Outage Hours'] = ""; final_list.append(row); i += 1
            
            final_df = pd.DataFrame(final_list).sort_values('Event Number', ascending=False)
            final_df.insert(0, 'Sr. No', range(1, len(final_df) + 1))
            cols = ['Sr. No', 'Event Number', 'Date', 'Time', 'Information', 'Object  Additional Information', 'Outage Hours']
            final_df = final_df[cols]
            summary = pd.DataFrame([["", "", "", "", "", "TOTAL OUTAGE HOURS:", format_duration(total_sec)]], columns=cols)
            final_df = pd.concat([final_df, summary], ignore_index=True)

            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                final_df.to_excel(writer, index=False)
            st.download_button(" Download Excel", data=output.getvalue(), file_name=f"Report_{selected_month}.xlsx")

