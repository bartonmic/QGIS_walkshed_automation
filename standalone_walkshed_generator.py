"""
Walkshed Generator

Generates walksheds for transit stops using QGIS processing tools.
Processes stops by route to create both individual and dissolved walksheds.

Required inputs:
- Stops shapefile: Point layer with 'rte' field
- Network shapefile: Line layer containing pedestrian network

Outputs:
- Walksheds: Individual walksheds for each stop
- Dissolved walksheds: Combined walksheds by route
- Service lines: Network segments within walking distance

Author: Michaela Barton
Date: 12/11/24
"""

# ------------------------ CONFIGURATION --------------------------#
# Input Files
STOPS_FILE = r"" # G:/TRIMET/stops.shp or subset
NETWORK_FILE = r"" # get a network .shp using G:/PUBLIC/OpenStreetMap/Pedestrian_network/ped_net_extract.py

# Output Settings
OUTPUT_FOLDER = r""
OUTPUT_PREFIX = ""  # prefix for output files (can be empty string)

# Processing Parameters
DISTANCE_METERS = 804.672  # walking distance for walkshed (1/2 mile)
CONCAVE_THRESHOLD = 0.015  # concave hull threshold
# -------------------------------------------------------------#

from qgis.core import QgsApplication, QgsVectorLayer, QgsProcessing, QgsProcessingFeedback, QgsExpression
import sys
import os
from datetime import datetime

# Initialize QGIS
qgs = QgsApplication([], False)
qgs.initQgis()

# Add the path to processing
qgis_path = os.path.join(qgs.prefixPath(), 'python', 'plugins')
sys.path.append(qgis_path)

# Import processing after QGIS is initialized
from qgis.analysis import QgsNativeAlgorithms
import processing
from processing.core.Processing import Processing

# Initialize processing
Processing.initialize()
QgsApplication.processingRegistry().addProvider(QgsNativeAlgorithms())

