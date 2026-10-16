import numpy as np
import os
from scipy.spatial import distance
import cv2
import json
import re
from dotenv import load_dotenv
import base64
import requests
import time

def fix_mosfet_nodes(netlist_lines):
    """
    Post-process netlist to ensure all MOSFETs have 4 nodes.
    Fixes cases where VLM outputs only 3 nodes.

    Args:
        netlist_lines: List of netlist lines

    Returns:
        List of corrected netlist lines
    """
    fixed_lines = []
    for line in netlist_lines:
        # Skip directive lines and comments
        if line.startswith('.') or line.startswith('*'):
            fixed_lines.append(line)
            continue

        # Check if this is a MOSFET line (starts with M)
        if re.match(r'^M\w+\s+', line, re.IGNORECASE):
            parts = line.split()

            # Check node count (parts[0]=name, parts[1-3 or 1-4]=nodes, last=model)
            # Valid MOSFET: Mname node1 node2 node3 node4 model
            # Invalid MOSFET: Mname node1 node2 node3 model (only 3 nodes)

            if len(parts) == 5:  # Mname + 3 nodes + model = 5 parts
                # This is a 3-node MOSFET - need to add Bulk
                name = parts[0]
                node1, node2, node3 = parts[1], parts[2], parts[3]
                model = parts[4]

                # Determine if NMOS or PMOS based on model name
                if 'PMOS' in model.upper():
                    # PMOS: Bulk = Source (node3)
                    bulk = node3
                else:
                    # NMOS (default): Bulk = 0
                    bulk = '0'

                # Reconstruct line with 4 nodes
                fixed_line = f"{name} {node1} {node2} {node3} {bulk} {model}"
                print(f"  Fixed MOSFET: '{line}' → '{fixed_line}'")
                fixed_lines.append(fixed_line)
            else:
                # Already has 4 nodes or different format - keep as is
                fixed_lines.append(line)
        else:
            # Not a MOSFET - keep as is
            fixed_lines.append(line)

    return fixed_lines

