import pandas as pd
import re
from datetime import datetime
from google.colab import files

def generate_perfect_bsnl_report():
    print("Please upload the raw 'BSNL Link status.xlsx' (or CSV) file.")
    uploaded = files.upload()
    if not uploaded:
        return

    file_name = list(uploaded.keys())[0]
    
    # Read raw content
    if file_name.endswith('.csv'):
        content = uploaded[file_name].decode('utf-8', errors='ignore')
        lines = content.splitlines()
    else:
        # Extract text log from Excel
        raw_df = pd.read_excel(file_name, header=None)
        lines = raw_df[0].astype(str).tolist()

    # Locate the header in the raw file
    header_idx = -1
    for i, line in enumerate(lines):
        if "#" in line and "Time" in line and "Information" in line:
            header_idx = i
            break

    if header_idx == -1:
        print("Error: Could not find the system log header.")
        return

    # 1. Parsing and Initial Filtering
    pattern = re.compile(r'(\d+)\s+(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2}:\d{2})\s+(.*?)\s{2,}([A-Z0-9\-_.]+)')
    records = []
    for line in lines[header_idx + 1:]:
        match = pattern.search(line.strip())
        if match:
            evt_no, date_str, time_str, info, obj = match.groups()
            info_clean = info.strip()
            if info_clean in ["Link Down", "Cleared Link Down"]:
                records.append({
                    'Event Number': int(evt_no),
                    'Date': date_str,
                    'Time': time_str,
                    'Information': info_clean,
                    'Object  Additional Information': obj.strip(),
                    'dt': pd.to_datetime(f"{date_str} {time_str}", format='mixed', dayfirst=False)
                })

    df = pd.DataFrame(records)
    if df.empty:
        print("No Link Down/Clear events found.")
        return

    # 2. Transition Filter (Delete redundant same-state events)
    df = df.sort_values(['Object  Additional Information', 'dt'], ascending=True)
    df['prev_info'] = df.groupby('Object  Additional Information')['Information'].shift(1)
    df_filtered = df[df['Information'] != df['prev_info']].copy()

    # 3. Pairing Engine (Group Clear + Down rows together)
    outage_groups = []
    links = df_filtered['Object  Additional Information'].unique()
    
    for link in links:
        link_df = df_filtered[df_filtered['Object  Additional Information'] == link].sort_values('dt', ascending=False)
        i = 0
        while i < len(link_df):
            row = link_df.iloc[i]
            if row['Information'] == "Cleared Link Down":
                # Look for a preceding 'Link Down' to form a pair
                if i + 1 < len(link_df) and link_df.iloc[i+1]['Information'] == "Link Down":
                    down_row = link_df.iloc[i+1].copy()
                    clear_row = row.copy()
                    
                    # Calculate duration
                    delta = clear_row['dt'] - down_row['dt']
                    total_sec = int(delta.total_seconds())
                    h, rem = divmod(total_sec, 3600)
                    m, s = divmod(rem, 60)
                    clear_row['Outage Hours'] = f"{h:02}:{m:02}:{s:02}"
                    down_row['Outage Hours'] = ""
                    
                    outage_groups.append({'time': clear_row['dt'], 'rows': [clear_row, down_row]})
                    i += 2
                else:
                    row_copy = row.copy()
                    row_copy['Outage Hours'] = ""
                    outage_groups.append({'time': row_copy['dt'], 'rows': [row_copy]})
                    i += 1
            else:
                row_copy = row.copy()
                row_copy['Outage Hours'] = ""
                outage_groups.append({'time': row_copy['dt'], 'rows': [row_copy]})
                i += 1
                
    # 4. Final Sorting (Latest outages first)
    outage_groups.sort(key=lambda x: x['time'], reverse=True)
    
    final_list = []
    for group in outage_groups:
        final_list.extend(group['rows'])
        
    final_df = pd.DataFrame(final_list)
    final_df.insert(0, 'Sr. No', range(1, len(final_df) + 1))
    
    # 5. Export
    cols = ['Sr. No', 'Event Number', 'Date', 'Time', 'Information', 'Object  Additional Information', 'Outage Hours']
    final_df = final_df[cols]
    output_fn = "BSNL_Polished_Paired_Report.xlsx"
    final_df.to_excel(output_fn, index=False)
    
    print(f"\nProcessing Complete! Paired Clear/Down rows and filtered extra events.")
    files.download(output_fn)

# Run the app
generate_perfect_bsnl_report()
