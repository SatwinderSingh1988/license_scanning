# IMAGE DETECTION API
# pip install fastapi paddlepaddle paddleocr uvicorn pyngrok
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import re
import os
import uvicorn
from paddleocr import PaddleOCR
from datetime import datetime

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# Initialize PaddleOCR
ocr = PaddleOCR(use_angle_cls=True, lang='en', gpu=True)

# List of possible license types
possible_license_types = ["CAR", "MOTORCYCLE", "TRUCK", "BUS", "TRACTOR", "VAN", "TAXI", "LORRY", "COACH"]
exclude_keywords = ['DRIVER', 'LICENCE', 'EXP', 'DATE', 'OF', 'BIRTH', 'CONDITIONS', 'TYPE', 'AUSTRALIA']

def extract_name(lines):
    possible_names = []

    # Use context clues method
    context_clues_names = []
    for i, line in enumerate(lines):
        if re.match(r'^[A-Z\s]+$', line) and all(keyword not in line for keyword in exclude_keywords):
            if i > 0 and re.match(r'^[A-Z\s]+$', lines[i-1]):
                context_clues_names.append(line.strip())
            elif i < len(lines) - 1 and re.match(r'^[A-Z\s]+$', lines[i+1]):
                context_clues_names.append(line.strip())

    # Simple pattern matching method
    simple_pattern_names = []
    for line in lines:
        if re.match(r'^[A-Z\s]+$', line) and 'DRIVER' not in line and 'LICENSE' not in line and 'EXP' not in line and 'DOB' not in line and 'ISS' not in line:
            simple_pattern_names.append(line.strip())

    # Decide which method to use based on the results
    if context_clues_names:
        possible_names.extend(context_clues_names)
    elif simple_pattern_names:
        possible_names.extend(simple_pattern_names)

    # Extract the full name
    full_name = ' '.join(possible_names).strip()

    # Only use the first two words as the name
    name_parts = full_name.split()
    if len(name_parts) > 2:
        full_name = ' '.join(name_parts[:2])

    return full_name

# Function to extract gender
def extract_gender(text):
    gender = ''
    # Regular expressions for male
    male_regex = r'^(male|Male|SexM)$'
    male_match = re.search(male_regex, text)
    if male_match:
        gender = 'Male'

    # Regular expressions for female
    female_regex = r'^(female|Female|SexF)$'
    female_match = re.search(female_regex, text)
    if female_match:
        gender = 'Female'

    return gender

def extract_dates(text):
    expiry_date = ''
    dob = ''
    iss_date = ''
    date_pattern = r'\b(\d{2}-\d{2}-\d{4})\b'
    # Find all dates in the text
    dates = re.findall(date_pattern, text)
    
    # If no dates are found, return None
    if not dates:
        return None, None
    
    dates = [datetime.strptime(date, '%d-%m-%Y') for date in dates]
    dates.sort()

    dob_match = re.search(r'\b(\d{2}-\d{2}-\d{4})\s*,*\s*DATE\s*O?F?\s*BIRTH\b', text, re.IGNORECASE)
    if dob_match:
        dob = dob_match.group(1)
    else:
        dob = dates[0].strftime('%d-%m-%Y') if len(dates) > 0 else None

    iss_date_match = re.search(r'\bISSUED\s*(\d{2}-\d{2}-\d{4})', text, re.IGNORECASE)
    if iss_date_match:
        iss_date = iss_date_match.group(1)
    else:
        iss_date_match = re.search(r'ISS\s*([\d/-]+)', text, re.IGNORECASE)
        if iss_date_match:
            # Search for the actual date pattern within the matched text
            iss_date_date_match = re.search(r'\d{2}[-/]\d{2}[-/]\d{4}', iss_date_match.group(1))
            if iss_date_date_match:
                iss_date = iss_date_date_match.group(0)

    exp_date_match = re.search(r'\bLICENCE\s*EXPIRY\s*(\d{2}-\d{2}-\d{4})', text, re.IGNORECASE)
    if exp_date_match:
        expiry_date = exp_date_match.group(1)
    else:
        expiry_date = dates[-1].strftime('%d-%m-%Y') if len(dates) > 1 else None

    return expiry_date, dob, iss_date


# Function to extract license type
def extract_license_type(lines):
    for line in lines:
        for l_type in possible_license_types:
            if l_type in line:
                return l_type
    return ''