def prepare_network(stops_layer, network_layer, distance_meters):
    """Pre-process the network by buffering all stops and clipping the network"""
    try:
        print("\nPreparing network for all stops...")
        
        # Buffer all stops
        print("Creating buffer for all stops...")
        buffer_params = {
            'INPUT': stops_layer,
            'DISTANCE': QgsExpression(f' {distance_meters} * 3.3').evaluate(), # feet to meters converstion
            'SEGMENTS': 5,
            'END_CAP_STYLE': 0,
            'JOIN_STYLE': 0,
            'MITER_LIMIT': 2,
            'DISSOLVE': True,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        buffer_result = processing.run('native:buffer', buffer_params)
        
        # Clip network to buffer
        print("Clipping network to buffer...")
        clip_params = {
            'INPUT': network_layer,
            'OVERLAY': buffer_result['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        clip_result = processing.run('native:clip', clip_params)
        
        # Step 3: Split lines
        print("Splitting network lines...")
        split_params = {
            'INPUT': clip_result['OUTPUT'],
            'LENGTH': 100, # max feature length - 100 meters
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        split_result = processing.run('native:splitlinesbylength', split_params)
        
        print("Network prep complete")
        return split_result['OUTPUT']
        
    except Exception as e:
        print(f"Error in prepare_network: {str(e)}")
        return None

def prepare_route_network(prepared_network, stops, distance_meters):
    """Further clip the network for a specific route's stops"""
    try:
        print("Preparing network for route...")
        
        # Create buffer around route's stops
        route_buffer_params = {
            'INPUT': stops,
            'DISTANCE': QgsExpression(f' {distance_meters} * 3.3').evaluate(),
            'SEGMENTS': 5,
            'END_CAP_STYLE': 0,
            'JOIN_STYLE': 0,
            'MITER_LIMIT': 2,
            'DISSOLVE': True,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        route_buffer_result = processing.run('native:buffer', route_buffer_params)
        
        # Clip pre-processed network to route buffer
        route_clip_params = {
            'INPUT': prepared_network,
            'OVERLAY': route_buffer_result['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        route_clip_result = processing.run('native:clip', route_clip_params)
        
        return route_clip_result['OUTPUT']
        
    except Exception as e:
        print(f"Error in prepare_route_network: {str(e)}")
        return None

def create_walkshed(stops_layer, prepared_network, distance_meters, concave_threshold):
    """Creates walksheds for given stops using pre-processed network"""
    try:
        # Step 1: Service area analysis
        service_params = {
            'INPUT': prepared_network,
            'STRATEGY': 0,
            'DIRECTION_FIELD': '',
            'VALUE_FORWARD': '',
            'VALUE_BACKWARD': '',
            'VALUE_BOTH': '',
            'DEFAULT_DIRECTION': 2,
            'SPEED_FIELD': '',
            'DEFAULT_SPEED': 50,
            'TOLERANCE': 0,
            'START_POINTS': stops_layer,
            'TRAVEL_COST': distance_meters,
            'INCLUDE_BOUNDS': False,
            'OUTPUT_LINES': QgsProcessing.TEMPORARY_OUTPUT,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        service_result = processing.run('native:serviceareafromlayer', service_params)
        print("Service areas created")
        
        # Step 2: Create convex hull
        convex_params = {
            'INPUT': service_result['OUTPUT_LINES'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        convex_result = processing.run('native:convexhull', convex_params)
        print("Convex hull created")
        
        # Step 3: Create concave hull
        concave_params = {
            'INPUT': service_result['OUTPUT'],
            'ALPHA': concave_threshold,
            'HOLES': False,
            'NO_MULTIGEOMETRY': False,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        concave_result = processing.run('native:concavehull', concave_params)
        print("Concave hull created")
        
        # Step 4: Clip convex hull with concave hull
        final_clip_params = {
            'INPUT': convex_result['OUTPUT'],
            'OVERLAY': concave_result['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        walksheds_result = processing.run('native:clip', final_clip_params)
        print("Final walksheds created")
        
        # Step 5: Dissolve by route
        dissolve_params = {
            'INPUT': walksheds_result['OUTPUT'],
            'FIELD': ['rte'],
            'SEPARATE_DISJOINT': False,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        dissolve_result = processing.run('native:dissolve', dissolve_params)
        print("Walksheds dissolved")
        
        return {
            'walksheds': walksheds_result['OUTPUT'],
            'dissolved': dissolve_result['OUTPUT'],
            'service_lines': service_result['OUTPUT_LINES']
        }
        
    except Exception as e:
        print(f"Error in create_walkshed: {str(e)}")
        return None

def process_routes(stops_layer, network_layer, output_prefix=""):
    """Process all routes individually using pre-processed network"""
    
    # Get unique route values
    routes = sorted(set([f['rte'] for f in stops_layer.getFeatures()]))
    total_routes = len(routes)
    print(f"\nFound {total_routes} routes to process")
    
    # Pre-process network for all stops
    prepared_network = prepare_network(stops_layer, network_layer, DISTANCE_METERS)
    if not prepared_network:
        print("Failed to prepare network. Exiting...")
        return
    
    # Create timestamp for this run
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Lists to store results for merging
    all_results = []
    
    # Process each route individually
    for i, route in enumerate(routes, 1):
        print(f"\nProcessing route {route} ({i}/{total_routes})")
        
        # Create filtered stops layer for this route
        filtered_stops = QgsVectorLayer("Point?crs=" + stops_layer.crs().authid(), "filtered_stops", "memory")
        filtered_stops.dataProvider().addAttributes(stops_layer.fields())
        filtered_stops.updateFields()
        
        features = [f for f in stops_layer.getFeatures() if f['rte'] == route]
        filtered_stops.dataProvider().addFeatures(features)
        print(f"Processing {len(features)} stops")
        
        try:
            # Further clip network for this specific route
            route_network = prepare_route_network(prepared_network, filtered_stops, DISTANCE_METERS)
            if not route_network:
                print(f"Failed to prepare network for route {route}")
                continue
            
            results = create_walkshed(filtered_stops, route_network, DISTANCE_METERS, CONCAVE_THRESHOLD)
            if results:
                all_results.append(results)
                print(f"Route {route} processed successfully")
            else:
                print(f"Failed to process route {route}")
        except Exception as e:
            print(f"Error processing route {route}: {str(e)}")
            continue
    
    # Merge and save results
    if all_results:
        prefix = f"{output_prefix}_" if output_prefix else ""
        
        # Prepare lists for merging
        walksheds_to_merge = [result['walksheds'] for result in all_results]
        dissolved_to_merge = [result['dissolved'] for result in all_results]
        service_lines_to_merge = [result['service_lines'] for result in all_results]
        
        # Merge and save each type
        outputs = {
            'walksheds': (walksheds_to_merge, f'{prefix}walksheds_{timestamp}.gpkg'),
            'dissolved': (dissolved_to_merge, f'{prefix}dissolved_{timestamp}.gpkg'),
            'service_lines': (service_lines_to_merge, f'{prefix}service_lines_{timestamp}.gpkg')
        }
        
        print("\nMerging and saving final results...")
        for output_type, (layers, filename) in outputs.items():
            output_path = os.path.join(OUTPUT_FOLDER, filename)
            
            merge_params = {
                'LAYERS': layers,
                'CRS': stops_layer.crs(),
                'OUTPUT': output_path
            }
            processing.run("native:mergevectorlayers", merge_params)
            print(f"Saved {output_type} to {output_path}")


# Ensure output directory exists
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Load the layers
print("Loading layers...")
stops_layer = QgsVectorLayer(STOPS_FILE, "stops", "ogr")
network_layer = QgsVectorLayer(NETWORK_FILE, "network", "ogr")

if not stops_layer.isValid() or not network_layer.isValid():
    print("Error loading layers!")
    qgs.exitQgis()
    sys.exit(1)

print("Layers loaded successfully")

# Process all routes
process_routes(stops_layer, network_layer, OUTPUT_PREFIX)

# Clean up
qgs.exitQgis()
print("\nProcessing complete!")