def generate_named_netlist(raw_netlist_lines, api_lines, ocr_text, image_path=None):
    """
    Replace internal component IDs in the netlist with real labels and values
    using the API response and OCR results. Includes reasoning per component.

    Returns:
        tuple: (final_netlist_lines, ground_node_number)
            - final_netlist_lines: List of SPICE netlist lines
            - ground_node_number: VLM-identified ground node (int or None)
    """
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not found in environment.")

    # Combine raw netlist into text
    raw_netlist_text = "\n".join(raw_netlist_lines)

    # Extract only lines that contain label:value format
    label_lines = [line for line in api_lines if re.search(r"\)\s*[A-Za-z]+\d*:", line)]

    # Remove any parenthetical description before the label
    cleaned_label_lines = [re.sub(r"^\(.*?\)", "", line).strip() for line in label_lines]
    component_label_text = "\n".join(cleaned_label_lines)

    # Optional image attachment
    image_block = []
    if image_path and os.path.isfile(image_path):
        with open(image_path, "rb") as img_file:
            base64_image = base64.b64encode(img_file.read()).decode("utf-8")
        image_block.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
        })


    prompt = (
    "You are a circuit assistant tasked with transforming a raw netlist into a labeled and value-annotated LTspice netlist.\n\n"
    "You are provided with the following data:\n"
    "- A RAW NETLIST showing internal component IDs and their node connections. Example: `Resistor_1 1 2`\n"
    "- A LABEL:VALUE list from an API vision model. Each line may have parenthetical descriptions before the label — ignore these completely. Example: `(This component was drawn like two parallel lines which fits capacitor description)C3: 100uF`\n"
    "- OCR results showing detected text with confidence scores, organized by component and proximity.\n\n"

    "\n"
    "CRITICAL OUTPUT RULES - READ FIRST\n"
     "\n"
    "Before processing anything, memorize these non-negotiable rules:\n\n"

    "1. MOSFET MANDATORY 4-NODE FORMAT:\n"
    "   ALL M devices MUST have exactly 4 nodes: Mname Drain Gate Source Bulk Model\n"
    "   - If raw netlist shows only 3 nodes, YOU MUST ADD the 4th Bulk node:\n"
    "     * NMOS devices: Add 0 as Bulk → Example: M1 3 2 1 0 NMOS1\n"
    "     * PMOS devices: Duplicate Source as Bulk → Example: M2 3 2 1 1 PMOS1\n"
    "   - NEVER output a MOSFET with fewer than 4 nodes.\n\n"

    "2. DO NOT DUPLICATE SPICE PREFIXES:\n"
    "   If label already starts with correct prefix, use it as-is:\n"
    "   - Use 'R1' NOT 'RR1', 'C3' NOT 'CC3', 'Q2' NOT 'QQ2', 'M1' NOT 'MM1'\n\n"

    "\n\n"

    "Your job is to:\n"
    "1. Parse the LABEL:VALUE list. For each line, extract only the component label and its value after the colon. Completely ignore any parenthetical text before the label.\n\n"
    
    "INTERNAL ID WARNING (CRITICAL):\n"
    "The RAW NETLIST component IDs (e.g., Resistor_1, Capacitor_2, VoltageSource_3, Transistor_BJT_1, MOSFET_1) are INTERNAL placeholders only.\n"
    "They are NOT the same as schematic labels (R1, R2, R3, C1, Q1, M1, etc.).\n"
    "The numeric suffix in an internal ID (e.g., the '1' in Resistor_1) has NO relationship to the schematic label number (e.g., R1).\n"
    "Therefore:\n"
    "  - NEVER use the internal ID number to guess or force the real label number.\n"
    "  - NEVER assume Resistor_1 corresponds to R1, Capacitor_2 corresponds to C2, etc.\n"
    "  - Use internal IDs ONLY to determine component TYPE (resistor vs capacitor vs transistor) and to link OCR proximity data for that same internal ID.\n"
    "All real labels MUST come from the API LABEL:VALUE mapping and/or OCR evidence, not from the internal ID numbering.\n\n"

    "2. For each component in the RAW NETLIST:\n"
    "   a) LABEL MATCHING: Find the real-world label using this process:\n"
    "      - Start with API labels for components of the same type\n"
    "      - Consider OCR text near that component ID as helpful guidance when available\n"
    "      - OCR provides valuable hints but is not always accurate (~90%) - weigh OCR evidence alongside other factors\n"
    "      - When OCR strongly suggests a specific label (high confidence, clear match), give it significant consideration\n"
    "      - When OCR is unclear or conflicts with logical assignment patterns, rely more on API reasoning\n"
    "      - Use case-insensitive comparison and partial matching for OCR hints\n"
    "      - Example: Transistor_BJT_1 has nearby OCR 'Q1' (95% confidence) → this strongly suggests label Q1\n"
    "      - Example: Transistor_BJT_2 has nearby OCR 'T_' (low confidence) → use as weak hint, rely more on API logic\n\n"
    
    "   b) VALUE ASSIGNMENT: Determine the component value using this priority:\n"
    "      - PRIMARY: Use the API's value for the matched label as the default\n"
    "      - VALIDATION: Check if the API value makes sense for the component type:\n"
    "        * Resistors should have resistance values (Ω, kΩ, MΩ)\n"
    "        * Capacitors should have capacitance values (F, uF, nF, pF)\n"
    "        * Voltage sources should have voltage values (V, mV)\n"
    "        * Current sources should have current values (A, mA, uA)\n"
    "      - ASSISTANCE: Use OCR text near the component as hints to help confirm, enhance, or correct values\n"
    "      - CORRECTION: If API value doesn't make sense, look for value hints in OCR near the component\n"
    "      - ENHANCEMENT: If API has label but no value, use OCR value hints if they make sense for the component\n\n"

    "3. IMPORTANT GUIDELINES:\n"
    "   - Balance API reasoning with OCR guidance - neither should be ignored\n"
    "   - OCR provides valuable hints (~90% accuracy) but should be weighed against logical patterns\n"
    "   - Strong OCR evidence (high confidence, clear text) should influence assignments significantly\n"
    "   - Weak OCR evidence (low confidence, unclear text) should be treated as minor hints\n"
    "   - Consider OCR confidence scores when available to gauge reliability\n"
    "   - For components without useful OCR hints, rely on API reasoning and assignment patterns\n"
    "   - Do NOT invent any labels or values not supported by the data\n"
    "   - Always validate that values make sense for the component type\n\n"

    "4. FINAL REVIEW STEP:\n"
    "   - Before submitting your answer, review your complete netlist for consistency\n"
    "   - Check that no component labels are duplicated (e.g., two different components both labeled Q1)\n"
    "   - Ensure all available labels of each type are used before any duplicates occur\n"
    "   - Verify that component types have the correct SPICE prefix (transistors need Q prefix, resistors need R prefix, etc.)\n"
    "   - If you find duplicates, reassign one of them to an unused label of the same type\n\n"

    "5. GENERIC TRANSISTOR MODEL HANDLING (LTspice):\n"
    "The RAW NETLIST may contain BJTs and MOSFETs whose model names are missing or not defined by any .model line.\n"
    "Your output MUST be simulatable in LTspice.\n"
    "A) If a BJT (Q-device) references a model name that is NOT defined anywhere in the netlist:\n"
    "   - Ensure the Q-device line ends with a model name token.\n"
    "   - Use the generic model name `QMOD` for all such undefined NPN BJTs unless a different valid model is explicitly provided.\n"
    "   - Append exactly one model definition (only if needed):\n"
    "     .model QMOD NPN(BF=100 IS=1e-14)\n"
    "B) If a MOSFET (M-device) references a model name that is NOT defined anywhere in the netlist:\n"
    "   - Ensure the M-device line ends with a model name token.\n"
    "   - Use the generic model name `NMOS1` for undefined NMOS devices, and `PMOS1` for undefined PMOS devices (only if you can confidently infer PMOS; otherwise default to NMOS1).\n"
    "   - Append required model definition(s) (only if needed):\n"
    "     .model NMOS1 NMOS (VTO=1 KP=1m)\n"
    "     .model PMOS1 PMOS (VTO=-1 KP=1m)\n"
    "C) Do NOT add any .model lines if every referenced model name is already defined.\n"
    "   Example: If raw netlist has `Qp 3 4 8 BC547` and `.model BC547 NPN(...)`, keep both as-is.\n"
    "D) Do NOT create multiple duplicate model definitions for the same name; each generic model must appear at most once.\n"
    "E) Do NOT invent manufacturer-specific models.\n\n"

    "6. TRANSISTOR PIN ORDER ENFORCEMENT (CRITICAL):\n"
    "SPICE transistor devices have fixed, non-negotiable pin ordering rules.\n"
    "A) BJT DEVICES (Q):\n"
    "   - Format: Qname Collector Base Emitter [Substrate] Model\n"
    "   - The first three nodes MUST be interpreted in this order: Collector → Base → Emitter\n"
    "   - Do NOT reorder nodes unless the RAW NETLIST explicitly violates this order AND there is strong evidence for correction.\n"
    "   - If node meaning is ambiguous, preserve the original node order exactly.\n"
    "B) MOSFET DEVICES (M):\n"
    "   - Format: Mname Drain Gate Source Bulk Model\n"
    "   - The four nodes MUST be interpreted in this order: Drain → Gate → Source → Bulk\n"
    "   - CRITICAL: MOSFETs MUST have exactly 4 nodes. Never output a MOSFET with only 3 nodes.\n"
    "   - If the raw netlist has fewer nodes, you must add the missing Bulk node following these rules:\n"
    "     * For NMOS devices: Add node 0 as the Bulk node\n"
    "     * For PMOS devices: Add the Source node as the Bulk node (duplicate the Source node number)\n"
    "     * If device type is unclear, default to NMOS behavior (use 0)\n"
    "   - Bulk is often tied to Source or Ground (node 0), but must still be present.\n"
    "   - Do NOT reorder nodes unless the RAW NETLIST explicitly violates this order AND there is strong evidence for correction.\n"
    "   - If node meaning is ambiguous, preserve the original node order exactly.\n"
    "C) ABSOLUTE CONSTRAINTS:\n"
    "   - Never infer pin order from schematic drawing orientation.\n"
    "   - Never reorder transistor nodes based solely on visual assumptions.\n\n"

    "7. OUTPUT REQUIREMENTS (STRICT):\n"
    "You must output ONLY ONE thing: a single LTspice-compatible netlist.\n"
    "Rules:\n"
    "   - Do NOT include any reasoning, comments, explanations, headers, or separators.\n"
    "   - Do NOT output internal component IDs (like Resistor_1) in the final netlist.\n"
    "   - Use proper SPICE element prefixes (R, C, V, I, Q, M, etc.) followed by a unique identifier (which may be numeric, alphanumeric, or descriptive).\n"
    "   - CRITICAL LABEL PREFIX RULES:\n"
    "     * ALWAYS preserve the exact identified label from the API/OCR - DO NOT modify, shorten, or replace it\n"
    "     * If the identified label already starts with the correct SPICE prefix for that component type, use it as-is (e.g., resistor with label 'R1' → use 'R1' NOT 'RR1', BJT with label 'Q3' → use 'Q3' NOT 'QQ3')\n"
    "     * If the identified label does NOT start with the correct prefix, add ONLY the correct SPICE letter at the beginning, keeping the rest exactly as identified (e.g., resistor with label '5' → use 'R5', BJT with label '2' → use 'Q2')\n"
    "   - CRITICAL FOR MOSFETS: All M devices MUST have exactly 4 nodes (Drain Gate Source Bulk). If you see only 3 nodes in the raw netlist, ADD the 4th Bulk node:\n"
    "     * NMOS: Use 0 for Bulk (e.g., M1 3 2 1 0 NMOS1)\n"
    "     * PMOS: Duplicate the Source node for Bulk (e.g., M2 3 2 1 1 PMOS1)\n"
    "   - Preserve node names exactly as provided (the numeric node IDs). Do NOT rename nodes (no N### convention).\n"
    "   - Place any required `.model` statements at the end.\n\n"
    "   - Do NOT wrap the output in triple backticks (```), code fences, Markdown, or any formatting.\n"
    "   - Output must be plain text only.\n"

    "COMPONENT VALUE VALIDATION (CRITICAL):\n"
    "You MUST validate all component values before including them in the netlist.\n\n"

    "ACCEPT these value formats:\n"
    "   - Numeric values with standard SPICE units: 10k, 1uF, 2.2mH, 100, 1e-6, 3.3M\n"
    "   - SPICE multipliers like k, m, u, M are part of the value (10k, 1u, 2m)\n"
    "   - Do NOT add unit names: use '1k' not '1k ohm', '15' not '15V', '1u' not '1uF'\n"
    "   - SPICE time-varying functions: SIN(0 5 1k), PULSE(0 5 0 1n 1n 10u 20u), PWL(...)\n"
    "   - Valid voltage/current specifications for sources: 12, 3.3, DC 5\n\n"

    "REJECT these value formats (omit value entirely if found):\n"
    "   - Symbolic variables: v₅(t), i(t), Vcc, Vdd, R, C, L, V, etc.\n"
    "   - Component type letters used as values: R1 2 3 R (wrong - omit 'R') same for other components.\n"
    "   - Mathematical expressions without SPICE functions: 2*V1, V+5\n"
    "   - Ambiguous text: varies, see datasheet, TBD\n\n"

    "If a value is invalid or ambiguous:\n"
    "   - For resistors, capacitors, inductors: Omit the value (e.g., 'R1 2 3' without value)\n"
    "   - For voltage/current sources: Omit the value if it's symbolic; if no valid value exists, still include the component line\n"
    "   - Never include values that would cause SPICE simulation errors\n\n"

    "NODE CONNECTIVITY IMMUTABILITY (CRITICAL):\n"
    "The RAW NETLIST provides the correct and authoritative node connectivity.\n"
    "You MUST preserve node ordering and node numbers exactly as given.\n\n"
    "Rules:\n"
    "- For ALL non-transistor components (resistors, capacitors, voltage sources, current sources, inductors, etc.):\n"
    "  - You are NOT allowed to change, reorder, infer, swap, or reinterpret node connections.\n"
    "  - The node numbers and their order MUST be copied exactly from the RAW NETLIST.\n\n"
    "- For transistor devices ONLY (BJT and MOSFET):\n"
    "  - You may interpret node meaning strictly according to SPICE pin order rules\n"
    "    (BJT: Collector Base Emitter, MOSFET: Drain Gate Source Bulk).\n"
    "  - You may ONLY adjust transistor node ordering if there is strong explicit evidence that the RAW NETLIST violates SPICE ordering.\n"
    "  - If there is any ambiguity, preserve the original node order exactly.\n\n"
    "- You are NEVER allowed to invent new nodes, remove nodes, or merge nodes.\n"
    "- You are NEVER allowed to change connectivity for readability, aesthetics, or perceived correctness.\n\n"
    "If a circuit's behavior appears incorrect, DO NOT fix it by altering nodes.\n"
    "Only labels, values, and model references may be adjusted.\n\n"

    "9. GROUND NODE IDENTIFICATION (CRITICAL):\n"
    "After generating the netlist, you MUST identify which node should be treated as the ground reference (node 0).\n\n"

    "Ground Identification Rules (apply in priority order):\n"
    "A) EXPLICIT NODE LABELS:\n"
    "   - If any node in the circuit is explicitly labeled '0' (via OCR or schematic annotation), that is the ground node.\n"
    "   - This takes highest priority.\n\n"

    "B) VOLTAGE SOURCE NEGATIVE TERMINAL:\n"
    "   - If the circuit contains voltage sources (batteries, DC supplies), the negative terminal node is typically ground.\n"
    "   - Look for components prefixed with V (e.g., V1, V_supply, Vbat).\n"
    "   - The second node in a voltage source component line is the negative terminal.\n"
    "   - Example: 'V1 5 3 12V' → node 3 is the negative terminal, likely ground.\n\n"

    "C) MOST COMMON NODE (CIRCUIT ANALYSIS):\n"
    "   - If no voltage sources exist, analyze the netlist to find the node that appears most frequently.\n"
    "   - The most common node often serves as the circuit's reference/ground.\n\n"

    "D) BEST ENGINEERING JUDGMENT:\n"
    "   - If none of the above applies, use circuit topology and standard practices to make your best guess.\n"
    "   - Common ground: bottom rail in schematics, source of n-channel MOSFETs, emitter of common-emitter BJTs.\n\n"

    "OUTPUT REQUIREMENT:\n"
    "After the complete netlist, on a new line, output EXACTLY:\n"
    "GROUND_NODE: <node_number>\n\n"

    "Where <node_number> is the node ID from the raw netlist that should be treated as ground.\n"
    "Example: If you determine node 3 should be ground, output: 'GROUND_NODE: 3'\n\n"

    "This line MUST appear after the .end directive.\n\n"


    "=== RAW NETLIST ===\n"
    f"{raw_netlist_text}\n\n"
    "=== LABEL:VALUE MAPPING ===\n"
    f"{component_label_text}\n\n"
    "=== OCR RESULTS ===\n"
    f"{ocr_text}\n\n"
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
                "content": [{"type": "text", "text": prompt}] + image_block
            }
        ],
        "max_tokens": 1500,
        "temperature": 0
    }

    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=60
    )
    response.raise_for_status()
    result = response.json()['choices'][0]['message']['content']

    # Remove markdown code fence blocks if LLM wrapped response in ```
    result = result.strip()
    if result.startswith("```"):
        lines = result.split('\n')
        # Remove first line if it's a code fence (e.g., ```spice or just ```)
        if lines[0].startswith("```"):
            lines = lines[1:]
        # Remove last line if it's a closing code fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        result = '\n'.join(lines)

    # Post-process to fix any 3-node MOSFETs
    result_lines = result.splitlines()
    result_lines = fix_mosfet_nodes(result_lines)

    # Parse the response to extract ground node
    ground_node = None
    for i, line in enumerate(result_lines):
        if line.strip().startswith("GROUND_NODE:"):
            ground_node_str = line.split(":", 1)[1].strip()
            try:
                ground_node = int(ground_node_str)
                # Remove this line from the final netlist
                result_lines.pop(i)
            except ValueError:
                print(f"Warning: Could not parse ground node from VLM response: {ground_node_str}")
            break

    return [line.strip() for line in result_lines if line.strip()], ground_node

