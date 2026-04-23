import json
import urllib.parse
import os
import math

def generate_hex_boundary(lat, lon, size_deg):
    """Fallback method to generate a hexagon boundary if the h3-py library is not installed"""
    pts = []
    for i in range(6):
        angle_deg = 60 * i - 30
        angle_rad = math.pi / 180 * angle_deg
        pts.append([
            lon + size_deg * math.cos(angle_rad) / math.cos(math.radians(lat)),
            lat + size_deg * math.sin(angle_rad)
        ])
    pts.append(pts[0])
    return pts

def load_json(filepath):
    if not os.path.exists(filepath):
        return None
    with open(filepath, 'r') as f:
        return json.load(f)

def generate_mod3_url():
    data = load_json('module3_geospatial/map_definition.json')
    if not data:
        return "File module3_geospatial/map_definition.json not found."

    geojson = {"type": "FeatureCollection", "features": []}

    # Load Points
    for pt in data.get("points", []):
        geojson["features"].append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [pt["lon"], pt["lat"]]},
            "properties": {"name": pt["name"], "marker-color": pt.get("color", "#ff0000")}
        })

    # Load Lines
    for line in data.get("lines", []):
        geojson["features"].append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": line["coordinates"]},
            "properties": {"name": line["name"], "stroke": line.get("color", "#0000ff"), "stroke-width": 4}
        })

    # Load Polygons
    for poly in data.get("polygons", []):
        geojson["features"].append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": poly["coordinates"]},
            "properties": {"name": poly["name"], "fill": poly.get("color", "#ff0000"), "fill-opacity": 0.2, "stroke": poly.get("color", "#ff0000")}
        })

    return "http://geojson.io/#data=data:application/json," + urllib.parse.quote(json.dumps(geojson))

def generate_mod4_url():
    data = load_json('module4_h3/map_definition.json')
    if not data:
        return "File module4_h3/map_definition.json not found."

    geojson = {"type": "FeatureCollection", "features": []}

    # Try to use H3 library if installed, otherwise use math approximation
    has_h3 = False
    try:
        import h3
        has_h3 = True
    except ImportError:
        pass

    for hex_data in data.get("hexagons", []):
        if has_h3:
            try:
                h3_idx = h3.latlng_to_cell(hex_data["lat"], hex_data["lon"], hex_data["resolution"])
                boundary = h3.cell_to_boundary(h3_idx, geo_json=True)
            except AttributeError:
                # Older h3-py version compatibility
                h3_idx = h3.geo_to_h3(hex_data["lat"], hex_data["lon"], hex_data["resolution"])
                boundary = h3.h3_to_geo_boundary(h3_idx, geo_json=True)
            
            # Close the polygon for GeoJSON standard
            boundary_list = list(boundary)
            boundary_list.append(boundary_list[0])
            coords = boundary_list
            name_ext = f" (H3 ID: {h3_idx})"
        else:
            coords = generate_hex_boundary(hex_data["lat"], hex_data["lon"], 0.002)
            name_ext = " (Mathematical Appx)"

        # Append Hexagon Polygon
        geojson["features"].append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [coords]},
            "properties": {"name": hex_data["name"] + name_ext, "fill": hex_data.get("color", "#0000ff"), "fill-opacity": 0.3}
        })
        
        # Append Center Point
        geojson["features"].append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [hex_data["lon"], hex_data["lat"]]},
            "properties": {"name": hex_data["name"], "marker-color": "#ff0000"}
        })

    return "http://geojson.io/#data=data:application/json," + urllib.parse.quote(json.dumps(geojson))

if __name__ == "__main__":
    print("\n" + "="*80)
    print("🗺️  GENERATING MAP URLs FROM JSON DEFINITIONS")
    print("="*80)
    
    print("\n[MODULE 3 GEOJSON URL]:")
    print(generate_mod3_url())
    
    print("\n" + "-"*80)
    
    print("\n[MODULE 4 GEOJSON URL]:")
    print(generate_mod4_url())
    print("\n" + "="*80 + "\n")
