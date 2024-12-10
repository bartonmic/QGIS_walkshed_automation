"""
Standalone Walkshed Generator
Processes walksheds for transit stops using network analysis
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
ROUTES_PER_BATCH = 5      # number of routes to process in each batch
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
        results['walksheds_poly'] = walksheds_result['OUTPUT']
        print("Final walksheds created")
        
        # Step 8: Dissolve by route
        dissolve_params = {
            'INPUT': walksheds_result['OUTPUT'],
            'FIELD': ['rte'],
            'SEPARATE_DISJOINT': False,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        dissolve_result = processing.run('native:dissolve', dissolve_params)
        results['walksheds_dissolved'] = dissolve_result['OUTPUT']
        print("Walksheds dissolved")
        
        return results
        
    except Exception as e:
        print(f"Error in create_walkshed: {str(e)}")
        return None

# Load the layers
print("Loading layers...")
stops_layer = QgsVectorLayer(STOPS_FILE, "stops", "ogr")
network_layer = QgsVectorLayer(NETWORK_FILE, "network", "ogr")

if not stops_layer.isValid() or not network_layer.isValid():
    print("Error loading layers!")
    qgs.exitQgis()
    sys.exit(1)

print("Layers loaded successfully")

# Test with one route
print("\nTesting walkshed creation for first route...")
test_route = sorted(set([f['rte'] for f in stops_layer.getFeatures()]))[0]

# Create filtered layer for test route
filtered_stops = QgsVectorLayer("Point?crs=" + stops_layer.crs().authid(), "filtered_stops", "memory")
filtered_stops.dataProvider().addAttributes(stops_layer.fields())
filtered_stops.updateFields()

features = [f for f in stops_layer.getFeatures() if f['rte'] == test_route]
filtered_stops.dataProvider().addFeatures(features)

print(f"Processing route {test_route} with {len(features)} stops")

# Create test walkshed
results = create_walkshed(filtered_stops, network_layer, DISTANCE_METERS, CONCAVE_THRESHOLD)

if results:
    # Save test outputs
    prefix = f"{OUTPUT_PREFIX}_test_" if OUTPUT_PREFIX else "test_"
    test_outputs = {
        'walksheds': os.path.join(OUTPUT_FOLDER, f'{prefix}walksheds.gpkg'),
        'dissolved': os.path.join(OUTPUT_FOLDER, f'{prefix}dissolved.gpkg'),
        'service_lines': os.path.join(OUTPUT_FOLDER, f'{prefix}service_lines.gpkg')
    }
    
    print("\nSaving test outputs...")
    for output_type, output_path in test_outputs.items():
        processing.run("native:package", {
            'LAYERS': [results[f'walksheds_poly' if output_type == 'walksheds' else 
                              'walksheds_dissolved' if output_type == 'dissolved' else 
                              'service_area_lines']],
            'OUTPUT': output_path,
            'OVERWRITE': True
        })
        print(f"Saved {output_type} to {output_path}")

# Clean up
qgs.exitQgis()
print("\nProcessing complete!")