def identify_crossing_nodes(crossing_data, node_labels, region_to_node_mapping=None):
    """
    Identifies which final node IDs contain crossing points.
    Returns a set of final node IDs that have crossings.

    Args:
        crossing_data: JSON data from crossing detection
        node_labels: The node labels array (regions)
        region_to_node_mapping: Mapping from regions to final node IDs
    """
    crossing_regions = set()
    crossing_nodes = set()

    if not crossing_data or not crossing_data.get('crossings'):
        return crossing_nodes

    h, w = node_labels.shape

    # First, identify which regions contain crossings
    for crossing in crossing_data['crossings']:
        x, y = crossing['crossing_point']

        # Check bounds and find regions at crossing point
        regions_at_crossing = set()

        # Check the exact point
        if 0 <= y < h and 0 <= x < w:
            region_id = node_labels[y, x]
            if region_id > 0:
                regions_at_crossing.add(region_id)

        # Also check nearby pixels in case the crossing point is slightly off
        for dx in [-3, -2, -1, 0, 1, 2, 3]:
            for dy in [-3, -2, -1, 0, 1, 2, 3]:
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w:
                    region_id = node_labels[ny, nx]
                    if region_id > 0:
                        regions_at_crossing.add(region_id)

        crossing_regions.update(regions_at_crossing)
        print(f"Crossing at ({x}, {y}) found in regions: {regions_at_crossing}")

    # Map regions to final node IDs if mapping is provided
    if region_to_node_mapping:
        for region in crossing_regions:
            if region in region_to_node_mapping:
                final_node_id = region_to_node_mapping[region]
                crossing_nodes.add(final_node_id)
                print(f"Region {region} -> Final node {final_node_id} (has crossing)")
    else:
        # If no mapping provided, use region IDs directly
        crossing_nodes = crossing_regions

    return crossing_nodes

