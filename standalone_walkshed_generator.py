from qgis.core import QgsApplication, QgsVectorLayer
import sys
import os

# Initialize QGIS
qgs = QgsApplication([], False)
qgs.initQgis()

# Add the path to processing
qgis_path = os.path.join(qgs.prefixPath(), 'python', 'plugins')
sys.path.append(qgis_path)

# Now try importing processing
from qgis.analysis import QgsNativeAlgorithms
import processing
from processing.core.Processing import Processing

# Initialize processing
Processing.initialize()
QgsApplication.processingRegistry().addProvider(QgsNativeAlgorithms())

# Load a layer from file
layer_path = "C:/Users/micba/OneDrive/Documents/trimet/qgis_walkshed_automation/stops_subset.shp"
layer = QgsVectorLayer(layer_path, "stops", "ogr")

if layer.isValid():
    print("Layer loaded successfully!")
    print(f"Number of features: {layer.featureCount()}")
    print("Fields:", [field.name() for field in layer.fields()])
else:
    print("Layer failed to load!")

# Clean up
qgs.exitQgis()