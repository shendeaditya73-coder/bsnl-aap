import streamlit as st
import pandas as pd
import re
from datetime import datetime
import io

st.set_page_config(page_title="BSNL Strict Polisher", layout="centered")
st.title("📱 BSNL Zero-Garbage Polisher")

def format_duration(seconds):
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02}:{int(m):02}:{int(s):02}"

# 1. Clear Cache Button
if st.button("🔄 Full Reset"):
    st.cache_data.clear()
    st.rerun()

uploaded_file = st.file_uploader("Upload Raw BSNL File", type=['xlsx', 'csv'])

if uploaded_file:
    # Handle File Types
    if uploaded_file.name.endswith('.csv'):
        content = uploaded_file.getvalue().decode('utf-8', errors='ignore')
        lines = content.splitlines()
    else:
        raw_df = pd.read_excel(uploaded_file, header=None)
        lines = raw_df[0].astype(str).tolist()

    # Find Header
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
            
            if st.button("🚀 Generate Final Accurate Report"):
                # Filter for the specific month
                df_m = full_df[full_df['MonthYear'] == selected_month].copy()
                
                # --- THE STICKY FILTER ---
                # Sort by Port and Time to see sequence
                df_m = df_m.sort_values(['Object', 'dt'], ascending=True)
                
                # Step A: Delete repeated states (e.g. Down followed immediately by another Down)
                df_m['prev_info'] = df_m.groupby('Object')['Information'].shift(1)
                df_clean = df_m[df_m['Information'] != df_m['prev_info']].copy()

                final_paired_list = []
                total_sec = 0
                
                # Step B: STRICT PAIRING (Delete any event that doesn't have a partner)
                for port, group in df_clean.groupby('Object'):
                    group = group.sort_values('dt', ascending=False)
                    i = 0
                    while i < (len(group) - 1):
                        current_row = group.iloc[i].copy()
                        next_row = group.iloc[i+1].copy()
                        
                        # Only keep if we have a CLEAR followed immediately by a DOWN
                        if current_row['Information'] == "Cleared Link Down" and next_row['Information'] == "Link Down":
                            # Calculate Outage
                            diff = int((current_row['dt'] - next_row['dt']).total_seconds())
                            total_sec += diff
                            
                            current_row['Outage Hours'] = format_duration(diff)
                            next_row['Outage Hours'] = ""
                            
                            final_paired_list.append(current_row)
                            final_paired_list.append(next_row)
                            i += 2 # Move past this perfect pair
                        else:
                            i += 1 # Skip lone event (it gets deleted because it's not added to list)

                if final_paired_list:
                    # Final Sort (Latest first)
                    final_df = pd.DataFrame(final_paired_list).sort_values('Event Number', ascending=False)
                    final_df.insert(0, 'Sr. No', range(1, len(final_df) + 1))
                    
                    # Columns selection
                    cols = ['Sr. No', 'Event Number', 'Date', 'Time', 'Information', 'Object', 'Outage Hours']
                    final_df = final_df[cols]
                    
                    # Add Total Row
                    summary = pd.DataFrame([["", "", "", "", "", "TOTAL OUTAGE HOURS:", format_duration(total_sec)]], columns=cols)
                    final_df = pd.concat([final_df, summary], ignore_index=True)

                    st.success(f"Report Generated: {len(final_df)-1} paired events found.")
                    
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        final_df.to_excel(writer, index=False)
                    
                    st.download_button("📥 Download Final Correct Excel", data=output.getvalue(), file_name=f"Final_{selected_month}.xlsx")
                else:
                    st.error("No valid completed pairs found for this month.")
        else:
            st.warning("No data found.")
            