def create_crossing_enhanced_netlist(raw_netlist_lines, crossing_nodes, region_to_node_mapping=None):
    """
    Creates an enhanced netlist with crossing markers (c prefix) for nodes that contain crossings.

    Args:
        raw_netlist_lines: List of netlist lines (e.g., ["Resistor_1 1 2", "Capacitor_1 2 3"])
        crossing_nodes: Set of node IDs that have crossings
        region_to_node_mapping: Optional mapping from regions to final node IDs

    Returns:
        List of enhanced netlist lines with crossing markers
    """
    enhanced_lines = []

    for line in raw_netlist_lines:
        if not line.strip():
            enhanced_lines.append(line)
            continue

        parts = line.strip().split()
        if len(parts) < 2:
            enhanced_lines.append(line)
            continue

        component = parts[0]
        nodes = parts[1:]

        # Apply crossing markers to nodes
        enhanced_nodes = []
        for node_str in nodes:
            try:
                node_id = int(node_str)
                if node_id in crossing_nodes:
                    enhanced_nodes.append(f"c{node_id}")
                else:
                    enhanced_nodes.append(node_str)
            except ValueError:
                # Non-numeric node (shouldn't happen in our case, but handle gracefully)
                enhanced_nodes.append(node_str)

        enhanced_line = f"{component} {' '.join(enhanced_nodes)}"
        enhanced_lines.append(enhanced_line)

    return enhanced_lines

def find_nearest_edge(node_labels, px, py):
    edge_points = np.argwhere(node_labels > 0)
    if edge_points.size == 0:
        return None
    distances = distance.cdist([(py, px)], edge_points)
    nearest_index = np.argmin(distances)
    return edge_points[nearest_index]  # (y, x)

def is_point_connected_or_nearest(node_labels, px, py):
    nearest = find_nearest_edge(node_labels, px, py)
    if nearest is not None:
        return True, (nearest[1], nearest[0])  # (x, y)
    print(f"No connection found for point ({px}, {py})")
    return False, None

