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
    """3.1 Table Architecture & The GiST Index"""
    conn = get_connection()
    cur = conn.cursor()
    
    q1 = """
    CREATE TABLE IF NOT EXISTS multimodal.location_events (
        event_id SERIAL PRIMARY KEY,
        event_type TEXT,
        geom geometry(Geometry, 4326) -- Geometry type allows Points, Lines, and Polygons
    );
    """
    
    q2 = """
    CREATE INDEX IF NOT EXISTS event_geom_idx 
    ON multimodal.location_events USING GIST (geom);
    """
    
    # Staging table for Bulk Load Method B
    q3 = """
    CREATE TABLE IF NOT EXISTS multimodal.staging_events (
        event_type TEXT,
        wkt TEXT
    );
    """
    
    print_step("Creating Schema and Spatial Tables", q1 + "\n" + q2)
    
    cur.execute(q1)
    cur.execute(q2)
    cur.execute(q3)
    
    conn.commit()
    print("✅ Module 3: Schema and tables created.")
    prompt_manual_test("\\dt multimodal.*\n  \\di multimodal.*\n  \\d multimodal.location_events")
    cur.close()
    conn.close()

def load_data_a():
    """3.2.A Real-time Single Ingestion (Points, Lines, Polygons)"""
    conn = get_connection()
    cur = conn.cursor()
    
    q = """
    -- 1. Insert a Point
    INSERT INTO multimodal.location_events (event_type, geom)
    VALUES (
        'Traffic Accident (Point)', 
        ST_SetSRID(ST_MakePoint(-3.7038, 40.4168), 4326)
    );
    
    -- 2. Insert a LineString (e.g., a route or road segment)
    INSERT INTO multimodal.location_events (event_type, geom)
    VALUES (
        'Marathon Route (Line)', 
        ST_SetSRID(ST_GeomFromText('LINESTRING(-3.7038 40.4168, -3.7100 40.4200, -3.7150 40.4250)'), 4326)
    );

    -- 3. Insert a Polygon (e.g., a restricted area)
    INSERT INTO multimodal.location_events (event_type, geom)
    VALUES (
        'Restricted Zone (Polygon)', 
        ST_SetSRID(ST_GeomFromText('POLYGON((-3.70 40.41, -3.71 40.41, -3.71 40.42, -3.70 40.42, -3.70 40.41))'), 4326)
    );
    """
    
    print_step("Method A: Real-time Ingestion (Points, Lines, Polygons)", q, execution_note="Executed directly via cur.execute() using standard SQL INSERT")
    cur.execute(q)
    conn.commit()
    print("✅ Module 3: Real-time single ingestion completed.")
    prompt_manual_test("SELECT event_id, event_type, ST_AsText(geom) FROM multimodal.location_events;")
    cur.close()
    conn.close()

def load_data_b():
    """3.2.B Bulk Ingestion from CSV via Staging Table"""
    conn = get_connection()
    cur = conn.cursor()
    
    csv_path = os.path.join(os.path.dirname(__file__), 'data.csv')
    
    q1 = "COPY multimodal.staging_events (event_type, wkt) FROM '/path/to/data.csv' WITH (FORMAT csv, HEADER true);"
    q2 = """
    INSERT INTO multimodal.location_events (event_type, geom)
    SELECT 
        event_type, 
        ST_SetSRID(ST_GeomFromText(wkt), 4326)
    FROM multimodal.staging_events;
    """
    
    print_step("Method B: Bulk Ingestion via Staging Table", q1 + "\n" + q2, execution_note="Executed via cur.copy_expert() reading from a physical CSV file into a staging table, then cur.execute() for final INSERT")
    
    # Step 1: Load into staging table
    cur.execute("TRUNCATE multimodal.staging_events;")
    with open(csv_path, 'r') as f:
        cur.copy_expert("COPY multimodal.staging_events (event_type, wkt) FROM STDIN WITH (FORMAT csv, HEADER true)", f)
    
    # Step 2: Bulk insert with Geometry transformation
    # cur.execute("TRUNCATE multimodal.location_events;")
    cur.execute(q2)
    
    conn.commit()
    print("✅ Module 3: Bulk ingestion using COPY and PostGIS functions completed.")
    prompt_manual_test("SELECT count(*) FROM multimodal.location_events;")
    cur.close()
    conn.close()

