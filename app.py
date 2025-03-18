import streamlit as st
import speech_recognition as sr
import requests
from twilio.rest import Client
import re
from word2number import w2n
import os
import datetime
import json
from dotenv import load_dotenv
import sys

# Load environment variables from .env file
load_dotenv()

# Twilio credentials from environment variables
TWILIO_SID = os.getenv('TWILIO_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')

# Invoice Generator API credentials from environment variables
INVOICE_GEN_API_URL = os.getenv('INVOICE_GEN_API_URL')
INVOICE_GEN_API_KEY = os.getenv('INVOICE_GEN_API_KEY')

# Gemini API credentials from environment variables
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')



# Initialize the speech recognizer
recognizer = sr.Recognizer()

# Session state initialization
if "is_listening" not in st.session_state:
    st.session_state.is_listening = False
if "customer_name" not in st.session_state:
    st.session_state.customer_name = ""
if "customer_number" not in st.session_state:
    st.session_state.customer_number = ""
if "bill_content" not in st.session_state:
    st.session_state.bill_content = ""
if "currency" not in st.session_state:
    st.session_state.currency = "USD"

# Language mapping for Google Speech Recognition
language_map = {
    'English': 'en-US',
    'Urdu': 'ur'
}

# # Function to recognize speech from the microphone
# def recognize_speech(language_code):
#     """Listen to the microphone and return the recognized text in the selected language"""
#     with sr.Microphone() as source:
#         st.write("Listening...")
#         audio = recognizer.listen(source)
#         try:
#             text = recognizer.recognize_google(audio, language=language_code)
#             st.write(f"You said: {text}")
#             return text
#         except Exception as e:
#             st.write("Sorry, I couldn't understand the audio.")
#             return None

def recognize_speech(language_code):
    """Listen to the microphone and return the recognized text in the selected language."""
    try:
        with sr.Microphone() as source:
            st.write("Listening...")
            audio = recognizer.listen(source)
            try:
                text = recognizer.recognize_google(audio, language=language_code)
                st.write(f"You said: {text}")
                return text
            except Exception as e:
                st.write("Sorry, I couldn't understand the audio.")
                return None
    except OSError as e:
        # If microphone is not available, show a message to use text input
        st.write("Microphone not detected in this environment. Please use text input instead.")
        return None

# Function to toggle the listening state
def toggle_listen(button_key):
    """Toggle listening on and off"""
    st.session_state.is_listening = not st.session_state.is_listening



def convert_number_words_to_digits(text, language):
    """Converts numbers written in words to digits in the text while preserving leading zeros."""
    if language == 'English':
        # Check if the text might be a phone number (contains only digits, spaces, or common separators)
        stripped_text = ''.join(c for c in text if c.isdigit() or c.isspace() or c in '+-')
        if stripped_text and all(c.isdigit() or c.isspace() or c in '+-' for c in text):
            # This is likely already a number, just return it as is to preserve any leading zeros
            return text
            
        # Find and replace number words with digits
        words = text.split()
        for i, word in enumerate(words):
            try:
                # Try to convert the word to a number
                num = w2n.word_to_num(word)
                words[i] = str(num)
            except ValueError:
                # If not a number word, keep original
                continue
        return ' '.join(words)
    elif language == 'Urdu':
        # First check if this is already a phone number to preserve it
        if re.match(r'^[\d\s\+\-]+$', text):
            return text
            
        # Urdu number word mapping
        persian_numbers = {
            "ایک": "1", "دو": "2", "تین": "3", "چار": "4", "پانچ": "5", 
            "چھے": "6", "سات": "7", "آٹھ": "8", "نو": "9", "دس": "10",
            "گیارہ": "11", "بارہ": "12", "تیرہ": "13", "چودہ": "14",
            "پندرہ": "15", "سولہ": "16", "سترہ": "17", "اٹھارہ": "18", 
            "انیس": "19", "بیس": "20", 
            "تیس": "30", "چالیس": "40", "پچاس": "50", "ساٹھ": "60", 
            "ستر": "70", "اسّی": "80", "نوے": "90", "سو": "100",
            "صفر": "0"  # Adding zero explicitly
        }
        # Replace Persian/Urdu numbers with digits using regex
        for word, digit in persian_numbers.items():
            text = re.sub(r'\b' + word + r'\b', digit, text, flags=re.IGNORECASE)
        return text
    else:
        return text