def overlay_and_find_nodes_with_connected_regions(node_labels, components, test_results_path, image_file):
    region_to_node = {}
    current_node_id = 1
    gnd_regions = set()
    height, width = node_labels.shape
    num_regions = node_labels.max()

    for component in components:
        comp_id = component["id"]
        for point in component["connection_points"]:
            px, py = point
            if py >= height or px >= width:
                continue
            is_connected, connection_point = is_point_connected_or_nearest(node_labels, px, py)
            if is_connected:
                connected_px, connected_py = connection_point
                region = node_labels[connected_py, connected_px]
                if region > 0:
                    if region not in region_to_node:
                        region_to_node[region] = current_node_id
                        current_node_id += 1
                    if component["label"].upper() == "GND":
                        gnd_regions.add(region)

    # Sort regions by top-left-most pixel
    region_top_left = {}
    for region in range(1, num_regions + 1):
        pixels = np.argwhere(node_labels == region)
        if len(pixels) > 0:
            top_left_pixel = pixels[np.lexsort((pixels[:, 1], pixels[:, 0]))][0]
            region_top_left[region] = top_left_pixel

    sorted_regions = sorted(region_top_left.items(), key=lambda x: (x[1][0], x[1][1]))
    new_region_to_node = {}

    # First, assign node 0 to all ground regions
    for region in gnd_regions:
        if region in region_to_node:
            new_region_to_node[region] = 0

    # Then assign sequential IDs (starting from 1) to non-ground nodes
    new_node_id = 1
    for region, _ in sorted_regions:
        if region in region_to_node and region not in gnd_regions:
            new_region_to_node[region] = new_node_id
            new_node_id += 1

    # Save region-to-node mapping for crossing detection use
    results_folder = os.path.join(test_results_path, os.path.splitext(image_file)[0])
    os.makedirs(results_folder, exist_ok=True)
    mapping_file = os.path.join(results_folder, 'region_to_node_mapping.json')
    with open(mapping_file, 'w') as f:
        # Convert numpy int32 keys to regular int for JSON serialization
        mapping_for_json = {int(k): int(v) for k, v in new_region_to_node.items()}
        json.dump(mapping_for_json, f, indent=4)

    # Save node connection results
    results_file = os.path.join(results_folder, 'netlist_structure.txt')
    with open(results_file, 'w') as results:
        for component in components:
            if component["label"].upper() == "GND":
                continue
            comp_id = component["id"]
            connected_nodes = []
            for point in component["connection_points"]:
                px, py = point
                if py >= height or px >= width:
                    continue
                is_connected, connection_point = is_point_connected_or_nearest(node_labels, px, py)
                if is_connected:
                    connected_px, connected_py = connection_point
                    region = node_labels[connected_py, connected_px]
                    if region > 0 and region in new_region_to_node:
                        node_id = new_region_to_node[region]
                        connected_nodes.append(node_id)
            if connected_nodes:
                results.write(f"{comp_id} {' '.join(map(str, connected_nodes))}\n")

def generate_netlist_for_image(image_file, output_files_path, test_results_path, create_test_netlist=True):
    image_name = os.path.splitext(image_file)[0]
    image_output_folder = os.path.join(output_files_path, image_name)
    os.makedirs(image_output_folder, exist_ok=True)

    # Load preprocessed circuit info
    json_path = os.path.join(image_output_folder, 'circuit_info.json')
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"Missing circuit_info.json at: {json_path}")
    with open(json_path, 'r') as json_file:
        components = json.load(json_file)

    masked_edges = cv2.imread(os.path.join(image_output_folder, "6_circuit_cut.png"))
    if masked_edges is not None and len(masked_edges.shape) == 3:
        masked_edges = cv2.cvtColor(masked_edges, cv2.COLOR_BGR2GRAY)

    node_labels = np.load(os.path.join(image_output_folder, "node_labels.npy"))

    # Generate standard netlist
    overlay_and_find_nodes_with_connected_regions(node_labels, components, test_results_path, image_file)

    # Create test_netlist with crossing markers if crossing data exists and is requested
    if create_test_netlist:
        crossing_data_path = os.path.join(image_output_folder, "crossing_data.json")
        if os.path.exists(crossing_data_path):
            with open(crossing_data_path, 'r') as f:
                crossing_data = json.load(f)

            # Load region-to-node mapping
            mapping_file = os.path.join(test_results_path, image_name, 'region_to_node_mapping.json')
            region_to_node_mapping = {}
            if os.path.exists(mapping_file):
                with open(mapping_file, 'r') as f:
                    region_to_node_mapping = json.load(f)
                    # Convert string keys back to integers
                    region_to_node_mapping = {int(k): v for k, v in region_to_node_mapping.items()}

            # Identify nodes that contain crossings
            crossing_nodes = identify_crossing_nodes(crossing_data, node_labels, region_to_node_mapping)

            if crossing_nodes:
                print(f"Found crossings in final nodes: {sorted(crossing_nodes)}")

                # Create test_netlist directory
                test_netlist_path = os.path.join(test_results_path, "test_netlist")
                os.makedirs(test_netlist_path, exist_ok=True)

                # Read the standard netlist structure
                standard_netlist_path = os.path.join(test_results_path, image_name, 'netlist_structure.txt')
                if os.path.exists(standard_netlist_path):
                    with open(standard_netlist_path, 'r') as f:
                        raw_netlist = f.read().splitlines()

                    # Create enhanced netlist with crossing markers
                    enhanced_netlist = create_crossing_enhanced_netlist(raw_netlist, crossing_nodes)

                    # Save enhanced netlist
                    test_netlist_file = os.path.join(test_netlist_path, f"{image_name}_with_crossings.txt")
                    with open(test_netlist_file, 'w') as f:
                        for line in enhanced_netlist:
                            f.write(line + "\n")

                    print(f"Created test netlist with crossing markers: {test_netlist_file}")

                else:
                    print(f"Warning: Standard netlist not found at {standard_netlist_path}")
            else:
                print("No crossings detected or no crossing nodes identified.")
        else:
            print(f"No crossing data found at {crossing_data_path}")

