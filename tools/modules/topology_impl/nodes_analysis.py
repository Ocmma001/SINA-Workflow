from ..image_io import read_image, write_image
from sklearn.cluster import DBSCAN
import numpy as np
import cv2
import os
import random
from collections import defaultdict
import json
import matplotlib
matplotlib.use('Agg')
from .find_crossing import detectCrossingLines

def create_comprehensive_detection_visualization(original_image, components, crossing_data, output_folder):
    """
    Create a comprehensive visualization showing all detected lines and crossings:
    - All detected lines (horizontal, vertical, diagonal) from testing_all_lines.json
    - Crossing points (smaller circles)
    """

    # Create a copy of the original image for drawing
    vis_image = original_image.copy()

    # Load all lines data from the dedicated JSON file
    all_lines_json_path = os.path.join(output_folder, "testing_all_lines.json")

    all_lines_data = None

    if os.path.exists(all_lines_json_path):
        try:
            with open(all_lines_json_path, 'r') as f:
                all_lines_data = json.load(f)
            total_lines = all_lines_data.get('total_lines', 0)

        except Exception as e:
            all_lines_data = None
    

    # Draw all detected lines
    if all_lines_data and all_lines_data.get('all_lines'):
        all_lines = all_lines_data['all_lines']

        lines_drawn = 0
        for line in all_lines:
            line_type = line.get('type', 'unknown')
            start = tuple(line['start'])
            end = tuple(line['end'])

            # Color code by line type (BGR format)
            if line_type == 'horizontal':
                color = (0, 165, 255)  # Orange
            elif line_type == 'vertical':
                color = (0, 255, 0)  # Green
            elif line_type == 'backward_diagonal':
                color = (0, 0, 255)  # Red
            elif line_type == 'forward_diagonal':
                color = (255, 0, 0)  # Blue
            else:
                color = (128, 128, 128)  # Gray for unknown

            cv2.line(vis_image, start, end, color, 2)
            lines_drawn += 1


    # Draw crossing points (smaller circles)
    if crossing_data and crossing_data.get('crossings'):
        crossings = crossing_data['crossings']
        for crossing in crossings:
            crossing_point = crossing['crossing_point']
            crossing_x, crossing_y = crossing_point

            # Draw smaller yellow circle for crossing point
            cv2.circle(vis_image, (crossing_x, crossing_y), 10, (0, 255, 255), -1)  # Larger radius
            cv2.circle(vis_image, (crossing_x, crossing_y), 10, (0, 0, 0), 1)  # Thin black border

        print(f"Drew {len(crossings)} crossing points on visualization")

    # Save the comprehensive visualization
    output_path = os.path.join(output_folder, "6a_all_detected_lines_and_crossings.png")
    write_image(output_path, vis_image)
    print(f"Saved comprehensive detection visualization: 6a_all_detected_lines_and_crossings.png")


def save_circuit_info_json(components, component_connections, output_folder):
    circuit_info = []
    for comp in components:
        comp_id = comp["id"]
        circuit_info.append({
            "id": comp_id,
            "label": comp["type"],
            "bounding_box": comp["bbox"],
            "connection_points": component_connections.get(comp_id, [])
        })

    json_path = os.path.join(output_folder, "circuit_info.json")
    with open(json_path, 'w') as f:
        json.dump(circuit_info, f, indent=4)
    print(f"Saved circuit_info.json to {json_path}")

