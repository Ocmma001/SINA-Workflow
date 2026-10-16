# IC Netlist Generator

This module provides a computer vision-based system for converting integrated circuit schematic images into netlists using YOLO object detection, OpenCV image processing, and OCR. The system detects circuit components, analyzes wire connections, handles wire crossings, and outputs netlists as text files representing the electrical connections between components.

## **Directory Structure**

### **1. model_training**

-   Resources for training the YOLO model.
-   Contents:
    -   Datasets
    -   Data preprocessing scripts
    -   Training pipeline and configuration
    -   CVAT-to-COCO format conversion tool

### **2. program_test**

-   Tools and scripts to evaluate model performance and test netlist generation.
-   Contents:
    -   Model testing scripts
    -   Netlist generation and comparison scripts
    -   Debugging tools

### **3. current_trained_model**

-   Contains the latest trained YOLO model used for inference.

### **4. .gitignore**

-   Specifies ignored files/directories for Git.

---

# Using Pre-Trained Model

**This section is for users who want to use the existing pre-trained model without training it themselves.**

## **Prerequisites**

-   **Python 3.12** installed on your system
-   **OpenAI API key** - Required for the application to function

---

## **Project Setup Guide**

### 1) Setup and Activate Environment

Run this command with your OpenAI API key:

**Windows (Command Prompt or PowerShell):**
```bash
.\setup_windows.bat your_api_key_here
```

**Mac/Linux/Git Bash/WSL:**
```bash
source setup_unix.sh your_api_key_here
```

---

## **Getting Started**

1. Ensure the pre-trained model is available in the `current_trained_model` directory.

2. Navigate to the netlist generator directory:

   **Windows:**
   ```bash
   cd "program_test\netlist_generator_algorithm_test"
   ```

   **Mac/Linux:**
   ```bash
   cd program_test/netlist_generator_algorithm_test
   ```

3. Run the netlist generator:

   **Windows:**
   ```bash
   py netlist_generator.py
   ```

   **Mac/Linux:**
   ```bash
   python3 netlist_generator.py
   ```

---

# Training Your Own Model

**This section is for users who want to train the model themselves with their own datasets.**

## **Prerequisites**

-   **Python 3.12** installed on your system
-   **OpenAI API key** - Required for the application to function
-   **CUDA-compatible NVIDIA GPU** - Strongly recommended for training

---

## **Project Setup Guide**

### 1) Install Python

-   Download **Python 3.12** (version 3.13 may work, but revert to 3.12 if you encounter issues).

### 2) Set Up Python Virtual Environment

-   Navigate to your project folder.

-   Create a new Python virtual environment:
    -   Windows:
    ```bash
    py -m venv env_netlist
    ```
    -   macOS/Linux:
    ```bash
    python3 -m venv env_netlist
    ```

### 3) Activate the Virtual Environment

-   Windows:
```bash
env_netlist\Scripts\activate
```
-   macOS/Linux:
```bash
source env_netlist/bin/activate
```

**Note:** You'll see `(env_netlist)` before the command prompt when activated.

### 4) Install All Dependencies

**Important:** For model training, you should have a CUDA-compatible NVIDIA GPU for reasonable training times. Training on CPU is possible but will be significantly slower.

**For Windows/Linux with NVIDIA GPU (CUDA 12.4) - Recommended for Training:**
```bash
pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cu124
```

**For Windows/Linux with CPU only (Not recommended for training):**
```bash
pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu
```

**For macOS (Apple Silicon M1/M2/M3 or Intel):**
```bash
pip install -r requirements.txt
```

**Notes:**
- The command automatically upgrades pip and installs PyTorch, Ultralytics YOLO, OpenCV, EasyOCR, NumPy, and Matplotlib
- **GPU strongly recommended:** Training YOLO models requires significant computational resources. A CUDA-compatible GPU will train 10-100x faster than CPU
- macOS users with Apple Silicon get Metal Performance Shaders (MPS) support, which provides GPU acceleration
- For different CUDA versions, visit https://pytorch.org/get-started/locally/ and replace `cu124` with your version (e.g., `cu118` for CUDA 11.8)
- Verify your GPU is detected after installation by running: `python -c "import torch; print(torch.cuda.is_available())"`

### 5) Environment Setup

-   Create a `.env` file in the project root with your OpenAI API key:
    ```
    OPENAI_API_KEY=your_api_key_here
    ```

### 6) Prepare Training Data

-   Navigate to the `model_training` directory.
-   Prepare your dataset in the required format (COCO or YOLO format).
-   If using CVAT annotations, use the provided conversion tool to convert to COCO format.
-   Organize your dataset with proper train/validation/test splits.
-   Update the configuration files with your dataset paths.

### 7) Configure Training Parameters

-   Review and adjust training parameters in the training configuration files:
    -   Number of epochs
    -   Batch size
    -   Learning rate
    -   Model architecture (YOLOv8n, YOLOv8s, YOLOv8m, etc.)
    -   Image size
-   Ensure your GPU memory can handle the chosen batch size.

---

## **Getting Started**

### Training the Model

1. Navigate to the `model_training` directory.
2. Ensure your dataset is properly prepared and configured.
3. Run the training script (refer to scripts in `model_training` directory).
4. Monitor training progress and metrics.
5. Once training is complete, your model will be saved in the output directory.
6. Copy the best performing model to `current_trained_model` for inference.

### Testing Your Trained Model

1. Navigate to the `program_test` directory.
2. Run the testing scripts with your newly trained model.
3. Compare results and iterate on training if necessary.