def generate_all_netlists(approved_images_path, output_files_path, test_results_path, create_test_netlist=True):

    os.makedirs(test_results_path, exist_ok=True)
    image_files = [f for f in os.listdir(approved_images_path) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]

    for image_file in image_files:
        image_basename = os.path.splitext(image_file)[0]

        generate_netlist_for_image(image_file, output_files_path, test_results_path, create_test_netlist)

        # === Define input paths ===
        raw_netlist_path = os.path.join(test_results_path, image_basename, "netlist_structure.txt")
        api_response_path = os.path.join(output_files_path, image_basename, "API_first_response.txt")
        ocr_text_path = os.path.join(output_files_path, image_basename, "ocr_results", "circuit_components_with_text.txt")

        # === Check for crossing disambiguation netlist ===
        crossing_netlist_path = os.path.join(output_files_path, image_basename, "crossing_disambiguation", "crossing_1_line1_connected_netlist.txt")

        # === Read input files ===
        if os.path.exists(crossing_netlist_path):
            print(f"Using crossing disambiguation netlist for {image_basename}")
            raw_netlist = clean_crossing_netlist(crossing_netlist_path)
        else:
            print(f"Using normal netlist structure for {image_basename}")
            with open(raw_netlist_path, "r", encoding="utf-8") as f:
                raw_netlist = f.read().splitlines()

        with open(api_response_path, "r", encoding="utf-8") as f:
            api_lines = f.read().splitlines()

        with open(ocr_text_path, "r", encoding="utf-8") as f:
            ocr_text = f.read()

        # === Generate final netlist ===
        final_netlist, vlm_ground_node = generate_named_netlist(raw_netlist, api_lines, ocr_text)

        # === Ground Node Remapping ===
        # If VLM identified a ground node and it's not already 0, remap it
        if vlm_ground_node is not None and vlm_ground_node != 0:
            # Check if the netlist already has a node 0 (from explicit GND)
            has_explicit_ground = any(' 0 ' in line or line.startswith('0 ') or line.endswith(' 0')
                                       for line in final_netlist if not line.startswith('.'))

            if not has_explicit_ground:
                print(f"  VLM identified node {vlm_ground_node} as ground. Remapping to node 0...")
                # Remap the VLM-suggested node to 0 throughout the netlist
                remapped_netlist = []
                for line in final_netlist:
                    # Skip directive lines (starting with .)
                    if line.startswith('.'):
                        remapped_netlist.append(line)
                    else:
                        # Use regex to replace whole-word node numbers
                        # Replace node number as whole word (surrounded by spaces or line boundaries)
                        updated_line = re.sub(rf'\b{vlm_ground_node}\b', '0', line)
                        remapped_netlist.append(updated_line)
                final_netlist = remapped_netlist
            else:
                print(f"  Node 0 already exists in netlist (explicit GND). Ignoring VLM ground suggestion.")
        elif vlm_ground_node == 0:
            print(f"  VLM confirmed node 0 as ground (already correct).")
        else:
            print(f"  VLM did not identify a ground node.")

        # === Add hardcoded analysis block ===
        analysis_block = [
            ".control",
            "tran 1m 1s uic",
            "print all",
            "quit",
            ".endc"
        ]

        # Find .end and insert analysis block before it
        if final_netlist and final_netlist[-1].strip() == ".end":
            final_netlist = final_netlist[:-1] + analysis_block + [".end"]
        else:
            final_netlist.extend(analysis_block)
            final_netlist.append(".end")

        # === Print final output ===
        print(f"\nFinal named netlist for {image_file}:\n" + "=" * 40)
        for line in final_netlist:
            print(line)

        # === Save final netlist to output_files_path/final_results/image_name.txt ===
        output_file_path = os.path.join(test_results_path, f"{image_basename}.txt")
        print(f"Saving final netlist to {output_file_path}")
        with open(output_file_path, "w", encoding="utf-8") as f:
            for line in final_netlist:
                f.write(line + "\n")

        # === Create enhanced final netlist with crossing markers for test_netlist ===
        if create_test_netlist:
            crossing_data_path = os.path.join(output_files_path, image_basename, "crossing_data.json")
            if os.path.exists(crossing_data_path):
                with open(crossing_data_path, 'r') as f:
                    crossing_data = json.load(f)

                # Load node_labels and mapping to identify crossing nodes
                node_labels_path = os.path.join(output_files_path, image_basename, "node_labels.npy")
                mapping_file = os.path.join(test_results_path, image_basename, 'region_to_node_mapping.json')

                if os.path.exists(node_labels_path) and os.path.exists(mapping_file):
                    node_labels = np.load(node_labels_path)

                    with open(mapping_file, 'r') as f:
                        region_to_node_mapping = json.load(f)
                        region_to_node_mapping = {int(k): v for k, v in region_to_node_mapping.items()}

                    crossing_nodes = identify_crossing_nodes(crossing_data, node_labels, region_to_node_mapping)

                    if crossing_nodes:
                        # Create enhanced final netlist with crossing markers
                        enhanced_final_netlist = create_crossing_enhanced_netlist(final_netlist, crossing_nodes)

                        # Save enhanced final netlist
                        test_netlist_path = os.path.join(test_results_path, "test_netlist")
                        os.makedirs(test_netlist_path, exist_ok=True)
                        enhanced_output_path = os.path.join(test_netlist_path, f"{image_basename}_final_with_crossings.txt")

                        with open(enhanced_output_path, "w", encoding="utf-8") as f:
                            for line in enhanced_final_netlist:
                                f.write(line + "\n")

                        print(f"Created enhanced final netlist with crossing markers: {enhanced_output_path}")

                        # === Print enhanced final output ===
                        print(f"\nEnhanced final netlist with crossings for {image_file}:\n" + "=" * 50)
                        for line in enhanced_final_netlist:
                            print(line)

                        # === Generate crossing disambiguation images and netlists ===
                        generate_crossing_disambiguation_images_and_netlists(
                            image_file, output_files_path, test_results_path, crossing_data, image_basename
                        )

        # Add delay between circuits to avoid OpenAI API rate limiting
        time.sleep(10)


def generate_crossing_disambiguation_images_and_netlists(image_file, output_files_path, test_results_path, crossing_data, image_basename):
    """
    Generate modified images with crossings removed and specific lines connected,
    then run the full pipeline on each to get actual netlists.
    """

    if not crossing_data or not crossing_data.get('crossings'):
        return

    print(f"\n" + "=" * 80)
    print(f"GENERATING CROSSING DISAMBIGUATION IMAGES AND NETLISTS")
    print(f"Original image: {image_file}")
    print(f"Found {len(crossing_data['crossings'])} crossings to process")
    print(f"=" * 80)

    # Load the original input image
    # Try to find the original image in the inputs folder
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    original_image_path = os.path.join(script_dir, 'inputs', 'test_images', image_file)

    if not os.path.exists(original_image_path):
        print(f"Warning: Could not find original input image at {original_image_path}")
        return

    original_image = cv2.imread(original_image_path)
    if original_image is None:
        print(f"Warning: Could not load original image")
        return

    print(f"Loaded original image from: {original_image_path}")

    # Create disambiguation folder
    disambiguation_folder = os.path.join(output_files_path, image_basename, "crossing_disambiguation")
    os.makedirs(disambiguation_folder, exist_ok=True)

    # Process each crossing
    for crossing_idx, crossing in enumerate(crossing_data['crossings']):
        crossing_id = crossing['id']
        crossing_point = crossing['crossing_point']
        line1 = crossing['line1']
        line2 = crossing['line2']

        print(f"\nProcessing Crossing {crossing_id} at {crossing_point}")
        print(f"Line 1 ({line1['type']}): {line1['start']} -> {line1['end']}")
        print(f"Line 2 ({line2['type']}): {line2['start']} -> {line2['end']}")

        # Create line1-only image (connect line1, remove crossing)
        line1_image = create_single_line_image(original_image, crossing_point, line1, line2, connect_line1=True)
        line1_image_path = os.path.join(disambiguation_folder, f"crossing_{crossing_id}_line1_connected.png")
        cv2.imwrite(line1_image_path, line1_image)
        print(f"Created line1-only image: {line1_image_path}")

        # Create line2-only image (connect line2, remove crossing)
        line2_image = create_single_line_image(original_image, crossing_point, line1, line2, connect_line1=False)
        line2_image_path = os.path.join(disambiguation_folder, f"crossing_{crossing_id}_line2_connected.png")
        cv2.imwrite(line2_image_path, line2_image)
        print(f"Created line2-only image: {line2_image_path}")

        # Run full pipeline on each modified image
        print(f"Running pipeline on line1-connected image...")
        run_pipeline_on_disambiguation_image(line1_image_path, f"crossing_{crossing_id}_line1_connected", disambiguation_folder)

        print(f"Running pipeline on line2-connected image...")
        run_pipeline_on_disambiguation_image(line2_image_path, f"crossing_{crossing_id}_line2_connected", disambiguation_folder)


