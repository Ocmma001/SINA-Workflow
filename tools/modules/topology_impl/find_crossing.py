from ..image_io import read_image, write_image
import cv2
import math
import numpy as np
import os
import json

DETECTION_COLOR = (0,255,0)
CROSSING_DOT_COLOR = (0,0,255)  # Red color for crossing dots
MIN_LINE_LENGTH = 15
REDUCTION = 2
DOT_RADIUS = 10  # Radius of red dots at crossings


def getDots(img):
    """
    Function applies morphological operation with a circular kernel for detecting connection
    dots in schematic.
    """
    
    # convert to grayscale and then create threshold image
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY_INV)

    # apply morpohlogical operation to extract connection dots
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3,3))
    opening = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=3)

    # find contours of connection dots
    roundCnts, _ = cv2.findContours(opening, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    return roundCnts


def removeObjects(image, components, dots):
    """Mask exactly the caller's frozen boxes; never load a detector here."""
    img = image.copy()
    background = tuple(int(v) for v in img[0, 0])
    height, width = img.shape[:2]
    for component in components:
        box = component['bbox']
        if len(box) != 4 or not all(math.isfinite(float(v)) for v in box):
            raise ValueError('Invalid component bounding box')
        x1, y1, x2, y2 = [int(v) for v in box]
        if x2 <= x1 or y2 <= y1:
            raise ValueError('Empty component bounding box')
        left, top = max(0, x1-REDUCTION), max(0, y1-REDUCTION)
        right, bottom = min(width-1, x2+REDUCTION), min(height-1, y2+REDUCTION)
        if left <= right and top <= bottom:
            cv2.rectangle(img, (left, top), (right, bottom), background, -1)
    if dots is not None:
        for contour in dots:
            ((x, y), radius) = cv2.minEnclosingCircle(contour)
            cv2.circle(img, (int(x), int(y)), int(radius+2), background, -1)
    return img


def getContours(refImg):
    """
    Function finds contours in each extracted image and finds corner coordinates of
    bounding rectangles around each contour 
    """
    
    # find contours
    cnts, _  = cv2.findContours(refImg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # get corner coordinates of bounding rectangles and store in list
    boxes = []
    for c in cnts:
        rect = cv2.minAreaRect(c)
        box = cv2.boxPoints(rect)
        box = np.intp(box)
        boxes.append(box)

    return boxes


def ccw(X,Y,Z):
    return (Z[1]-X[1]) * (Y[0]-X[0]) > (Y[1]-X[1]) * (Z[0]-X[0])


def checkForIntersection(line1, line2):
    """
    Explanation for this of method of checking for intersection two lines
    is at https://www.geeksforgeeks.org/dsa/check-if-two-given-line-segments-intersect/
    """ 
    A = line1[0]
    B = line1[1]
    
    C = line2[0]
    D = line2[1]

    if ccw(A,C,D) != ccw(B,C,D) and ccw(A,B,C) != ccw(A,B,D):
        return True

    return False


def getIntersectionPoint(line1, line2):
    """
    Calculate the intersection point of two line segments.
    Returns the intersection point (x, y) if lines intersect, None otherwise.
    """
    x1, y1 = line1[0]
    x2, y2 = line1[1]
    x3, y3 = line2[0]
    x4, y4 = line2[1]
    
    # Calculate the denominator
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    
    # If denominator is 0, lines are parallel
    if abs(denom) < 1e-10:
        return None
    
    # Calculate intersection point
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denom
    
    # Check if intersection is within both line segments
    if 0 <= t <= 1 and 0 <= u <= 1:
        x = x1 + t * (x2 - x1)
        y = y1 + t * (y2 - y1)
        return (int(x), int(y))
    
    return None


def makeLines(boxes, code):
    """
    Function is responsible for finding line endpoints from rectangle's bounding contours.
    Each rectangle is described by four points corresponding to its four corners. From 
    experimentation, it seems there are two possible arrangements in which OpenCV stores these points,
    with no discernible pattern for when one arrangement is used. If a line is extrapolated based on the 
    wrong arrangement of rectangle corners, that line will span the width of the rectangle and thus be extremely 
    short. The right line will obviously cover the rectangle's length, and thus the right arrangement is the 
    one that produces the longest line (at least in all of the cases I've tried). Therefore, this function 
    produces two lines, one based on each possible arrangement of corner points, and the longest line is the 
    one that corresponds to the wire segment in the schematic.
    """
    
    # empty list to store lines produced from rectangle corner coordinates
    linePts = []
    
    # create lines based on both possible arrangements of corner points
    for box in boxes:
        x1 = int((box[0][0] + box[3][0]) / 2)
        x2 = int((box[1][0] + box[2][0]) / 2)
        y1 = int((box[0][1] + box[3][1]) / 2)
        y2 = int((box[1][1] + box[2][1]) / 2)
        line1 = [(x1,y1),(x2,y2)]
        
        a1 = int((box[0][0] + box[1][0]) / 2)
        a2 = int((box[2][0] + box[3][0]) / 2)
        b1 = int((box[0][1] + box[1][1]) / 2)
        b2 = int((box[2][1] + box[3][1]) / 2)
        line2 = [(a1,b1),(a2,b2)]
        
        # find length of both lines
        lenLine1 = math.sqrt((x1-x2)**2 + (y1-y2)**2)
        lenLine2 = math.sqrt((a1-a2)**2 + (b1-b2)**2)

        # longest line is stored in list of correct lines
        # also check if longest line is longer than minimum line length parameter
        if lenLine1 > lenLine2 and lenLine1 > MIN_LINE_LENGTH:
            linePts.append(line1)
        elif lenLine2 > lenLine1 and lenLine2 > MIN_LINE_LENGTH:
            linePts.append(line2)

    return linePts


def getLines(img, outputPath):
    """
    Function responsible for finding crossing lines, contains four main steps:
    1. Convert input 'img' into binary
    2. Isolate horizontal, vertical, forward diagonal, and backward diagonal
       lines through a series of morphological operations
    3. Find coordinates for lines in schematics using bounding rectangles around contours
    4. Iterate through detected lines and check if they're crossing
    """

    print(f"\nSTARTING LINE DETECTION PROCESS...")
    print(f" Input image shape: {img.shape}")
    print(f" Output path: {outputPath}")
    
    # convert image to grayscale, then create threshold image
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray,100,255,cv2.THRESH_BINARY_INV)

    # create kernels for isolating diagonal lines of both orientations
    backDiagKern = np.eye(19)
    forwardDiagKern = np.fliplr(backDiagKern)
    backDiagKern = backDiagKern.astype(np.uint8)
    forwardDiagKern = forwardDiagKern.astype(np.uint8)
    
    # create kernels for isolating horizontal and vertical lines
    vertKern = np.ones((15,1),np.uint8)
    horzKern = np.ones((1,20),np.uint8)

    # dilate threshold image to make morphological operations detect more detail
    dilateKern = np.ones((3,3),np.int8)
    thresh = cv2.dilate(thresh, dilateKern, iterations=1)

    # Apply morphological operations to get extracted images
    imgVert = cv2.erode(thresh, vertKern, iterations=1)
    imgHorz = cv2.erode(thresh, horzKern, iterations=1)
    imgBackDiag = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, backDiagKern, iterations=1)
    imgForwardDiag = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, forwardDiagKern, iterations=1)

    # dilate extracted images to make contours more pronounced
    dilateKern = np.ones((3,3),np.int8)
    imgVert = cv2.dilate(imgVert, dilateKern, iterations=1)
    imgHorz = cv2.dilate(imgHorz, dilateKern, iterations=1)
    imgBackDiag = cv2.dilate(imgBackDiag, dilateKern, iterations=3)
    imgForwardDiag = cv2.dilate(imgForwardDiag, dilateKern, iterations=3)

    # find boxes bounding contours
    vertBoxes = getContours(imgVert)
    horzBoxes = getContours(imgHorz)
    backDiagBoxes = getContours(imgBackDiag)
    forwardDiagBoxes = getContours(imgForwardDiag)
    
    # extrapolate line endpoints from boxes
    vertLines = makeLines(vertBoxes,1)
    horzLines = makeLines(horzBoxes,0)
    backDiagLines = makeLines(backDiagBoxes,1)
    forwardDiagLines = makeLines(forwardDiagBoxes,0)

    # revert extracted images back to RBG so that lines can be drawn for debugging
    imgVert = cv2.cvtColor(imgVert, cv2.COLOR_GRAY2BGR)
    imgHorz = cv2.cvtColor(imgHorz, cv2.COLOR_GRAY2BGR)
    imgBackDiag = cv2.cvtColor(imgBackDiag, cv2.COLOR_GRAY2BGR)
    imgForwardDiag = cv2.cvtColor(imgForwardDiag, cv2.COLOR_GRAY2BGR)

    # draw lines
    for line in vertLines:
        cv2.line(imgVert, line[0], line[1], DETECTION_COLOR, 2)
    for line in horzLines:
        cv2.line(imgHorz, line[0], line[1], DETECTION_COLOR, 2)
    for line in backDiagLines:
        cv2.line(imgBackDiag, line[0], line[1], DETECTION_COLOR, 2)
    for line in forwardDiagLines:
        cv2.line(imgForwardDiag, line[0], line[1], DETECTION_COLOR, 2)
    
    # intersection detections assumes that crossing lines are normal to each other 
    # ie only horz and vert, or backDiag and forwardDiag lines intersect
    intersecting = []
    crossingPoints = []  # Store intersection points for red dots
    crossingLinePairs = []  # Store line pairs for each crossing
    
    for vertLine in vertLines:
        intersected = False
        for horzLine in horzLines:
            isIntersecting = checkForIntersection(vertLine, horzLine)
            if isIntersecting:  
                intersecting.append(horzLine)
                intersected = True
                # Calculate and store intersection point
                intersection_point = getIntersectionPoint(vertLine, horzLine)
                if intersection_point:
                    crossingPoints.append(intersection_point)
                    # Store the line pair (vertical line, horizontal line, line types)
                    crossingLinePairs.append((vertLine, horzLine, "vertical", "horizontal"))
    
        # wait to add each vertLine until inner loop is completed so not counted multiple times
        # in case multiple lines cross the same line
        if intersected == True: 
            intersecting.append(vertLine)
        
    for backDiagLine in backDiagLines:
        intersected = False
        for forwardDiagLine in forwardDiagLines:
            isIntersecting = checkForIntersection(backDiagLine, forwardDiagLine)
            if isIntersecting:   
                intersecting.append(forwardDiagLine)
                intersected = True
                # Calculate and store intersection point
                intersection_point = getIntersectionPoint(backDiagLine, forwardDiagLine)
                if intersection_point:
                    crossingPoints.append(intersection_point)
                    # Store the line pair (back diagonal line, forward diagonal line, line types)
                    crossingLinePairs.append((backDiagLine, forwardDiagLine, "backward_diagonal", "forward_diagonal"))

        if intersected == True: 
            intersecting.append(backDiagLine)

    # output debug results for each extracted image
    write_image(outputPath.replace('.', 'vert.'), imgVert)
    write_image(outputPath.replace('.', 'horz.'), imgHorz)
    write_image(outputPath.replace('.', 'backD.'), imgBackDiag)
    write_image(outputPath.replace('.', 'forwD.'), imgForwardDiag)

    # Save all detected lines to JSON for visualization (before returning)
    debugDir = os.path.dirname(outputPath)
    all_lines_json_path = os.path.join(debugDir, "testing_all_lines.json")

    print(f"\nPREPARING TO SAVE ALL DETECTED LINES...")
    print(f"   Vertical lines: {len(vertLines)}")
    print(f"   Horizontal lines: {len(horzLines)}")
    print(f"   Backward diagonal lines: {len(backDiagLines)}")
    print(f"   Forward diagonal lines: {len(forwardDiagLines)}")

    # Collect all detected lines
    all_detected_lines = []

    # Add all vertical lines
    for line in vertLines:
        all_detected_lines.append({
            "start": [int(line[0][0]), int(line[0][1])],
            "end": [int(line[1][0]), int(line[1][1])],
            "type": "vertical"
        })

    # Add all horizontal lines
    for line in horzLines:
        all_detected_lines.append({
            "start": [int(line[0][0]), int(line[0][1])],
            "end": [int(line[1][0]), int(line[1][1])],
            "type": "horizontal"
        })

    # Add all backward diagonal lines
    for line in backDiagLines:
        all_detected_lines.append({
            "start": [int(line[0][0]), int(line[0][1])],
            "end": [int(line[1][0]), int(line[1][1])],
            "type": "backward_diagonal"
        })

    # Add all forward diagonal lines
    for line in forwardDiagLines:
        all_detected_lines.append({
            "start": [int(line[0][0]), int(line[0][1])],
            "end": [int(line[1][0]), int(line[1][1])],
            "type": "forward_diagonal"
        })

    print(f"   TOTAL LINES: {len(all_detected_lines)}")

    all_lines_data = {
        "total_lines": len(all_detected_lines),
        "vertical_lines": len(vertLines),
        "horizontal_lines": len(horzLines),
        "backward_diagonal_lines": len(backDiagLines),
        "forward_diagonal_lines": len(forwardDiagLines),
        "all_lines": all_detected_lines
    }

    print(f"Saving all lines data to: {all_lines_json_path}")

    try:
        with open(all_lines_json_path, 'w') as f:
            json.dump(all_lines_data, f, indent=4)
        print(f"Successfully saved testing_all_lines.json!")
    except Exception as e:
        print(f"ERROR saving testing_all_lines.json: {e}")

    print(f"SUMMARY: Total lines detected: {len(all_detected_lines)} (V:{len(vertLines)}, H:{len(horzLines)}, BD:{len(backDiagLines)}, FD:{len(forwardDiagLines)})")

    return intersecting, crossingPoints, crossingLinePairs