# Function to extract address
def extract_address(text):
    # This regex pattern captures addresses in the format you provided
    address_pattern = re.compile(r'\b[A-Z0-9]+\s*[A-Z0-9]*\s*[A-Z]+\s+[A-Z]+\s+[A-Z]{2,3}\s+\d{4}\b')
    matches = address_pattern.findall(text)

    filtered_addresses = []

    for match in matches:
        for keyword in exclude_keywords:
            if keyword in match:
                # Replace the keyword with a space
                match = match.replace(keyword, ' ')

        # Replace newline characters with spaces and strip any extra whitespace
        formatted_address = re.sub(r'\s+', ' ', match).strip()
        if formatted_address:
            filtered_addresses.append(formatted_address)

    if filtered_addresses:
        return "\n".join(filtered_addresses)
    return ''

# Function to extract height information
def extract_height(text):
    height_match = re.search(r'Hgt[\d\'\-"]+', text)
    if height_match:
        height_match = height_match.group(0).replace('Hgt', '').replace('"', '').replace('\\', '').strip()
        return height_match
    return ''

# Function to extract eye color information
def extract_eye_color(text):
    eye_color_match = re.search(r'Eyes[A-Z]+', text)
    if eye_color_match:
        return eye_color_match.group(0).replace('Eyes', '').strip()
    return ''

#  Function to extract issuing state
def extract_issuing_state(text):
    states = ['ACT', 'NSW', 'NT', 'QLD', 'SA', 'TAS', 'VIC', 'WA']
    for state in states:
        if state in text:
            return state

#  Function to extract Post code
def extract_post_code(text):
    # check for postcode after state in the entire text
    state = extract_issuing_state(text)
    if state:
        # Look for state followed by a four-digit number
        pattern = rf'{state}\s+(\d{{4}})'
        match = re.search(pattern, text)
        if match:
            return match.group(1)

    # If no state or no four-digit number after the state, check the entire text
    postcodes_in_text = re.findall(r'\b(?!19|20)\d{4}\b', text)
    if postcodes_in_text:
        return postcodes_in_text[-1]

    return None

# FastAPI endpoint for uploading image and extracting information
@app.post("/extract_info/")
async def upload_file(file: UploadFile = File(...)):
    # Save the uploaded image temporarily
    with open(file.filename, "wb") as image_file:
        image_file.write(await file.read())

    # Perform OCR on the uploaded image
    result = ocr.ocr(file.filename, cls=True)
    os.remove(file.filename)

    # Extracted text from OCR result
    extracted_text_lines = [line[-1][0] for line in result[0]]
    extracted_text = "\n".join(extracted_text_lines)

    # Initialize variables to store extracted information
    extracted_info = {
        'name': '',
        'expiry_date': '',
        'dob': '',
        'issue_date': '',
        'gender': '',
        'address': '',
        'id': '',
        'height': '',
        'eyes_color': '',
        'license_type': '',
        'issuing_state': '',
        'post_code': ''
    }

    # Extract name
    extracted_info['name'] = extract_name(extracted_text_lines)

    # Extract ID number (9 digits)
    id_number_match_1 = re.search(r'\b[0-9]{9}\b', extracted_text)

    # Extract ID number (14-16 alphanumeric characters)
    id_number_match_2 = re.search(r'\b[A-Z0-9]{14,16}\b', extracted_text)

    if id_number_match_1:
        extracted_info['id'] = id_number_match_1.group(0).strip()
    elif id_number_match_2:
        extracted_info['id'] = id_number_match_2.group(0).strip()

    # Extracted information
    extracted_info['expiry_date'], extracted_info['dob'], extracted_info['iss_date'] = extract_dates(extracted_text)
    extracted_info['gender'] = extract_gender(extracted_text)
    extracted_info['license_type'] = extract_license_type(extracted_text_lines)
    extracted_info['height'] = extract_height(extracted_text)
    extracted_info['eyes_color'] = extract_eye_color(extracted_text)
    extracted_info['address'] = extract_address(extracted_text)
    extracted_info['issuing_state'] = extract_issuing_state(extracted_text)
    extracted_info['post_code'] = extract_post_code(extracted_text)
    extracted_info['extracted_text'] = extracted_text_lines

    # Return extracted information
    return extracted_info

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
