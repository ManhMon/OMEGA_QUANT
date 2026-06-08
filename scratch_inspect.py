import sqlite3
import os

db_path = r'.code-review-graph\graph.db'
if not os.path.exists(db_path):
    print(f"File not found: {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
c = conn.cursor()

c.execute("SELECT id, name, entry_point_id, depth, node_count, file_count, criticality FROM flows")
flows = c.fetchall()
print(f"Flows ({len(flows)}):")
for f in flows:
    print(f"  ID: {f[0]}, Name: {f[1]}, EntryPointNodeID: {f[2]}, Depth: {f[3]}, Nodes: {f[4]}, Files: {f[5]}, Criticality: {f[6]}")

c.execute("SELECT flow_id, name, entry_point, criticality, node_count, file_count FROM flow_snapshots")
snapshots = c.fetchall()
print(f"\nFlow Snapshots ({len(snapshots)}):")
for s in snapshots:
    print(f"  FlowID: {s[0]}, Name: {s[1]}, EntryPoint: {s[2]}, Criticality: {s[3]}, Nodes: {s[4]}, Files: {s[5]}")

conn.close()










