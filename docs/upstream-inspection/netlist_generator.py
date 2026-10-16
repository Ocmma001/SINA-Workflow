#  Generates netlist using the latest trained object detection model

import os
from helper_files.process_images import process_all_images
from helper_files.generate_netlists import generate_all_netlists

if __name__ == '__main__':
    # Get the directory of this script (now one level higher)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    PROJECT_PATH = os.path.dirname(os.path.dirname(script_dir))  # Two levels up from script

    # Construct paths based on new script location
    model_folder = os.path.join(PROJECT_PATH, 'current_trained_model')
    train_folders = [folder for folder in os.listdir(model_folder) if folder.startswith('train')]

    if not train_folders:
        raise FileNotFoundError("No 'train' folders found in the directory.")

    def extract_suffix(folder_name):
        if folder_name == "train":
            return 0
        else:
            return int(folder_name[5:])

    latest_train_folder = max(train_folders, key=extract_suffix)
    latest_train_path = os.path.join(model_folder, latest_train_folder, 'weights', 'last.pt')

    test_images_folder = os.path.join(script_dir, 'inputs', 'test_images')
    output_files_path = os.path.join(script_dir, 'outputs', 'debugging')
    test_results_path = os.path.join(script_dir, 'outputs', 'test_results')

    # Step 1: Detect components and generate connection points (with crossing detection enabled)
    process_all_images(test_images_folder, latest_train_path, output_files_path, use_ocr=True, use_gpu=True, detect_crossings=True)

    # Step 2: Generate netlists from connection points (with test_netlist enabled)
    approved_images_path = os.path.join(script_dir, 'outputs', 'approved_images')
    generate_all_netlists(approved_images_path, output_files_path, test_results_path, create_test_netlist=True)