# Function to extract structured item details from Gemini API response
def extract_item_details_from_gemini(bill_content):
    """Extract structured item details from Gemini API."""
    prompt = f"Extract structured JSON for bill items, including item names, quantities, and prices from the following text: '{bill_content}'"
    
    # Corrected Gemini API URL
    gemini_api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    
    headers = {
        "Content-Type": "application/json"
    }
    
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }
    
    try:
        response = requests.post(gemini_api_url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

        # # Display the structured response from Gemini
        # st.write("Structured Data Extracted from Gemini API:")
        # st.json(data)

        # The JSON response is inside the text field as a string, so we need to parse it
        raw_json = data['candidates'][0]['content']['parts'][0]['text']
        
        # Clean the response from unwanted characters and backticks that are not part of JSON
        cleaned_json = raw_json.strip('```json').strip().strip('```').strip()

        # Try to parse the cleaned JSON
        try:
            structured_items = json.loads(cleaned_json)
            return structured_items
        except json.JSONDecodeError as e:
            st.write(f"Error parsing JSON: {e}")
            return None

    except requests.exceptions.RequestException as e:
        st.write(f"Error extracting item details: {e}")
        return None

# Function to generate an invoice using Invoice Generator API
def generate_invoice_pdf(customer_name, customer_number, items, currency):
    """Generate invoice PDF using Invoice Generator API."""
    
    current_date = datetime.datetime.now().strftime("%b %d, %Y")
    due_date = (datetime.datetime.now() + datetime.timedelta(days=7)).strftime("%b %d, %Y")
    invoice_number = f"INV-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    data = {
        "from": "Saqib Zeen House (Textile)",
        "to": customer_name,
        "logo": "https://example.com/logo.png",
        "number": invoice_number,
        "date": current_date,
        "due_date": due_date,
        "currency": currency,
        "notes": """● Thank you for your business! We appreciate your trust and look forward to serving you again.
● Great choice! Quality products, fair pricing, and timely service—what more could you ask for?
● If this invoice were a novel, the ending would be "Paid in Full." Let's make it a bestseller!
● Questions? Concerns? Compliments? We're just a message away.""",
        "terms": """● Payment is due by the due date to keep our accountants happy (and to avoid late fees).
● Late payments may result in a [X]% charge per month—or worse, a strongly worded email.
● If you notice any discrepancies, please inform us within [X] days. We promise we didn't do it on purpose.
● We accept payments via [Bank Transfer, PayPal, Credit Card, etc.]. Choose wisely, but choose soon."""
    }

    # Add items to the invoice
    for i, item in enumerate(items):
        data[f"items[{i}][name]"] = item["item_name"]
        data[f"items[{i}][quantity]"] = item["quantity"]
        
        # Fix the price field handling to handle different field names
        if "price" in item:
            data[f"items[{i}][unit_cost]"] = item["price"]
        elif "price_per_item" in item:
            data[f"items[{i}][unit_cost]"] = item["price_per_item"]
        else:
            # Fallback if neither field is present
            st.write("Warning: Price field not found in item data")
            data[f"items[{i}][unit_cost]"] = 0

    headers = {
        'Authorization': f'Bearer {INVOICE_GEN_API_KEY}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    try:
        response = requests.post(INVOICE_GEN_API_URL, headers=headers, data=data)
        response.raise_for_status()
        
        with open("invoice.pdf", "wb") as f:
            f.write(response.content)
        
        return "invoice.pdf"
    except requests.exceptions.RequestException as e:
        st.write(f"Error generating invoice: {e}")
        return None


def upload_to_tempfiles(file_path):
    """Uploads the file to tempfiles.org and returns the public link."""
    url = "https://tmpfiles.org/api/v1/upload"
    
    # Open the file in binary mode
    with open(file_path, 'rb') as file:
        files = {'file': file}
        try:
            response = requests.post(url, files=files)
            response.raise_for_status()
            
            # Extract the file URL from the response
            response_json = response.json()
            if response_json.get("status") == "success":
                file_url = response_json["data"].get("url")
                # Convert the URL to direct download link by inserting '/dl' after tmpfiles.org
                if file_url and "tmpfiles.org" in file_url:
                    file_url = file_url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
                return file_url
            else:
                st.write(f"Error: {response_json.get('status')}")
                return None
        except requests.exceptions.RequestException as e:
            st.write(f"Error uploading file: {e}")
            return None

        

def send_pdf_via_whatsapp(pdf_file, customer_number):
    """Uploads the PDF to tempfiles.org and sends the generated PDF to the customer via WhatsApp."""
    # Upload the PDF to tempfiles.org
    pdf_file_url = upload_to_tempfiles(pdf_file)
    st.write(pdf_file_url)
    
    if not pdf_file_url:
        return "Error: Could not upload file to tempfiles.org."
    
    client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)

    try:
        message = client.messages.create(
            body="Boss, this bill is honored to be in your inbox. Now, do it a favor and make it disappear.",
            from_=TWILIO_PHONE_NUMBER,
            media_url=[pdf_file_url],  # Use the tempfiles.org link here
            to=f'whatsapp:{customer_number}'
        )
        return f"Bill successfully sent to {customer_number}"
    except Exception as e:
        return f"Error sending bill via WhatsApp: {str(e)}"


    

