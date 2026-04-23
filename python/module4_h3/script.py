import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_connection

def print_step(title, query, execution_note=None, description=None):
    print(f"\n{'-'*80}")
    print(f"STEP: {title}")
    if description:
        print(f"🔍 [DESCRIPTION]: {description}")
    print(f"{'-'*80}")
    print(f"[EXECUTING SQL]:\n{query.strip()}\n")
    if execution_note:
        print(f"💡 [EXECUTION NOTE]: {execution_note}\n")

def prompt_manual_test(psql_command):
    print(f"👉 [TRY IT MANUALLY IN PSQL]:\n  {psql_command}\n")
    user_input = input("👉 Press 'y' or 'Y' to continue, or any other key to exit: ")
    if user_input.strip().lower() != 'y':
        print("Exiting script...")
        sys.exit(0)

def setup():
    """4.1 Table Architecture & Indexing"""
    conn = get_connection()
    cur = conn.cursor()
    
    # Ensure H3 is available (requires superuser, ignore if it fails as Ansible might have installed it)
    q0 = "CREATE EXTENSION IF NOT EXISTS h3 CASCADE;"
    
    q1 = """
    CREATE TABLE IF NOT EXISTS multimodal.h3_events (
        event_id SERIAL PRIMARY KEY,
        event_type TEXT,
        h3_index h3index
    );
    """
    
    q2 = """
    CREATE INDEX IF NOT EXISTS h3_events_idx 
    ON multimodal.h3_events (h3_index);
    """
    
    print_step("Creating Schema and H3 Spatial Tables", q1 + "\n" + q2)
    
    try:
        cur.execute(q0)
    except Exception:
        conn.rollback()

    cur.execute(q1)
    cur.execute(q2)
    conn.commit()
    print("✅ Module 4: Schema and tables created.")
    prompt_manual_test("\\dt multimodal.*\n  \\di multimodal.*\n  \\d multimodal.h3_events")
    cur.close()
    conn.close()

def load_data():
    """4.2 Data Ingestion & Transformation"""
    conn = get_connection()
    cur = conn.cursor()
    
    q = """
    INSERT INTO multimodal.h3_events (event_type, h3_index)
    VALUES 
        ('Delivery Dropoff (Center)', h3_lat_lng_to_cell(point(40.4168, -3.7038), 9)),
        ('Pickup (North)', h3_lat_lng_to_cell(point(40.4500, -3.7038), 9)),
        ('Delivery Dropoff (South)', h3_lat_lng_to_cell(point(40.3800, -3.7038), 9));
    """
    
    print_step("Data Ingestion & H3 Transformation", q, execution_note="Executed directly via cur.execute() using standard SQL INSERT and h3_lat_lng_to_cell")
    cur.execute(q)
    conn.commit()
    print("✅ Module 4: H3 data ingestion completed.")
    prompt_manual_test("SELECT event_id, event_type, h3_index FROM multimodal.h3_events;")
    cur.close()
    conn.close()

def query_h3():
    """4.3 Querying H3 Data"""
    conn = get_connection()
    cur = conn.cursor()
    
    q = """
    -- Find events in the center hexagon or its neighbors
    SELECT 
        event_type, 
        h3_index
    FROM 
        multimodal.h3_events
    WHERE 
        h3_are_neighbor_cells(h3_index, h3_lat_lng_to_cell(point(40.4168, -3.7038), 9))
        OR h3_index = h3_lat_lng_to_cell(point(40.4168, -3.7038), 9);
    """
    
    print_step("Querying H3 Data (Neighbors)", q, description="Search for events located in the exact same H3 hexagon or any of its immediate neighbors")
    cur.execute(q)
    print("--- 🎯 RESULTS (Events in target hex or neighbors) ---")
    for row in cur.fetchall():
        print(f"Event: {row[0]:<30} | H3 Cell: {row[1]}")
    prompt_manual_test(q.strip())
    cur.close()
    conn.close()

if __name__ == "__main__":
    print("\n" + "="*80)
    print("🚀 EXECUTING MODULE 4: H3 Spatial Index (Uber H3)")
    print("="*80)
    setup()
    load_data()
    query_h3()
    print("\n🎉 Module 4 execution finished.\n")
