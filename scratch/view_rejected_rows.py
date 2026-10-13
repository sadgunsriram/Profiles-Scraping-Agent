import openpyxl

wb = openpyxl.load_workbook('skills/output/profiles.xlsx')
for sheet in ['SET_1', 'SET_2', 'SET_3', '_Rejected_Set1', '_Rejected_Set2', '_Rejected_Set3']:
    print(f"\n--- Sheet: {sheet} ---")
    ws = wb[sheet]
    rows = list(ws.iter_rows(values_only=True))
    header = rows[0]
    print("Header:", header)
    for idx, r in enumerate(rows[-5:], 1):
        print(f"Row {idx}: {r}")
wb.close()