def load_data_c():
    """3.2.C The Professional Toolset: ogr2ogr"""
    import subprocess
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from database import get_config
    
    config = get_config()
    
    # GDAL requires the connection string in this exact format
    conn_str = f"PG:dbname={config['database_name']} user={config['admin_user']} password={config['password']} host={config['host']} port={config['port']}"
    geojson_path = os.path.join(os.path.dirname(__file__), 'events_data.geojson')
    
    cmd = [
        "ogr2ogr",
        "-f", "PostgreSQL",
        conn_str,
        geojson_path,
        "-nln", "multimodal.location_events",
        "-append"
    ]
    
    print_step(
        "Method C: The Professional Toolset (ogr2ogr GDAL command)", 
        f"-- NOT SQL --\n# This runs directly in your terminal:\n{' '.join(cmd)}",
        execution_note="Executed via Python's subprocess.run() executing an external OS command (GDAL ogr2ogr)"
    )
    
    try:
        # We run the command via the OS
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print("✅ Module 3: ogr2ogr ingestion completed successfully from GeoJSON.")
        prompt_manual_test("SELECT event_type, ST_AsText(geom) FROM multimodal.location_events;")
    except FileNotFoundError:
        print("⚠️ Module 3 Note: 'ogr2ogr' command not found in your OS. You need to install GDAL (e.g., sudo apt-get install gdal-bin) to test Method C. Skipping...")
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Module 3 Error executing ogr2ogr: {e.stderr.decode('utf-8')}")

def query_radius():
    """3.3 Radius / Proximity Search"""
    conn = get_connection()
    cur = conn.cursor()
    
    q = """
    SELECT 
        event_type,
        ST_Distance(geom::geography, ST_SetSRID(ST_MakePoint(-3.7100, 40.4200), 4326)::geography) AS distance_m,
        ST_AsText(geom) as coordinates
    FROM 
        multimodal.location_events
    WHERE 
        ST_DWithin(
            geom::geography, 
            ST_SetSRID(ST_MakePoint(-3.7100, 40.4200), 4326)::geography, 
            5000 
        )
    ORDER BY 
        distance_m ASC;
    """
    
    print_step("Radius / Proximity Search (ST_DWithin)", q, description="Search the nearest events (points/polygons/lines) to the Radius search origin, ordered by distance")
    cur.execute(q)
    
    print("--- 🎯 RESULTS (Events within 5km of Madrid center) ---")
    for row in cur.fetchall():
        print(f"Event: {row[0]:<25} | Dist: {row[1]:.1f}m | Coords: {row[2]}")
    prompt_manual_test(q.strip())
    cur.close()
    conn.close()

def query_spatial_relationships():
    """3.4 Spatial Relationships (Intersection & Containment)"""
    conn = get_connection()
    cur = conn.cursor()
    
    q_intersect = """
    -- Find which events (points, lines, or polygons) intersect with our target Polygon
    SELECT 
        event_type,
        ST_GeometryType(geom) as shape_type
    FROM multimodal.location_events
    WHERE ST_Intersects(
        geom,
        ST_SetSRID(ST_GeomFromText('POLYGON((-3.705 40.415, -3.705 40.420, -3.700 40.420, -3.700 40.415, -3.705 40.415))'), 4326)
    );
    """
    
    q_contains = """
    -- Find events fully contained inside our Restricted Zone Polygon
    SELECT 
        e1.event_type as target_event,
        e2.event_type as containing_polygon
    FROM multimodal.location_events e1
    JOIN multimodal.location_events e2 
      ON e2.event_type = 'Restricted Zone (Polygon)'
    WHERE ST_Contains(e2.geom, e1.geom) AND e1.event_type != 'Restricted Zone (Polygon)';
    """
    
    print_step("Spatial Relationships: ST_Intersects", q_intersect, description="Search the events (points/polygons/lines) that have an intersect relationship with the Search Area")
    cur.execute(q_intersect)
    print("--- 🎯 RESULTS (Shapes intersecting the search Polygon) ---")
    for row in cur.fetchall():
        print(f"Event: {row[0]:<25} | Type: {row[1]}")
    prompt_manual_test(q_intersect.strip())

    print_step("Spatial Relationships: ST_Contains", q_contains, description="Search for events that are fully contained within the Restricted Zone Polygon")
    cur.execute(q_contains)
    print("--- 🎯 RESULTS (Shapes contained strictly inside Restricted Zone) ---")
    for row in cur.fetchall():
        print(f"Target Event: {row[0]:<25} | Contained inside: {row[1]}")
    prompt_manual_test(q_contains.strip())
        
    cur.close()
    conn.close()

