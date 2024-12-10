"""
Walkshed Generator Script with Fixed Batch Size
Processes routes in fixed-size batches to manage memory usage
"""
# ------------------------ CONFIGURATION --------------------------#
# Layer Names (must match exactly what appears in your Layers panel)
STOPS_LAYER_NAME = "stops_subset"
NETWORK_LAYER_NAME = "full_ped_net"
# Processing Parameters
DISTANCE_METERS = 804.672  # walking distance for walkshed
CONCAVE_THRESHOLD = 0.015  # concave hull threshold
# Batch Processing Settings
ROUTES_PER_BATCH = 5  # Number of routes to process in each batch
# Output Settings
OUTPUT_FOLDER = "C:/Users/micba/OneDrive/Documents/trimet/projects/QGIS_walkshed_automation/output"
OUTPUT_PREFIX = "test_"  # prefix for output files (can be empty string)
# -------------------------------------------------------------#

from qgis.core import (QgsProcessing, QgsProcessingFeedback, QgsVectorLayer,
                      QgsProject, QgsExpression)
import processing
import os
from datetime import datetime

def clean_temporary_layers():
    """Clean up temporary layers to free memory"""
    for layer in QgsProject.instance().mapLayers().values():
        if 'memory' in layer.dataProvider().dataSourceUri():
            QgsProject.instance().removeMapLayer(layer.id())

