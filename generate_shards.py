# generate_shards.py
import os
import random
import re
import pandas as pd

os.makedirs("shards", exist_ok=True)
random.seed(42)

email_regex = r"^[\w\.-]+@[\w\.-]+\.\w+$"

print("--- Generating 8 Data Shards ---")
for i in range(8):
    rows = []
    invalid_target = random.randint(3, 12)
    valid_target = 100 - invalid_target
    
    # Valid rows
    for _ in range(valid_target):
        rows.append({"email": f"user{random.randint(100,999)}@example.com", "name": "Valid User"})
        
    # Invalid rows (deliberately malformed email or missing name)
    for _ in range(invalid_target):
        if random.random() < 0.5:
            rows.append({"email": "bad_email_format", "name": "Valid Name"})
        else:
            rows.append({"email": f"user{random.randint(100,999)}@example.com", "name": ""})
            
    random.shuffle(rows)
    df = pd.DataFrame(rows)
    
    filename = f"shards/shard_{i}.csv"
    df.to_csv(filename, index=False)
    
    # Verify ground truth directly from the generated CSV
    df_check = pd.read_csv(filename).fillna("")
    actual_invalid = 0
    for _, row in df_check.iterrows():
        email = str(row["email"]).strip()
        name = str(row["name"]).strip()
        if not name or name.lower() == "nan" or not re.match(email_regex, email):
            actual_invalid += 1
            
    print(f"Shard {i} generated -> Ground Truth Invalid Rows: {actual_invalid}")