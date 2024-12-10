"""
Standalone Walkshed Generator
Processes walksheds for transit stops using network analysis, one route at a time
"""

# ------------------------ CONFIGURATION --------------------------#
# Input Files
STOPS_FILE = "C:/Users/micba/OneDrive/Documents/trimet/qgis_walkshed_automation/stops_subset.shp"
NETWORK_FILE = "C:/Users/micba/OneDrive/Documents/trimet/qgis_walkshed_automation/full_ped_net.shp"

# Output Settings
OUTPUT_FOLDER = "C:/Users/micba/OneDrive/Documents/trimet/projects/QGIS_walkshed_automation/output"
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

def create_walkshed(stops_layer, network_layer, distance_meters, concave_threshold):
    """Creates walksheds for given stops using network analysis"""
    results = {}
    
    try:
        # Step 1: Buffer stops
        buffer_params = {
            'INPUT': stops_layer,
            'DISTANCE': QgsExpression(f' {distance_meters} * 3.3').evaluate(),
            'SEGMENTS': 5,
            'END_CAP_STYLE': 0,
            'JOIN_STYLE': 0,
            'MITER_LIMIT': 2,
            'DISSOLVE': False,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        buffer_result = processing.run('native:buffer', buffer_params)
        print("Buffer created")
        
        # Step 2: Clip network to buffer
        clip_params = {
            'INPUT': network_layer,
            'OVERLAY': buffer_result['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        clip_result = processing.run('native:clip', clip_params)
        print("Network clipped")
        
        # Step 3: Split lines
        split_params = {
            'INPUT': clip_result['OUTPUT'],
            'LENGTH': 100,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        split_result = processing.run('native:splitlinesbylength', split_params)
        print("Lines split")
        
        # Step 4: Service area analysis
        service_params = {
            'INPUT': split_result['OUTPUT'],
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
        results['service_area_lines'] = service_result['OUTPUT_LINES']
        print("Service areas created")
        
        # Step 5: Create convex hull
        convex_params = {
            'INPUT': service_result['OUTPUT_LINES'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        convex_result = processing.run('native:convexhull', convex_params)
        print("Convex hull created")
        
        # Step 6: Create concave hull
        concave_params = {
            'INPUT': service_result['OUTPUT'],
            'ALPHA': concave_threshold,
            'HOLES': False,
            'NO_MULTIGEOMETRY': False,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        concave_result = processing.run('native:concavehull', concave_params)
        print("Concave hull created")
        
        # Step 7: Clip convex hull with concave hull
        final_clip_params = {
            'INPUT': convex_result['OUTPUT'],
            'OVERLAY': concave_result['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        walksheds_result = processing.run('native:clip', final_clip_params)
        print("Final walksheds created")
        
        # Step 8: Dissolve by route
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
    """Process all routes individually"""
    
    # Get unique route values
    routes = sorted(set([f['rte'] for f in stops_layer.getFeatures()]))
    total_routes = len(routes)
    print(f"\nFound {total_routes} routes to process")
    
    # Create timestamp for this run
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Storage for all results
    all_walksheds = []
    all_dissolved = []
    all_service_lines = []
    
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
            results = create_walkshed(filtered_stops, network_layer, DISTANCE_METERS, CONCAVE_THRESHOLD)
            if results:
                all_walksheds.append(results['walksheds'])
                all_dissolved.append(results['dissolved'])
                all_service_lines.append(results['service_area_lines'])
                print(f"Route {route} processed successfully")
            else:
                print(f"Failed to process route {route}")
        except Exception as e:
            print(f"Error processing route {route}: {str(e)}")
            continue
    
    # Save final combined results
    prefix = f"{output_prefix}_" if output_prefix else ""
    outputs = {
        'walksheds': (all_walksheds, f'{prefix}walksheds_{timestamp}.gpkg'),
        'dissolved': (all_dissolved, f'{prefix}dissolved_{timestamp}.gpkg'),
        'service_lines': (all_service_lines, f'{prefix}service_lines_{timestamp}.gpkg')
    }
    
    print("\nSaving final results...")
    for output_type, (layers, filename) in outputs.items():
        output_path = os.path.join(OUTPUT_FOLDER, filename)
        processing.run("native:package", {
            'LAYERS': layers,
            'OUTPUT': output_path,
            'OVERWRITE': True
        })
        print(f"Saved {output_type} to {output_path}")

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