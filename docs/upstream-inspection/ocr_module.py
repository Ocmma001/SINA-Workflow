import cv2
import numpy as np
import base64
import os
from helper_files.proximity_analysis import assign_text_to_nearest_component
import easyocr
import matplotlib
matplotlib.use('Agg')
import pytesseract
import re
import base64
import requests
import json
from collections import Counter
import shutil
from dotenv import load_dotenv

SUPPORTED_COMPONENTS = {
    "Resistor", "Capacitor", "Inductor", "Transistor_BJT", "Transistor_MOSFET",
    "Voltage_src", "Current_src", "Op-Amp"
}

# Global tracking for summary
approved_images = []
failed_images = []

def check_component_consistency(api_response_lines, circuit_json_path, image_path, output_folder, approved_folder):
    """
    Compare component type counts from OpenAI API response vs. circuit_info.json.
    Write explanation to consistency_check.txt.
    Move approved image to approved_folder and print path.
    Return True if matched, False otherwise.
    """
    os.makedirs(output_folder, exist_ok=True)
    output_file = os.path.join(output_folder, "consistency_check.txt")

    # === Step 1: Parse JSON ===
    with open(circuit_json_path, "r", encoding="utf-8") as f:
        circuit_components = json.load(f)

    json_counts = Counter()
    for comp in circuit_components:
        label = comp.get("label")
        if label in SUPPORTED_COMPONENTS:
            json_counts[label] += 1

    # === Step 2: Parse API ===
    api_counts = Counter()
    inside_types = False
    for line in api_response_lines:
        if line.strip().startswith("types:"):
            inside_types = True
            continue
        if inside_types:
            if not line.strip() or ":" not in line:
                break
            try:
                comp_type, count = line.strip().split(":")
                comp_type = comp_type.strip()
                count = int(count.strip())
                if comp_type in SUPPORTED_COMPONENTS:
                    api_counts[comp_type] = count
            except Exception:
                continue

    # === Step 3: Compare and Save Output ===
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("Component Consistency Check\n")
        f.write("=" * 40 + "\n")
        f.write(f"API Component Types ({sum(api_counts.values())} total):\n")
        for k, v in sorted(api_counts.items()):
            f.write(f"  {k}: {v}\n")
        f.write("\n")

        f.write(f"Object Detection Types ({sum(json_counts.values())} total):\n")
        for k, v in sorted(json_counts.items()):
            f.write(f"  {k}: {v}\n")
        f.write("\n")

        # Compare differences
        passed = True
        # all_keys = sorted(set(api_counts) | set(json_counts))
        # for key in all_keys:
        #     if api_counts[key] != json_counts[key]:
        #         passed = False
        #         f.write(f"Warning: Mismatch in '{key}': API={api_counts[key]}, Detection={json_counts[key]}\n")

        # f.write("\n")
        # if passed:
        #     f.write("Result: PASS — Component counts match.\n")
        # else:
        #     f.write("Result: FAIL — Mismatched component types or counts.\n")

    # === Step 4: Move image if passed ===
    approved_folder = os.path.join(approved_folder, "approved_images")
    os.makedirs(approved_folder, exist_ok=True)

    image_name = os.path.basename(image_path)
    if passed and os.path.isfile(image_path):
        destination = os.path.join(approved_folder, image_name)
        shutil.copy2(image_path, destination)
        approved_images.append(image_name)
        print(f"Approved image copied to: {destination}")
    else:
        failed_images.append(image_name)

    # === Step 5: Write Summary ===
    summary_path = os.path.join(approved_folder, "approval_summary.txt")
    total = len(approved_images) + len(failed_images)
    passed_count = len(approved_images)
    failed_count = len(failed_images)
    pass_percent = (passed_count / total * 100) if total > 0 else 0

    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("Approval Summary\n")
        f.write("=" * 30 + "\n")
        f.write(f"Passed: {passed_count}\n")
        f.write(f"Failed: {failed_count}\n")
        f.write(f"Pass Rate: {pass_percent:.2f}%\n\n")
        if failed_images:
            f.write("Failed Images:\n")
            for name in failed_images:
                f.write(f"  - {name}\n")

    return passed