def detectCrossingLines(imgPath, modelPath, outputPath, debugPath, *, components=None):
    """
    Program handles overall structure of program. Schematic image is first loaded,
    then connection dots and component symbols are removed from the image. Then the 
    coordinates for the endpoints of detected crossing lines are returned, drawn on 
    original schematic, and outputed to results folder  
    """
    
    # modelPath remains positional for compatibility; detection belongs upstream.
    if components is None:
        raise ValueError('Frozen component boxes are required for crossing analysis')
    img = read_image(imgPath)
    
    # simplifiy images and isolate crossing wires
    roundCnts = getDots(img)
    workingImg = removeObjects(img, components, roundCnts)
    
    # find coordinates of endpoints of crossing line and intersection points
    interLines, crossingPoints, crossingLinePairs = getLines(workingImg, debugPath)

    # draw crossing lines with proper colors based on their types
    if crossingLinePairs:
        for line1, line2, type1, type2 in crossingLinePairs:
            # Draw line1 with color based on its type
            if type1 == 'horizontal':
                color1 = (0, 165, 255)  # Orange
            elif type1 == 'vertical':
                color1 = (0, 255, 0)  # Green
            elif type1 == 'backward_diagonal':
                color1 = (0, 0, 255)  # Red
            elif type1 == 'forward_diagonal':
                color1 = (255, 0, 0)  # Blue
            else:
                color1 = (128, 128, 128)  # Gray

            # Draw line2 with color based on its type
            if type2 == 'horizontal':
                color2 = (0, 165, 255)  # Orange
            elif type2 == 'vertical':
                color2 = (0, 255, 0)  # Green
            elif type2 == 'backward_diagonal':
                color2 = (0, 0, 255)  # Red
            elif type2 == 'forward_diagonal':
                color2 = (255, 0, 0)  # Blue
            else:
                color2 = (128, 128, 128)  # Gray

            cv2.line(img, line1[0], line1[1], color1, 2)
            cv2.line(img, line2[0], line2[1], color2, 2)
    
    # draw crossing points (matching comprehensive visualization style)
    if crossingPoints:
        for point in crossingPoints:
            # Use same style as comprehensive visualization - small yellow circles with black border
            cv2.circle(img, point, 10, (0, 255, 255), -1)  # Yellow circle, radius 10
            cv2.circle(img, point, 10, (0, 0, 0), 1)  # Black border
    
    # save crossing coordinates to text file in debug folder
    if crossingPoints:
        # create coordinates text file path
        debugDir = os.path.dirname(debugPath)
        filename = os.path.splitext(os.path.basename(imgPath))[0]
        coordsPath = os.path.join(debugDir, f"{filename}_crossing_coordinates.txt")
        jsonPath = os.path.join(debugDir, f"{filename}_crossing_data.json")
        
        # write coordinates to text file (backward compatibility)
        with open(coordsPath, 'w') as f:
            f.write("Crossing Points Coordinates (x, y):\n")
            f.write("=" * 35 + "\n")
            for i, point in enumerate(crossingPoints, 1):
                f.write(f"Crossing {i}: ({point[0]}, {point[1]})\n")
            f.write(f"\nTotal crossings detected: {len(crossingPoints)}\n")
        
        # create JSON data with crossing points and line information
        crossing_data = {
            "total_crossings": len(crossingPoints),
            "crossings": []
        }
        
        for i, (point, line_data) in enumerate(zip(crossingPoints, crossingLinePairs)):
            line1, line2, type1, type2 = line_data
            crossing_info = {
                "id": i + 1,
                "crossing_point": [int(point[0]), int(point[1])],
                "line1": {
                    "start": [int(line1[0][0]), int(line1[0][1])],
                    "end": [int(line1[1][0]), int(line1[1][1])],
                    "type": type1
                },
                "line2": {
                    "start": [int(line2[0][0]), int(line2[0][1])],
                    "end": [int(line2[1][0]), int(line2[1][1])],
                    "type": type2
                }
            }
            crossing_data["crossings"].append(crossing_info)
        
        # write JSON data to file
        with open(jsonPath, 'w') as f:
            json.dump(crossing_data, f, indent=4)
    
    # output result
    write_image(outputPath, img)


if __name__ == '__main__':
    inputDir = "inputs"
    mainOutputDir = "outputs"

    os.makedirs(mainOutputDir, exist_ok=True)

    supported_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}

    modelPath = "weights/best.pt" # path to machine learning model for detecting component symbols
    for filename in os.listdir(inputDir):
        ext = os.path.splitext(filename)[1].lower()
        if ext in supported_extensions:
            inputPath = os.path.join(inputDir, filename)
            mainOutputPath = os.path.join(mainOutputDir, filename)
            
            # create a debug folder inside 'outputs' for each input schematic 
            debugOutputDir = f"outputs/{filename.replace('.', '_debug')}"
            os.makedirs(debugOutputDir, exist_ok=True)
            debugOutputPath = os.path.join(debugOutputDir, filename)

            print(f"\nProcessing {filename}...")
            detectCrossingLines(inputPath, modelPath, mainOutputPath, debugOutputPath)