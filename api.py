from email import policy
import os
import json
import random
import time
import re
from base64 import b64decode
import json
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from model import get_ai_content
import html
import requests
from utils import get_email_intent, verify_policy,verify_policy_details
from dbOperations import init_db, store_conversation, get_conversation_body, validate_conversation_id
from verify import validate_claim

# Create Flask app
app = Flask(__name__)

init_db()

@app.route("/onPrem/v2/createClaim", methods=["POST"])
def create_claim():
    try:
        conversation_id = request.headers.get("ConversationID")
        if not conversation_id and request.is_json:
            conversation_id = request.json.get("ConversationID")
        
        # Extract and clean HTML content
        html_content = request.get_data(as_text=True)
        
        soup = BeautifulSoup(html_content, "html.parser")
        plain_text = soup.get_text(separator=" ")
        decoded_text = html.unescape(plain_text)
        cleaned_text = re.sub(r'(\\n|/n|\n|\r)', ' ', decoded_text)
        cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()

        
        if not validate_conversation_id(conversation_id):

            # Calling the extract policy details function to get the policy details,
            #  and extract policy number and loss date using Gen AI
            policy_details, policy_number, loss_date = extract_policy_details(cleaned_text)
            if policy_details is None:
                return jsonify({
                    "claimNumber": None,
                    "policyNumber": policy_number,
                    "message": "Policy Number is Invalid or Policy Does Not Exist",
                    "action": "InvalidPolicy"
                }), 200
            
            # Function to verify if the policy is expired or not using the policy details
            policy_status = verify_policy(policy_details, loss_date)
            print(f"[DEBUG] Policy Status: {policy_status}")
            if policy_status =="PolicyInvalid":
                return jsonify({
                    "claimNumber": None,
                    "policyNumber": policy_number,
                    "message": "Policy is Expired or Invalid",
                    "action": "PolicyExpired"
                }), 200
            elif policy_status == "Not Eligible":
                return jsonify({
                    "claimNumber": None,
                    "policyNumber": policy_number,
                    "message": "Policy is Not Eligible for Claim",
                    "action": "NotEligible"
                }), 200
            
            
            # Function to check if duplicate claim exists using Gen AI
            # Uncommenqt the below line and comment the next line to use the old duplicate claim validation function
            # which uses Gen AI to validate duplicate claims

            # result = validate_Duplicate_Claim(policy_number, cleaned_text)
            
            result = validate_claim(policy_number, loss_date)
            
            if result is None or result.get("status") == "new":
                return attempt_claim_creation(cleaned_text, policy_details, policy_number)

            elif result.get("Status") == "Duplicate":
                store_conversation(conversation_id, cleaned_text)
                return jsonify({
                    "policyNumber": result.get("PolicyNumber"),
                    "claimNumber": result.get("ClaimNumber"),
                    "lossDate": result.get("LossDate"),
                    "claimStatus": result.get("ClaimStatus"),
                    "message": "Duplicate Claim Found",
                    "action": "DuplicateClaim"
                }), 200

        # Follow-up email in an existing conversation
        else:

            # Uncomment below lines to use Gen AI to determine email intent
            # email_intent = get_email_intent(cleaned_text)
            # print(f"[DEBUG] Email Intent: {email_intent}")
            # if email_intent == "Proceed":
            
            if "proceed" in cleaned_text.lower():
                body = get_conversation_body(conversation_id)
                print("[DEBUG] Retrieved body for FollowUp:", body)
                if body:
                    policy_details, policy_number, loss_date = extract_policy_details(body)
                    if policy_details is None:
                        return jsonify({
                            "claimNumber": None,
                            "policyNumber": policy_number,
                            "message": "Policy Number is Invalid or Policy Does Not Exist",
                            "action": "InvalidPolicy"
                        }), 200
                    
                    policy_status = verify_policy(policy_details, loss_date)
                    if policy_status =="PolicyInvalid":
                        return jsonify({
                            "claimNumber": None,
                            "policyNumber": policy_number,
                            "message": "Policy is Expired or Invalid",
                            "action": "PolicyExpired"
                        }), 200
                    elif policy_status == "Not Eligible":
                        return jsonify({
                            "claimNumber": None,
                            "policyNumber": policy_number,
                            "message": "Policy is Not Eligible for Claim",
                            "action": "NotEligible"
                        }), 200
                    
                    return attempt_claim_creation(body, policy_details, policy_number)

            return jsonify({
                "message": "No claim action required for this email",
                "action": "NotRequired"
            }), 200

    except Exception as e:
        return jsonify({
            "error": "Exception occurred during claim creation",
            "message": str(e),
            "policyNumber": policy_number if 'policy_number' in locals() else None
        }), 500


def attempt_claim_creation(cleaned_text, policy_details, policy_number):
    """Helper to retry claim creation up to 3 times."""
    claim_number = None
    for attempt in range(3):
        response_payload = generate_response(cleaned_text, policy_details)
        createClaimResponse = createClaim(response_payload)

        if createClaimResponse.status_code in [200, 201]:
            response_json = createClaimResponse.json()
            claim_number = response_json.get("claimNumber", "N/A")
            return jsonify({
                "claimNumber": claim_number,
                "policyNumber": policy_number,
                "message": "Claim Created Successfully",
                "action": "ClaimCreated"
            }), 200

    return jsonify({
        "claimNumber": claim_number,
        "policyNumber": policy_number,
        "message": "Failed"
    }), createClaimResponse.status_code


