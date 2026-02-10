import streamlit as st
import pandas as pd
import re
from datetime import datetime
import io

st.set_page_config(page_title="BSNL 100% Accuracy Polisher", layout="centered")
st.title("📱 BSNL Strict Link Polisher")

def format_duration(seconds):
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02}:{int(m):02}:{int(s):02}"

# UI Reset
if st.button("🔄 Clear App Cache"):
    st.cache_data.clear()
    st.rerun()

uploaded_file = st.file_uploader("Upload BSNL Status File", type=['xlsx', 'csv'])

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
                    dt_obj = pd.to_datetime(f"{date_str} {time_str}", dayfirst=True, errors='coerce')
                    if pd.notnull(dt_obj):
                        records.append({
                            'Event Number': int(evt_no), 'Date': date_str, 'Time': time_str,
                            'Information': info_clean, 'Object': obj.strip(),
                            'dt': dt_obj, 'MonthYear': dt_obj.strftime('%B %Y')
                        })
        
        full_df = pd.DataFrame(records)
        if not full_df.empty:
            months = sorted(full_df['MonthYear'].unique(), key=lambda x: datetime.strptime(x, '%B %Y'), reverse=True)
            selected_month = st.selectbox("📅 Select Month:", months)
            
            if st.button("🚀 Generate Final Report"):
                # 1. Filter by Month
                df_month = full_df[full_df['MonthYear'] == selected_month].copy()
                
                # 2. STRICT STATE FILTER (The Fix for 100% Accuracy)
                # We sort by object and time, then only keep rows where the status CHANGES.
                df_month = df_month.sort_values(['Object', 'dt'], ascending=True)
                df_month['prev_info'] = df_month.groupby('Object')['Information'].shift(1)
                # Only keep if current Information is NOT equal to previous Information for that port
                df_filtered = df_month[df_month['Information'] != df_month['prev_info']].copy()

                final_list = []
                total_sec = 0
                
                # 3. Pairing Engine
                # Now that noise is gone, we can safely pair Down and Clear
                for obj_name, group in df_filtered.groupby('Object'):
                    group = group.sort_values('dt', ascending=False)
                    i = 0
                    while i < len(group):
                        row = group.iloc[i].copy()
                        if row['Information'] == "Cleared Link Down":
                            # Look for the immediate preceding Down
                            if i + 1 < len(group) and group.iloc[i+1]['Information'] == "Link Down":
                                down_row = group.iloc[i+1].copy()
                                sec = int((row['dt'] - down_row['dt']).total_seconds())
                                total_sec += sec
                                row['Outage Hours'] = format_duration(sec)
                                down_row['Outage Hours'] = ""
                                final_list.append(row); final_list.append(down_row)
                                i += 2
                            else:
                                row['Outage Hours'] = ""
                                final_list.append(row); i += 1
                        else:
                            row['Outage Hours'] = ""
                            final_list.append(row); i += 1
                
                # 4. Final Polish
                final_df = pd.DataFrame(final_list).sort_values('Event Number', ascending=False)
                final_df.insert(0, 'Sr. No', range(1, len(final_df) + 1))
                cols = ['Sr. No', 'Event Number', 'Date', 'Time', 'Information', 'Object', 'Outage Hours']
                final_df = final_df[cols]
                
                # 5. Total Summary
                total_str = format_duration(total_sec)
                summary = pd.DataFrame([["", "", "", "", "", "TOTAL OUTAGE HOURS:", total_str]], columns=cols)
                final_df = pd.concat([final_df, summary], ignore_index=True)

                st.success(f"Cleaned report for {selected_month} generated!")
                
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    final_df.to_excel(writer, index=False)
                st.download_button("📥 Download Excel", data=output.getvalue(), file_name=f"Final_{selected_month}.xlsx")
        else:
            st.warning("No data found.")
    else:
        st.error("Header not found.")