def create_single_line_image(original_image, crossing_point, line1, line2, connect_line1=True):
    """
    Create a modified image where the crossing is removed and only one line is connected.

    Args:
        original_image: The original image
        crossing_point: [x, y] coordinates of the crossing
        line1: Line 1 data with start/end points
        line2: Line 2 data with start/end points
        connect_line1: If True, connect line1. If False, connect line2.
    """

    # Create a copy of the original image
    modified_image = original_image.copy()

    crossing_x, crossing_y = crossing_point

    # Step 1: Get the color at the crossing point before removing it
    crossing_color = modified_image[crossing_y, crossing_x].copy()
    print(f"  Crossing color at ({crossing_x}, {crossing_y}): {crossing_color}")

    # Step 2: Remove the crossing point by drawing a circle (background color)
    # Determine background color by looking at corners of image
    background_color = modified_image[0, 0].copy()  # Use top-left corner as background
    cv2.circle(modified_image, (crossing_x, crossing_y), 6, background_color.tolist(), -1)
    print(f"  Removed crossing point with background color: {background_color}")

    # Step 3: Draw the selected line using the original crossing color
    if connect_line1:
        start1 = tuple(line1['start'])
        end1 = tuple(line1['end'])
        cv2.line(modified_image, start1, end1, crossing_color.tolist(), 2)
        print(f"  Connected line1: {start1} -> {end1} with color {crossing_color}")
    else:
        start2 = tuple(line2['start'])
        end2 = tuple(line2['end'])
        cv2.line(modified_image, start2, end2, crossing_color.tolist(), 2)
        print(f"  Connected line2: {start2} -> {end2} with color {crossing_color}")

    return modified_image


def run_pipeline_on_disambiguation_image(image_path, image_name, disambiguation_folder):
    """
    Run the full netlist generation pipeline on a disambiguation image.
    """
    import sys
    import os
    from helper_files.process_images import process_circuit_image

    print(f"  Running full pipeline on {image_name}...")

    try:
        # Get model path (same as main pipeline)
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        PROJECT_PATH = os.path.dirname(os.path.dirname(script_dir))
        model_folder = os.path.join(PROJECT_PATH, 'current_trained_model')
        train_folders = [folder for folder in os.listdir(model_folder) if folder.startswith('train')]

        if not train_folders:
            print(f"  No model found")
            return

        def extract_suffix(folder_name):
            if folder_name == "train":
                return 0
            else:
                return int(folder_name[5:])

        latest_train_folder = max(train_folders, key=extract_suffix)
        model_path = os.path.join(model_folder, latest_train_folder, 'weights', 'last.pt')

        # Create temporary output folder for this disambiguation image
        temp_output_folder = os.path.join(disambiguation_folder, f"{image_name}_processing")
        os.makedirs(temp_output_folder, exist_ok=True)

        # Load crossing data for bridge component injection
        crossing_data = None
        disambiguation_context = None

        # Determine disambiguation context from image name and load crossing data
        if "line1_connected" in image_name:
            disambiguation_context = "line1_connected"
        elif "line2_connected" in image_name:
            disambiguation_context = "line2_connected"

        if disambiguation_context:
            # Try to find crossing_data.json in the parent debugging folder
            debug_folder = os.path.dirname(disambiguation_folder)
            crossing_data_path = os.path.join(debug_folder, 'crossing_data.json')
            if os.path.exists(crossing_data_path):
                try:
                    with open(crossing_data_path, 'r') as f:
                        crossing_data = json.load(f)
                    print(f"  Loaded crossing data for bridge injection: {disambiguation_context}")
                except Exception as e:
                    print(f"  Failed to load crossing data: {e}")

        # Process the disambiguation image with bridge component injection
        print(f"  Processing image with YOLO and bridge components...")
        process_circuit_image(image_path, model_path, temp_output_folder, use_ocr=False, use_gpu=True, detect_crossings=False, crossing_data=crossing_data, disambiguation_context=disambiguation_context)

        # Generate netlist from the processed components
        print(f"  Generating netlist...")
        circuit_info_path = os.path.join(temp_output_folder, 'circuit_info.json')
        node_labels_path = os.path.join(temp_output_folder, 'node_labels.npy')

        if os.path.exists(circuit_info_path) and os.path.exists(node_labels_path):
            # Generate netlist using same logic as main pipeline
            with open(circuit_info_path, 'r') as f:
                components = json.load(f)

            node_labels = np.load(node_labels_path)

            # Generate connections (simplified version)
            netlist_lines = generate_disambiguation_netlist(components, node_labels)

            # Save netlist
            netlist_path = os.path.join(disambiguation_folder, f"{image_name}_netlist.txt")
            with open(netlist_path, 'w') as f:
                f.write(f"# Disambiguation netlist for {image_name}\n")
                f.write(f"# Generated from: {image_path}\n")
                f.write(f"# This shows actual connections when crossing is resolved\n\n")
                for line in netlist_lines:
                    f.write(line + "\n")

            print(f"  Generated netlist: {netlist_path}")

            # Print netlist to terminal
            print(f"\nNETLIST FOR {image_name.upper()}:")
            print("=" * 60)
            for line in netlist_lines:
                print(line)
            print("=" * 60)

        else:
            print(f"  Failed to generate circuit info or node labels")

    except Exception as e:
        print(f"  Error running pipeline: {e}")
        import traceback
        traceback.print_exc()