def generate_response(user_input, policy_details):
    # Load claim template
    with open('claim_template.json', 'r') as f:
        claim_template = json.load(f)

    prompt = f"""
You are a professional insurance claim assistant.

Your job is to extract structured data from the user's claim description and populate a valid claim creation JSON object.

---

Master Data (use ONLY these values exactly):

ClaimantType:
- insured
- householdmember
- propertyowner
- customer
- employee
- other

PolicyType:
- BusinessOwners
- BusinessAuto
- CommercialPackage
- CommercialProperty
- farmowners
- GeneralLiability
- HOPHomeowners
- InlandMarine
- PersonalAuto
- travel_per
- PersonalUmbrella
- prof_liability
- WorkersComp
- D and 0

RelationshipToInsured:
- self
- agent
- attorney
- employee
- claimant
- claimantatty
- rentalrep
- repairshop
- other

LossCause:
- animal_bite
- burglary
- earthquake
- explosion
- fire
- glassbreakage
- hail
- hurricane
- vandalism
- mold
- riotandcivil
- snowice
- structfailure
- waterdamage
- wind

---

Context:

You will receive:
- A **free-text claim description** (from user or email).
- A **policy_details object** containing valid coverages.

---

Instructions:

1. **Extract structured data** only when confidently inferable.
2. **Leave fields blank or omit them entirely** if data is missing or uncertain.
3. For `InvolvedVehicles`, add only if vehicle info (like VIN or plate) is present.
4. For each `InvolvedCoverage`:
   - Extract coverage **based on incident description** (e.g., "rear-ended" = Collision)
   -Find the matching coverage object from `policy_details['coverages']` where `"Coverage"` matches.
   - Use the corresponding `public id` from that object.
   - Only include if it's listed in the policy's coverages, if not then do not add the array also.
   - Include:
     - Coverage (e.g., "Collision", "Comprehensive")
     - CoverageType (extract from policy_details)
     - CoverageSubtype (same as CoverageType)
     - Claimant_FirstName
     - Claimant_LastName
     - ClaimantType

5. Determine:
   - `PolicyType` from policy context or description
   - `RelationshipToInsured` based on who is reporting (e.g., "I", "my friend")
   - `LossCause` from incident nature (choose from predefined list)

6. Date format for `LossDate` must be ISO 8601 with timezone offset, like:
   "2024-06-19T00:00:00+05:30"

7. If any field is not mentioned try to add it from the policy_details object.
   eg if addess is not mentioned in the claim description, try to add it from the policy_details object.
   eg if phone number is not mentioned in the claim description, try to add it from the policy_details object.
   eg if losscause are not mentioned in the claim description, keep the default value as glassbreakage.
8. Loss occured should be a string value, eg "Home"/"At Premises"/"At Work"/ "At Street"

---

Output:
Return only a valid, structured JSON object with human-readable formatting. No explanation text. Do not hallucinate missing details.

Claim Information:
{user_input}

Policy Details:
{policy_details}

---

Fill out the below template using only values inferred from the above:
{claim_template}
"""

    
    response = get_ai_content(prompt)

    if not response:
        raise ValueError("Failed to get a valid response from the AI.")

    # Extract JSON from the AI response
    extracted_json = extract_json_from_response(response)

    
    return extracted_json


def extract_json_from_response(response_data):
    match = re.search(r'```json\n(.*?)\n```', response_data, re.DOTALL)
    if match:
        json_str = match.group(1)
        try:
            json_obj = json.loads(json_str)
            return json_obj
        except json.JSONDecodeError as e:
            print("Invalid JSON:", e)
    else:
        print("No JSON block found.")
    return None


# Method to create claim by calling the claim creation API
def createClaim(response):

    url = "http://18.218.57.115:8090/cc/rest/fnol/v1/createFNOL"

    payload = json.dumps(response)

    headers = {
      'Content-Type': 'application/json',
      'Authorization': 'Basic c3U6Z3c='
    }

    response = requests.request("POST", url, headers=headers, data=payload)

    
    return response

# Function to call the policy details API and extract the policy number and loss date using Gen AI
def extract_policy_details(text):
    # Prompt AI to extract the policy number
    prompt = f"""From the following text, extract the policy details in text format. Eg: "PolicyNumber": "12312312", "LossDate":"2025-07-22T22:30:00.000Z". Do not return anything else.\n\n{text}"""
    policy = get_ai_content(prompt)

    

    # Extract policy number using regex
    match = re.search(r'"PolicyNumber":\s*"(\d+)"', policy)
    if not match:
        
        return None

    policy_number = match.group(1)
    

    # Extract loss date using regex
    match_loss_date = re.search(r'"LossDate":\s*"([\d\-T:\.Z]+)"', policy)
    if not match_loss_date:
    
        return None

    loss_date = match_loss_date.group(1)

    # Prepare API request
    url = "http://18.218.57.115:8190/pc/rest/policy/v1/latestDetailsBasedOnAccOrPocNo"
    headers = {
        'Content-Type': 'text/plain',
        'Authorization': 'Basic c3U6Z3c='
    }

    payload = f"{policy_number}\r\n"

    # Send request
    try:
        response = requests.post(url, headers=headers, data=payload)
        response.raise_for_status()  # Raises an exception for HTTP 4xx/5xx

       
        return response.text,policy_number,loss_date

    except requests.exceptions.RequestException as e:
        
        return None, policy_number,loss_date

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