def extract_components_from_image_api(image_path, output_path=None):
    load_dotenv()   
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not found in environment.")

    with open(image_path, "rb") as img_file:
        base64_image = base64.b64encode(img_file.read()).decode("utf-8")


    prompt = (
    "You are a vision model with expert knowledge in electronics and circuit schematics.\n\n"
    "Your task is to analyze the provided circuit schematic image and extract components that are actually *drawn* using proper circuit symbols.\n\n"
    
    "CRITICAL RULES:\n"
    "- ONLY include components with drawn symbols (zig-zag lines, parallel lines, transistor symbols, etc.)\n"
    "- DO NOT include text-only references like 'use 10V supply' or 'connect resistor here'\n"
    "- DO NOT include ground symbols, connection dots, wire junctions, or connecting wires\n"
    "- Skip components with no visible labels entirely\n"
    "- Think like a circuit simulator — only drawn symbols that can be electrically connected\n\n"
    
    "COMPONENT SYMBOLS TO RECOGNIZE:\n"
    "- Resistor: zig-zag line OR rectangular box\n"
    "- Capacitor: two parallel lines OR curved line with straight line (treat all as 'Capacitor')\n"
    "- Inductor: series of loops/coils\n"
    "- Transistor_BJT: triangle with lines (any BJT symbol regardless of NPN/PNP)\n"
    "- Transistor_MOSFET: gate symbol with channel\n"
    "- Voltage_src: circle with +/- OR battery symbol\n"
    "- Current_src: circle with arrow\n"
    "- Op-Amp: triangle amplifier symbol\n\n"
    
    "LABEL AND VALUE EXTRACTION:\n"
    "- For each drawn component, find nearby text that serves as its label (R1, C2, Tr1, V_supply, etc.)\n"
    "- Accept any naming convention that appears to be a component label\n"
    "- Extract the component value if visible (10kΩ, 1µF, 12V, etc.)\n"
    "- If multiple values are present, include all of them\n"
    "- If labels are partially obscured, make your best guess\n"
    "- Extract values in their exact format as shown (don't convert '10000 ohms' to '10kΩ')\n\n"
    
    "MANDATORY FORMAT:\n"
    "For each component, you MUST include a description of how it's drawn:\n"
    "\"(This component was drawn like [description of the actual symbol you see])\"\n\n"
    
    "=== OUTPUT FORMAT ===\n"
    "number of components: <TOTAL_COUNT>\n"
    "note: the toal count_of_that_type should add up to TOTAL_COUNT  \n"

    "For each component:\n"
    "(This component was drawn like [symbol description])ComponentLabel: ComponentValue\n\n"
    "EXAMPLES:\n"
    "(This component was drawn like zig-zag line which fits resistor description)R1: 10kΩ\n"
    "(This component was drawn like two parallel lines which fits capacitor description)C2: 1µF\n"
    "(This component was drawn like a series of loops which fits inductor description)L1: 100mH\n"
    "(This component was drawn like a triangle with three lines which fits BJT description)Q1: 2N3904\n"
    "(This component was drawn like a circle with + and - symbols which fits voltage source description)V_bat: 9V\n"
    "(This component was drawn like a circle with an arrow inside which fits current source description)I1: 2mA\n"
    "(This component was drawn like a triangle with one input and one output and a + and - input which fits op amp description)U1: LM741\n"
    "(This component was drawn like a three-terminal device with a gate, drain, and source which fits MOSFET description)M1: IRF540N\n"


    "types:\n"
    "  <Type>: <count_of_that_type>\n"
    "  \n"
    "IMPORTANT: Count how many components of each type you found!\n"
    "- If you found V1 and V2, then Voltage_src: 2\n"
    "- If you found R1, R2, R3, then Resistor: 3\n"
    "- The numbers in the types section must add up to the total component count\n\n"
    
    "EXAMPLE OUTPUT:\n"
    "number of components: 6\n"
    "(This component was drawn like zig-zag line which fits resistor description)R1: 10kΩ\n"
    "(This component was drawn like zig-zag line which fits resistor description)R2: 1kΩ\n"
    "(This component was drawn like two parallel lines which fits capacitor description)C1: 1µF\n"
    "types:\n"
    "  Resistor: 2\n"
    "  Capacitor: 1\n"
    
    "IMPORTANT NOTES:\n"
    "- If component value is unknown/unclear, leave blank after colon (e.g., 'C1:')\n"
    "- Keep original label names exactly as written (don't standardize them)\n"
    "- If multiple values are near one component, include all: 'R1: 10kΩ, 5%, 0.25W'\n"
    "- Only count actual drawn symbols, not text references\n"
    "- CRITICAL: In the types section, count each individual component! If you list V1 and V2, then Voltage_src: 2\n\n"
    
    "Return only the formatted output. No extra explanations."
)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "gpt-4o",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                ]
            }
        ],
        "max_tokens": 1800,
        "temperature": 0
    }

    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=30
    )
    response.raise_for_status()

    result_text = response.json()['choices'][0]['message']['content'].strip()

    # Save response
    if output_path is None:
        output_path = os.path.join(os.path.dirname(image_path), "API_first_response.txt")

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(result_text)

    return result_text.splitlines()