def query_spatial_distances():
    """3.5 Spatial KNN (Nearest Neighbor) & Operators"""
    conn = get_connection()
    cur = conn.cursor()
    
    q_knn = """
    SELECT 
        event_type,
        ST_Distance(geom::geography, ST_SetSRID(ST_MakePoint(-3.71, 40.42), 4326)::geography) AS distance_m
    FROM multimodal.location_events
    ORDER BY geom <-> ST_SetSRID(ST_MakePoint(-3.7100, 40.4200), 4326)
    LIMIT 3;
    """
    
    q_bbox = """
    SELECT 
        event_type,
        geom <#> ST_SetSRID(ST_MakePoint(-3.7100, 40.4200), 4326) AS bbox_distance
    FROM multimodal.location_events
    ORDER BY geom <#> ST_SetSRID(ST_MakePoint(-3.7100, 40.4200), 4326)
    LIMIT 3;
    """
    
    q_bbox_intersect = """
    SELECT 
        event_type
    FROM 
        multimodal.location_events
    WHERE 
        geom && ST_SetSRID(ST_GeomFromText('POLYGON((-3.705 40.415, -3.705 40.420, -3.700 40.420, -3.700 40.415, -3.705 40.415))'), 4326)
        AND event_type != 'Search Area (Intersects Polygon)';
    """
    
    q_bbox_poly = """
    SELECT 
        e2.event_type AS target_polygon,
        e1.geom <#> e2.geom AS bbox_distance_degrees
    FROM 
        multimodal.location_events e1,
        multimodal.location_events e2
    WHERE 
        e1.event_type = 'Restricted Zone (Polygon)'
        AND e2.event_type LIKE 'Complex Intersecting Zone%';
    """
    
    print_step("Query 1: Spatial KNN Search (2D Distance <->)", q_knn, description="Find the top 3 closest events to the search origin based on precise 2D distance")
    cur.execute(q_knn)
    print("--- 🎯 RESULTS (Closest 3 by precise distance) ---")
    for row in cur.fetchall():
        print(f"Event: {row[0]:<20} | Distance: {row[1]:.2f} meters")
    prompt_manual_test(q_knn.strip())

    print_step("Query 2: Bounding Box Distance Search (<#>)", q_bbox, description="Find the top 3 closest events to the search origin based on bounding box distance (faster but less precise)")
    cur.execute(q_bbox)
    print("--- 🎯 RESULTS (Closest 3 by BBox distance) ---")
    for row in cur.fetchall():
        print(f"Event: {row[0]:<20} | BBox Dist: {row[1]:.4f}")
    prompt_manual_test(q_bbox.strip())

    print_step("Query 3: Bounding Box Distance between Polygons (<#>)", q_bbox_poly, description="Calculate the bounding box distance between the Restricted Zone and the Complex Zones")
    cur.execute(q_bbox_poly)
    print("--- 🎯 RESULTS (BBox distance between polygons) ---")
    for row in cur.fetchall():
        print(f"Target: {row[0]:<30} | BBox Dist: {row[1]:.4f}")
    prompt_manual_test(q_bbox_poly.strip())

    print_step("Query 4: Bounding Box Intersects (&&)", q_bbox_intersect, description="Find events whose bounding box overlaps with the Search Area's bounding box")
    cur.execute(q_bbox_intersect)
    print("--- 🎯 RESULTS (Events with overlapping Bounding Boxes) ---")
    for row in cur.fetchall():
        print(f"Event: {row[0]:<30}")
    prompt_manual_test(q_bbox_intersect.strip())
        
    cur.close()
    conn.close()

if __name__ == "__main__":
    print("\n" + "="*80)
    print("🚀 EXECUTING MODULE 3: Geospatial Search (PostGIS)")
    print("="*80)
    setup()
    load_data_a()
    load_data_b()
    load_data_c()
    query_radius()
    query_spatial_relationships()
    query_spatial_distances()
    print("\n🎉 Module 3 execution finished.\n")