def create_walksheds(stops_layer, network_layer, distance_meters, concave_threshold, feedback):
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
        
        # Step 2: Clip network to buffer
        clip_params = {
            'INPUT': network_layer,
            'OVERLAY': buffer_result['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        clip_result = processing.run('native:clip', clip_params)
        
        # Step 3: Split lines
        split_params = {
            'INPUT': clip_result['OUTPUT'],
            'LENGTH': 100,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        split_result = processing.run('native:splitlinesbylength', split_params)
        
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
        
        # Step 5: Create convex hull
        convex_params = {
            'INPUT': service_result['OUTPUT_LINES'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        convex_result = processing.run('native:convexhull', convex_params)
        
        # Step 6: Create concave hull
        concave_params = {
            'INPUT': service_result['OUTPUT'],
            'ALPHA': concave_threshold,
            'HOLES': False,
            'NO_MULTIGEOMETRY': False,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        concave_result = processing.run('native:concavehull', concave_params)
        
        # Step 7: Clip convex hull with concave hull
        final_clip_params = {
            'INPUT': convex_result['OUTPUT'],
            'OVERLAY': concave_result['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        walksheds_result = processing.run('native:clip', final_clip_params)
        results['walksheds_poly'] = walksheds_result['OUTPUT']
        
        # Step 8: Dissolve by route
        dissolve_params = {
            'INPUT': walksheds_result['OUTPUT'],
            'FIELD': ['rte'],
            'SEPARATE_DISJOINT': False,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        dissolve_result = processing.run('native:dissolve', dissolve_params)
        results['walksheds_dissolved'] = dissolve_result['OUTPUT']
        
    except Exception as e:
        print(f"Error in create_walksheds: {str(e)}")
        results = None
        
    finally:
        # Clean up temporary layers
        clean_temporary_layers()
        
    return results

def save_batch_results(output_list, output_path):
    """Save batch results to file"""
    if output_list:
        try:
            processing.run("native:mergevectorlayers", {
                'LAYERS': output_list,
                'OUTPUT': output_path
            })
            return True
        except Exception as e:
            print(f"Error saving batch: {str(e)}")
            return False

def process_routes(stops_layer, network_layer, output_prefix="", distance_meters=DISTANCE_METERS, 
                  concave_threshold=CONCAVE_THRESHOLD):
    """Process walksheds route by route with batch processing"""
    # Get unique route values
    routes = sorted(set(f['rte'] for f in stops_layer.getFeatures()))
    total_routes = len(routes)
    
    batch_size = ROUTES_PER_BATCH
    print(f"Processing {total_routes} routes in batches of {batch_size}")
    
    # Create feedback object for processing
    feedback = QgsProcessingFeedback()
    
    # Ensure output directory exists
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    
    # Create timestamp for intermediate files
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Initialize result tracking
    batch_results = {
        'walksheds': [],
        'dissolved': [],
        'service_lines': []
    }
    
    # Process routes in batches
    for i in range(0, total_routes, batch_size):
        batch_routes = routes[i:min(i + batch_size, total_routes)]
        print(f"\nProcessing batch {i//batch_size + 1} of {(total_routes + batch_size - 1)//batch_size}")
        print(f"Routes in this batch: {batch_routes}")
        
        # Process each route in the batch
        for route in batch_routes:
            # Create filtered stops layer
            filtered_stops = QgsVectorLayer("Point?crs=" + stops_layer.crs().authid(), "filtered_stops", "memory")
            filtered_stops.dataProvider().addAttributes(stops_layer.fields())
            filtered_stops.updateFields()
            
            features = [f for f in stops_layer.getFeatures() if f['rte'] == route]
            filtered_stops.dataProvider().addFeatures(features)
            
            print(f"Processing route {route} with {len(features)} stops")
            
            try:
                results = create_walksheds(filtered_stops, network_layer, distance_meters, concave_threshold, feedback)
                if results:
                    batch_results['walksheds'].append(results['walksheds_poly'])
                    batch_results['dissolved'].append(results['walksheds_dissolved'])
                    batch_results['service_lines'].append(results['service_area_lines'])
                    print(f"Successfully processed route {route}")
            except Exception as e:
                print(f"Error processing route {route}: {str(e)}")
                continue
            finally:
                QgsProject.instance().removeMapLayer(filtered_stops)
        
        # Save intermediate results after each batch
        prefix = f"{output_prefix}_" if output_prefix else ""
        intermediate_prefix = f"{prefix}batch_{i//batch_size + 1}_{timestamp}"
        
        print("\nSaving batch results...")
        for result_type, results_list in batch_results.items():
            if results_list:
                output_path = os.path.join(OUTPUT_FOLDER, f'{intermediate_prefix}_{result_type}.gpkg')
                save_batch_results(results_list, output_path)
        
        # Clear batch results after saving
        batch_results = {'walksheds': [], 'dissolved': [], 'service_lines': []}
        clean_temporary_layers()
    
    # Merge all intermediate results
    print("\nMerging all results...")
    final_outputs = {
        'walksheds': f'{prefix}walksheds_all.gpkg',
        'dissolved': f'{prefix}dissolved_all.gpkg',
        'service_lines': f'{prefix}service_area_lines_all.gpkg'
    }
    
    for result_type, final_name in final_outputs.items():
        # Find all intermediate files for this type
        pattern = f"{output_prefix}_batch_*_{timestamp}_{result_type}.gpkg"
        intermediate_files = [os.path.join(OUTPUT_FOLDER, f) for f in os.listdir(OUTPUT_FOLDER) 
                            if f.endswith(f'_{result_type}.gpkg') and timestamp in f]
        
        if intermediate_files:
            final_path = os.path.join(OUTPUT_FOLDER, final_name)
            save_batch_results(intermediate_files, final_path)
            print(f"Created final output: {final_path}")
            
            # Clean up intermediate files
            for f in intermediate_files:
                try:
                    os.remove(f)
                except:
                    print(f"Could not remove intermediate file: {f}")

print("Script started...")
stops_layer = QgsProject.instance().mapLayersByName(STOPS_LAYER_NAME)
network_layer = QgsProject.instance().mapLayersByName(NETWORK_LAYER_NAME)

if not stops_layer:
    print(f"Error: Could not find stops layer named '{STOPS_LAYER_NAME}'")
elif not network_layer:
    print(f"Error: Could not find network layer named '{NETWORK_LAYER_NAME}'")
else:
    stops_layer = stops_layer[0]
    network_layer = network_layer[0]
    
    print(f"Loaded stops layer: {stops_layer.name()}, Feature count: {stops_layer.featureCount()}")
    print(f"Loaded network layer: {network_layer.name()}, Feature count: {network_layer.featureCount()}")
    print(f"Fields in stops layer: {[field.name() for field in stops_layer.fields()]}")
    
    print("Processing...")
    process_routes(stops_layer, network_layer, OUTPUT_PREFIX)
    print("Processing complete!")