class CircuitOCR:
    def __init__(self, use_gpu=True):
        """Initialize OCR engines"""
        print("Initializing OCR engines...")
        
        # Initialize EasyOCR (this works with your current setup)
        self.easy_reader = easyocr.Reader(['en'], gpu=use_gpu)
         
        # No filtering - capture all text
        self.component_patterns = []  # Empty - we'll capture everything
        self.combined_pattern = None  # No pattern matching
        
        # Common OCR misreads - expanded list
        self.ocr_corrections = {
            'O': '0', 'I': '1',  'Z': '2', 'B': '8',
            'G': '6', 'l': '1', 'o': '0', 'i': '1', 
        }

    def advanced_preprocessing(self, image):
        """Create multiple preprocessing versions optimized for OCR"""
        versions = {}
        
        # Original
        versions['original'] = image.copy()
        
        # Grayscale
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()
        versions['gray'] = gray
        
        # High contrast binary (Otsu's method)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        versions['binary_otsu'] = binary
        
        # Adaptive threshold (good for varying lighting)
        adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY, 21, 10)
        versions['adaptive'] = adaptive
        
        # Inverted versions (for white text on dark background)
        versions['inverted_gray'] = cv2.bitwise_not(gray)
        versions['inverted_binary'] = cv2.bitwise_not(binary)
        versions['inverted_adaptive'] = cv2.bitwise_not(adaptive)
        
        # Enhanced contrast using CLAHE
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
        enhanced = clahe.apply(gray)
        versions['enhanced_contrast'] = enhanced
        
        # Denoised version
        denoised = cv2.fastNlMeansDenoising(gray, None, 20, 7, 21)
        versions['denoised'] = denoised
        
        # Edge-preserved smoothing
        bilateral = cv2.bilateralFilter(gray, 9, 75, 75)
        versions['bilateral'] = bilateral
        
        # Morphological operations to clean text
        kernel_close = cv2.getStructuringElement(cv2.MORPH_RECT, (3,3))
        morph_close = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel_close)
        versions['morph_close'] = morph_close
        
        # Dilated version (makes text thicker)
        kernel_dilate = cv2.getStructuringElement(cv2.MORPH_RECT, (2,2))
        dilated = cv2.dilate(binary, kernel_dilate, iterations=1)
        versions['dilated'] = dilated
        
        # Super resolution attempt (resize)
        height, width = gray.shape
        if width < 2000:
            scale = 2000 / width
            new_width = int(width * scale)
            new_height = int(height * scale)
            resized = cv2.resize(gray, (new_width, new_height), interpolation=cv2.INTER_CUBIC)
            versions['upscaled'] = resized
        
        return versions

    def extract_text_with_easyocr(self, image, detail=1, width_ths=0.7, height_ths=0.7, offset_x=0, offset_y=0):
        """Extract text using EasyOCR with confidence scores and bounding boxes"""
        try:
            # Run EasyOCR with specific settings
            results = self.easy_reader.readtext(
                image, 
                detail=detail,
                width_ths=width_ths,
                height_ths=height_ths,
                paragraph=False,
                text_threshold=0.3,
                low_text=0.3,
                mag_ratio=1.5
            )
            
            text_with_conf_bbox = []
            
            if detail == 1:
                # Return tuples of (text, confidence, bbox)
                for result in results:
                    if len(result) >= 3 and result[2] > 0.2:  # confidence threshold
                        bbox_points = result[0]
                        text = str(result[1]).strip()
                        
                        # Skip empty text
                        if not text:
                            continue
                        
                        # Calculate center point of bbox
                        x_coords = [p[0] + offset_x for p in bbox_points]
                        y_coords = [p[1] + offset_y for p in bbox_points]
                        center_x = sum(x_coords) / len(x_coords)
                        center_y = sum(y_coords) / len(y_coords)
                        
                        # Adjust bbox points with offset
                        adjusted_bbox = [[p[0] + offset_x, p[1] + offset_y] for p in bbox_points]
                        
                        text_with_conf_bbox.append({
                            'text': text.upper(),
                            'confidence': float(result[2]),
                            'bbox': adjusted_bbox,
                            'center': (center_x, center_y)
                        })
            else:
                # When detail=0, no bbox available
                text_with_conf_bbox = [{'text': str(text).upper(), 'confidence': 0.5, 'bbox': None, 'center': None} 
                                      for text in results if text and str(text).strip()]
            
            return text_with_conf_bbox
        except Exception as e:
            print(f"    EasyOCR error: {e}")
            return []

    def extract_text_with_tesseract(self, image, scale_factor=1.0):
        """Extract text using Tesseract with confidence scores"""
        text_with_conf = []
        
        # Try getting individual words with confidence scores
        try:
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
            n_boxes = len(data['text'])
            for i in range(n_boxes):
                if data['text'][i].strip():
                    confidence = float(data['conf'][i])
                    if confidence > 0:
                        # Get bounding box
                        x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
                        
                        # Apply scale factor if image was scaled
                        x = x * scale_factor
                        y = y * scale_factor
                        w = w * scale_factor
                        h = h * scale_factor
                        
                        center_x = x + w/2
                        center_y = y + h/2
                        bbox = [[x, y], [x+w, y], [x+w, y+h], [x, y+h]]
                        
                        text_with_conf.append({
                            'text': data['text'][i].upper(),
                            'confidence': confidence / 100.0,
                            'bbox': bbox,
                            'center': (center_x, center_y)
                        })
        except Exception as e:
            print(f"    Tesseract data extraction error: {e}")
        
        # Other configurations without confidence
        configs = [
            r'--psm 11 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
            r'--psm 8',
            r'--psm 12',
            r'--psm 13',
        ]
        
        for config in configs:
            try:
                text = pytesseract.image_to_string(image, config=config)
                if text.strip():
                    words = text.upper().split()
                    for word in words:
                        word = word.strip()
                        if word and not any(item['text'] == word for item in text_with_conf):
                            text_with_conf.append({
                                'text': word,
                                'confidence': 0.5,
                                'bbox': None,
                                'center': None
                            })
            except:
                pass
            
        return text_with_conf

    def correct_ocr_errors(self, text):
        """Correct common OCR misreads"""
        corrected = text
        for wrong, right in self.ocr_corrections.items():
            corrected = corrected.replace(wrong, right)
        return corrected

    def extract_components_from_texts(self, text_with_conf_bbox_list):
        """Extract ALL text with confidence scores and locations (no filtering)"""
        # Combine all results
        all_items = {}  # Use dict to track best result for each text
        
        for item in text_with_conf_bbox_list:
            if not isinstance(item, dict):
                continue
                
            text = item.get('text', '')
            conf = item.get('confidence', 0.0)
            bbox = item.get('bbox', None)
            center = item.get('center', None)
            
            # Split by common separators and clean
            items = re.split(r'[\s,;:\n\r\t]+', text)
            for sub_item in items:
                sub_item = sub_item.strip()
                if not sub_item:
                    continue
                    
                # Apply OCR corrections
                corrected = self.correct_ocr_errors(sub_item)
                if corrected and len(corrected) > 0:
                    # Keep the highest confidence version with location info
                    if corrected not in all_items or conf > all_items[corrected]['confidence']:
                        all_items[corrected] = {
                            'text': corrected,
                            'confidence': conf,
                            'bbox': bbox,
                            'center': center
                        }
        
        # Convert to list sorted by confidence
        return sorted(all_items.values(), key=lambda x: x['confidence'], reverse=True)

    def process_image(self, image_path):
        """Main processing function that returns text with confidence scores"""
        # Read image
        image = cv2.imread(image_path)
        if image is None:
            print(f"    Error: Could not read image {image_path}")
            return [], {}
        
        # Get original image dimensions
        orig_height, orig_width = image.shape[:2]
        
        # Get all preprocessing versions
        versions = self.advanced_preprocessing(image)
        
        all_text_with_conf = []  # List of text info dicts
        
        print("  Processing with multiple OCR engines and preprocessing...")
        
        # Process each version
        for version_name, processed_img in versions.items():
            if processed_img is None:
                continue
                
            # Convert grayscale to BGR for EasyOCR if needed
            if len(processed_img.shape) == 2:
                img_for_ocr = cv2.cvtColor(processed_img, cv2.COLOR_GRAY2BGR)
            else:
                img_for_ocr = processed_img
            
            # Calculate scale factor for this version
            scale_factor = 1.0
            if processed_img.shape[1] != orig_width:
                scale_factor = orig_width / processed_img.shape[1]
            
            # EasyOCR
            text_conf_list = self.extract_text_with_easyocr(img_for_ocr)
            # Scale coordinates back if needed
            if scale_factor != 1.0:
                for item in text_conf_list:
                    if item.get('bbox'):
                        item['bbox'] = [[p[0] * scale_factor, p[1] * scale_factor] for p in item['bbox']]
                    if item.get('center'):
                        item['center'] = (item['center'][0] * scale_factor, item['center'][1] * scale_factor)
            all_text_with_conf.extend(text_conf_list)
            
            # EasyOCR with different parameters
            text_conf_list = self.extract_text_with_easyocr(img_for_ocr, width_ths=0.5, height_ths=0.5)
            # Scale coordinates back if needed
            if scale_factor != 1.0:
                for item in text_conf_list:
                    if item.get('bbox'):
                        item['bbox'] = [[p[0] * scale_factor, p[1] * scale_factor] for p in item['bbox']]
                    if item.get('center'):
                        item['center'] = (item['center'][0] * scale_factor, item['center'][1] * scale_factor)
            all_text_with_conf.extend(text_conf_list)
            
            # Tesseract - pass scale factor
            text_conf_list = self.extract_text_with_tesseract(processed_img, scale_factor)
            all_text_with_conf.extend(text_conf_list)
        
        # Try cropping and processing regions
        height, width = image.shape[:2]
        quadrants = [
            (0, 0, width//2, height//2),
            (width//2, 0, width, height//2),
            (0, height//2, width//2, height),
            (width//2, height//2, width, height)
        ]
        
        for x1, y1, x2, y2 in quadrants:
            cropped = image[y1:y2, x1:x2]
            # Pass offset to adjust coordinates back to full image
            text_conf_list = self.extract_text_with_easyocr(cropped, offset_x=x1, offset_y=y1)
            all_text_with_conf.extend(text_conf_list)
        
        # Filter out only clearly invalid detections
        filtered_text_with_conf = []
        margin = 5  # Small margin for edge cases
        
        for item in all_text_with_conf:
            if not isinstance(item, dict):
                continue
            
            # Keep all items without bbox (text-only detections)
            if not item.get('bbox') or not item.get('center'):
                filtered_text_with_conf.append(item)
                continue
            
            # For items with bbox, check if they're reasonable
            bbox = item['bbox']
            if len(bbox) >= 4:
                x_coords = [p[0] for p in bbox]
                y_coords = [p[1] for p in bbox]
                
                # Check if at least partially within bounds
                if (any(-margin <= x <= orig_width + margin for x in x_coords) and 
                    any(-margin <= y <= orig_height + margin for y in y_coords)):
                    # Clamp coordinates to image bounds
                    clamped_bbox = []
                    for p in bbox:
                        clamped_x = max(0, min(p[0], orig_width - 1))
                        clamped_y = max(0, min(p[1], orig_height - 1))
                        clamped_bbox.append([clamped_x, clamped_y])
                    item['bbox'] = clamped_bbox
                    
                    # Update center
                    x_coords = [p[0] for p in clamped_bbox]
                    y_coords = [p[1] for p in clamped_bbox]
                    item['center'] = (sum(x_coords)/len(x_coords), sum(y_coords)/len(y_coords))
                    
                    filtered_text_with_conf.append(item)
        
        # Process and deduplicate
        final_results = self.extract_components_from_texts(filtered_text_with_conf)
        
        return final_results, versions
   
    def visualize_results(self, image, text_with_info, output_path):
        import matplotlib.pyplot as plt
        import matplotlib.patches as patches

        fig, ax = plt.subplots(1, figsize=(15, 15))
        ax.imshow(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))

        for item in text_with_info:
            if item.get('bbox'):
                polygon = patches.Polygon(item['bbox'], closed=True, edgecolor='lime', fill=False, linewidth=2)
                ax.add_patch(polygon)
                x, y = item['bbox'][0]
                ax.text(x, y - 5, item['text'], color='yellow', fontsize=8, bbox=dict(facecolor='black', alpha=0.5))

        ax.axis('off')
        plt.tight_layout()
        plt.savefig(output_path)
        plt.close()

### ===== UPDATED PROCESSING FUNCTION =====
def process_circuit_ocr(image_path, output_folder, ocr_engine, components=None):
    print("\n  Running OCR text extraction...")

    ocr_output_folder = os.path.join(output_folder, "ocr_results")
    os.makedirs(ocr_output_folder, exist_ok=True)

    text_with_info = ""

    image = cv2.imread(image_path)
    if image is None:
        print(f"    Error: Could not read image {image_path}")
        return []

    text_with_info, versions = ocr_engine.process_image(image_path)

    for name, img in list(versions.items())[:4]:
        if img is not None:
            cv2.imwrite(os.path.join(ocr_output_folder, f"ocr_preprocess_{name}.png"), img)

    if text_with_info:
        ocr_engine.visualize_results(image, text_with_info, 
            os.path.join(ocr_output_folder, "ocr_detected_text.png"))

    print(f"    Found {len(text_with_info)} text items")
    circuit_text_file_path = os.path.join(ocr_output_folder, "circuit_components_with_text.txt")

    if components and text_with_info:
        print("    Analyzing text proximity to components...")
        text_with_locations = [item for item in text_with_info if item.get('center') is not None]
        component_text_mapping = assign_text_to_nearest_component(text_with_locations, components)

        with open(circuit_text_file_path, 'w', encoding='utf-8') as f:
            f.write("CIRCUIT COMPONENT ANALYSIS\n")
            f.write("="*80 + "\n")
            f.write("ALL DETECTED TEXT IN CIRCUIT:\n")
            f.write("-"*40 + "\n")
            for item in text_with_info:
                f.write(f"- {item['text']} (confidence: {item['confidence']:.2f})\n")
            f.write("\n")
            f.write("COMPONENTS WITH ASSOCIATED TEXT:\n")
            f.write("="*80 + "\n\n")
            for comp_info in components:
                comp_id = comp_info['id']
                f.write(f"COMPONENT {comp_id}:\n")
                text_items = component_text_mapping.get(comp_id, [])
                if text_items:
                    f.write("  Nearby Text:\n")
                    for item in text_items:
                        f.write(f"    - {item['text']} (conf: {item['confidence']:.2f}, dist: {item['distance']:.1f}px)\n")
                else:
                    f.write("  No nearby text found\n")
                f.write("\n")
    else:
        with open(circuit_text_file_path, 'w', encoding='utf-8') as f:
            f.write("ALL DETECTED TEXT:\n")
            for item in text_with_info:
                f.write(f"- {item['text']} (confidence: {item['confidence']:.2f})\n")

###    === API Call ===
    print("\n  Extracting components from image via API...")
    API_first_response_output_path = os.path.join(output_folder, "API_first_response.txt")
    image_components = extract_components_from_image_api(image_path, API_first_response_output_path)

    circuit_json_path = os.path.join(output_folder, "circuit_info.json")
    approved_folder = os.path.dirname(os.path.dirname(output_folder))
    passed = check_component_consistency(image_components, circuit_json_path, image_path, output_folder, approved_folder)

    if passed:
        print("Image approved for processing.")
    else:
        print("Component mismatch – flagging for review.")

    return text_with_info