def generate_disambiguation_netlist(components, node_labels):
    """
    Generate a simplified netlist from components and node labels.
    """
    from scipy.spatial import distance

    netlist_lines = []
    region_to_node = {}
    current_node_id = 1
    height, width = node_labels.shape

    # Map regions to nodes (simplified version of main logic)
    for component in components:
        comp_id = component["id"]
        connected_nodes = []

        for point in component["connection_points"]:
            px, py = point
            if py >= height or px >= width:
                continue

            # Find nearest edge point
            edge_points = np.argwhere(node_labels > 0)
            if edge_points.size > 0:
                distances = distance.cdist([(py, px)], edge_points)
                nearest_index = np.argmin(distances)
                nearest_point = edge_points[nearest_index]
                region = node_labels[nearest_point[0], nearest_point[1]]

                if region > 0:
                    if region not in region_to_node:
                        region_to_node[region] = current_node_id
                        current_node_id += 1

                    node_id = region_to_node[region]
                    if node_id not in connected_nodes:
                        connected_nodes.append(node_id)

        if connected_nodes:
            # Add 'c' suffix to nodes connected to bridge components
            if comp_id.startswith('Bridge_'):
                node_strings = [f"{node}c" for node in connected_nodes]
            else:
                node_strings = [str(node) for node in connected_nodes]
            netlist_lines.append(f"{comp_id} {' '.join(node_strings)}")

    # Merge nodes connected by bridge components and remove bridge entries
    netlist_lines = merge_bridge_connected_nodes(netlist_lines)

    return netlist_lines


def merge_bridge_connected_nodes(netlist_lines):
    """
    Merge nodes that are connected by bridge components.
    Bridge components indicate that two nodes should actually be the same node.
    """
    # Find bridge components and the nodes they connect
    bridge_connections = {}  # {bridge_id: [node1, node2]}
    node_merge_map = {}  # {old_node: new_node}

    # Extract bridge connections
    for line in netlist_lines:
        parts = line.strip().split()
        if len(parts) >= 2 and parts[0].startswith('Bridge_'):
            bridge_id = parts[0]
            # Extract nodes (remove 'c' suffix)
            nodes = []
            for node_str in parts[1:]:
                if node_str.endswith('c'):
                    node_num = int(node_str[:-1])  # Remove 'c' suffix
                    nodes.append(node_num)

            if len(nodes) >= 1:
                bridge_connections[bridge_id] = nodes

    # Collect all nodes that are connected by bridge components
    # All bridge nodes should be merged together (they represent the same cut wire)
    all_bridge_nodes = []
    for bridge_id, nodes in bridge_connections.items():
        all_bridge_nodes.extend(nodes)

    if len(all_bridge_nodes) >= 2:
        # Merge all bridge nodes to the lowest numbered node
        min_node = min(all_bridge_nodes)
        for node in all_bridge_nodes:
            if node != min_node:
                node_merge_map[node] = min_node
                print(f"Merged node {node} -> {min_node} (bridge connection)")

    # Apply merging to all netlist lines (except bridge components)
    merged_lines = []
    for line in netlist_lines:
        parts = line.strip().split()
        if len(parts) >= 2:
            comp_id = parts[0]

            # Skip bridge components in final netlist
            if comp_id.startswith('Bridge_'):
                continue

            # Merge nodes for regular components
            new_nodes = []
            for node_str in parts[1:]:
                node_num = int(node_str)
                # Apply merge mapping
                merged_node = node_merge_map.get(node_num, node_num)
                new_nodes.append(str(merged_node))

            merged_lines.append(f"{comp_id} {' '.join(new_nodes)}")

    # Final cleanup: renumber nodes to fill gaps in sequence
    merged_lines = renumber_nodes_sequentially(merged_lines)

    return merged_lines


def renumber_nodes_sequentially(netlist_lines):
    """
    Renumber nodes to eliminate gaps in the numbering sequence.
    For example: if nodes 1,2,3,4,6 are used, replace all 6 with 5.
    """
    # Extract all unique node numbers from the netlist
    used_nodes = set()
    for line in netlist_lines:
        parts = line.strip().split()
        if len(parts) >= 2:
            for node_str in parts[1:]:
                try:
                    node_num = int(node_str)
                    used_nodes.add(node_num)
                except ValueError:
                    continue  # Skip non-numeric values

    if not used_nodes:
        return netlist_lines

    # Find gaps in the sequence and create renumbering map
    max_node = max(used_nodes)
    renumber_map = {}

    # Create sequential numbering starting from 1
    sorted_nodes = sorted(used_nodes)
    for i, node in enumerate(sorted_nodes):
        new_node = i + 1
        if node != new_node:
            renumber_map[node] = new_node

    # Apply renumbering if needed
    if renumber_map:
        print(f"Renumbering nodes: {renumber_map}")
        renumbered_lines = []
        for line in netlist_lines:
            parts = line.strip().split()
            if len(parts) >= 2:
                comp_id = parts[0]
                new_nodes = []
                for node_str in parts[1:]:
                    try:
                        node_num = int(node_str)
                        new_node = renumber_map.get(node_num, node_num)
                        new_nodes.append(str(new_node))
                    except ValueError:
                        new_nodes.append(node_str)  # Keep non-numeric as is

                renumbered_lines.append(f"{comp_id} {' '.join(new_nodes)}")
            else:
                renumbered_lines.append(line)

        return renumbered_lines

    return netlist_lines


def clean_crossing_netlist(crossing_netlist_path):
    """
    Clean the crossing disambiguation netlist for use as raw netlist structure.
    Removes comments, GND components, and empty lines.
    """
    try:
        with open(crossing_netlist_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()

        cleaned_lines = []
        for line in lines:
            line = line.strip()
            # Skip comment lines, GND components, and empty lines
            if (line and
                not line.startswith('#') and
                not line.startswith('GND_')):
                cleaned_lines.append(line)

        print(f"Cleaned crossing netlist: {len(cleaned_lines)} lines")
        return cleaned_lines

    except Exception as e:
        print(f"Error reading crossing netlist: {e}")
        return []
