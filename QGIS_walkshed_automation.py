"""
Walkshed Generator Script
Iterates through routes in a stops layer and generates walksheds using the Create Walksheds model
Outputs all routes to single walksheds and dissolved files
"""
# ------------------------ CONFIGURATION --------------------------#
# Layer Names (must match exactly what appears in your Layers panel)
STOPS_LAYER_NAME = "stops_2_10"
NETWORK_LAYER_NAME = "full_ped_net"
# Processing Parameters
DISTANCE_METERS = 804.672  # walking distance for walkshed
CONCAVE_THRESHOLD = 0.015  # concave hull threshold
# Output Settings
OUTPUT_FOLDER = "C:/Users/micba/OneDrive/Documents/trimet/projects/QGIS_walkshed_automation/output"
# -------------------------------------------------------------#
from qgis.core import QgsProject, QgsProcessing, QgsProcessingFeedback, QgsVectorLayer
import processing
import os

def run_walkshed_by_route(stops_layer, network_layer, distance_meters=DISTANCE_METERS, 
                          concave_threshold=CONCAVE_THRESHOLD):
    # Get unique route values
    routes = sorted(set(f['rte'] for f in stops_layer.getFeatures()))
    print(f"Found routes: {routes}")
    
    # Create feedback object for processing
    feedback = QgsProcessingFeedback()
    
    # Ensure output directory exists
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    
    # Create temporary list to store outputs
    walksheds_list = []
    dissolved_list = []
    
    total_routes = len(routes)
    for i, route in enumerate(routes):
        feedback.pushInfo(f"Processing route {route} ({i + 1}/{total_routes})")
        
        # Create a memory layer for the filtered stops
        filtered_stops = QgsVectorLayer("Point?crs=" + stops_layer.crs().authid(), "filtered_stops", "memory")
        filtered_stops.dataProvider().addAttributes(stops_layer.fields())
        filtered_stops.updateFields()
        
        # Add features for the current route
        features = [f for f in stops_layer.getFeatures() if f['rte'] == route]
        filtered_stops.dataProvider().addFeatures(features)
        
        print(f"Processing route {route} with {len(features)} stops")
        
        # Use temporary outputs for all routes
        params = {
            'stops': filtered_stops,
            'pedestrian_network': network_layer,
            'distance_meters': distance_meters,
            'concave_hull_threshold': concave_threshold,
            'walksheds_poly': QgsProcessing.TEMPORARY_OUTPUT,
            'walksheds_dissolved': QgsProcessing.TEMPORARY_OUTPUT,
            'concave_hull': QgsProcessing.TEMPORARY_OUTPUT,
            'convex_hull': QgsProcessing.TEMPORARY_OUTPUT,
            'service_area_lines': QgsProcessing.TEMPORARY_OUTPUT,
            'service_area_nodes': QgsProcessing.TEMPORARY_OUTPUT,
            'clipped_ped_net': QgsProcessing.TEMPORARY_OUTPUT
        }
        
        try:
            # Run the model for this route's stops
            result = processing.run("model:Create Walksheds", params)
            print(f"Successfully processed route {route}")
            
            # Add results to our lists
            walksheds_list.append(result['walksheds_poly'])
            dissolved_list.append(result['walksheds_dissolved'])
            
        except Exception as e:
            feedback.pushInfo(f"Error processing route {route}: {str(e)}")
            print(f"Error processing route {route}: {str(e)}")
            continue
    
    # Merge all results at the end
    if walksheds_list:
        walksheds_final = os.path.join(OUTPUT_FOLDER, 'walksheds_all.gpkg')
        dissolved_final = os.path.join(OUTPUT_FOLDER, 'dissolved_all.gpkg')
        
        print(f"\nMerging results:")
        print(f"Walksheds to merge: {len(walksheds_list)}")
        print(f"Dissolved to merge: {len(dissolved_list)}")
        
        # Merge walksheds
        processing.run("native:mergevectorlayers", {
            'LAYERS': walksheds_list,
            'OUTPUT': walksheds_final
        })
        
        # Merge dissolved walksheds
        processing.run("native:mergevectorlayers", {
            'LAYERS': dissolved_list,
            'OUTPUT': dissolved_final
        })
        
        print(f"\nFinal outputs created:")
        print(f"- Combined walksheds: {walksheds_final}")
        print(f"- Combined dissolved walksheds: {dissolved_final}")

# Main execution
def main():
    print("Script started...")
    # Get layers
    stops_layer = QgsProject.instance().mapLayersByName(STOPS_LAYER_NAME)
    network_layer = QgsProject.instance().mapLayersByName(NETWORK_LAYER_NAME)
    # Check if layers exist
    if not stops_layer:
        print(f"Error: Could not find stops layer named '{STOPS_LAYER_NAME}'")
        return
    if not network_layer:
        print(f"Error: Could not find network layer named '{NETWORK_LAYER_NAME}'")
        return
    
    stops_layer = stops_layer[0]
    network_layer = network_layer[0]
    
    print(f"Loaded stops layer: {stops_layer.name()}, Feature count: {stops_layer.featureCount()}")
    print(f"Loaded network layer: {network_layer.name()}, Feature count: {network_layer.featureCount()}")
    print(f"Fields in stops layer: {[field.name() for field in stops_layer.fields()]}")
    
    # Run processing
    print("Processing...")
    run_walkshed_by_route(stops_layer, network_layer)
    print("Processing complete!")

# Run the script
main()