# Apply modern dark theme styling with the provided color palette
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap');
    
    :root {
        --dark-green: #2C3930;
        --medium-green: #3F4F44;
        --accent-brown: #A27B5C;
        --light-cream: #DCD7C9;
    }
    
    body {
        font-family: 'Poppins', sans-serif;
        background-color: var(--dark-green);
        color: var(--light-cream);
    }
    
    /* Main container styling */
    .stApp {
        background: linear-gradient(135deg, var(--dark-green) 0%, #263228 100%);
    }
    
    /* Header styling */
    .title {
        font-family: 'Poppins', sans-serif;
        text-align: center;
        font-size: 3.5rem;
        font-weight: 700;
        background: linear-gradient(90deg, var(--accent-brown), var(--light-cream) 70%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-shadow: 0px 2px 4px rgba(0, 0, 0, 0.1);
        letter-spacing: 1px;
        margin-top: 1.5rem;
        margin-bottom: 0.5rem;
        transform: scale(1);
        transition: transform 0.3s ease-in-out;
    }
    
    .title:hover {
        transform: scale(1.02);
    }
    
    .tagline {
        font-family: 'Poppins', sans-serif;
        text-align: center;
        font-size: 1.5rem;
        color: var(--light-cream);
        font-weight: 300;
        margin-bottom: 2.5rem;
        opacity: 0.9;
        letter-spacing: 0.5px;
    }
    
    /* Card styling */
    .card {
        background: rgba(63, 79, 68, 0.25);
        backdrop-filter: blur(8px);
        -webkit-backdrop-filter: blur(8px);
        border-radius: 16px;
        border: 1px solid rgba(162, 123, 92, 0.2);
        padding: 28px;
        margin-bottom: 24px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
        transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
    }
    
    .card:hover {
        transform: translateY(-5px);
        box-shadow: 0 12px 40px rgba(0, 0, 0, 0.15);
        border: 1px solid rgba(162, 123, 92, 0.4);
    }
    


    /* Input field styling */
    .stTextInput > div > div > input, .stTextArea > div > div > textarea {
        background-color: rgba(44, 57, 48, 0.8) !important; /* Increased opacity */
        border: 1px solid rgba(162, 123, 92, 0.3) !important;
        color: var(--light-cream) !important;
        border-radius: 8px !important;
        padding: 12px 16px !important;
        font-size: 16px !important;
        transition: all 0.3s ease !important;
    }

    .stTextInput > div > div > input:hover, .stTextArea > div > div > textarea:hover {
        background-color: rgba(44, 57, 48, 0.9) !important; /* Even higher opacity on hover */
        border: 1px solid rgba(162, 123, 92, 0.5) !important; /* More visible border on hover */
    }

    .stTextInput > div > div > input:focus, .stTextArea > div > div > textarea:focus {
        background-color: rgba(44, 57, 48, 1) !important; /* Full opacity on focus */
        border: 1px solid var(--accent-brown) !important;
        box-shadow: 0 0 0 2px rgba(162, 123, 92, 0.2) !important;
    }
    
    /* Select box styling */
    .stSelectbox > div > div {
        background-color: rgba(44, 57, 48, 0.6) !important;
        border: 1px solid rgba(162, 123, 92, 0.3) !important;
        border-radius: 8px !important;
        color: var(--light-cream) !important;
    }
    
    .stSelectbox > div > div > div {
        color: var(--light-cream) !important;
        font-size: 16px !important;
    }
    
    .stSelectbox > div > div:hover {
        border: 1px solid var(--accent-brown) !important;
    }
    
    /* Button styling */
    .stButton > button {
        background: linear-gradient(135deg, var(--accent-brown) 0%, #8a6a4d 100%) !important;
        color: var(--light-cream) !important;
        font-weight: 500 !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 0.6rem 1.2rem !important;
        font-size: 1rem !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1) !important;
        text-transform: uppercase !important;
        letter-spacing: 0.5px !important;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 20px rgba(0, 0, 0, 0.15) !important;
        background: linear-gradient(135deg, #b38b68 0%, var(--accent-brown) 100%) !important;
    }
    
    .stButton > button:active {
        transform: translateY(1px) !important;
    }
    
    /* Generate button styling */
    div[data-testid="element-container"]:has(button#generate_button) button {
        background: linear-gradient(135deg, var(--medium-green) 0%, var(--dark-green) 100%) !important;
        border: 1px solid var(--accent-brown) !important;
        color: var(--light-cream) !important;
        font-weight: 600 !important;
        font-size: 1.2rem !important;
        padding: 0.8rem 1.6rem !important;
        box-shadow: 0 6px 16px rgba(0, 0, 0, 0.15) !important;
        position: relative;
        overflow: hidden;
    }
    
    div[data-testid="element-container"]:has(button#generate_button) button:before {
        content: '';
        position: absolute;
        top: 0;
        left: -100%;
        width: 100%;
        height: 100%;
        background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.1), transparent);
        transition: 0.5s;
    }
    
    div[data-testid="element-container"]:has(button#generate_button) button:hover:before {
        left: 100%;
    }
    
    /* Label styling */
    .input-label {
        color: var(--accent-brown);
        font-size: 1rem;
        font-weight: 500;
        margin-bottom: 0.5rem;
        display: block;
    }
    
    /* Subheader styling */
    .stSubheader, .css-10trblm {
        color: var(--accent-brown) !important;
        font-size: 1.5rem !important;
        font-weight: 600 !important;
        margin: 1rem 0 !important;
        letter-spacing: 0.5px !important;
    }
    
    /* Success/Error message styling */
    .success {
        background-color: rgba(46, 125, 50, 0.1);
        color: #81c784;
        font-size: 1rem;
        font-weight: 500;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #4caf50;
        margin-top: 1rem;
    }
    
    .error {
        background-color: rgba(211, 47, 47, 0.1);
        color: #e57373;
        font-size: 1rem;
        font-weight: 500;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #f44336;
        margin-top: 1rem;
    }
    
    /* Audio recording indication */
    .stMarkdown p {
        font-size: 1rem;
        color: var(--light-cream);
    }
    
    /* JSON display styling */
    .element-container .stJson {
        background-color: rgba(44, 57, 48, 0.7) !important;
        border-radius: 8px !important;
        border: 1px solid rgba(162, 123, 92, 0.3) !important;
    }

    /* Divider styling */
    hr {
        border: 0;
        height: 1px;
        background: linear-gradient(to right, transparent, var(--accent-brown), transparent);
        margin: 2rem 0;
    }
    
    /* Animation for the listening text */
    @keyframes pulse {
        0% { opacity: 0.6; }
        50% { opacity: 1; }
        100% { opacity: 0.6; }
    }
    
    .listening {
        animation: pulse 1.5s infinite;
        color: var(--accent-brown);
        font-weight: 500;
    }
    
    /* Scrollbar styling */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }
    
    ::-webkit-scrollbar-track {
        background: var(--dark-green);
    }
    
    ::-webkit-scrollbar-thumb {
        background: var(--accent-brown);
        border-radius: 4px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: #8a6a4d;
    }
    </style>
    """, unsafe_allow_html=True)

# Title
st.markdown('<div class="title">BillBot</div>', unsafe_allow_html=True)
st.markdown('<div class="tagline">Speak, and Let AI Create Your Bill</div>', unsafe_allow_html=True)

# Main layout with two columns
col1, col2 = st.columns([1, 3])

# Left Column (Settings Panel)
with col1:
    # st.markdown('<div class="card">', unsafe_allow_html=True)
    
    st.markdown("<p class='input-label'>Speech Recognition Language</p>", unsafe_allow_html=True)
    language_options = ['English', 'Urdu']
    selected_language = st.selectbox(" ", language_options, label_visibility="collapsed")

    st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)

    st.markdown("<p class='input-label'>Select Currency</p>", unsafe_allow_html=True)
    currency_options = ['USD', 'PKR']
    selected_currency = st.selectbox("  ", currency_options, label_visibility="collapsed")
    st.session_state.currency = selected_currency
    
    st.markdown('</div>', unsafe_allow_html=True)

# Right Column (Customer Information Fields)
with col2:
    # Customer Name
    # st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("<p class='stSubheader'>Customer Name</p>", unsafe_allow_html=True)
    customer_name = st.text_area("Enter Customer Name", st.session_state.customer_name, height=70, key="name_input", label_visibility="collapsed")
    st.session_state.customer_name = customer_name

    col_record, col_space = st.columns([1, 1])
    with col_record:
        record_name_btn = st.button("Record Name", key="name_button")
    
    if record_name_btn:
        toggle_listen("name_button")
        if st.session_state.is_listening:
            recognized_name = recognize_speech(language_map[selected_language])
            if recognized_name:
                st.session_state.customer_name = recognized_name
    st.markdown('</div>', unsafe_allow_html=True)

    # Customer Number
    # st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("<p class='stSubheader'>Customer Number</p>", unsafe_allow_html=True)
    customer_number = st.text_area("Enter Customer Number", st.session_state.customer_number, height=70, key="number_input", label_visibility="collapsed")
    st.session_state.customer_number = customer_number

    col_record, col_space = st.columns([1, 1])
    with col_record:
        record_number_btn = st.button("Record Number", key="number_button")
    
    if record_number_btn:
        toggle_listen("number_button")
        if st.session_state.is_listening:
            recognized_number = recognize_speech(language_map[selected_language])
            if recognized_number:
                recognized_number = convert_number_words_to_digits(recognized_number, selected_language)
                st.session_state.customer_number = recognized_number
    st.markdown('</div>', unsafe_allow_html=True)

    # Bill Content
    # st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("<p class='stSubheader'>Bill Content</p>", unsafe_allow_html=True)
    bill_content = st.text_area("Enter Bill Content", st.session_state.bill_content, height=140, key="bill_input", label_visibility="collapsed")
    st.session_state.bill_content = bill_content

    col_record, col_space = st.columns([1, 1])
    with col_record:
        record_content_btn = st.button("Record Bill Content", key="content_button")
    
    if record_content_btn:
        toggle_listen("content_button")
        if st.session_state.is_listening:
            recognized_bill_content = recognize_speech(language_map[selected_language])
            if recognized_bill_content:
                recognized_bill_content = convert_number_words_to_digits(recognized_bill_content, selected_language)
                st.session_state.bill_content = recognized_bill_content
    st.markdown('</div>', unsafe_allow_html=True)

# Generate Bill Button (centered)
st.markdown('<div style="margin-top:2rem;"></div>', unsafe_allow_html=True)
_, center_col, _ = st.columns([1, 2, 1])
with center_col:
    generate_btn = st.button("Generate and Send Bill", key="generate_button", use_container_width=True)

# Process the bill if button is clicked
if generate_btn:
    if st.session_state.customer_name and st.session_state.customer_number and st.session_state.bill_content:
        # Use Gemini to structure the bill content
        structured_bill_content = extract_item_details_from_gemini(st.session_state.bill_content)

        if structured_bill_content:
            # Generate invoice PDF
            pdf_file = generate_invoice_pdf(
                st.session_state.customer_name,
                st.session_state.customer_number,
                structured_bill_content,
                st.session_state.currency
            )

            if pdf_file:
                result = send_pdf_via_whatsapp(pdf_file, st.session_state.customer_number)
                st.markdown(f"<div class='success'>{result}</div>", unsafe_allow_html=True)
            else:
                st.markdown("<div class='error'>Error: Could not generate invoice PDF.</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='error'>Error: Could not extract structured content from bill text.</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='error'>Please fill in all required fields: Customer Name, Customer Number, and Bill Content.</div>", unsafe_allow_html=True)

