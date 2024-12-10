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

# Test loading both layers
print("Testing layer loading...")

stops_layer = QgsVectorLayer(STOPS_FILE, "stops", "ogr")
if stops_layer.isValid():
    print("Stops layer loaded successfully!")
    print(f"Number of stops: {stops_layer.featureCount()}")
    print("First few routes:", sorted(set([f['rte'] for f in stops_layer.getFeatures()]))[:5])
else:
    print("Failed to load stops layer!")

network_layer = QgsVectorLayer(NETWORK_FILE, "network", "ogr")
if network_layer.isValid():
    print("\nNetwork layer loaded successfully!")
    print(f"Number of features: {network_layer.featureCount()}")
else:
    print("\nFailed to load network layer!")

# Test output folder
print(f"\nChecking output folder...")
if not os.path.exists(OUTPUT_FOLDER):
    try:
        os.makedirs(OUTPUT_FOLDER)
        print("Created output folder")
    except Exception as e:
        print(f"Error creating output folder: {str(e)}")
else:
    print("Output folder exists")

# Clean up
qgs.exitQgis()