import streamlit as st
import pandas as pd
import re
from datetime import datetime
import io

st.set_page_config(page_title="BSNL Perfect Polisher", layout="centered")
st.title("📱 BSNL Strict Monthly Polisher")

def format_duration(seconds):
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02}:{int(m):02}:{int(s):02}"

if st.button("🔄 Reset App"):
    st.cache_data.clear()
    st.rerun()

uploaded_file = st.file_uploader("Upload Raw BSNL File", type=['xlsx', 'csv'])

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
            
            if st.button("🚀 Generate Perfect Pairs"):
                # 1. Monthly Filter
                df_m = full_df[full_df['MonthYear'] == selected_month].copy()
                
                # 2. Strict State Transition (Remove same-status duplicates)
                df_m = df_m.sort_values(['Object', 'dt'], ascending=True)
                df_m['prev_info'] = df_m.groupby('Object')['Information'].shift(1)
                df_filtered = df_m[df_m['Information'] != df_m['prev_info']].copy()

                final_rows = []
                total_sec = 0
                
                # 3. Strict Pairing Engine (Keep ONLY Completed Pairs)
                for obj_name, group in df_filtered.groupby('Object'):
                    group = group.sort_values('dt', ascending=False)
                    i = 0
                    while i < len(group):
                        row = group.iloc[i].copy()
                        # Only start if we find a 'Cleared' event
                        if row['Information'] == "Cleared Link Down":
                            if i + 1 < len(group) and group.iloc[i+1]['Information'] == "Link Down":
                                down_row = group.iloc[i+1].copy()
                                
                                # Math for duration
                                diff = int((row['dt'] - down_row['dt']).total_seconds())
                                total_sec += diff
                                
                                row['Outage Hours'] = format_duration(diff)
                                down_row['Outage Hours'] = ""
                                
                                final_rows.append(row)
                                final_rows.append(down_row)
                                i += 2 # Move past the pair
                            else:
                                i += 1 # Skip lone 'Cleared'
                        else:
                            i += 1 # Skip lone 'Down'

                if final_rows:
                    final_df = pd.DataFrame(final_rows).sort_values('Event Number', ascending=False)
                    final_df.insert(0, 'Sr. No', range(1, len(final_df) + 1))
                    
                    cols = ['Sr. No', 'Event Number', 'Date', 'Time', 'Information', 'Object', 'Outage Hours']
                    final_df = final_df[cols]
                    
                    # 4. Final Summary Row
                    summary = pd.DataFrame([["", "", "", "", "", "TOTAL OUTAGE HOURS:", format_duration(total_sec)]], columns=cols)
                    final_df = pd.concat([final_df, summary], ignore_index=True)

                    # Export
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        final_df.to_excel(writer, index=False)
                    
                    st.success(f"Cleaned Pairs for {selected_month}!")
                    st.download_button("📥 Download Perfect Report", data=output.getvalue(), file_name=f"Clean_{selected_month}.xlsx")
                else:
                    st.error("No complete Down/Clear pairs found in this month.")
        else:
            st.warning("No valid Link events found.")
            