def identify_circuit_nodes(merged_labels, components, output_folder, original_image, model_path=None, detect_crossings=True, crossing_data=None, disambiguation_context=None):
    h, w = merged_labels.shape
    circuit_image = merged_labels.copy()

    # STEP 1: Cut out the component areas to isolate wiring nodes
    component_mask = np.zeros_like(circuit_image)
    shrink_amount = 3
    for component in components:
        x_min, y_min, x_max, y_max = component["bbox"]
        x_min_r = x_min + shrink_amount
        y_min_r = y_min + shrink_amount
        x_max_r = x_max - shrink_amount
        y_max_r = y_max - shrink_amount
        if x_min_r < x_max_r and y_min_r < y_max_r:
            component_mask[y_min_r:y_max_r, x_min_r:x_max_r] = 1

    circuit_cut = circuit_image.copy()
    circuit_cut[component_mask == 1] = 0
    write_image(os.path.join(output_folder, "6_circuit_cut.png"), circuit_cut * 255)

    # Save circuit_cut as numpy array for crossing variant generation
    np.save(os.path.join(output_folder, "circuit_cut.npy"), circuit_cut)

    # Bridge components will be added after 8_valid_nodes.png generation
    updated_components = components.copy()

    # STEP 1.5: Detect and handle wire crossings
    # crossing_data is now passed as a parameter, don't overwrite it

    crossing_status = {'status': 'skipped', 'source': 'fixed_detection_boxes', 'component_count': len(components)}
    if detect_crossings:
        # Save original image temporarily for crossing detection
        temp_image_path = os.path.join(output_folder, "temp_original.png")
        write_image(temp_image_path, original_image)

        # Create paths for crossing detection output
        crossing_output_path = os.path.join(output_folder, "6a_crossings_detected.png")
        crossing_debug_path = os.path.join(output_folder, "6a_crossings_debug.png")

        # Run crossing detection
        try:
            detectCrossingLines(temp_image_path, model_path, crossing_output_path, crossing_debug_path, components=components)

            crossing_status['status'] = 'completed'

            # Load crossing data from JSON
            image_name = os.path.splitext(os.path.basename(temp_image_path))[0]
            crossing_json_path = os.path.join(output_folder, f"{image_name}_crossing_data.json")
            if os.path.exists(crossing_json_path):
                with open(crossing_json_path, 'r') as f:
                    crossing_data = json.load(f)

                # Create small gaps at crossing points to prevent incorrect connections
                if crossing_data and crossing_data.get('crossings'):
                    for crossing in crossing_data['crossings']:
                        x, y = crossing['crossing_point']
                        # Create a small gap (3x3 pixels) around the crossing point
                        gap_size = 1
                        x_start = max(0, x - gap_size)
                        x_end = min(w, x + gap_size + 1)
                        y_start = max(0, y - gap_size)
                        y_end = min(h, y + gap_size + 1)
                        circuit_cut[y_start:y_end, x_start:x_end] = 0

                    print(f"Processed {len(crossing_data['crossings'])} wire crossings")

        except Exception as e:
            crossing_status.update(status='failed', error_type=type(e).__name__)
            print(f"Warning: Crossing detection failed ({type(e).__name__})")
            crossing_data = None

        # Clean up temporary file
        if os.path.exists(temp_image_path):
            os.remove(temp_image_path)

    with open(os.path.join(output_folder, 'crossing_status.json'), 'w', encoding='utf-8') as stream:
        json.dump(crossing_status, stream, indent=2)

    # Save crossing data for later use in netlist generation
    if crossing_data:
        crossing_save_path = os.path.join(output_folder, "crossing_data.json")
        with open(crossing_save_path, 'w') as f:
            json.dump(crossing_data, f, indent=4)

    # Create comprehensive visualization showing everything detected
    create_comprehensive_detection_visualization(original_image, components, crossing_data, output_folder)

    # STEP 2: Connected component labeling to identify node blobs
    num_labels, node_labels, stats, centroids = cv2.connectedComponentsWithStats(
        circuit_cut.astype(np.uint8), connectivity=8)

    # saving node labels to be later used for netlist generation 
    np.save(os.path.join(output_folder, "node_labels.npy"), node_labels)

    step2_node_vis = np.zeros((h, w, 3), dtype=np.uint8)
    for label_id in range(1, num_labels):
        color = np.random.randint(0, 255, 3).tolist()
        step2_node_vis[node_labels == label_id] = color
    write_image(os.path.join(output_folder, "7_node_labels.png"), step2_node_vis)

    # STEP 3: Identify valid nodes and collect raw contact points
    valid_nodes = set()
    node_to_components = defaultdict(set)
    component_to_nodes = defaultdict(set)
    raw_contact_points = defaultdict(list)  # (component_id -> list of (x, y))

    for component in components:
        x_min, y_min, x_max, y_max = component["bbox"]
        comp_id = component["id"]
        comp_perimeter = np.zeros((h, w), dtype=np.uint8)
        if y_min < h: comp_perimeter[y_min, max(0, x_min):min(w, x_max + 1)] = 1
        if y_max < h: comp_perimeter[y_max, max(0, x_min):min(w, x_max + 1)] = 1
        if x_min < w: comp_perimeter[max(0, y_min):min(h, y_max + 1), x_min] = 1
        if x_max < w: comp_perimeter[max(0, y_min):min(h, y_max + 1), x_max] = 1

        for label_id in range(1, num_labels):
            node_mask = (node_labels == label_id)
            intersection = np.logical_and(comp_perimeter, node_mask)
            if np.any(intersection):
                valid_nodes.add(label_id)
                node_to_components[label_id].add(comp_id)
                component_to_nodes[comp_id].add(label_id)

                y_points, x_points = np.where(intersection)
                for cx, cy in zip(x_points, y_points):
                    raw_contact_points[comp_id].append((cx, cy))

    # STEP 4: Show valid nodes and all raw contact points
    step4_vis = np.zeros((h, w, 3), dtype=np.uint8)
    for node_id in valid_nodes:
        color = np.random.randint(0, 255, 3).tolist()
        step4_vis[node_labels == node_id] = color

    component_colors = {
        component["id"]: (random.randint(100, 255), random.randint(100, 255), random.randint(100, 255))
        for component in components
    }

    for component in components:
        comp_id = component["id"]
        x_min, y_min, x_max, y_max = component["bbox"]
        color = component_colors[comp_id]
        cv2.rectangle(step4_vis, (x_min, y_min), (x_max, y_max), (255, 255, 255), 1)
        cv2.putText(step4_vis, comp_id, (x_min, y_min - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
        for (cx, cy) in raw_contact_points[comp_id]:
            cv2.circle(step4_vis, (cx, cy), 2, color, -1)

    write_image(os.path.join(output_folder, "8_valid_nodes.png"), step4_vis)

    # STEP 4.5: Add bridge components immediately after node validation
    if crossing_data and disambiguation_context == "line1_connected":
        from .process_images import inject_bridge_components
        updated_components = inject_bridge_components(updated_components, crossing_data, disambiguation_context)
        print(f"Bridge components added after 8_valid_nodes.png generation. Total components: {len(updated_components)}")

        # Process bridge components to add their contact points
        try:
            for component in updated_components:
                if component.get("type") == "Bridge" and "center_point" in component:
                    comp_id = component["id"]
                    x, y = component["center_point"]
                    # Add bridge center point as raw contact point
                    if comp_id not in raw_contact_points:
                        raw_contact_points[comp_id] = []
                    raw_contact_points[comp_id].append((x, y))
                    print(f"Added raw contact point for bridge {comp_id} at ({x}, {y})")

            # Add colors for bridge components
            for component in updated_components:
                if component.get("type") == "Bridge":
                    comp_id = component["id"]
                    if comp_id not in component_colors:
                        component_colors[comp_id] = (255, 0, 255)  # Magenta for bridges

            # STEP 4.7: Attach bridge components to nearest nodes (before filtering)
            component_connections = defaultdict(list)

            for component in updated_components:
                if component.get("type") == "Bridge" and "center_point" in component:
                    comp_id = component["id"]
                    bridge_x, bridge_y = component["center_point"]

                    # Find nearest node to bridge center point (search all nodes, not just filtered ones)
                    min_distance = float('inf')
                    nearest_node_point = None

                    # Look through all nodes and find the closest one
                    for node_id in range(1, np.max(node_labels) + 1):
                        node_mask = (node_labels == node_id)
                        node_pixels = np.argwhere(node_mask)

                        if node_pixels.size > 0:
                            # Calculate distances from bridge center to all pixels of this node
                            for pixel in node_pixels:
                                pixel_y, pixel_x = pixel  # argwhere returns (y, x)
                                distance = np.sqrt((bridge_x - pixel_x)**2 + (bridge_y - pixel_y)**2)

                                if distance < min_distance:
                                    min_distance = distance
                                    nearest_node_point = (pixel_x, pixel_y)

                    if nearest_node_point:
                        x, y = nearest_node_point
                        # Convert numpy int64 to regular Python int for JSON serialization
                        x, y = int(x), int(y)
                        component_connections[comp_id].append((x, y))
                        print(f"Connected bridge {comp_id} to nearest node at ({x}, {y}) - distance: {min_distance:.1f}")
                    else:
                        # Fallback to center point if no nodes found
                        x, y = int(bridge_x), int(bridge_y)
                        component_connections[comp_id].append((x, y))
                        print(f"No nodes found, using bridge center for {comp_id} at ({x}, {y})")

            # STEP 4.8: Create debugging visualizations after bridge attachment
            # Create first debugging image (before filtering)
            step4b_vis = original_image.copy()

            # Draw all nodes (including those that will be filtered out)
            for node_id in range(1, np.max(node_labels) + 1):
                node_mask = (node_labels == node_id)
                if np.any(node_mask):
                    # Count how many different components connect to this node
                    connected_components = len(node_to_components.get(node_id, []))
                    # Add bridge connections to the count
                    bridge_connections = 0
                    for bridge_comp_id, bridge_points in component_connections.items():
                        for (bx, by) in bridge_points:
                            if 0 <= by < node_labels.shape[0] and 0 <= bx < node_labels.shape[1]:
                                if node_labels[by, bx] == node_id:
                                    bridge_connections += 1
                                    break

                    total_connections = connected_components + bridge_connections

                    # Color based on validity: green = valid (2+ components), orange = invalid (1 component)
                    if total_connections >= 2:
                        node_color = (0, 255, 0)  # Green for valid nodes
                    else:
                        node_color = (0, 165, 255)  # Orange for invalid nodes

                    # Fill the node area with the validity color
                    step4b_vis[node_mask] = node_color

            # Draw all components (including bridges)
            for component in updated_components:
                comp_id = component["id"]
                x_min, y_min, x_max, y_max = component["bbox"]

                # Different colors for different component types
                if component.get("type") == "Bridge":
                    color = (255, 0, 255)  # Magenta for bridges
                    # Draw bridge as circle instead of rectangle
                    center_x, center_y = component["center_point"]
                    cv2.circle(step4b_vis, (center_x, center_y), 5, color, -1)
                else:
                    color = component_colors.get(comp_id, (255, 255, 255))  # Original component colors
                    thickness = 2
                    cv2.rectangle(step4b_vis, (x_min, y_min), (x_max, y_max), color, thickness)
                cv2.putText(step4b_vis, comp_id, (x_min, y_min - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

            # Draw connection points for all components
            for comp_id, points in raw_contact_points.items():
                for (x, y) in points:
                    cv2.circle(step4b_vis, (x, y), 2, (255, 255, 255), -1)  # White dots for connection points

            write_image(os.path.join(output_folder, "8b_nodes_with_bridges_before_filtering.png"), step4b_vis)

            # Create second debugging image (showing bridge attachments)
            step6b_vis = step4b_vis.copy()

            # Only add bridge attachment visualization (lines and connection points)
            for component in updated_components:
                if component.get("type") == "Bridge":
                    comp_id = component["id"]
                    # Draw connection lines from bridge to nearest nodes
                    if comp_id in component_connections:
                        bridge_center = component["center_point"]
                        for (conn_x, conn_y) in component_connections[comp_id]:
                            cv2.line(step6b_vis, bridge_center, (conn_x, conn_y), (255, 255, 255), 2)
                            cv2.circle(step6b_vis, (conn_x, conn_y), 5, (0, 255, 255), -1)  # Cyan for connection points

            write_image(os.path.join(output_folder, "8c_bridges_attached_to_nearest_nodes.png"), step6b_vis)

        except Exception as e:
            print(f"Error processing bridge components: {e}")
            import traceback
            traceback.print_exc()
    else:
        component_connections = defaultdict(list)


    # STEP 5: Cluster raw contact points into logical connection points
    clustered_contact_points = defaultdict(list)
    cluster_vis = original_image.copy()

    for comp_id, points in raw_contact_points.items():
        if len(points) == 0:
            continue

        points_array = np.array(points)
        clustering = DBSCAN(eps=10, min_samples=1).fit(points_array)  # eps = pixel radius
        labels = clustering.labels_

        unique_labels = set(labels)
        for cluster_id in unique_labels:
            if cluster_id == -1:
                continue  # skip noise

            cluster_pts = points_array[labels == cluster_id]
            if cluster_pts.shape[0] == 0:
                continue  # skip empty cluster just in case

            cx = int(np.mean(cluster_pts[:, 0]))
            cy = int(np.mean(cluster_pts[:, 1]))
            clustered_contact_points[comp_id].append((cx, cy))

            # Draw the clustered point
            cv2.circle(cluster_vis, (cx, cy), 4, component_colors[comp_id], -1)
            cv2.putText(cluster_vis, comp_id, (cx + 4, cy - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, component_colors[comp_id], 1)

    write_image(os.path.join(output_folder, "9_clustered_connection_points.png"), cluster_vis)

    # STEP 6: Filter clustered contact points by real node intersection
    # Include bridge connections when counting components per node
    updated_node_to_components = defaultdict(set)

    # Start with original component connections
    for node_id, comps in node_to_components.items():
        updated_node_to_components[node_id].update(comps)

    # Add bridge connections to the count
    for bridge_comp_id, bridge_points in component_connections.items():
        for (bx, by) in bridge_points:
            if 0 <= by < node_labels.shape[0] and 0 <= bx < node_labels.shape[1]:
                node_id = node_labels[by, bx]
                if node_id > 0:
                    updated_node_to_components[node_id].add(bridge_comp_id)

    real_nodes = {n for n, comps in updated_node_to_components.items() if len(comps) >= 2}
    component_to_real_nodes = {
        comp_id: [n for n in nodes if n in real_nodes]
        for comp_id, nodes in component_to_nodes.items()
    }

    # Bridge components were already processed and attached after injection

    step6_intersections = original_image.copy()

    # Continue with normal component processing
    for component in updated_components:
        comp_id = component["id"]

        # Skip bridge components as they are already processed
        if component.get("type") == "Bridge":
            continue

        # Normal component connection point detection
        if comp_id not in clustered_contact_points or comp_id not in component_to_real_nodes:
            continue

        relevant_nodes = component_to_real_nodes[comp_id]
        for (x, y) in clustered_contact_points[comp_id]:
            for node_id in relevant_nodes:
                node_mask = (node_labels == node_id)
                if node_mask[y, x]:  # pixel overlaps node
                    component_connections[comp_id].append((x, y))
                    cv2.circle(step6_intersections, (x, y), 3, (0, 0, 255), -1)
                    break  # avoid duplicating same point for multiple nodes

    write_image(os.path.join(output_folder, "10_node_intersections.png"), step6_intersections)

    # STEP 6a: Visualize only real (valid) nodes with connection points and bounding boxes
    valid_node_only_vis = original_image.copy()

    # Use a single color for all valid nodes (cyan)
    valid_node_color = (0, 225, 0)
    for node_id in real_nodes:
        valid_node_only_vis[node_labels == node_id] = valid_node_color

    # Overlay the actual confirmed connection points
    for comp_id, points in component_connections.items():
        for (x, y) in points:
            cv2.circle(valid_node_only_vis, (x, y), 3, (0, 0, 255), -1)  # red dot

    # Draw bounding boxes for components
    for component in components:
        x_min, y_min, x_max, y_max = component["bbox"]
        comp_id = component["id"]
        cv2.rectangle(valid_node_only_vis, (x_min, y_min), (x_max, y_max), (255, 155, 0) , 1)

    # Save the visualization
    write_image(os.path.join(output_folder, "10a_valid_nodes_with_contacts_and_boxes.png"), valid_node_only_vis)

    # STEP 7: Final annotated result — clean output with labeled connection points
    final_image = original_image.copy()
    for comp_id, points in component_connections.items():
        for (x, y) in points:
            cv2.circle(final_image, (x, y), 4, (0, 0, 255), -1)
            cv2.putText(final_image, comp_id, (x + 5, y - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)

    write_image(os.path.join(output_folder, "11_final_connection_points.png"), final_image)

    # prepare circuit_info.json for netlist generation
    save_circuit_info_json(updated_components, component_connections, output_folder)
