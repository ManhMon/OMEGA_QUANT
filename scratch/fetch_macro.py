import sys
sys.path.insert(0, "src")
import requests
from omega.data.macro_pipeline import MacroDataPipeline

print("Fetching with 60s timeout...")
pipeline = MacroDataPipeline(timeout=60)
df = pipeline.run()
print("FETCH SUCCESSFUL, ROWS:", len(df))
print(df.tail(10))
